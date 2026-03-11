# Chat Hub - WebRTC Video Conferencing

A peer-to-peer video conferencing app built with Django, Django Channels, and WebRTC. Create rooms, invite users, and video chat directly in the browser.

## Features

- Create and join video rooms with unique links
- Real-time P2P video/audio via WebRTC
- Camera and microphone selection
- Mute mic / disable camera during calls
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

Open http://localhost:8000. Two test users are created automatically (temporary solution): `test1` / `test2` (password: `Testing123.`).

PostgreSQL and Redis are bundled inside the container. No external services needed.


### Local Development

```bash
chmod +x deploy.sh && ./deploy.sh
```


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

## License

MIT
