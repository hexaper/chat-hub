# Project Roadmap & Progression Plan

A prioritised, opinionated guide for evolving Chat Hub into a production-grade video conferencing platform — without turning it into an over-engineered monolith.

---

## Design Philosophy

Before any feature work, the ground rules:

1. **Django does most of it.** The framework already gives us ORM, auth, sessions, CSRF, file uploads, form validation, admin, migrations, management commands. Before adding a library, check if Django has it built in. Most of the time it does.
2. **Zero new languages.** The stack is Python + vanilla JS + HTML/CSS. That stays. No TypeScript transpilation, no React build step, no Node.js sidecar. The frontend is server-rendered templates with progressive enhancement via JS. This is a strength — it keeps deployment simple (one container, one process) and eliminates an entire class of build/bundle/version issues.
3. **New dependency = last resort.** Every pip package is a maintenance liability. If a feature can be built in 50 lines of Python, it should be. The current `requirements.txt` is 12 lines — that's excellent for what the app does. Guard it.
4. **One database, one cache, one queue.** PostgreSQL for data, Redis for channel layers and caching. No Elasticsearch, no Celery, no RabbitMQ. PostgreSQL full-text search is good enough for chat search. Redis pub/sub is good enough for real-time. Django Channels is good enough for WebSockets. Stay on the well-worn path until there is measured evidence it doesn't scale.
5. **P2P until proven otherwise.** The WebRTC mesh works for 2-6 participants. An SFU (mediasoup, LiveKit) adds a whole runtime, a signaling protocol change, and operational complexity. Don't add it speculatively.

---

## Current Status

As of the latest commit, Chat Hub is a functional MVP with core video chat, text chat, and user management features. Key implemented components:
- P2P WebRTC video/audio calls with STUN (no TURN yet)
- Real-time text chat with image uploads via WebSockets
- Server/room hierarchy with invite codes and basic permissions
- User authentication, profiles, and device management
- Docker deployment (all-in-one and production modes)
- SQLite/PostgreSQL support with Redis for channels

Not yet implemented: test suite, rate limiting, TURN server, screen sharing, chat editing/deletion, CI/CD, performance optimizations, or advanced features like SFU or mobile support.

The roadmap below outlines the prioritized path to production-grade stability and feature completeness.

---

## Current Stack Inventory

| Layer | Technology | Role | Verdict |
|-------|-----------|------|---------|
| Web framework | Django 5.2.12 | Views, ORM, auth, forms, templates | Keep — mature, batteries-included |
| ASGI server | Daphne 4.2.1 | HTTP + WebSocket serving | Keep — native Channels integration, no nginx needed for dev |
| WebSocket | Django Channels 4.3.2 | Real-time signaling + chat | Keep — tight Django integration, shares auth/session |
| Channel backend | channels-redis 4.3.0 + Redis 7.3.0 | Pub/sub between consumer instances | Keep — only viable production backend for Channels |
| Database | PostgreSQL (prod) / SQLite (dev) | All persistent data | Keep — PostgreSQL is the right default for Django |
| Media storage | django-storages[s3] 1.14.4 + boto3 1.38.34 (prod) / filesystem (dev/allinone) | User uploads (avatars, chat images) | Keep — proven pattern, swap-friendly via STORAGES setting |
| Static files | WhiteNoise 6.12.0 | Serve collected static from the app process | Keep — eliminates need for nginx/CDN in simple deploys |
| Image processing | Pillow 12.1.1 | Upload validation (magic byte check), avatar handling | Keep — already a Django dependency for ImageField |
| Forms | django-crispy-forms 2.6 + crispy-bootstrap5 2026.3 | Form rendering with Bootstrap 5 markup | Keep — small footprint, big DX improvement |
| Frontend | Bootstrap 5 (CDN) + vanilla JS | UI + WebRTC logic | Keep — no build step, fast page loads |
| Containerisation | Docker + docker-compose | Deployment packaging | Keep — standard, well-understood; production files organized in `production/` directory for clean separation |
| CI/CD | GitHub Actions (CodeQL only) | Security scanning | Expand — needs test + deploy workflows |

**Total Python dependencies: 12.** Goal: stay under 20 through Phase 6.

