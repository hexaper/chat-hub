# Phase 2 Reliability and Scale Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real-time chat behavior correct under multi-instance deployments and short disconnects by moving presence to Redis, adding reconnect catch-up, and refining WebSocket rate-limit behavior.

**Architecture:** Introduce a dedicated Redis-backed presence helper used by `ServerChatConsumer`, then add explicit catch-up messages (`catch_up`) to both chat consumers so reconnecting clients can recover missed messages by cursor (`after_id`). Keep the existing Django + Channels flow, payload contracts, and soft-delete/edit semantics, and evolve responses in a backward-compatible way with optional new message types (`rate_limited`, `catch_up`).

**Tech Stack:** Django 5.2, Django Channels, Redis (cache + channel layer), PostgreSQL/SQLite, vanilla JavaScript in server-rendered templates.

---

## Scope Check

Phase 2 has three features, but they are tightly coupled in the same runtime paths (`apps/rooms/consumers.py` + chat templates). This plan keeps them in one implementation stream while still delivering testable milestones per task.

If you want to de-risk rollout further, split after Task 2:
- Plan A: Redis presence + reconnect catch-up.
- Plan B: rate-limit refinement + UX feedback.

## File Structure

- Create: `apps/rooms/presence.py` (Redis-backed ephemeral presence operations)
- Create: `apps/rooms/tests/test_presence.py` (unit coverage for presence helper behavior)
- Modify: `apps/rooms/consumers.py` (presence integration, catch-up handlers, per-event rate limits + `rate_limited` payload)
- Modify: `apps/rooms/tests/test_consumers.py` (presence and reconnect catch-up consumer tests)
- Modify: `apps/rooms/tests/test_ratelimit.py` (WebSocket rate-limit feedback behavior tests)
- Modify: `templates/rooms/server_detail.html` (presence heartbeat ping, reconnect catch-up client flow, rate-limit UX)
- Modify: `templates/rooms/room_detail.html` (reconnect catch-up flow, rate-limit UX)
- Modify: `apps/rooms/tests/test_views_extended.py` (template-level regression checks for catch-up/rate-limit client hooks)
- Modify: `CLAUDE.md` (presence + reconnect behavior docs)
- Modify: `docs/codebase/ARCHITECTURE.md` (runtime contract updates)
- Modify: `docs/codebase/CONCERNS.md` (remove resolved concern, add remaining residual risks)

### Task 1: Replace In-Process Presence With Redis Presence Helper

**Files:**
- Create: `apps/rooms/tests/test_presence.py`
- Create: `apps/rooms/presence.py`
- Modify: `apps/rooms/consumers.py`
- Test: `apps/rooms/tests/test_presence.py`
- Test: `apps/rooms/tests/test_consumers.py`

- [ ] **Step 1: Write failing presence tests**

```python
# apps/rooms/tests/test_presence.py
import asyncio
from django.test import TestCase
from django.core.cache import cache

from apps.rooms.presence import presence_add, presence_remove, presence_list, presence_touch


class PresenceStoreTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_presence_add_and_list_are_unique_by_username(self):
        async def run():
            users = await presence_add('server-a', 'chan-1', 'alice')
            self.assertEqual(users, ['alice'])

            users = await presence_add('server-a', 'chan-2', 'alice')
            self.assertEqual(users, ['alice'])

            users = await presence_add('server-a', 'chan-3', 'bob')
            self.assertEqual(users, ['alice', 'bob'])

        asyncio.run(run())

    def test_presence_remove_drops_only_target_channel(self):
        async def run():
            await presence_add('server-a', 'chan-1', 'alice')
            await presence_add('server-a', 'chan-2', 'bob')

            users = await presence_remove('server-a', 'chan-1')
            self.assertEqual(users, ['bob'])
            self.assertEqual(await presence_list('server-a'), ['bob'])

        asyncio.run(run())

    def test_presence_touch_returns_false_for_missing_channel(self):
        async def run():
            touched = await presence_touch('server-a', 'missing-channel')
            self.assertFalse(touched)

        asyncio.run(run())
```

