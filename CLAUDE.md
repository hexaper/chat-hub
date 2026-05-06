# CLAUDE.md

Agent-facing operating notes for this repository. Keep responses concise and favor code truth over docs when they conflict.

## What This Repo Is

- Django 5.2 + Channels + Daphne + Redis real-time chat/video app (Discord-like server + room model).
- No npm/build step; frontend is server-rendered templates plus vanilla JS.
- HTTP routes: `config/urls.py`; ASGI app: `config/asgi.py`; websocket routes: `apps/rooms/routing.py`.
- WebRTC media is peer-to-peer; server handles signaling only (`static/js/webrtc.js`).

## Fast Commands

```bash
source venv/bin/activate
python manage.py runserver --settings=config.settings.development
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
python manage.py test --settings=config.settings.development --keepdb
```

Notes:
- `manage.py` defaults to `config.settings.development`.
- `config/asgi.py` defaults to `config.settings.production`; set `DJANGO_SETTINGS_MODULE=config.settings.development` locally when using Daphne.
- Do not use `--parallel` for tests in this repo (Python 3.13 pickle issue).

## Current Product Reality (Implemented)

- Server and room chat with history paging, edit window (15 min), soft delete via `deleted_at`, typing indicators.
- Server trust/core UX primitives are live:
  - `ServerMember.role` (`owner` by ownership, plus `admin` and `member`) and `muted_until`.
  - Moderation models: `ServerBan`, `ModerationAction`.
  - Mention models: `ChatMention`, `RoomChatMention`.
  - Read-state models: `ChatReadState`, `RoomChatReadState`.
  - View endpoints: role change, ban/mute, mark-read, search, unread summary.
  - Consumer enforcement: ban blocks connect, mute blocks message send; mention metadata in payloads.
  - UI hooks: server search input/unread badge; mention highlight in server and room chat templates.

## Real-Time Constraints

- Use `database_sync_to_async` for ORM in async consumers.
- Use `sync_to_async` only for non-ORM sync helpers (for example rate-limit helper wrappers).
- Preserve websocket sender self-exclusion contract (`exclude` channel pattern).
- Presence is still in-process in `apps/rooms/consumers.py` (`_presence`), not Redis-backed yet.
  - Locking now uses per-event-loop locks via `_get_presence_lock()` and `WeakKeyDictionary` to avoid cross-loop lock binding failures.
  - Presence remains process-local and resets on restart.

## Deploy/Infra Notes

- Redis is required for channel layer, cache/rate limits, and `/healthz/`.
  - Channel layer uses Redis DB 0.
  - Cache/rate-limit usage uses Redis DB 1.
- `docker-compose.yml`: production/external services path (expects external Postgres/Redis/S3 and `.env`).
- `allinone/docker-compose.yml`: bundled PostgreSQL + Redis + self-signed TLS for local self-host mode.

## Testing Expectations

- Use Django test runner, not pytest.
- Consumer tests require Redis and `TransactionTestCase` semantics.
- Recommended focused runs:

```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_integration --settings=config.settings.development
python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development
python manage.py test apps.rooms.tests.test_permissions --settings=config.settings.development
```

## Documentation Map

- Generated codebase docs: `docs/codebase/STACK.md`, `docs/codebase/STRUCTURE.md`, `docs/codebase/ARCHITECTURE.md`, `docs/codebase/CONVENTIONS.md`, `docs/codebase/INTEGRATIONS.md`, `docs/codebase/TESTING.md`, `docs/codebase/CONCERNS.md`.
- Product direction and status: `docs/ROADMAP.md`.
- Superpowers plans/specs: `docs/superpowers/plans/`, `docs/superpowers/specs/`.

## Practical Guardrails

- Keep dependencies lean; do not add packages without clear need.
- Do not add frontend build tooling.
- Preserve soft-delete/edit-window semantics unless task explicitly changes them.
- Treat `apps/rooms/consumers.py` and `apps/rooms/views.py` as high-churn/high-risk files; pair changes with focused tests.
- Migrations currently include `apps/rooms/migrations/0013_servermember_muted_until_servermember_role_and_more.py`.