---

## Priority Matrix

| Area | Risk if Ignored | Effort | Dependencies |
|------|----------------|--------|--------------|
| Testing | Critical — no safety net for any change | High | None |
| Security hardening | High — brute force + CSWSH are open | Low | None |
| TURN server | High — 10-30% of users simply can't connect | Low | External infra only |
| Chat features (edit/delete) | Medium — UX limitation, not a correctness issue | Medium | None |
| Performance (indexes, caching) | Medium — fine at current scale, will hurt later | Low | None |
| CI/CD | Medium — manual deploys are error-prone | Medium | Tests must exist first |
| Screen sharing | Medium — expected feature for video apps | Medium | None |
| REST API | Low — only needed if mobile or third-party integrations planned | High | New dependency |
| SFU architecture | Low — only needed if rooms regularly exceed 6 people | Very high | New runtime |

---

## Phase 1 — Foundation (Weeks 1-4)

The goal: make the existing codebase safe to change with confidence.

### 1.1 Test Suite

**Why this is first:** Every subsequent phase changes code. Without tests, every change is a gamble. The project currently has zero test files.

**Technology choice: Django's built-in test framework (`django.test`)**

*Why not pytest?* Django's `TestCase`, `TransactionTestCase`, and `channels.testing.WebsocketCommunicator` work out of the box with `manage.py test`. Zero config, zero new dependencies. pytest-django is nice but adds a dependency, a `conftest.py` convention, and fixture syntax that diverges from Django docs. The stdlib `unittest` patterns are fine for this project's scale.

*Why not factory-boy?* Model creation helpers can be plain functions in a `tests/helpers.py` file. `Server.objects.create(name='Test', owner=user)` is already readable. A factory library adds indirection for no meaningful gain at this scale.

**What to test (priority order):**

1. **Auth boundaries (~30 tests)** — the highest-value tests. For every view: does it 401 without login? Does it 403 for non-members? Does a non-host get blocked from kick/mute? These are the tests that catch security regressions.

2. **Model logic (~20 tests)** — invite code uniqueness, `Room.set_password` / `check_room_password` round-trip, `ChatMessage.image` validation flow, `generate_invite_code()` output format, `last_empty_at` lifecycle.

3. **Consumer tests (~25 tests)** — use `channels.testing.WebsocketCommunicator`. Test: connect as non-authenticated user (should close), connect as non-member (should close), send `chat_message` → verify it persists and broadcasts, send `offer`/`answer`/`ice-candidate` → verify they relay to the correct channel, host sends `kick` → verify target receives `kicked`, non-host sends `kick` → verify it's ignored.

4. **Form validation (~15 tests)** — `RegisterForm` with duplicate username, `RoomForm` with blank name, `RoomPasswordForm` empty submission, `ServerForm` with oversized avatar.

5. **Integration flows (~10 tests)** — full room lifecycle (create server → join → create room → enter → leave → verify cleanup), chat image upload with valid/invalid files.

**Target: ~100 tests, runnable in under 30 seconds on SQLite.**

No new dependencies needed.

### 1.2 Rate Limiting

**The problem:** Login, registration, chat send, image upload, and device registration have no rate limits. A script can brute-force passwords, spam chat, or exhaust S3 storage.

**Technology choice: Django's built-in cache framework + a simple decorator**

*Why not django-ratelimit?* It's a well-maintained library, but this is a ~40-line decorator using Django's cache backend. The logic is: increment a cache key `ratelimit:{ip_or_user}:{view_name}`, check if it exceeds threshold, return 429 if so. Redis is already running — use it as the cache backend.

**Implementation:**

```python
# In base.py — reuse the existing Redis for caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',  # DB 1, separate from channel layers on DB 0
    }
}
```

A `@ratelimit(key='ip', rate='5/m')` decorator on `login_view`, `register_view`. A `@ratelimit(key='user', rate='30/m')` on chat message send. A `@ratelimit(key='user', rate='10/m')` on image upload.

For WebSocket consumers: check rate in `receive()` using the same cache, drop messages silently if exceeded.

Implement the `@ratelimit` decorator in a new `utils/ratelimit.py` file. Apply to views in `apps/accounts/views.py` (login/register) and `apps/rooms/consumers.py` (chat send). Update `config/settings/base.py` to add the Redis cache config.

