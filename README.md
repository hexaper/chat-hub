# Chat Hub

Real-time server/room communication app built with Django, Channels, Redis, and WebRTC.

## Stack

- Backend: Django 5.2, Channels, Daphne
- Realtime: Redis channel layer + cache/rate limiting
- Data: SQLite (dev), PostgreSQL (prod/all-in-one)
- Frontend: server-rendered templates + vanilla JS (no npm/build pipeline)
- Media path: WebRTC peer-to-peer (server is signaling only)

## Repository Tree

```text
chat-hub/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── manage.py
├── requirements.txt
├── deploy.sh
├── docker-compose.yml
├── allinone/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── entrypoint.sh
├── config/
│   ├── AGENTS.md
│   ├── asgi.py
│   ├── urls.py
│   └── settings/
├── apps/
│   ├── accounts/
│   │   └── AGENTS.md
│   ├── devices/
│   │   └── AGENTS.md
│   └── rooms/
│       └── AGENTS.md
├── templates/
│   └── AGENTS.md
├── static/
│   ├── AGENTS.md
│   └── js/webrtc.js
├── utils/
│   └── AGENTS.md
└── docs/
    ├── AGENTS.md
    ├── codebase/
    ├── ROADMAP.md
    └── superpowers/
        ├── specs/
        └── plans/
```

## Current Features

- Public/private servers with invite-based joins
- Room-based video/audio calls with WebRTC signaling
- Server and room chat over WebSockets with:
  - history pagination
  - message edit window (15 minutes)
  - soft delete (`deleted_at`)
  - typing indicators
  - image + video media messages (video types: mp4/webm/ogg, 25MB cap)
- Trust/core UX features:
  - server roles (`admin`/`member`, with server owner implicit)
  - moderation records (`ServerBan`, `ModerationAction`)
  - mute windows (`ServerMember.muted_until`)
  - mention persistence (`ChatMention`, `RoomChatMention`)
  - read-state tracking (`ChatReadState`, `RoomChatReadState`)
  - server chat search and unread summary endpoints
- Health endpoint: `GET /healthz/` (DB + Redis check)

## Recent Additions

- Performance updates from superpowers specs are now implemented:
  - composite indexes for chat history and active room lookup (`chat_server_created_idx`, `roomchat_room_created_idx`, `room_server_active_idx`)
  - PostgreSQL connection reuse in prod/all-in-one (`CONN_MAX_AGE=600`)
- Server chat now supports video upload + inline playback with `video_url` in websocket history/live payloads.
- Agent context routing was split into module-local `AGENTS.md` files (`config/`, `apps/*`, `templates/`, `static/`, `utils/`, `docs/`) to reduce navigation overhead.
- `docs/superpowers/` now includes current specs/plans for:
  - MVP-first scale-ready roadmap
  - performance/scale/video-chat updates
  - AGENTS.md context routing

## Quick Start (Local)

```bash
git clone https://github.com/hexaper/chat-hub.git
cd chat-hub
chmod +x deploy.sh
./deploy.sh
```

`deploy.sh` bootstraps venv/deps, Redis, migrations, and test users (`test1` / `test2`, password `Tester123.`).

## Running Locally

HTTP only:

```bash
source venv/bin/activate
python manage.py runserver --settings=config.settings.development
```

WebSockets/chat/video (required for realtime work):

```bash
source venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Optional local TLS/WebRTC testing:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development daphne -e ssl:8443:privateKey=ssl.key:certKey=ssl.crt config.asgi:application
```

## Testing

```bash
source venv/bin/activate
python manage.py test --settings=config.settings.development --keepdb
```

Focused examples:

```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_integration --settings=config.settings.development
python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development
```

Notes:
- Redis must be running for consumer/rate-limit coverage.
- Do not use `--parallel` (known Python 3.13 pickle issue in this repo).

## Deployment Paths

- `docker-compose.yml`: production-oriented path with external Postgres/Redis/S3 via `.env`.
- `allinone/docker-compose.yml`: self-contained path bundling PostgreSQL + Redis, served over self-signed HTTPS on `https://localhost:8000`.

## Important Constraints

- Keep dependencies lean; avoid new pip deps unless justified.
- Preserve `database_sync_to_async` for ORM work inside async consumers.
- Presence is currently in-process (`apps/rooms/consumers.py`), process-local, and not multi-instance-safe.
- Keep chat soft-delete and edit-window contracts unless intentionally changing behavior.

## Docs

- Agent/workflow guidance: `AGENTS.md`, `CLAUDE.md`
- Codebase maps: `docs/codebase/`
- Product status/direction: `docs/ROADMAP.md`
- Plan/spec history: `docs/superpowers/`