```python
# apps/rooms/tests/test_consumers.py (add to ConsumerTests)
def test_server_chat_history_includes_online_users_from_redis_presence(self):
    ServerMember.objects.get_or_create(server=self.server, user=self.user)
    ServerMember.objects.get_or_create(server=self.server, user=self.other)
    transaction.commit()

    headers1 = self._get_cookie_header(self.user)
    headers2 = self._get_cookie_header(self.other)
    comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
    comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

    async def run():
        await comm1.connect()
        await drain_until(comm1, 'history')

        await comm2.connect()
        history2 = await drain_until(comm2, 'history')
        self.assertIn(self.user.username, history2.get('online_users', []))
        self.assertIn(self.other.username, history2.get('online_users', []))

        await safe_disconnect(comm1)
        await safe_disconnect(comm2)

    asyncio.run(run())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_presence apps.rooms.tests.test_consumers.ConsumerTests.test_server_chat_history_includes_online_users_from_redis_presence --settings=config.settings.development`
Expected: FAIL with import errors for `apps.rooms.presence` or incorrect `online_users` behavior.

- [ ] **Step 3: Implement Redis presence helper**

```python
# apps/rooms/presence.py
from __future__ import annotations

from django.conf import settings
from redis.asyncio import Redis

PRESENCE_TTL_SECONDS = getattr(settings, 'PRESENCE_TTL_SECONDS', 90)

_redis_client: Redis | None = None


def _redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        location = settings.CACHES['default']['LOCATION']
        _redis_client = Redis.from_url(location, decode_responses=True)
    return _redis_client


def _channels_key(server_slug: str) -> str:
    return f'presence:{server_slug}:channels'


def _channel_key(server_slug: str, channel_name: str) -> str:
    return f'presence:{server_slug}:channel:{channel_name}'


async def presence_add(server_slug: str, channel_name: str, username: str) -> list[str]:
    redis = _redis()
    await redis.set(_channel_key(server_slug, channel_name), username, ex=PRESENCE_TTL_SECONDS)
    await redis.sadd(_channels_key(server_slug), channel_name)
    return await presence_list(server_slug)


async def presence_remove(server_slug: str, channel_name: str) -> list[str]:
    redis = _redis()
    await redis.delete(_channel_key(server_slug, channel_name))
    await redis.srem(_channels_key(server_slug), channel_name)
    return await presence_list(server_slug)


async def presence_touch(server_slug: str, channel_name: str) -> bool:
    redis = _redis()
    return bool(await redis.expire(_channel_key(server_slug, channel_name), PRESENCE_TTL_SECONDS))


async def presence_list(server_slug: str) -> list[str]:
    redis = _redis()
    channel_names = list(await redis.smembers(_channels_key(server_slug)))
    if not channel_names:
        return []

    values = await redis.mget([_channel_key(server_slug, c) for c in channel_names])
    stale = [c for c, v in zip(channel_names, values) if not v]
    if stale:
        await redis.srem(_channels_key(server_slug), *stale)

    return sorted(set(v for v in values if v))
```

- [ ] **Step 4: Integrate consumer with Redis presence helper**

```python
# apps/rooms/consumers.py (imports)
from .presence import presence_add, presence_remove, presence_touch

# apps/rooms/consumers.py (ServerChatConsumer.connect)
online_users = await presence_add(self.server_slug, self.channel_name, self.user.username)

# apps/rooms/consumers.py (ServerChatConsumer.disconnect)
await presence_remove(self.server_slug, self.channel_name)

# apps/rooms/consumers.py (ServerChatConsumer.receive)
elif msg_type == 'presence_ping':
    await presence_touch(self.server_slug, self.channel_name)
```

- [ ] **Step 5: Run targeted tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_presence apps.rooms.tests.test_consumers.ConsumerTests.test_server_chat_history_includes_online_users_from_redis_presence --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/presence.py apps/rooms/tests/test_presence.py apps/rooms/consumers.py apps/rooms/tests/test_consumers.py
git commit -m "feat: back server chat presence with redis"
```

### Task 2: Add WebSocket Reconnect Catch-Up For Server and Room Chat

**Files:**
- Modify: `apps/rooms/tests/test_consumers.py`
- Modify: `apps/rooms/consumers.py`
- Test: `apps/rooms/tests/test_consumers.py`

- [ ] **Step 1: Write failing catch-up tests**

```python
# apps/rooms/tests/test_consumers.py (add to ConsumerTests)
def test_server_chat_catch_up_returns_messages_after_cursor(self):
    ServerMember.objects.get_or_create(server=self.server, user=self.user)
    for i in range(1, 6):
        ChatMessage.objects.create(server=self.server, user=self.user, content=f'msg {i}')
    transaction.commit()

    headers = self._get_cookie_header(self.user)
    communicator = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers)

    async def run():
        await communicator.connect()
        await drain_until(communicator, 'history')

        await communicator.send_json_to({'type': 'catch_up', 'after_id': 3})
        page = await drain_until(communicator, 'catch_up')

        ids = [m['id'] for m in page['messages']]
        self.assertEqual(ids, [4, 5])

        await safe_disconnect(communicator)

    asyncio.run(run())