**New dependencies: 0.** Django 4.0+ has a built-in Redis cache backend.

### 1.3 WebSocket Origin Validation

**The problem:** `RoomConsumer` and `ServerChatConsumer` accept connections from any origin. A malicious page on `evil.com` could open a WebSocket to your server and send/receive messages as the authenticated user (via session cookie).

**Fix:** Add an `AllowedHostsOriginValidator` wrapper in `config/asgi.py`. Django Channels ships this — it's a one-line change:

```python
from channels.security.websocket import AllowedHostsOriginValidator
application = ProtocolTypeRouter({
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
```

**New dependencies: 0.** Already in `channels`.

### 1.4 Custom Error Pages

Three templates: `templates/404.html`, `templates/500.html`, `templates/403.html`. Extend `base.html`, match the dark theme. Add a "Go home" link. 20 minutes of work, big UX improvement in production.

**New dependencies: 0.**

### 1.5 Health Check Endpoint

The Docker `HEALTHCHECK` hits `/` which requires authentication — it may report unhealthy when the app is fine.

Add a `/healthz/` view that returns `200 OK` with a simple DB query (`SELECT 1`) and Redis ping. No authentication required. Update the `HEALTHCHECK` in Dockerfile to use it.

**New dependencies: 0.**

---

## Phase 2 — Core Feature Gaps (Weeks 5-10)

The goal: fill the features users expect from a video chat app.

### 2.1 TURN Server

**The problem:** Only STUN is configured. STUN discovers your public IP but cannot relay traffic. Users behind symmetric NAT, strict corporate firewalls, or carrier-grade NAT (common on mobile networks) simply cannot establish a peer connection. This affects 10-30% of users depending on geography and ISP.

**Technology choice: coturn (self-hosted) or Cloudflare TURN (managed)**

*Why coturn?*
- Open source, battle-tested (used by Jitsi, Nextcloud Talk, Signal)
- Runs as a single binary, ~50MB memory footprint
- Supports both TURN (relay) and STUN in one process
- Can run in the same Docker Compose stack or on a separate $5/mo VPS

*Why not Twilio/Xirsys?*
- They work, but cost per-minute. For a self-hosted project, coturn is free and you control the data path. If you deploy to a cloud provider, a managed TURN service makes sense to avoid NAT/firewall headaches on the TURN server itself.

*Why not Cloudflare TURN?*
- Cloudflare offers free TURN as part of Calls. Good option if you want zero ops. But it's a newer service and may have usage limits. Worth evaluating as a drop-in alternative.

**Implementation:**

Server-side: expose TURN credentials via a Django view (short-lived credentials using HMAC-based auth — coturn supports this). The view returns ICE server config with time-limited username/password.

Client-side: fetch ICE config from `/api/ice-servers/` before creating `RTCPeerConnection`, replacing the hardcoded `ICE_SERVERS` constant in `webrtc.js`.

```javascript
// Before: hardcoded, no TURN
const ICE_SERVERS = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };

// After: fetched from server, includes TURN with rotating credentials
const iceConfig = await fetch('/api/ice-servers/').then(r => r.json());
const pc = new RTCPeerConnection(iceConfig);
```

**New Python dependencies: 0.** New infrastructure: 1 coturn instance (or managed service).

### 2.2 Screen Sharing

**The problem:** Expected feature in any video conferencing app. No `getDisplayMedia()` call exists in `webrtc.js`.

**Design choice: track replacement, not a second peer connection**

The WebRTC standard supports replacing the video track on an existing `RTCRtpSender`. This avoids renegotiation (no new offer/answer cycle) and keeps the same peer connections.

**Implementation plan:**

