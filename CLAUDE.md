# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project description
Chat Hub is a web-based communication platform inspired by Discord, built to stay simpler and more focused while still covering the core features people expect from a modern community and voice/video app. The product centers on servers, rooms, and live communication: users can join public or private servers, move between text and real-time voice/video spaces, and keep conversations active across server-wide chat and room-specific chat. The current product direction is to make the web app strong enough to stand on its own first, then expand toward desktop and mobile clients once the core experience is reliable.

The long-term goal is not to clone Discord feature-for-feature, but to deliver a credible alternative with a cleaner scope and less operational bloat. That means keeping the current stack lean while still covering the areas that matter most in practice: reliable video and audio rooms, fast live chat, strong account and device settings, discoverability for public communities, and the social features that make people stay in the product.

Core implemented and near-term product areas include:
- public and private servers with invite-based access and a public discovery path
- server-wide text chat plus room-specific live chat with persistent history
- multi-user audio and video rooms with host controls, per-user mute flows, and screen sharing
- text, image, and video messaging with live updates, editing, deletion, typing indicators, and search as a target capability
- account, profile, and device settings so users can configure microphones, cameras, avatars, bios, and appearance preferences

Features a Discord-like app will also need as the product matures:
- direct messages, group DMs, and a friends system with presence-aware private conversations
- server roles, permissions, moderation tools, bans, mutes, reporting, and audit-friendly admin actions
- channel organization features such as categories, pinned messages, mentions, notifications, unread states, and better message search/filtering
- richer identity and social features including custom statuses, profile personalization, and community onboarding flows
- stronger multi-platform support, push notifications, and better reliability under larger room sizes and multi-instance deployments


## Commands

**Start dev server (HTTP only, no WebSockets):**
```bash
source venv/bin/activate
python manage.py runserver --settings=config.settings.development
```

**Start dev server with WebSockets (and optional SSL):**
```bash
source venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
# With self-signed TLS (mirrors allinone):
DJANGO_SETTINGS_MODULE=config.settings.development daphne -e ssl:8443:privateKey=ssl.key:certKey=ssl.crt config.asgi:application
```

**Run all tests (Redis must be running):**
```bash
source venv/bin/activate
python manage.py test --settings=config.settings.development --keepdb
```

Note: `--parallel` causes a pickle error on this Python version; run sequentially.

**Run a single test class or method:**
```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_consumers.RoomChatConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_unauthenticated_connection_rejected --settings=config.settings.development
```

**Migrations:**
```bash
python manage.py migrate --settings=config.settings.development
python manage.py makemigrations --settings=config.settings.development
```

**Auto-cleanup management command:**
```bash
python manage.py cleanup_empty_rooms --settings=config.settings.development
```

**Full local setup from scratch:**
```bash
./deploy.sh  # installs deps, starts Redis, runs migrations, seeds test users, starts server
```

---

## Architecture

### The big picture

This is a **Django + Django Channels + WebRTC** application. The HTTP layer is standard Django; the real-time layer is Django Channels over Redis. Video is pure P2P WebRTC — the server only relays signaling messages, never media.

```
Browser ──HTTP/WS──► Daphne (ASGI)
                         │
              ┌──────────┴──────────┐
           HTTP views          WebSocket consumers
           (Django ORM)        (Channels + Redis pub/sub)
              │                     │
           SQLite / PostgreSQL     Redis channel layer (DB 0)
                                   Redis cache (DB 1)
```

### Settings split (`config/settings/`)

| File | When used |
|------|-----------|
| `base.py` | Always imported by the others; shared config |
| `development.py` | Local dev — SQLite, `DEBUG=True`, `ALLOWED_HOSTS=['*']` |
| `production.py` | Docker prod — external PostgreSQL (SSL), external Redis, S3 media, full security headers |
| `allinone.py` | Docker self-host — bundled PostgreSQL + Redis, local media storage, WhiteNoise, self-signed TLS |

Always pass `--settings=config.settings.development` when running management commands locally. The `DJANGO_SETTINGS_MODULE` env var also works.

### Static files

