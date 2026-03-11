# Chat Hub
<img width="1280" height="720" alt="project-banner" src="https://github.com/user-attachments/assets/599a6818-cb3e-44d2-87c7-84d3822363c3" />

A real-time video conferencing and chat platform built with Django, Django Channels, and WebRTC. Users create and join servers (similar to Discord), start video rooms with peer-to-peer calls, and communicate through real-time text chat with image support.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start (Local Development)](#quick-start-local-development)
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

- **Servers** -- Create public or private servers with 8-character invite codes. Public servers appear on the homepage; private servers require an invite link.
- **Video Rooms** -- WebRTC peer-to-peer video/audio calls within servers. Rooms support optional password protection.
- **Real-Time Chat** -- Per-server text chat with image uploads, delivered over WebSockets. Message history (last 50 messages) is loaded on connect.
- **User Accounts** -- Registration, login, profile with avatar and bio, unified settings page with live camera/mic preview.
- **Device Management** -- Camera and microphone selection persisted per user via the browser MediaDevices API.
- **Admin Panel** -- Staff users (`is_staff=True`) can manage servers, rooms, and users from `/admin-panel/`.
- **Room Host Controls** -- The room creator can kick participants and force-mute their microphones.
- **Auto-Cleanup** -- Rooms empty for 15+ minutes are automatically deactivated.
- **Dark Theme** -- Modern responsive UI with Bootstrap 5.

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Backend | Django | 5.2 |
| WebSockets / ASGI | Django Channels + Daphne | 4.3 / 4.2 |
| Channel Layer | channels-redis | 4.3 |
| Database (dev) | SQLite | -- |
| Database (prod) | PostgreSQL | 16 |
| Message Broker | Redis | 7.x |
| Frontend | Bootstrap 5, vanilla JS | -- |
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
         [ Daphne ]     STUN Server
         (ASGI)       (stun.l.google.com:19302)
          /     \
     HTTP       WebSocket
    views       consumers
      |           |
   Django      Channels
   ORM         Redis
      \         /
     PostgreSQL
```

### Apps

| App | Responsibility |
|-----|---------------|
| `apps.accounts` | Custom `User` model (extends `AbstractUser` with `avatar` and `bio`). Views for registration, login, logout, profile, and account settings. |
| `apps.rooms` | Core application. Models: `Server`, `ServerMember`, `Room`, `RoomParticipant`, `ChatMessage`. WebSocket consumers: `RoomConsumer` (WebRTC signaling) and `ServerChatConsumer` (text chat). Admin panel views. |
| `apps.devices` | `Device` model storing browser media devices (camera/microphone). REST endpoint for device registration from the frontend. |

### Server / Room Hierarchy

- **Server** -- Has a name, owner, avatar, description, invite code, and public/private flag. Members join via invite link or by browsing public servers.
- **Room** -- Belongs to a server. Created by a member (the "host"). Supports optional password protection. Tracks `last_empty_at` for auto-cleanup.
- **ChatMessage** -- Text or image message scoped to a server. Delivered in real time via WebSocket and persisted to the database.

### Settings Structure

Settings are split across `config/settings/`:

| File | Purpose |
|------|---------|
| `base.py` | Shared configuration (installed apps, middleware, auth, templates, static/media paths) |
| `development.py` | `DEBUG=True`, SQLite, `ALLOWED_HOSTS=['*']` |
| `production.py` | `DEBUG=False`, external PostgreSQL (SSL required), external Redis, S3 media storage, WhiteNoise static files, full security headers |
| `allinone.py` | `DEBUG=False`, bundled PostgreSQL (localhost), bundled Redis, local media storage, WhiteNoise static files, relaxed security for self-hosting |

### WebRTC Signaling Flow

1. User opens a room. `webrtc.js` calls `navigator.mediaDevices.enumerateDevices()` and registers devices via `POST /devices/register/`.
2. A WebSocket connection opens to `ws://.../ws/rooms/<room-slug>/`.
3. `RoomConsumer.connect()` adds the user to the channel group, clears `last_empty_at`, and broadcasts `user_joined` with the user's channel name.
4. Existing peers receive `user_joined` and create an SDP offer, sent as an `offer` message targeting the new peer's channel.
5. The new peer responds with an `answer`. Both sides exchange `ice-candidate` messages.
6. Direct peer-to-peer media streams are established using STUN server `stun:stun.l.google.com:19302`.
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

### Manual Setup

If you prefer to set things up manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ensure Redis is running
redis-cli ping  # Should return PONG

# Run migrations
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py migrate

# Create a superuser (optional)
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py createsuperuser

# Start the server
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver 0.0.0.0:8000
```

**Note:** Django's built-in `runserver` does not support WebSockets. For full WebSocket functionality (video calls, real-time chat), use Daphne:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

## Docker Deployment

### All-in-One Container

A single container that bundles PostgreSQL 16 and Redis alongside the Django application. Best for self-hosting, demos, or development without installing external services.

**Using Docker Compose (recommended):**

```bash
docker compose -f allinone/docker-compose.yml up --build
```

**Using Docker directly:**

```bash
docker build -t chat-hub -f allinone/Dockerfile .
docker run -p 8000:8000 chat-hub
```

The all-in-one mode uses `config.settings.allinone` which stores media files locally (no S3 required) and connects to the bundled PostgreSQL and Redis on localhost.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_NAME` | `videocall` | PostgreSQL database name |
| `DB_USER` | `videocall` | PostgreSQL user |
| `DB_PASSWORD` | `videocall` | PostgreSQL password |
| `TEST_USER_PASSWORD` | *(empty)* | If set, creates `test1` and `test2` users with this password and a "Test Server" |
| `ALLOWED_HOSTS` | `localhost` | Comma-separated allowed hostnames |
| `SECRET_KEY` | *(auto-generated)* | Django secret key; auto-generated and persisted to `/app/mediafiles/.secret_key` if not provided |

The Compose file defines two persistent volumes: `media_files` (uploaded images) and `pg_data` (PostgreSQL data directory).

### Production (External Services)

For production, the application container connects to externally managed PostgreSQL, Redis, and S3-compatible storage.

**Using Docker Compose:**

Create a `.env` file in the project root with the required variables (see the table below), then:

```bash
docker compose up --build
```

**Using Docker directly:**

```bash
docker build -t chat-hub .
docker run -p 8000:8000 \
  -e ALLOWED_HOSTS=yourdomain.com \
  -e SECRET_KEY=your-secret-key \
  -e POSTGRES_HOST=your-db-host \
  -e POSTGRES_NAME=your-db-name \
  -e POSTGRES_USER=your-db-user \
  -e POSTGRES_PASS=your-db-password \
  -e REDIS_HOST=redis://your-redis-host:6379 \
  -e AWS_STORAGE_BUCKET_NAME=your-bucket \
  -e AWS_ACCESS_KEY_ID=your-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret \
  chat-hub
```

The entrypoint script automatically runs migrations, optionally seeds test users (`TEST_USER_PASSWORD`) and an admin user (`ADMIN_USER_PASSWORD`), then starts Daphne on port 8000.

**Example `.env`:**

```
SECRET_KEY=your-random-secret-key
ALLOWED_HOSTS=myapp.koyeb.app
POSTGRES_HOST=ep-xxx.pg.koyeb.app
POSTGRES_NAME=mydb
POSTGRES_USER=admin
POSTGRES_PASS=mypassword
REDIS_HOST=rediss://default:token@my-redis.upstash.io:6379
AWS_STORAGE_BUCKET_NAME=my-media-bucket
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your-secret-key
SECURE_SSL_REDIRECT=false
TEST_USER_PASSWORD=MyTestPass123.
ADMIN_USER_PASSWORD=AdminPass456.
```

## Environment Variables

### Production (`config.settings.production`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | No* | Auto-generated | Django secret key; auto-generated and persisted if not set |
| `ALLOWED_HOSTS` | **Yes** | -- | Comma-separated hostnames (e.g., `yourdomain.com,www.yourdomain.com`) |
| `POSTGRES_HOST` | Yes | -- | PostgreSQL host |
| `POSTGRES_NAME` | Yes | -- | PostgreSQL database name |
| `POSTGRES_USER` | Yes | -- | PostgreSQL user |
| `POSTGRES_PASS` | Yes | -- | PostgreSQL password |
| `REDIS_HOST` | Yes | -- | Full Redis URL (e.g., `redis://redis.example.com:6379`) |
| `AWS_STORAGE_BUCKET_NAME` | Yes | -- | S3 bucket name for media uploads |
| `AWS_ACCESS_KEY_ID` | Yes | -- | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | -- | S3 secret key |
| `AWS_S3_REGION_NAME` | No | `us-east-1` | S3 region |
| `AWS_S3_ENDPOINT_URL` | No | *(empty)* | Custom S3 endpoint (for MinIO, Cloudflare R2, Backblaze B2) |
| `AWS_S3_CUSTOM_DOMAIN` | No | *(empty)* | Custom domain for media URLs (e.g., a CDN domain) |
| `SECURE_SSL_REDIRECT` | No | `false` | Set to `true` to redirect HTTP to HTTPS |
| `CSRF_TRUSTED_ORIGINS` | No | *(empty)* | Comma-separated trusted origins for CSRF (e.g., `https://yourdomain.com`) |
| `TEST_USER_PASSWORD` | No | *(empty)* | If set, creates `test1`/`test2` users and a "Test Server" on startup |
| `ADMIN_USER_PASSWORD` | No | *(empty)* | If set, creates an `admin` user with `is_staff=True` on startup |

### All-in-One (`config.settings.allinone`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | No | Auto-generated | Django secret key |
| `ALLOWED_HOSTS` | No | `localhost` | Comma-separated allowed hostnames |
| `DB_NAME` | No | `videocall` | Bundled PostgreSQL database name |
| `DB_USER` | No | `videocall` | Bundled PostgreSQL user |
| `DB_PASSWORD` | No | `videocall` | Bundled PostgreSQL password |
| `SECURE_SSL_REDIRECT` | No | `false` | HTTP-to-HTTPS redirect |
| `TEST_USER_PASSWORD` | No | *(empty)* | Seed test users on startup |

## URL Reference

### Pages

| URL | Method | Description | Auth Required |
|-----|--------|-------------|---------------|
| `/` | GET | Server list (homepage); public servers visible to all | Yes |
| `/servers/create/` | GET, POST | Create a new server | Yes |
| `/servers/join/?code=XXXXXXXX` | GET | Join a server via invite code | Yes |
| `/servers/<uuid>/` | GET | Server detail page with room list and chat | Yes (member) |
| `/servers/<uuid>/settings/` | GET, POST | Server settings (owner only) | Yes (owner) |
| `/servers/<uuid>/leave/` | POST | Leave a server | Yes (member) |
| `/servers/<uuid>/delete/` | POST | Delete a server | Yes (owner) |
| `/servers/<uuid>/rooms/create/` | GET, POST | Create a room within a server | Yes (member) |
| `/servers/<uuid>/rooms/<uuid>/` | GET | Room detail -- video call interface | Yes (member) |
| `/servers/<uuid>/rooms/<uuid>/leave/` | POST | Leave a room | Yes |
| `/servers/<uuid>/rooms/<uuid>/delete/` | POST | Delete a room | Yes (host) |
| `/accounts/register/` | GET, POST | User registration | No |
| `/accounts/login/` | GET, POST | User login | No |
| `/accounts/logout/` | POST | User logout | Yes |
| `/accounts/profile/` | GET | View own profile | Yes |
| `/accounts/settings/` | GET, POST | Edit profile (avatar, bio, device preview) | Yes |
| `/devices/` | GET | List registered devices | Yes |
| `/devices/register/` | POST | Register browser media devices (JSON) | Yes |
| `/devices/<pk>/set-default/` | POST | Set a device as default | Yes |
| `/admin-panel/` | GET | Admin panel | Yes (staff) |
| `/admin/` | GET | Django admin interface | Yes (staff) |

### API Endpoints

| URL | Method | Payload | Description |
|-----|--------|---------|-------------|
| `/devices/register/` | POST | `{"devices": [{"deviceId": "...", "label": "...", "kind": "videoinput"}]}` | Register browser media devices |
| `/servers/<uuid>/chat/upload/` | POST | Multipart form with `image` file | Upload an image to server chat |
| `/servers/<uuid>/settings/kick/` | POST | `{"user_id": <int>}` | Kick a member from the server (owner only) |
| `/servers/<uuid>/settings/regenerate-invite/` | POST | -- | Regenerate the server invite code (owner only) |

## WebSocket Endpoints

### Room Consumer: `ws://<host>/ws/rooms/<room-slug>/`

Handles WebRTC signaling for video rooms.

**Messages sent by server:**

| Type | Fields | Description |
|------|--------|-------------|
| `my_channel` | `channel` | Sent on connect; the client's own channel name used as a target for signaling |
| `user_joined` | `username`, `channel`, `seq` | A user joined the room |
| `user_left` | `username`, `channel`, `seq` | A user left the room |
| `offer` | `payload`, `sender`, `username` | SDP offer forwarded from another peer |
| `answer` | `payload`, `sender`, `username` | SDP answer forwarded from another peer |
| `ice-candidate` | `payload`, `sender`, `username` | ICE candidate forwarded from another peer |
| `media_state` | `channel`, `mic`, `cam` | A peer's mic/camera on/off state changed |
| `kicked` | -- | You have been kicked by the host |
| `force_mute` | -- | The host force-muted your microphone |
| `room_closed` | -- | The room has been closed |

**Messages sent by client:**

| Type | Fields | Description |
|------|--------|-------------|
| `offer` | `target`, `payload` | Send SDP offer to a specific peer channel |
| `answer` | `target`, `payload` | Send SDP answer to a specific peer channel |
| `ice-candidate` | `target`, `payload` | Send ICE candidate to a specific peer channel |
| `device_update` | `cameraId`, `microphoneId` | Update selected device IDs for this participant |
| `media_state` | `mic`, `cam` | Broadcast mic/camera on/off state |
| `kick` | `target_channel`, `username` | Kick a participant (host only) |
| `mute_user` | `target_channel` | Force-mute a participant (host only) |

### Chat Consumer: `ws://<host>/ws/chat/<server-slug>/`

Handles real-time text chat per server.

**Messages sent by server:**

| Type | Fields | Description |
|------|--------|-------------|
| `history` | `messages` (array) | Sent on connect; last 50 messages with `id`, `username`, `avatar_url`, `content`, `image_url`, `created_at` |
| `chat_message` | `id`, `username`, `avatar_url`, `content`, `image_url`, `created_at` | A new chat message |

**Messages sent by client:**

| Type | Fields | Description |
|------|--------|-------------|
| `chat_message` | `content` | Send a text message (max 2000 characters) |
| `chat_image` | `message_id` | Notify the group about an uploaded image (upload via `/servers/<uuid>/chat/upload/` first) |

## Project Structure

```
chat-hub/
├── apps/
│   ├── accounts/            # Custom User model, auth views, forms
│   ├── devices/             # Device model, registration endpoint
│   └── rooms/               # Servers, rooms, chat, WebSocket consumers
│       ├── consumers.py     # RoomConsumer + ServerChatConsumer
│       ├── models.py        # Server, ServerMember, Room, RoomParticipant, ChatMessage
│       ├── routing.py       # WebSocket URL patterns
│       ├── views.py         # All server/room/admin views
│       └── management/
│           └── commands/
│               └── cleanup_empty_rooms.py
├── config/
│   ├── asgi.py              # ASGI entrypoint (HTTP + WebSocket routing)
│   ├── urls.py              # Root URL configuration
│   └── settings/
│       ├── base.py          # Shared settings
│       ├── development.py   # SQLite, DEBUG=True
│       ├── production.py    # External PostgreSQL + S3 + security headers
│       └── allinone.py      # Bundled PostgreSQL + Redis
├── static/
│   ├── css/main.css         # Dark theme styles
│   └── js/webrtc.js         # WebRTC + WebSocket client logic
├── templates/
│   ├── base.html            # Base template (Bootstrap 5)
│   ├── accounts/            # Login, register, profile, settings
│   ├── devices/             # Device list
│   └── rooms/               # Server list/detail, room list/detail/create, admin panel
├── allinone/
│   ├── Dockerfile           # All-in-one image (bundles PostgreSQL 16 + Redis)
│   ├── docker-compose.yml   # Compose for all-in-one
│   └── entrypoint.sh        # Starts PostgreSQL, Redis, then Daphne
├── Dockerfile               # Production image (external services)
├── docker-compose.yml       # Compose for production
├── entrypoint.sh            # Production entrypoint (migrations, seed data, Daphne)
├── deploy.sh                # Local development setup script
├── requirements.txt         # Python dependencies
└── manage.py
```

## Management Commands

```bash
# Clean up rooms that have been empty for 15+ minutes
python manage.py cleanup_empty_rooms

# Run the full test suite
python manage.py test

# Create a superuser
python manage.py createsuperuser
```

## Troubleshooting

**Redis connection refused**

The application requires Redis for WebSocket channel layers. Ensure Redis is running on `localhost:6379`:

```bash
redis-cli ping
# Expected: PONG
```

If Redis is not installed, `deploy.sh` will attempt to install it automatically on Debian/Ubuntu, macOS (Homebrew), Fedora, and Arch Linux.

**WebSocket connections fail on `runserver`**

Django's built-in `runserver` does not support WebSockets. Use Daphne instead:

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

The `deploy.sh` script uses `runserver` for convenience. For full WebSocket functionality locally, run Daphne directly.

**WebRTC calls fail (no video/audio)**

- Ensure you are accessing the site over HTTPS or `localhost`. Browsers block `getUserMedia()` on insecure origins.
- Check that the STUN server (`stun:stun.l.google.com:19302`) is reachable. Restrictive firewalls may block STUN/TURN traffic on UDP.
- If peers are behind symmetric NATs, a TURN server may be required (not bundled with this project).

**Static files not loading in production**

Ensure `collectstatic` has been run. The Docker images run this at build time. If deploying manually:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production python manage.py collectstatic --noinput
```

**Media uploads fail in production**

Verify that all `AWS_*` environment variables are set correctly and that the S3 bucket has appropriate permissions. In all-in-one mode, media is stored locally in `/app/mediafiles/` and served by Django directly.

**CSRF errors behind a reverse proxy**

Set `CSRF_TRUSTED_ORIGINS` to your domain (e.g., `https://yourdomain.com`). The production settings also automatically build CSRF trusted origins from `ALLOWED_HOSTS`.

## License

No license file is currently included in this repository.