1. Add "Share Screen" button to room UI (next to camera toggle)
2. On click: `navigator.mediaDevices.getDisplayMedia({ video: true })`
3. Replace the video track on all peer connections: `sender.replaceTrack(screenTrack)`
4. Send `screen_share_started` message via WebSocket so peers can adjust layout (e.g., make the screen share larger)
5. When the user stops sharing (browser's native "Stop sharing" button fires `track.onended`): swap back to camera track, broadcast `screen_share_stopped`

**Why not add a separate video track for screen share?**
That would require renegotiation (new offer/answer) with every peer, and peers would need to handle a third track. Track replacement is simpler, more reliable, and sufficient for one-screen-at-a-time sharing.

**New dependencies: 0.** Pure browser API + existing WebSocket signaling.

### 2.3 Chat Message Editing & Deletion

**Design choice: soft delete with `deleted_at`, edit with `updated_at`**

*Why soft delete?*
- Audit trail — you can see that a message existed even after deletion
- Simpler to broadcast — send `message_deleted` event, client hides the message (shows "message deleted" placeholder)
- Reversible in admin if needed
- Avoids foreign key cascade issues if reactions or replies reference the message later

*Why time-limited edits?*
- Prevents retroactive rewriting of conversation history
- 15-minute window matches user expectations (Discord uses 1 hour, Slack has no limit — 15 min is conservative and safe)
- After window closes, the edit button disappears client-side, and the consumer rejects edit attempts

**Model changes:**
```python
class ChatMessage(models.Model):
    # Existing fields...
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
```

Two new WebSocket message types in `ServerChatConsumer`: `edit_message` and `delete_message`. Both broadcast to the group so all connected clients update in real-time.

**New dependencies: 0.**

### 2.4 Typing Indicators

**Design choice: stateless, debounced, ephemeral**

Typing indicators should never touch the database. They're fire-and-forget WebSocket messages with no persistence.

**Implementation:**
- Client sends `{ "type": "typing" }` on keypress, debounced to max 1 per 3 seconds
- `ServerChatConsumer` broadcasts `{ "type": "user_typing", "username": "..." }` to group (excluding sender)
- Client shows "X is typing..." for 5 seconds, resets timer on each new event
- No new model, no new field, no database query

**Why not track typing state server-side?**
It's unnecessary state. The consumer just relays the event. If the user disconnects, they stop typing — the 5-second client-side timeout handles cleanup naturally.

**New dependencies: 0.**

### 2.5 User Presence

**Design choice: WebSocket connection = online, no heartbeat polling**

*Why not a `last_seen` database field?*
Database writes on every action are expensive and unnecessary. The WebSocket connection itself is the presence signal. If a user has an open `ServerChatConsumer` connection, they're online. When they disconnect, they're offline. Channels already tracks this via the group membership.

**Implementation:**
- On `ServerChatConsumer.connect()`: broadcast `{ "type": "presence", "username": "...", "status": "online" }` to the server's chat group
- On `ServerChatConsumer.disconnect()`: broadcast `{ "type": "presence", "username": "...", "status": "offline" }`
- Client maintains a local `Set` of online usernames, renders green/grey dots
- For the initial state on connect: include `online_users` list in the `history` payload (the consumer knows who's in the group via `self.channel_layer.group_channels` or a simple Redis set)

**New dependencies: 0.**

---

## Phase 3 — Operational Maturity (Weeks 11-16)

The goal: make the app reliable, observable, and safe to deploy frequently.

### 3.1 CI/CD Pipeline

**Technology choice: GitHub Actions (already in use for CodeQL)**

*Why not GitLab CI, CircleCI, etc.?*
The repo is on GitHub. Actions are free for public repos and have generous minutes for private ones. No reason to introduce a second CI platform.

**Workflow 1: `test.yml` (runs on every push and PR)**
```yaml
services:
  redis:
    image: redis:7-alpine
    ports: [6379:6379]
steps:
  - pip install -r requirements.txt
  - DJANGO_SETTINGS_MODULE=config.settings.development python manage.py test
```

SQLite for CI — fast, no PostgreSQL service needed for unit tests. If a test specifically needs PostgreSQL features (full-text search in Phase 4), add a PostgreSQL service to a separate workflow.

**Workflow 2: `deploy.yml` (runs on merge to main)**
Build Docker image, push to GitHub Container Registry (free), deploy to target. Details depend on hosting (Koyeb, Railway, VPS).

**Linting:**

*Technology choice: ruff*

*Why ruff over flake8/black/isort?*
It replaces all three in a single binary. It's 10-100x faster. One config section in `pyproject.toml`. One tool to run. No dependency chain.

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
```

**New dependencies: 1 dev tool (ruff, not a runtime dependency).**

### 3.2 Database Indexes

**The problem:** No explicit `db_index=True` on foreign keys that are filtered frequently. Django auto-creates indexes on `ForeignKey` fields, but composite lookups and ordering queries benefit from explicit composite indexes.

**What to add:**

```python
class ChatMessage(models.Model):
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['server', '-created_at']),  # Chat history query
        ]