- **Development** (`DEBUG=True`): `staticfiles_urlpatterns()` in `config/urls.py` serves files from `STATICFILES_DIRS` directly. No `ASGIStaticFilesHandler` — it was removed because it can't serve hashed filenames.
- **Production/allinone** (`DEBUG=False`): WhiteNoise middleware (`whitenoise.middleware.WhiteNoiseMiddleware`) serves from `STATIC_ROOT` using `CompressedManifestStaticFilesStorage` (hashed filenames). `collectstatic` runs at Docker build time.

### Apps

| App | Key files | Responsibility |
|-----|-----------|---------------|
| `apps.accounts` | `models.py`, `views.py`, `forms.py` | Custom `User` (extends `AbstractUser` with `avatar`, `bio`, unique `email`), registration/login/profile/settings views |
| `apps.rooms` | `models.py`, `views.py`, `consumers.py`, `routing.py` | Everything rooms-related: servers, memberships, rooms, participants, chat messages, WebSocket consumers, admin panel views, landing page view |
| `apps.devices` | `models.py`, `views.py` | `Device` model (camera/mic), REST endpoint called by the browser on room entry |

### Data model hierarchy

```
User (unique email, nullable — enforced at DB + form level)
└── Server (owner FK)
    ├── ServerMember (User ↔ Server M2M through table)
    ├── Room (belongs to Server, created by "host" User)
    │   ├── RoomParticipant (User ↔ Room M2M through table, stores channel_name)
    │   ├── RoomChatMessage (room-scoped chat; has updated_at, deleted_at)
    │   └── last_empty_at (set when room empties; drives cleanup command)
    └── ChatMessage (server-scoped chat, supports images; has updated_at, deleted_at)
```

`Server.slug` and `Room.slug` are used in URLs and as channel group names.

`ChatMessage` and `RoomChatMessage` use soft delete (`deleted_at`) — deleted messages are retained in the DB with content cleared in API responses. Edits are time-limited to 15 minutes (`EDIT_WINDOW_SECONDS = 900`).

### URL structure

| Path | View | Notes |
|------|------|-------|
| `/` | `landing` | Public landing page; redirects to `server_list` if authenticated |
| `/servers/` | `server_list` | Requires login |
| `/accounts/login/` | `login_view` | Rate-limited 5/m per IP |
| `/accounts/register/` | `register_view` | Rate-limited 5/m per IP |
| `/servers/<uuid>/chat/upload/` | `chat_image_upload` | Rate-limited 10/m per user |
| `/api/ice-servers/` | `ice_servers` | Login required; returns ICE server config JSON with TURN credentials when `TURN_ENABLED` |
| `/healthz/` | `healthz` | DB `SELECT 1` + Redis ping; returns `{"status":"ok"}` or 503 |

### WebSocket consumers (`apps/rooms/consumers.py`)

**Consumer method routing**: `group_send({'type': 'foo_bar', ...})` dispatches to `async def foo_bar(self, event)`. Dots and hyphens in type names become underscores in method names.

**Sender self-exclusion pattern** (our convention, not a Channels built-in): pass `'exclude': self.channel_name` in the `group_send` payload; check `if event.get('exclude') == self.channel_name: return` at the top of the handler.

Three consumers:

**`RoomConsumer`** — WebRTC signaling. Group = `room_{room.slug}`. Sends `my_channel` on connect, broadcasts `user_joined`. Relays `offer`/`answer`/`ice-candidate` with `avatar_url` and `seq`. Host-only: `kick`, `mute_user`. Sets `last_empty_at` on disconnect.

**`ServerChatConsumer`** — Server-scoped text/image chat. Group = `server_chat_{server.slug}`.

| Message type (receive) | Behaviour |
|---|---|
| `chat_message` | Rate-check (30/m), save, broadcast |
| `chat_image` | Look up uploaded image by ID, broadcast |
| `edit_message` | Author-only, 15-min window; update DB, broadcast `message_edited` |
| `delete_message` | Author-only; set `deleted_at`, broadcast `message_deleted` |
| `typing` | Broadcast `user_typing` to group excluding sender |
| `load_history` | Fetch 50 messages with `id < before_id`, reply with `history_page` |