# apps/rooms/tests/test_consumers.py (add to RoomChatConsumerTests)
def test_room_chat_catch_up_returns_messages_after_cursor(self):
    for i in range(1, 6):
        RoomChatMessage.objects.create(room=self.room, user=self.author, content=f'room msg {i}')
    transaction.commit()

    headers = self._get_cookie_header(self.author)
    communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

    async def run():
        await communicator.connect()
        await communicator.receive_from(timeout=20)

        await communicator.send_json_to({'type': 'catch_up', 'after_id': 3})
        raw = await communicator.receive_from(timeout=20)
        page = json.loads(raw)

        self.assertEqual(page.get('type'), 'catch_up')
        ids = [m['id'] for m in page['messages']]
        self.assertEqual(ids, [4, 5])

        await safe_disconnect(communicator)

    asyncio.run(run())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_server_chat_catch_up_returns_messages_after_cursor apps.rooms.tests.test_consumers.RoomChatConsumerTests.test_room_chat_catch_up_returns_messages_after_cursor --settings=config.settings.development`
Expected: FAIL because `catch_up` message type is not implemented.

- [ ] **Step 3: Implement catch-up handlers in both consumers**

```python
# apps/rooms/consumers.py (ServerChatConsumer.receive)
elif msg_type == 'catch_up':
    after_id = data.get('after_id')
    if not isinstance(after_id, int) or after_id < 0:
        return
    page = await self.get_catch_up_page(after_id)
    await self.send(text_data=json.dumps({
        'type': 'catch_up',
        'messages': page['messages'],
        'has_more': page['has_more'],
    }))

@database_sync_to_async
def get_catch_up_page(self, after_id):
    qs = ChatMessage.objects.filter(
        server__slug=self.server_slug,
        id__gt=after_id,
    ).select_related('user').order_by('id')[:200]
    rows = list(qs)
    messages = []
    for m in rows:
        deleted = m.deleted_at is not None
        messages.append({
            'id': m.id,
            'username': m.user.username,
            'avatar_url': self._avatar_url(m.user),
            'content': m.content if not deleted else '',
            'image_url': (m.image.url if m.image else '') if not deleted else '',
            'video_url': (m.video.url if m.video else '') if not deleted else '',
            'created_at': m.created_at.isoformat(),
            'updated_at': m.updated_at.isoformat() if m.updated_at else None,
            'deleted_at': m.deleted_at.isoformat() if m.deleted_at else None,
            'mentions': self._mention_usernames(m),
        })
    return {'messages': messages, 'has_more': len(rows) == 200}

# apps/rooms/consumers.py (RoomChatConsumer.receive + helper mirror)
elif msg_type == 'catch_up':
    after_id = data.get('after_id')
    if not isinstance(after_id, int) or after_id < 0:
        return
    page = await self.get_catch_up_page(after_id)
    await self.send(text_data=json.dumps({
        'type': 'catch_up',
        'messages': page['messages'],
        'has_more': page['has_more'],
    }))
```

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_server_chat_catch_up_returns_messages_after_cursor apps.rooms.tests.test_consumers.RoomChatConsumerTests.test_room_chat_catch_up_returns_messages_after_cursor --settings=config.settings.development`
Expected: PASS.

- [ ] **Step 5: Commit catch-up backend changes**

```bash
git add apps/rooms/consumers.py apps/rooms/tests/test_consumers.py
git commit -m "feat: add websocket catch-up flow for reconnects"
```

### Task 3: Refine WebSocket Rate Limits Per Event and Return Sender Feedback

**Files:**
- Modify: `apps/rooms/tests/test_ratelimit.py`
- Modify: `apps/rooms/consumers.py`
- Test: `apps/rooms/tests/test_ratelimit.py`

- [ ] **Step 1: Write failing rate-limit feedback tests**