class ServerMember(models.Model):
    class Meta:
        unique_together = ('server', 'user')  # Already creates a composite index — good

class Room(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['server', 'is_active']),  # Room listing per server
        ]
```

*Why not add indexes everywhere?*
Indexes speed up reads but slow down writes and consume storage. Only add them where there's a measured or obvious query pattern. The three above cover the hot paths (chat history, room listing, membership check). `unique_together` already creates indexes on `ServerMember` and `RoomParticipant`.

**New dependencies: 0.** Just a migration.

### 3.3 Caching

**Technology choice: Django's built-in Redis cache backend**

Redis is already running for channel layers. Use a separate Redis database (db 1) for caching to avoid key collisions.

**What to cache:**

| Key pattern | Data | TTL | Invalidation |
|-------------|------|-----|--------------|
| `server_list:public` | Public server queryset | 60s | On server create/update/delete |
| `server:{uuid}:member_count` | Integer count | 300s | On member join/leave |
| `server:{uuid}:online_users` | Set of usernames | Real-time | WebSocket connect/disconnect |

*Why not cache aggressively?*
Cache invalidation is the second hardest problem in computer science. Cache only what's expensive to compute and safe to serve stale. Server list and member counts are safe. Chat messages and room state are not — they change constantly and users expect instant updates.

**New dependencies: 0.** Django 4.0+ includes `django.core.cache.backends.redis.RedisCache`.

### 3.4 Chat Pagination

**The problem:** `ServerChatConsumer.get_history()` loads the last 50 messages on connect. There's no way to load older messages.

**Design choice: cursor-based REST endpoint, not WebSocket**

*Why REST and not a WebSocket message type?*

Historical data is a request-response pattern: "give me messages older than X". WebSocket is designed for real-time push, not request-response. A REST endpoint is:
- Cacheable (same cursor = same response)
- Testable with standard tools (curl, browser, test client)
- Doesn't complicate the consumer with pagination state

**Implementation:**
```
GET /servers/<uuid>/chat/history/?before=<message_id>&limit=50
```

Returns JSON array of messages older than the given ID. Client calls this on scroll-to-top. The consumer still sends the last 50 on connect for fast initial load.

**New dependencies: 0.** Django `JsonResponse` + queryset filtering.

### 3.5 Structured Logging

**Technology choice: Django's built-in `logging` module with JSON formatting**

*Why not python-json-logger?*
A `json.dumps()` formatter is 15 lines of code. Adding a dependency for JSON formatting is the definition of unnecessary.

```python
import json, logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'ts': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
            'module': record.module,
        })
```

**What to log (INFO level):**
- User login/logout
- Server create/delete
- Room create/close
- WebSocket connect/disconnect (with user + room)
- Image upload (user + size)
- Rate limit hits (WARNING level)

**What NOT to log:**
- Chat message content (privacy)
- Passwords or tokens (obviously)
- Every HTTP request (nginx/load balancer handles access logs)

**Monitoring:**

*Why not django-prometheus?*
For a self-hosted project, this adds Prometheus + Grafana infrastructure that needs maintaining. If you're deploying to Koyeb/Railway, they provide basic metrics (request count, latency, memory) out of the box. If you genuinely need custom metrics, add them later — don't build an observability stack before you have observability problems.

**New dependencies: 0.**

### 3.6 Container Hardening

**Run as non-root:**
```dockerfile
RUN useradd -r -s /bin/false appuser && \
    chown -R appuser:appuser /app/mediafiles