On connect: adds to in-process `_presence` store, broadcasts `presence online` to group, sends `history` with `online_users` list and `has_more` flag.
On disconnect: removes from `_presence`, broadcasts `presence offline`.

**`RoomChatConsumer`** — Room-scoped text chat. Group = `room_chat_{room.slug}`. Requires active `RoomParticipant`. Same message types as `ServerChatConsumer` except no `chat_image` and no presence (participants are already visible in the room UI).

### Presence (`_presence` store in `consumers.py`)

Module-level dict `_presence: dict[str, dict[str, str]]` mapping `server_slug → {channel_name: username}`, guarded by `asyncio.Lock`. Tracks all open `ServerChatConsumer` connections. Multiple browser tabs by the same user collapse to one username via `set()`. No database writes — purely in-process, resets on server restart (clients reconnect and re-broadcast their presence naturally).

### Rate limiting (`utils/ratelimit.py`)

`@ratelimit(key, rate)` decorator backed by Redis cache (DB 1).

- **HTML views** (login, register): on limit, adds a Django `messages.warning` and redirects to `request.path`. Renders as a dismissible Bootstrap alert via `base.html`.
- **AJAX/JSON views** (image upload): detects `Accept: application/json` or `X-Requested-With`, returns `{"error": "rate_limited"}` with 429. Frontend catches this and calls `showToast(...)`.
- **WebSocket consumers** (chat): `is_rate_limited()` standalone helper, silently drops the message.
- `MESSAGE_TAGS` in `base.py` maps Django message levels to Bootstrap classes (`error` → `danger`, etc.).

### WebRTC signaling flow

1. Browser opens `ws://.../ws/rooms/<slug>/` → `RoomConsumer.connect()`
2. Consumer sends `my_channel` (channel name + `avatar_url` + `join_seq`) to the new peer
3. Existing peers receive `user_joined` → create SDP offer → send `offer` with `target=new_peer_channel`
4. Consumer forwards `offer`; target responds with `answer`; both sides exchange `ice-candidate`. `avatar_url` and `seq` forwarded with every signal.
5. P2P media via STUN (`stun:stun.l.google.com:19302`). Optional TURN relay via coturn (set `TURN_HOST` + `TURN_SECRET`, or `TURN_HOST` + `TURN_USERNAME` + `TURN_PASSWORD`).

### Frontend (`static/js/webrtc.js` + inline template scripts)

No build step. Server-rendered templates with progressive enhancement.

`webrtc.js` handles WebRTC only. Chat, presence, and typing are implemented in inline `<script>` blocks in each template.

**`server_detail.html`** chat features:
- WebSocket to `ServerChatConsumer`; auto-reconnects on close
- Infinite scroll: scroll to top triggers `load_history`; older messages prepended while preserving scroll position
- Edit (pencil) and delete (trash) buttons on own messages; edit button auto-hides after 15-min window
- Inline textarea editor: Enter saves, Escape cancels
- Typing indicator: debounced (1 send per 3 s), shown for 5 s after last event, supports multiple typers
- Presence bar: green dot + username for each connected member; seeded from `history.online_users`, updated by `presence` events

**`room_detail.html`** chat features:
- Same edit/delete, typing indicator, and infinite scroll as server chat
- No presence bar (participants visible in the room panel)

**`webrtc.js`** key state: `peers` (channel → RTCPeerConnection), `userChannels` (username → channel), `userSeqs` (username → join_seq). Guards against stale peers via `join_seq` comparison.

Features: camera/mic toggle, screen sharing (replaces outbound video track), spotlight (DOM-moves tile to `#spotlightArea`), avatar placeholders, room loading overlay, ICE config fetched from `/api/ice-servers/` before first peer connection.

### Allinone Docker deployment

