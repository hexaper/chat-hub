# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A WebRTC video conferencing application built with Django and Django Channels. Users can create/join video rooms, with real-time signaling handled over WebSockets and P2P video via WebRTC.

## Development Setup & Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start development server (use Daphne for WebSocket support)
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application

# Or with Django's built-in server (no WebSocket support)
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver

# Create a superuser
python manage.py createsuperuser

# Run tests
python manage.py test

# Run a single test
python manage.py test apps.rooms.tests.TestRoomConsumer
```

**External dependency:** Redis must be running on `localhost:6379` for WebSocket channel layers.

## Architecture

### Settings
Split into `config/settings/base.py`, `development.py`, and `production.py`. Development uses SQLite; production uses PostgreSQL with env vars (`SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `ALLOWED_HOSTS`).

### Apps (`apps/`)
- **accounts** — Custom `User` model extending `AbstractUser` with `avatar` and `bio`. Standard auth views (register, login, logout, profile).
- **rooms** — `Room` (UUID slug, host FK, is_active) and `RoomParticipant` (through model tracking joined_at, selected camera/mic device IDs). `RoomConsumer` (AsyncWebsocketConsumer) handles WebRTC signaling messages: `offer`, `answer`, `ice-candidate`, `user_joined`, `user_left`, `device_update`.
- **devices** — `Device` model stores browser MediaDevices API entries (device_id, label, device_type, is_default). REST-ish endpoint at `/devices/register/` accepts JSON POST from the frontend.

### WebRTC Signal Flow
1. User opens room → `webrtc.js` calls `enumerateDevices()`, registers devices via `/devices/register/`
2. `connectWebSocket()` opens `ws://.../ws/rooms/<slug>/`
3. `RoomConsumer.connect()` adds user to channel group, broadcasts `user_joined`
4. Existing peers receive `user_joined` → call `createOffer()` → send `offer` message
5. New peer handles `offer` → sends `answer` → both exchange `ice-candidate` messages
6. STUN server: `stun:stun.l.google.com:19302`

### URL Structure
- `/` and `/rooms/` → room list
- `/rooms/create/` → create room
- `/rooms/<uuid:slug>/` → room detail (enter room)
- `/rooms/<uuid:slug>/leave/` → leave room
- `/accounts/{register,login,logout,profile}/`
- `/devices/`, `/devices/register/`, `/devices/<pk>/set-default/`
- `ws://…/ws/rooms/<slug>/` → RoomConsumer

### Frontend
- `static/js/webrtc.js` — all WebRTC and WebSocket logic
- `static/css/main.css` — minimal video element styles
- Templates use Bootstrap 5 via `base.html`; forms rendered with `django-crispy-forms` + `crispy-bootstrap5`

### Auth Settings
- `AUTH_USER_MODEL = 'accounts.User'`
- `LOGIN_URL = /accounts/login/`
- `LOGIN_REDIRECT_URL = /rooms/`
- `LOGOUT_REDIRECT_URL = /accounts/login/`