USER appuser
```

**Fix health check:** Point to `/healthz/` (from Phase 1.5).

**Pin base image:** `python:3.12.8-slim` instead of `python:3.12-slim`. Reproducible builds.

**New dependencies: 0.**

---

## Phase 4 — Scalability and Ecosystem (Weeks 17-24)

The goal: support larger deployments and expand beyond the browser.

### 4.1 SFU Architecture for Large Rooms
**When:** When rooms regularly exceed 6 participants and P2P mesh becomes unreliable.
**Technology choice:** mediasoup or LiveKit (self-hosted or managed).
**Implementation:** Add SFU signaling alongside P2P, with automatic fallback. New dependency: ~2-3 packages for signaling.

### 4.2 Progressive Web App (PWA)
**Why:** Enable installable app experience on mobile/desktop.
**Implementation:** Add service worker, web app manifest, and offline chat caching. No new backend changes.

### 4.3 REST API for Third-Party Integrations
**Why:** Allow bots, mobile apps, or external tools to interact with servers/rooms.
**Implementation:** Django REST Framework for endpoints like `/api/servers/`, `/api/messages/`. New dependency: DRF (~5 packages).

### 4.4 Mobile App (Optional)
**Technology choice:** React Native or Flutter for cross-platform.
**Why optional:** Increases scope significantly; start with PWA first.

**New dependencies: Variable (0-10 depending on choices).**

---

## Phase 5 — Rich Features (Weeks 25-32)

The goal: features that differentiate Chat Hub from a toy project.

### 4.1 Server Roles & Permissions

**Design choice: a simple permission system, not a full RBAC framework**

*Why not django-guardian, django-rules, or django-role-permissions?*
These are designed for complex object-level permission systems. Chat Hub has three roles: Owner, Moderator, Member. That's a `CharField` with choices on `ServerMember`, not a permission framework.

```python
class ServerMember(models.Model):
    ROLES = [('owner', 'Owner'), ('moderator', 'Moderator'), ('member', 'Member')]
    role = models.CharField(max_length=20, choices=ROLES, default='member')
```

**Permission logic (in views and consumers):**
```python
def can_kick(member):       return member.role in ('owner', 'moderator')
def can_delete_room(member): return member.role in ('owner', 'moderator')
def can_manage_server(member): return member.role == 'owner'
```

This replaces the current `is_staff` check (which is global, not per-server) with a per-server role. Three functions, no new dependencies, no new models — just a field on an existing model.

**New dependencies: 0.**

### 4.2 Server Bans

**The problem:** Kick is temporary — the user can rejoin immediately via invite code.

**Model:**
```python
class ServerBan(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='bans')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    banned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # null = permanent
```

**Enforcement:** Check `ServerBan.objects.filter(server=server, user=user)` (with expiry check) in `server_join`, `server_detail`, and `ServerChatConsumer.connect()`. One query, cached per session.

**New dependencies: 0.**

### 4.3 Chat Search

**Technology choice: PostgreSQL full-text search via Django ORM**

*Why not Elasticsearch/Meilisearch/Typesense?*
They're excellent search engines, but they're entire services to deploy, monitor, and keep in sync with your database. PostgreSQL `SearchVector` + `SearchQuery` handles keyword search on chat messages well enough for thousands of servers with millions of messages. It requires zero additional infrastructure.

**Implementation:**
```python
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

ChatMessage.objects.filter(server=server, deleted_at__isnull=True).annotate(
    rank=SearchRank(SearchVector('content'), SearchQuery(query))
).filter(rank__gt=0).order_by('-rank')[:50]
```

Add a `GIN` index for performance:
```python
class ChatMessage(models.Model):
    class Meta:
        indexes = [
            GinIndex(fields=['content'], name='chat_content_search_idx',
                     opclasses=['gin_trgm_ops']),
        ]
```

*Limitation:* this only works in production (PostgreSQL). Development uses SQLite. For dev, fall back to `content__icontains` — slower but functional.

**New dependencies: 0.** `django.contrib.postgres` is built into Django.

### 4.4 Notifications & Mentions

**Design choice: piggyback on existing WebSocket, no new consumer**

The `ServerChatConsumer` already broadcasts messages to all connected members. @mention parsing happens in `receive()`: if the message contains `@username`, create a `Notification` record and include a `mentions: ["username"]` field in the broadcast.

```python
class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Client-side: highlight @mentions in messages, show unread badge on server list, play notification sound.