Self-contained single-container deployment. `allinone/entrypoint.sh`:
1. Starts bundled PostgreSQL 16 (data persisted to named volume)
2. Starts bundled Redis
3. Runs `manage.py migrate`
4. Optionally seeds test users if `TEST_USER_PASSWORD` is set
5. Generates a self-signed TLS cert (persisted to `mediafiles/ssl/`, reused on restart)
6. Starts Daphne with Twisted SSL endpoint: `-e ssl:8000:privateKey=...:certKey=...`

Access at `https://localhost:8000` (self-signed cert, browser will warn).

### Custom error pages

`templates/404.html`, `templates/403.html`, `templates/500.html` extend `base.html`. Served automatically when `DEBUG=False`.

---

## Test suite

Consumer tests live in two classes:
- `ConsumerTests` — `ServerChatConsumer` tests (connect/disconnect, messaging, edit/delete, typing, presence, history pagination)
- `RoomChatConsumerTests` — `RoomChatConsumer` tests (same coverage for room chat)

All consumer tests use `TransactionTestCase` (required — Channels consumer threads can't see `TestCase`'s uncommitted transaction). All other test classes use `TestCase` with `setUpTestData`.

```
apps/accounts/tests/    auth boundaries, registration/login/profile forms, rate limiting
apps/rooms/tests/       models, forms, views (permissions), consumers, integration flows, rate limiting
apps/devices/tests/     auth boundaries, device registration endpoint
utils/tests.py          ratelimit decorator unit tests
```

Rate-limit tests send `HTTP_ACCEPT='application/json'` when testing the image upload endpoint (needed to trigger the JSON 429 response path).

**Redis must be running** to execute consumer and rate-limit tests.

---

## Current project state

The active branch is **`rate-limit`**.

### Completed phases

- **1.1** — Full test suite
- **1.2** — Rate limiting (`@ratelimit` decorator, `is_rate_limited` helper; login/register 5/m, image upload 10/m, chat 30/m)
- **1.3** — WebSocket origin validation (`AllowedHostsOriginValidator` in `config/asgi.py`)
- **1.4** — Custom error pages (404, 403, 500)
- **1.5** — Health check at `/healthz/`
- **2.1** — TURN server support (coturn HMAC REST API or static TURN credentials, `/api/ice-servers/`, optional coturn service in both Docker Compose stacks)
- **2.3** — Chat message editing (15-min window) and soft deletion, for both `ServerChatConsumer` and `RoomChatConsumer`
- **2.4** — Typing indicators (debounced, ephemeral, no DB writes) for both chat consumers
- **2.5** — User presence (WebSocket connection = online; in-process `_presence` store; green dot bar in server chat)
- **Pagination** — Infinite scroll chat history (`load_history` / `history_page` WS messages, 50 msgs per page)
- **Landing page** — Public page at `/`; authenticated users redirect to `/servers/`
- **Unique email** — `User.email` is `unique=True, null=True`; case-insensitive validation in forms
- **Allinone TLS** — Self-signed cert generated in entrypoint, Daphne runs HTTPS on port 8000

---

## Key design constraints

1. **No new pip dependencies** unless strictly necessary. Current `requirements.txt` is 12 lines — guard it.
2. **No frontend build step** — vanilla JS, no TypeScript, no npm.
3. **One DB, one cache, one queue** — PostgreSQL, Redis, nothing else.
4. **P2P WebRTC** — no SFU (mediasoup, LiveKit) until measured evidence the mesh doesn't scale.
5. **Presence is stateless** — no `last_seen` DB field; WebSocket connection is the signal.
6. **Soft delete for chat** — `deleted_at` field; content cleared in responses, record retained for audit.

## Important notes

1. **Tests** — write tests for new features as you go. Use the `django-test-engineer` agent for it.
2. **`--parallel` is broken** on this environment (Python 3.13 pickle issue) — always run tests without it.
3. **`_presence` resets on restart** — this is intentional; clients reconnect and re-broadcast presence naturally.
4. **`database_sync_to_async`** wraps ORM calls (manages the DB connection thread). **`sync_to_async`** wraps other sync callables (e.g. `is_rate_limited`). Don't use `sync_to_async` for ORM work.
5. **Latest migrations**: `rooms` → `0010`, `accounts` → `0002`.
