# Chat Hub

A video conferencing and community platform built with Django, Django Channels, and WebRTC. Create servers, invite members, chat in real time, and video call directly in the browser.

## Features

- **Servers** — Create public or private servers with invite codes, avatars, and member management
- **Rooms** — Video/audio rooms inside servers with WebRTC P2P connections
- **Real-time chat** — Persistent text chat per server via WebSockets
- **Video calls** — Camera/mic selection, mute, disable camera, voice activity detection, password-protected rooms
- **User accounts** — Registration, login, avatars, bio, unified settings page with live camera/mic preview
- **Auto-cleanup** — Empty rooms are automatically deleted after 15 minutes
- **Dark theme** — Modern responsive UI with Bootstrap 5

## Tech Stack

- **Backend:** Django 5.2, Django Channels 4.3, Daphne (ASGI)
- **Database:** PostgreSQL (production), SQLite (local dev)
- **Real-time:** Redis (WebSocket channel layer)
- **Frontend:** Bootstrap 5, Inter font, vanilla JS, WebRTC API
- **Static files:** WhiteNoise (production)

---

## Deployment Options

### 1. Local Development

Uses SQLite and Django's built-in server. Requires Python 3 and Redis.

```bash
chmod +x deploy.sh && ./deploy.sh
```

This will create a virtualenv, install dependencies, start Redis, run migrations, create test users, and start the server at `http://localhost:8000`.

Default test users: `test1` / `test2` (password: `Heksaper12.`)

### 2. Docker — External Services (Production)

Lightweight image. PostgreSQL and Redis must be provided externally (Koyeb, Neon, Upstash, etc.).

```bash
docker compose up --build
```

Requires a `.env` file or environment variables:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key |
| `ALLOWED_HOSTS` | Yes | Comma-separated hostnames, or `*` |
| `POSTGRES_HOST` | Yes | PostgreSQL hostname |
| `POSTGRES_NAME` | Yes | Database name |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASS` | Yes | Database password |
| `REDIS_HOST` | Yes | Redis URL (e.g. `rediss://default:token@host:6379`) |
| `AWS_STORAGE_BUCKET_NAME` | Yes | S3 bucket name for media uploads (avatars) |
| `AWS_ACCESS_KEY_ID` | Yes | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | S3 secret key |
| `AWS_S3_REGION_NAME` | No | S3 region (default: `us-east-1`) |
| `AWS_S3_ENDPOINT_URL` | No | Custom S3 endpoint (for Cloudflare R2, MinIO, etc.) |
| `AWS_S3_CUSTOM_DOMAIN` | No | Custom domain for serving media |
| `SECURE_SSL_REDIRECT` | No | `true` or `false` (default: `false`) |
| `TEST_USER_PASSWORD` | No | If set, creates test1/test2 users with this password |
| `CSRF_TRUSTED_ORIGINS` | No | Comma-separated origins (e.g. `https://myapp.koyeb.app`) |

Example `.env`:

```
SECRET_KEY=your-random-secret-key
ALLOWED_HOSTS=*
POSTGRES_HOST=ep-xxx.pg.koyeb.app
POSTGRES_NAME=mydb
POSTGRES_USER=admin
POSTGRES_PASS=mypassword
REDIS_HOST=rediss://default:token@my-redis.upstash.io:6379
AWS_STORAGE_BUCKET_NAME=my-avatars
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your-secret-key
SECURE_SSL_REDIRECT=false
TEST_USER_PASSWORD=MyTestPass123.
```

### 3. Docker — All-in-One (Self-hosted)

Single container with PostgreSQL 16 and Redis bundled inside. No external services needed. Good for self-hosting or quick demos.

```bash
cd allinone
docker compose up --build
```

Data persists in Docker volumes (`pg_data` for the database, `media_files` for uploads).

Optional environment variables:

| Variable | Default | Description |
|---|---|---|
| `DB_NAME` | `videocall` | PostgreSQL database name |
| `DB_USER` | `videocall` | PostgreSQL user |
| `DB_PASSWORD` | `videocall` | PostgreSQL password |
| `TEST_USER_PASSWORD` | — | If set, creates test1/test2 users |

---

## Project Structure

```
apps/
  accounts/     Custom User model, auth views, settings page
  rooms/        Server, Room, ChatMessage models, WebSocket consumers
  devices/      Device model, browser media device registration
config/
  settings/
    base.py          Shared settings
    development.py   SQLite, DEBUG=True
    production.py    PostgreSQL, Redis, WhiteNoise (reads env vars)
    allinone.py      Bundled PG + Redis with localhost defaults
  asgi.py       ASGI application with Channels routing
  urls.py       URL configuration
allinone/       Dockerfile, entrypoint, compose for all-in-one setup
static/
  js/webrtc.js  WebRTC + WebSocket client logic
  css/main.css  Dark theme styles
templates/      Django templates (Bootstrap 5, crispy-forms)
```

## WebRTC Signal Flow

```
User opens room
  -> enumerateDevices() -> reads preferences from localStorage
  -> WebSocket connects to ws://.../ws/rooms/<slug>/
  -> Server broadcasts user_joined to room group
  -> Existing peers create SDP offer -> send via WebSocket
  -> New peer receives offer -> sends answer
  -> Both exchange ICE candidates
  -> P2P connection established (STUN: stun.l.google.com:19302)
```

## URL Structure

```
/                                    Server list (home)
/servers/create/                     Create server
/servers/join/?code=XXXXXXXX         Join via invite code
/servers/<uuid>/                     Server detail (rooms + chat)
/servers/<uuid>/settings/            Server settings (owner only)
/servers/<uuid>/rooms/create/        Create room
/servers/<uuid>/rooms/<uuid>/        Video room
/accounts/login/                     Login
/accounts/register/                  Register
/accounts/settings/                  User settings (profile + devices)
```

## License

MIT