*Why not a separate notification consumer?*
It's unnecessary complexity. The user is either connected to the server's chat WebSocket (and gets real-time notification inline) or they're not connected (and see unread count on next page load via a template context processor).

**New dependencies: 0.**

### 4.5 REST API (Only If Needed)

**When to build this:** Only if you're building a mobile app, a desktop client, or third-party integrations. If the app stays browser-only, the existing Django views + WebSocket consumers are the API.

**Technology choice: Django REST Framework**

*Why DRF and not Django Ninja or plain JsonResponse?*
DRF is the standard. It has serializers (validation), viewsets (CRUD boilerplate), authentication classes (token, JWT), permissions, pagination, throttling, and auto-generated OpenAPI docs via drf-spectacular. The ecosystem is massive.

*Why not Django Ninja?*
It's newer, faster (Pydantic-based), and has a cleaner API. But the ecosystem is smaller, community support is thinner, and DRF's maturity matters for a project that already uses Django conventions.

**Auth: Token authentication (DRF built-in), not JWT**

*Why not JWT (djangorestframework-simplejwt)?*
JWT adds token refresh logic, token blacklisting, and a whole category of security concerns (token theft, replay attacks, revocation). DRF's `TokenAuthentication` is simpler: one token per user, stored in the database, revocable instantly. For a project that already has Django sessions for the web UI, token auth for API clients is the simplest addition.

**New dependencies: 1 (`djangorestframework`). Possibly 2 (`drf-spectacular` for API docs).**

### 4.6 Recording

**Design choice: client-side MediaRecorder, not server-side**

*Why client-side?*
- No new infrastructure (SFU or media server)
- Works with the existing P2P architecture
- The browser's `MediaRecorder` API can record any `MediaStream`
- Recordings stay on the user's device (privacy-friendly) or upload to S3

*Limitations:*
- Only the user who starts recording gets the file
- If the browser tab crashes, the recording is lost
- Can't record if you're not a participant

**Implementation:**
- Combine all remote audio tracks + screen/video into one `MediaStream` using `AudioContext.createMediaStreamDestination()`
- Create `MediaRecorder` with `video/webm; codecs=vp9,opus`
- On stop: offer download as `.webm` file, or upload to `/servers/<uuid>/recordings/`
- Consent: broadcast `recording_started` via WebSocket, show red indicator to all peers. Any peer can see someone is recording.

**New dependencies: 0.** Pure browser API.

---

## Phase 5 — Polish (Weeks 25+)

### 5.1 PWA Support

A `manifest.json` + a minimal service worker that serves an "offline" page. No aggressive caching (the app requires a live server). This gives:
- "Add to Home Screen" on mobile
- App-like launch experience
- Offline feedback instead of Chrome's dinosaur

**New dependencies: 0.**

### 5.2 Accessibility

Run axe-core on every page. Fix the high-impact items:
- `aria-label` on all icon-only buttons (mute, camera, share, leave, kick)
- Focus management in modals (trap focus, return focus on close)
- `role="status"` on participant join/leave notifications
- Keyboard navigation for room controls
- Colour contrast check on the dark theme

**New dependencies: 0.**

### 5.3 Bandwidth Adaptation

Use `RTCPeerConnection.getStats()` to monitor available bandwidth. When bandwidth drops:
1. Reduce video resolution (720p → 480p → 360p) via `sender.setParameters()`
2. Reduce frame rate (30 → 15 → 10 fps)
3. Last resort: disable video, keep audio

Show a connection quality indicator (green/yellow/red) per peer based on round-trip time and packet loss from the stats API.

**New dependencies: 0.** Pure WebRTC API.

### 5.4 SFU Architecture (Only If Needed)

**When to consider:** If rooms regularly have 6+ participants and bandwidth is a bottleneck.

**Technology choice: LiveKit**

*Why LiveKit over mediasoup or Janus?*
- Open source, self-hostable
- Go-based (single binary, low memory)
- Has a Python SDK for server-side room management
- Has a JS SDK for client-side WebRTC
- Handles TURN, simulcast, bandwidth estimation, recording, and egress out of the box
- Can run in a single Docker container

