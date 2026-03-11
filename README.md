# Chat Hub - WebRTC Video Conferencing

A peer-to-peer video conferencing app built with Django, Django Channels, and WebRTC. Create rooms, invite users, and video chat directly in the browser.

## Features

- Create and join video rooms with unique links
- Real-time P2P video/audio via WebRTC
- Camera and microphone selection
- Mute mic / disable camera during calls
- Host controls: mute or kick participants, delete room
- Password-protected rooms
- User accounts with avatar and bio
- Voice activity detection (speaking indicator)

## Tech Stack

- **Backend:** Django 5.2, Django Channels 4.3, Daphne (ASGI)
- **Database:** PostgreSQL 16 (production), SQLite (development)
- **Real-time:** Redis 7 (WebSocket channel layer)
- **Frontend:** Bootstrap 5, vanilla JS, WebRTC API
- **Static files:** WhiteNoise

## Quick Start

### Docker (recommended)

```bash
git clone <repo-url> && cd chat-hub
docker compose up --build
```

Open http://localhost:8000. Two test users are created automatically: `test1` / `test2` (password: `Heksaper12.`).

### Single Container (for cloud hosting)

```bash
docker build -t chat-hub .
docker run -p 8000:8000 chat-hub
```

PostgreSQL and Redis are bundled inside the container. No external services needed.

### Bare-Metal Production

```bash
sudo ./deploy.sh
```

### Local Development

Requires Redis running on `localhost:6379`.

```bash
./start.sh
```



Installs PostgreSQL, Redis, Nginx (reverse proxy with WebSocket support), and creates a systemd service running Daphne. Tested on Ubuntu 22.04/24.04 and Debian 12.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | auto-generated | Django secret key. Generated and persisted on first run if not set |
| `DB_HOST` | `localhost` | PostgreSQL host. `localhost` = use bundled PG |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `videocall` | Database name |
| `DB_USER` | `videocall` | Database user |
| `DB_PASSWORD` | `videocall` | Database password |
| `REDIS_HOST` | `localhost` | Redis host. `localhost` = use bundled Redis |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `SECURE_SSL_REDIRECT` | `false` | Set `true` if not behind a TLS-terminating proxy |
| `CSRF_TRUSTED_ORIGINS` | derived from `ALLOWED_HOSTS` | Additional CSRF trusted origins |

## Project Structure

```
apps/
  accounts/     Custom User model, auth views (register, login, profile)
  rooms/        Room model, RoomParticipant, WebSocket consumer (signaling)
  devices/      Device model, browser media device registration endpoint
config/
  settings/     base.py, development.py, production.py
  asgi.py       ASGI application with Channels routing
  urls.py       URL configuration
static/
  js/webrtc.js  WebRTC + WebSocket client logic
  css/main.css  Video grid styles
templates/      Django templates (Bootstrap 5, crispy-forms)
```

## WebRTC Signal Flow

```
User opens room
  -> enumerateDevices() -> POST /devices/register/
  -> WebSocket connects to ws://.../ws/rooms/<slug>/
  -> Server broadcasts user_joined to room group
  -> Existing peers create SDP offer -> send via WebSocket
  -> New peer receives offer -> sends answer
  -> Both exchange ICE candidates
  -> P2P connection established (STUN: stun.l.google.com:19302)
```

## URL Routes

| Path | Description |
|---|---|
| `/` | Room list |
| `/rooms/create/` | Create a room |
| `/rooms/<uuid>/` | Join / enter room |
| `/accounts/register/` | Register |
| `/accounts/login/` | Login |
| `/devices/register/` | Register browser media device (JSON POST) |
| `ws://.../ws/rooms/<uuid>/` | WebSocket signaling |

## License

MIT