```python
# apps/rooms/tests/test_ratelimit.py (add to ChatConsumerRateLimitTest)
def test_thirty_first_message_sends_rate_limited_feedback_to_sender(self):
    headers_sender = self._get_cookie_header(self.user)
    headers_observer = self._get_cookie_header(self.observer)
    comm_sender = WebsocketCommunicator(self.application, self._chat_url(), headers=headers_sender)
    comm_observer = WebsocketCommunicator(self.application, self._chat_url(), headers=headers_observer)

    async def run():
        await comm_sender.connect()
        await comm_observer.connect()
        await comm_sender.receive_from(timeout=20)
        await comm_observer.receive_from(timeout=20)

        for i in range(30):
            await comm_sender.send_json_to({'type': 'chat_message', 'content': f'm{i}'})

        for _ in range(30):
            await comm_observer.receive_from(timeout=20)

        await comm_sender.send_json_to({'type': 'chat_message', 'content': 'over-limit'})

        sender_raw = await comm_sender.receive_from(timeout=20)
        sender_msg = json.loads(sender_raw)
        self.assertEqual(sender_msg.get('type'), 'rate_limited')
        self.assertEqual(sender_msg.get('event'), 'chat_message')

        with self.assertRaises(asyncio.TimeoutError):
            await comm_observer.receive_from(timeout=0.5)

        await comm_sender.disconnect()
        await comm_observer.disconnect()

    asyncio.run(run())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_ratelimit.ChatConsumerRateLimitTest.test_thirty_first_message_sends_rate_limited_feedback_to_sender --settings=config.settings.development`
Expected: FAIL because consumer currently drops over-limit events silently.

- [ ] **Step 3: Implement per-event limits and sender feedback**

```python
# apps/rooms/consumers.py
SERVER_CHAT_RATE_LIMITS = {
    'chat_message': '30/m',
    'chat_image': '10/m',
    'typing': '20/m',
    'load_history': '60/m',
    'catch_up': '60/m',
}
ROOM_CHAT_RATE_LIMITS = {
    'chat_message': '30/m',
    'typing': '20/m',
    'load_history': '60/m',
    'catch_up': '60/m',
}

async def _rate_limited(self, scope: str, rate: str, event_name: str) -> bool:
    limited = await sync_to_async(is_rate_limited)(scope, self.user.pk, rate)
    if not limited:
        return False
    await self.send(text_data=json.dumps({
        'type': 'rate_limited',
        'event': event_name,
        'message': 'Too many requests — please wait a moment before trying again.',
    }))
    return True

# usage inside receive() branches
if await self._rate_limited('server_chat_message', SERVER_CHAT_RATE_LIMITS['chat_message'], 'chat_message'):
    return
```

- [ ] **Step 4: Run tests for updated behavior**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_ratelimit --settings=config.settings.development`
Expected: PASS with updated expectation that sender gets `rate_limited` and observer gets no extra broadcast.

- [ ] **Step 5: Commit rate-limit refinements**

```bash
git add apps/rooms/consumers.py apps/rooms/tests/test_ratelimit.py
git commit -m "feat: add websocket rate-limit feedback and per-event limits"
```

### Task 4: Update Chat Clients for Presence Heartbeat, Catch-Up, and Rate-Limit UX

**Files:**
- Modify: `apps/rooms/tests/test_views_extended.py`
- Modify: `templates/rooms/server_detail.html`
- Modify: `templates/rooms/room_detail.html`
- Test: `apps/rooms/tests/test_views_extended.py`

- [ ] **Step 1: Write failing template regression tests**

```python
# apps/rooms/tests/test_views_extended.py

def test_server_detail_template_includes_presence_ping_and_catch_up_hooks(self):
    ServerMember.objects.create(server=self.server, user=self.user)
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('server_detail', args=[self.server.slug]))
    self.assertContains(response, "type: 'presence_ping'")
    self.assertContains(response, "type: 'catch_up'")
    self.assertContains(response, "data.type === 'rate_limited'")


def test_room_detail_template_includes_catch_up_and_rate_limit_hooks(self):
    ServerMember.objects.create(server=self.server, user=self.user)
    RoomParticipant.objects.create(room=self.room, user=self.user)
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('room_detail', args=[self.server.slug, self.room.slug]))
    self.assertContains(response, "type: 'catch_up'")
    self.assertContains(response, "data.type === 'rate_limited'")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests.test_server_detail_template_includes_presence_ping_and_catch_up_hooks apps.rooms.tests.test_views_extended.RoomViewTests.test_room_detail_template_includes_catch_up_and_rate_limit_hooks --settings=config.settings.development`
Expected: FAIL because template scripts do not include these handlers yet.

- [ ] **Step 3: Implement reconnect + feedback client logic**

```javascript
// templates/rooms/server_detail.html (inside chat script)
const renderedMessageIds = new Set();
let maxSeenId = 0;
let resumeAfterId = null;
let pingTimer = null;

function markSeen(msg) {
    if (!msg || typeof msg.id !== 'number') return;
    maxSeenId = Math.max(maxSeenId, msg.id);
}