*Why not mediasoup?*
Requires a Node.js sidecar process. You'd have two runtimes (Python + Node) to deploy and monitor.

*Why not Janus?*
C-based, harder to deploy and configure, the API is more complex, and the community is smaller.

**Migration path:**
1. Keep the current P2P architecture for 1-on-1 calls
2. For rooms with 3+ participants, route through LiveKit
3. The signaling changes from custom WebSocket messages to LiveKit's SDK (different protocol)
4. This is a significant rewrite of `webrtc.js` and `RoomConsumer`

**New dependencies: LiveKit server (Docker), `livekit-api` (Python SDK), LiveKit JS SDK (client).**

**Recommendation:** Don't start this until P2P is a proven bottleneck with real users. It's a major architectural change.

---

## Dependency Audit Summary

| Phase | New Runtime Dependencies | New Dev Dependencies |
|-------|------------------------|---------------------|
| 1 | 0 | 0 |
| 2 | 0 (coturn is infrastructure, not a pip package) | 0 |
| 3 | 0 | 1 (ruff, dev only) |
| 4 | Variable (0-10 depending on choices) | 0 |
| 5 | 0-1 (DRF, only if API is needed) | 0-1 (drf-spectacular) |
| 6 | 0-1 (livekit-api, only if SFU is needed) | 0 |

---

## Risks and Contingencies

- **P2P Limitations:** If TURN/STUN proves insufficient for target users, prioritize Phase 2.1 early.
- **Dependency Creep:** Re-evaluate philosophy if new features require >5 new packages; consider alternatives.
- **Scalability Bottlenecks:** Monitor Redis/PostgreSQL performance in Phase 3; if issues arise, add read replicas or sharding.
- **Security:** Conduct a third-party audit before public launch; use tools like Bandit for static analysis.
- **Maintenance:** Set up automated dependency updates (Dependabot) to avoid version drift.

**Worst case through Phase 4: 13-14 runtime dependencies.** Still lean.

---

## What This Roadmap Deliberately Omits

These are commonly suggested features that would add complexity without proportional value for this project:

| Feature | Why Not |
|---------|---------|
| **Celery task queue** | No long-running background tasks. Room cleanup runs in a management command + on-request check. Image processing is synchronous and fast (Pillow verify). |
| **GraphQL** | REST (or no API at all) is simpler for CRUD + real-time. GraphQL adds a schema layer, resolver boilerplate, and N+1 query risks. |
| **Microservices** | One Django process handles everything. Splitting into services adds network hops, deployment complexity, and distributed debugging. |
| **Kubernetes** | Docker Compose or a single container is sufficient. K8s is for when you need auto-scaling, rolling deploys, and service mesh — not for a single-app deployment. |
| **Redis Streams / Kafka** | Django Channels + Redis pub/sub already handles message distribution. Event sourcing adds complexity with no clear benefit here. |
| **CDN for static files** | WhiteNoise serves compressed static files with cache headers. A CDN helps at scale but adds configuration and cost. Add it when page load times are measurably affected. |
| **WebAssembly** | No computation-heavy client-side logic that would benefit. The browser's native WebRTC APIs are already fast. |
| **Server-Side Rendering (SSR) with React/Vue** | Django templates are already server-rendered. Adding a JS framework would require a build step, a Node process, and hydration logic. The current vanilla JS approach is simpler and faster. |

---

## Decision Log

Record architectural decisions as they're made, so future contributors understand the "why":

| Date | Decision | Rationale |
|------|----------|-----------|
| — | P2P mesh for video | Simplest architecture, no media server to operate, works for 2-6 participants |
| — | Django Channels over Socket.IO | Native Django integration, shares auth/session, no Node.js dependency |
| — | SQLite for dev, PostgreSQL for prod | Fast dev setup, production-grade data guarantees |
| — | Session auth over JWT | Simpler, revocable, no token refresh logic, sufficient for browser-only clients |
| — | WhiteNoise over nginx | One fewer process to configure and monitor, good enough for moderate traffic |
| — | S3 for media in prod, filesystem in dev/allinone | Standard pattern, swappable via Django STORAGES setting |
| — | Server-rendered templates over SPA | No build step, no API layer, faster initial page load, works without JS for basic navigation |
