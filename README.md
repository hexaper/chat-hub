# Chat Hub
<img width="1280" height="720" alt="project-banner" src="https://github.com/user-attachments/assets/599a6818-cb3e-44d2-87c7-84d3822363c3" />

A real-time video conferencing and chat platform built with Django, Django Channels, and WebRTC. Users create and join servers (similar to Discord), start video rooms with peer-to-peer calls, and communicate through real-time text chat with image support.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start (Local Development)](#quick-start-local-development)
- [Testing](#testing)
- [Docker Deployment](#docker-deployment)
  - [All-in-One Container](#all-in-one-container)
  - [Production (External Services)](#production-external-services)
- [Environment Variables](#environment-variables)
- [URL Reference](#url-reference)
- [WebSocket Endpoints](#websocket-endpoints)
- [Project Structure](#project-structure)
- [Management Commands](#management-commands)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

- **Servers** — Create public or private servers with 8-character invite codes. Public servers appear on the homepage; private servers require an invite link.
- **Video Rooms** — WebRTC peer-to-peer video/audio calls within servers. Rooms support optional password protection, screen sharing, camera/mic toggle, and host controls (kick, force-mute).
- **Real-Time Chat** — Per-server and per-room text chat with image uploads, delivered over WebSockets. Infinite scroll loads older messages on demand (50 per page).
- **Message Editing & Deletion** — Edit your own messages within a 15-minute window. Soft delete shows a "Message deleted" placeholder. All changes broadcast in real time to connected members.
- **Typing Indicators** — Debounced, ephemeral "X is typing…" indicator. No database writes — purely WebSocket relay.
- **User Presence** — Green dot next to each online member in the chat panel. Presence is derived from active WebSocket connections; no polling.
- **User Accounts** — Registration, login, profile with avatar and bio, account settings with live camera/mic preview. Email addresses are unique per account.
- **Rate Limiting** — Login and registration capped at 5/min per IP; image uploads at 10/min per user; chat messages at 30/min per user. Backed by Redis cache.
- **Health Check** — `GET /healthz/` performs a DB query and Redis ping; used by Docker `HEALTHCHECK`.
- **TURN Server Support** — Optional coturn integration for users behind strict NAT/firewalls. Credentials generated server-side via HMAC and served from `/api/ice-servers/`.
- **Admin Panel** — Staff users (`is_staff=True`) can manage servers, rooms, and users from `/admin-panel/`.
- **Auto-Cleanup** — Rooms empty for 15+ minutes are automatically deactivated via a management command.
- **Dark Theme** — Modern responsive UI with Bootstrap 5.

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Backend | Django | 5.2 |
| WebSockets / ASGI | Django Channels + Daphne | 4.3 / 4.2 |
| Channel Layer | channels-redis | 4.3 |
| Database (dev) | SQLite | — |
| Database (prod) | PostgreSQL | 16 |
| Message Broker / Cache | Redis | 7.x |
| Frontend | Bootstrap 5, vanilla JS | — |
| Forms | django-crispy-forms + crispy-bootstrap5 | 2.6 |
| Static Files (prod) | WhiteNoise | 6.12 |
| Media Storage (prod) | S3 via django-storages + boto3 | 1.14 |
| Image Processing | Pillow | 12.1 |

## Architecture

```
                  Browser
                  /     \
          HTTPS/WSS     WebRTC (P2P)
              |              |
         [ Daphne ]     STUN/TURN Server
         (ASGI)
          /     \
     HTTP       WebSocket
    views       consumers
      |           |
   Django      Channels
   ORM         Redis (DB 0)
      \
   PostgreSQL     Redis cache (DB 1)
```

### Apps

| App | Responsibility |
|-----|---------------|
| `apps.accounts` | Custom `User` model (extends `AbstractUser` with `avatar`, `bio`, unique `email`). Views for registration, login, logout, profile, and account settings. |
| `apps.rooms` | Core application. Models: `Server`, `ServerMember`, `Room`, `RoomParticipant`, `ChatMessage`, `RoomChatMessage`. WebSocket consumers: `RoomConsumer` (WebRTC signaling), `ServerChatConsumer` (server chat), `RoomChatConsumer` (room chat). Admin panel views. Landing page. |
| `apps.devices` | `Device` model storing browser media devices (camera/microphone). REST endpoint for device registration from the frontend. |

### Data Model Hierarchy

```
User (unique email, nullable)
└── Server (owner FK)
    ├── ServerMember (User ↔ Server M2M through table)
    ├── ChatMessage (server-scoped chat; has updated_at, deleted_at)
    └── Room (belongs to Server, created by "host" User)
        ├── RoomParticipant (User ↔ Room M2M, stores channel_name + device IDs)
        ├── RoomChatMessage (room-scoped chat; has updated_at, deleted_at)
        └── last_empty_at (drives auto-cleanup command)
```

`ChatMessage` and `RoomChatMessage` use **soft delete** (`deleted_at`): the record is retained with content cleared in API responses. Edits are allowed within a 15-minute window (`updated_at` is set on save).

### Settings Structure

| File | Purpose |
|------|---------|
| `base.py` | Shared configuration (installed apps, middleware, auth, templates, static/media paths, rate limiting cache) |
| `development.py` | `DEBUG=True`, SQLite, `ALLOWED_HOSTS=['*']`, static files served via `staticfiles_urlpatterns()` |
| `production.py` | `DEBUG=False`, external PostgreSQL (SSL), external Redis, S3 media, WhiteNoise static files, full security headers |
| `allinone.py` | `DEBUG=False`, bundled PostgreSQL + Redis, local media, WhiteNoise, self-signed TLS on port 8000 |

### WebRTC Signaling Flow

1. User opens a room. `webrtc.js` fetches ICE server config from `/api/ice-servers/` (includes TURN credentials when configured).
2. A WebSocket connection opens to `ws://.../ws/rooms/<room-slug>/`.
3. `RoomConsumer.connect()` adds the user to the channel group and broadcasts `user_joined` with avatar URL and join sequence number.
4. Existing peers create an SDP offer targeting the new peer's channel name.
5. The new peer responds with an `answer`. Both sides exchange `ice-candidate` messages.
6. Direct P2P media established via STUN (`stun:stun.l.google.com:19302`) or relayed via TURN if configured.
7. On disconnect, `user_left` is broadcast and `last_empty_at` is set if the room becomes empty.

## Prerequisites

- **Python 3.10+**
- **Redis** running on `localhost:6379`
- **Git**

For Docker deployments, only **Docker** (and optionally **Docker Compose**) is required.

## Quick Start (Local Development)

The `deploy.sh` script automates the entire local setup: creates a virtual environment, installs dependencies, starts Redis, runs migrations, seeds test data, and launches the development server.

```bash
git clone https://github.com/hexaper/chat-hub.git
cd chat-hub
sudo apt install python3 python3-venv
chmod +x deploy.sh
./deploy.sh
```

Once running:

| | |
|---|---|
| **URL** | `http://localhost:8000` |
| **Test accounts** | `test1` / `test2` (password: `Tester123.`) |
| **Database** | `db.sqlite3` (SQLite) |
| **Settings module** | `config.settings.development` |

To stop the server, press `Ctrl+C`.

## Testing

The application includes a comprehensive test suite covering models, views, forms, permissions, WebSocket consumers, integration flows, and rate limiting.

### Running Tests

Ensure Redis is running, then activate the virtual environment and run the tests:

```bash
source venv/bin/activate
python manage.py test --settings=config.settings.development --keepdb
```

**Note:** Do not use `--parallel` — it causes a pickle error on Python 3.13.

### Test Structure

| Directory | What's tested |
|-----------|---------------|
| `apps/accounts/tests/` | Registration, login, profile, auth boundaries, rate limiting |
| `apps/rooms/tests/` | Server/room CRUD, permissions, WebSocket consumers (`ConsumerTests`, `RoomChatConsumerTests`), integration flows, rate limiting |
| `apps/devices/tests/` | Device registration endpoint, auth boundaries |
| `utils/tests.py` | `@ratelimit` decorator unit tests |

Consumer tests use `TransactionTestCase` (required — Channels consumer coroutines can't see `TestCase`'s uncommitted transaction). All other classes use `TestCase` with `setUpTestData`.

### Manual Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

redis-cli ping  # Should return PONG

DJANGO_SETTINGS_MODULE=config.settings.development python manage.py migrate
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py createsuperuser  # optional

# HTTP only:
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver 0.0.0.0:8000

# With WebSockets (required for chat and video):
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

## Docker Deployment

### All-in-One Container

A single container that bundles PostgreSQL 16 and Redis alongside the Django application. Starts Daphne with a self-signed TLS certificate — access at `https://localhost:8000` (browser will warn about the self-signed cert).

**Using Docker Compose (recommended):**

```bash
docker compose -f allinone/docker-compose.yml up --build
```

**Using Docker directly:**

```bash
docker build -t chat-hub -f allinone/Dockerfile .
docker run -p 8000:8000 chat-hub
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_NAME` | `videocall` | PostgreSQL database name |
| `DB_USER` | `videocall` | PostgreSQL user |
| `DB_PASSWORD` | `videocall` | PostgreSQL password |
| `TEST_USER_PASSWORD` | *(empty)* | If set, creates `test1`/`test2` users and a "Test Server" |
| `SECRET_KEY` | *(auto-generated)* | Persisted to `/app/mediafiles/.secret_key` on first run |
| `TURN_HOST` | *(empty)* | TURN server hostname (enables TURN when set alongside `TURN_SECRET`) |
| `TURN_SECRET` | *(empty)* | HMAC secret shared with coturn |

The Compose file defines two persistent volumes: `media_files` (uploads + TLS cert + secret key) and `pg_data` (PostgreSQL data).

### Production (External Services)

For production, the application container connects to externally managed PostgreSQL, Redis, and S3-compatible storage.

```bash
docker compose up --build
```

Create a `.env` file in the project root (see Environment Variables below).

**Example `.env`:**

```
SECRET_KEY=your-random-secret-key
ALLOWED_HOSTS=myapp.example.com
POSTGRES_HOST=db.example.com
POSTGRES_NAME=chathub
POSTGRES_USER=admin
POSTGRES_PASS=mypassword
REDIS_HOST=redis://redis.example.com:6379
AWS_STORAGE_BUCKET_NAME=my-media-bucket
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your-secret
SECURE_SSL_REDIRECT=false
TEST_USER_PASSWORD=MyTestPass123.
ADMIN_USER_PASSWORD=AdminPass456.
TURN_HOST=turn.example.com
TURN_SECRET=my-turn-secret
```

## Environment Variables

### Production (`config.settings.production`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | No* | Auto-generated | Django secret key; persisted if not set |
| `ALLOWED_HOSTS` | **Yes** | — | Comma-separated hostnames |
| `POSTGRES_HOST` | Yes | — | PostgreSQL host |
| `POSTGRES_NAME` | Yes | — | PostgreSQL database name |
| `POSTGRES_USER` | Yes | — | PostgreSQL user |
| `POSTGRES_PASS` | Yes | — | PostgreSQL password |
| `REDIS_HOST` | Yes | — | Full Redis URL |
| `AWS_STORAGE_BUCKET_NAME` | Yes | — | S3 bucket for media |
| `AWS_ACCESS_KEY_ID` | Yes | — | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | S3 secret |
| `AWS_S3_REGION_NAME` | No | `us-east-1` | S3 region |
| `AWS_S3_ENDPOINT_URL` | No | *(empty)* | Custom S3 endpoint (MinIO, R2, B2) |
| `AWS_S3_CUSTOM_DOMAIN` | No | *(empty)* | CDN domain for media URLs |
| `SECURE_SSL_REDIRECT` | No | `false` | Redirect HTTP → HTTPS |
| `CSRF_TRUSTED_ORIGINS` | No | *(empty)* | Comma-separated trusted origins |
| `TURN_HOST` | No | *(empty)* | TURN server hostname |
| `TURN_SECRET` | No | *(empty)* | coturn HMAC secret |
| `TURN_TTL` | No | `3600` | TURN credential TTL in seconds |
| `TEST_USER_PASSWORD` | No | *(empty)* | Seed `test1`/`test2` users on startup |
| `ADMIN_USER_PASSWORD` | No | *(empty)* | Seed `admin` (staff) user on startup |

### All-in-One (`config.settings.allinone`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | No | Auto-generated | Persisted to `mediafiles/.secret_key` |
| `DB_NAME` | No | `videocall` | Bundled PostgreSQL database name |
| `DB_USER` | No | `videocall` | Bundled PostgreSQL user |
| `DB_PASSWORD` | No | `videocall` | Bundled PostgreSQL password |
| `SECURE_SSL_REDIRECT` | No | `false` | HTTP-to-HTTPS redirect |
| `TURN_HOST` | No | *(empty)* | TURN server hostname |
| `TURN_SECRET` | No | *(empty)* | coturn HMAC secret |
| `TEST_USER_PASSWORD` | No | *(empty)* | Seed test users on startup |

## URL Reference

### Pages

| URL | Description | Auth |
|-----|-------------|------|
| `/` | Landing page; redirects to server list if authenticated | No |
| `/servers/` | Server list | Yes |
| `/servers/create/` | Create a server | Yes |
| `/servers/join/?code=XXXXXXXX` | Join via invite code | Yes |
| `/servers/<uuid>/` | Server detail — rooms + chat | Yes (member) |
| `/servers/<uuid>/settings/` | Server settings | Yes (owner) |
| `/servers/<uuid>/leave/` | Leave a server | Yes (member) |
| `/servers/<uuid>/delete/` | Delete a server | Yes (owner) |
| `/servers/<uuid>/rooms/create/` | Create a room | Yes (member) |
| `/servers/<uuid>/rooms/<uuid>/` | Room — video call interface | Yes (member) |
| `/servers/<uuid>/rooms/<uuid>/leave/` | Leave a room | Yes |
| `/servers/<uuid>/rooms/<uuid>/delete/` | Delete a room | Yes (host) |
| `/accounts/register/` | Registration (rate-limited 5/min) | No |
| `/accounts/login/` | Login (rate-limited 5/min) | No |
| `/accounts/logout/` | Logout | Yes |
| `/accounts/profile/` | View own profile | Yes |
| `/accounts/settings/` | Edit profile, avatar, device preview | Yes |
| `/admin-panel/` | Admin panel | Yes (staff) |
| `/admin/` | Django admin | Yes (staff) |
| `/healthz/` | Health check (DB + Redis ping) | No |

### API Endpoints

| URL | Method | Description |
|-----|--------|-------------|
| `/api/ice-servers/` | GET | ICE server config with TURN credentials (when `TURN_ENABLED`) |
| `/devices/register/` | POST | Register browser media devices |
| `/servers/<uuid>/chat/upload/` | POST | Upload image to server chat (rate-limited 10/min) |
| `/servers/<uuid>/settings/kick/` | POST | Kick a member (owner only) |
| `/servers/<uuid>/settings/regenerate-invite/` | POST | Regenerate invite code (owner only) |

## WebSocket Endpoints

### Room Consumer: `ws://<host>/ws/rooms/<room-slug>/`

Handles WebRTC signaling for video rooms.

**Sent by server:**

| Type | Fields | Description |
|------|--------|-------------|
| `my_channel` | `channel`, `avatar_url`, `seq` | Client's own channel name on connect |
| `user_joined` | `username`, `channel`, `seq`, `avatar_url` | A user joined |
| `user_left` | `username`, `channel`, `seq` | A user left |
| `offer` / `answer` / `ice-candidate` | `payload`, `sender`, `username`, `avatar_url`, `seq` | Signaling forwarded from a peer |
| `media_state` | `channel`, `mic`, `cam` | Peer mic/camera state changed |
| `kicked` | — | You were kicked by the host |
| `force_mute` | — | Host force-muted your mic |
| `room_closed` | — | Room was closed |

**Sent by client:**

| Type | Fields | Description |
|------|--------|-------------|
| `offer` / `answer` / `ice-candidate` | `target`, `payload` | Forward signaling to a specific peer |
| `device_update` | `cameraId`, `microphoneId` | Update selected devices |
| `media_state` | `mic`, `cam` | Broadcast mic/camera toggle |
| `kick` | `target_channel`, `username` | Kick a participant (host only) |
| `mute_user` | `target_channel` | Force-mute a participant (host only) |

### Server Chat Consumer: `ws://<host>/ws/chat/<server-slug>/`

**Sent by server:**

| Type | Fields | Description |
|------|--------|-------------|
| `history` | `messages[]`, `has_more`, `online_users[]` | Last 50 messages + online user list on connect |
| `history_page` | `messages[]`, `has_more` | Older messages in response to `load_history` |
| `chat_message` | `id`, `username`, `avatar_url`, `content`, `image_url`, `created_at` | New message |
| `message_edited` | `id`, `content`, `updated_at` | A message was edited |
| `message_deleted` | `id` | A message was soft-deleted |
| `user_typing` | `username` | A user is typing |
| `presence` | `username`, `status` (`online`/`offline`) | Presence change |

**Sent by client:**

| Type | Fields | Description |
|------|--------|-------------|
| `chat_message` | `content` | Send a text message |
| `chat_image` | `message_id` | Broadcast an uploaded image (upload via HTTP first) |
| `edit_message` | `message_id`, `content` | Edit own message (within 15-min window) |
| `delete_message` | `message_id` | Soft-delete own message |
| `typing` | — | Notify others you are typing (debounced) |
| `load_history` | `before_id` | Request 50 messages older than `before_id` |

### Room Chat Consumer: `ws://<host>/ws/room-chat/<room-slug>/`

Same message types as Server Chat Consumer except no `chat_image`, no `presence`.

## Project Structure

```
chat-hub/
├── apps/
│   ├── accounts/            # Custom User model, auth views, forms
│   ├── devices/             # Device model, registration endpoint
│   └── rooms/               # Servers, rooms, chat, WebSocket consumers
│       ├── consumers.py     # RoomConsumer, ServerChatConsumer, RoomChatConsumer
│       ├── models.py        # Server, Room, ChatMessage, RoomChatMessage, …
│       ├── routing.py       # WebSocket URL patterns
│       ├── views.py         # All server/room/admin/landing views
│       └── management/commands/cleanup_empty_rooms.py
├── config/
│   ├── asgi.py              # ASGI entrypoint (HTTP + WebSocket routing)
│   ├── urls.py              # Root URL config (healthz, ice-servers, static in dev)
│   └── settings/
│       ├── base.py          # Shared settings + Redis cache config
│       ├── development.py   # SQLite, DEBUG=True
│       ├── production.py    # External PostgreSQL + S3 + security headers
│       └── allinone.py      # Bundled PostgreSQL + Redis + WhiteNoise + TLS
├── utils/
│   ├── ratelimit.py         # @ratelimit decorator + is_rate_limited() helper
│   └── turn.py              # HMAC credential generator for coturn
├── static/
│   ├── css/main.css         # Dark theme styles
│   └── js/webrtc.js         # WebRTC + signaling client logic
├── templates/
│   ├── base.html            # Bootstrap 5 base (toasts, messages, nav)
│   ├── landing.html         # Public landing page
│   ├── accounts/            # Login, register, profile, settings
│   ├── devices/             # Device list
│   └── rooms/               # Server list/detail, room detail, admin panel
├── docs/
│   └── ROADMAP.md           # Prioritised feature roadmap
├── allinone/
│   ├── Dockerfile           # All-in-one image (PostgreSQL 16 + Redis bundled)
│   ├── docker-compose.yml   # Compose for all-in-one
│   └── entrypoint.sh        # Starts PG, Redis, migrates, generates TLS cert, starts Daphne
├── Dockerfile               # Production image (external services)
├── docker-compose.yml       # Compose for production
├── entrypoint.sh            # Production entrypoint
├── deploy.sh                # Local development setup script
├── requirements.txt         # Python dependencies (12 packages)
└── manage.py
```

## Management Commands

```bash
# Clean up rooms empty for 15+ minutes
python manage.py cleanup_empty_rooms --settings=config.settings.development

# Run the full test suite
python manage.py test --settings=config.settings.development --keepdb

# Create a superuser
python manage.py createsuperuser --settings=config.settings.development
```

## Troubleshooting

**Redis connection refused**

The application requires Redis for WebSocket channel layers and rate limiting. Ensure it's running:

```bash
redis-cli ping  # Expected: PONG
```

**WebSocket connections fail on `runserver`**

Django's built-in `runserver` does not support WebSockets. Use Daphne:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

**Static files return HTML (MIME mismatch) over HTTPS**

In development, static files are served via `staticfiles_urlpatterns()` (added in `config/urls.py` when `DEBUG=True`). In production/allinone, WhiteNoise middleware serves hashed filenames from `STATIC_ROOT`. Do not re-add `ASGIStaticFilesHandler` to `asgi.py` — it cannot serve hashed filenames and intercepts requests before WhiteNoise can handle them.

**WebRTC calls fail (no video/audio)**

- Access the site over HTTPS or `localhost`. Browsers block `getUserMedia()` on insecure origins.
- Check that STUN (`stun:stun.l.google.com:19302`) is reachable.
- If peers are behind strict NAT, configure a TURN server (`TURN_HOST` + `TURN_SECRET`).

**CSRF errors behind a reverse proxy**

Set `CSRF_TRUSTED_ORIGINS` to your domain (e.g., `https://yourdomain.com`).

**Self-signed certificate warning (allinone)**

The allinone container generates a self-signed TLS certificate on first run. Browsers will display a security warning — click "Advanced → Proceed" for local use. The cert is stored in `mediafiles/ssl/` and reused on subsequent restarts.

**Media uploads fail in production**

Verify all `AWS_*` environment variables are set correctly and the S3 bucket has write permissions. In allinone mode, media is stored in `/app/mediafiles/` inside the container (persisted via the `media_files` volume).

## License

No license file is currently included in this repository.