function appendMessage(msg) {
    if (renderedMessageIds.has(msg.id)) return;
    renderedMessageIds.add(msg.id);
    markSeen(msg);
    const el = buildMessageEl(msg);
    messagesDiv.appendChild(el);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function startPresencePing() {
    stopPresencePing();
    pingTimer = setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'presence_ping' }));
        }
    }, 25000);
}

function stopPresencePing() {
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = null;
}

function connect() {
    resumeAfterId = maxSeenId || null;
    socket = new WebSocket(chatUrl);

    socket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        if (data.type === 'history') {
            renderedMessageIds.clear();
            messagesDiv.innerHTML = '';
            data.messages.forEach(appendMessage);
            if (resumeAfterId) {
                socket.send(JSON.stringify({ type: 'catch_up', after_id: resumeAfterId }));
                resumeAfterId = null;
            }
        } else if (data.type === 'catch_up') {
            data.messages.forEach(appendMessage);
        } else if (data.type === 'rate_limited') {
            showToast(data.message, 'warning');
        }
    };

    socket.onopen = startPresencePing;
    socket.onclose = function() {
        stopPresencePing();
        setTimeout(connect, 3000);
    };
}

// templates/rooms/room_detail.html (inside chat script)
if (data.type === 'catch_up') {
    data.messages.forEach(appendMessage);
} else if (data.type === 'rate_limited') {
    showToast(data.message, 'warning');
}
```

- [ ] **Step 4: Run template regression tests**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests.test_server_detail_template_includes_presence_ping_and_catch_up_hooks apps.rooms.tests.test_views_extended.RoomViewTests.test_room_detail_template_includes_catch_up_and_rate_limit_hooks --settings=config.settings.development`
Expected: PASS.

- [ ] **Step 5: Commit template and tests**

```bash
git add templates/rooms/server_detail.html templates/rooms/room_detail.html apps/rooms/tests/test_views_extended.py
git commit -m "feat: add chat reconnect catch-up and websocket rate-limit UX"
```

### Task 5: Documentation Update and End-to-End Verification

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/codebase/ARCHITECTURE.md`
- Modify: `docs/codebase/CONCERNS.md`

- [ ] **Step 1: Write documentation updates to match new behavior**

```markdown
# CLAUDE.md (presence section)
### Presence (`apps/rooms/presence.py`)
Presence is Redis-backed and ephemeral. Each active websocket connection stores
`presence:<server_slug>:channel:<channel_name>` with a short TTL refreshed by
`presence_ping`. Online user lists are computed from live keys only.

# docs/codebase/ARCHITECTURE.md (chat section)
Server and room chat consumers now support `catch_up` requests with `after_id`
cursor recovery for reconnects. Clients dedupe messages by id and request missed
messages after reconnect.

# docs/codebase/CONCERNS.md (top risks)
Remove process-local presence risk, replace with note about TTL heartbeat tuning.
```

- [ ] **Step 2: Run focused and broader verification suite**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_presence apps.rooms.tests.test_consumers apps.rooms.tests.test_ratelimit apps.rooms.tests.test_views_extended --settings=config.settings.development`
Expected: PASS.

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests apps.rooms.tests.test_consumers.RoomChatConsumerTests --settings=config.settings.development`
Expected: PASS with no reconnect or presence regressions.

- [ ] **Step 3: Commit docs and verification-complete checkpoint**

```bash
git add CLAUDE.md docs/codebase/ARCHITECTURE.md docs/codebase/CONCERNS.md
git commit -m "docs: document redis presence and reconnect catch-up contracts"
```

## Self-Review

1. **Spec coverage:**
- Redis-backed ephemeral presence: Task 1 + Task 4 heartbeat.
- Reconnect gap-fill: Task 2 backend + Task 4 client flow.
- Rate-limit refinement + clearer feedback: Task 3 backend + Task 4 client UX.
- Success criteria alignment: Task 5 verification suite validates presence correctness, reconnect recovery, and anti-abuse behavior.

2. **Placeholder scan:**
- No `TODO`/`TBD` placeholders are present.
- Each code-changing task includes explicit code snippets, exact commands, expected outcomes, and commit commands.

3. **Type consistency:**
- `catch_up` message type and `after_id` cursor are used consistently in both consumers and templates.
- `rate_limited` payload uses consistent keys: `type`, `event`, `message`.
- Presence helper API names are consistent (`presence_add`, `presence_remove`, `presence_touch`, `presence_list`).
