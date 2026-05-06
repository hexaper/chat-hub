# AGENTS.md

**Stack**
- Django 5.2 + Channels + Daphne + Redis. There is no npm/build step; frontend behavior is server-rendered templates plus vanilla JS.
- HTTP entrypoint: `config/urls.py`. ASGI entrypoint: `config/asgi.py`. WebSocket routes: `apps/rooms/routing.py`.
- Non-obvious split: `static/js/webrtc.js` handles room WebRTC/signaling only. Server chat and room chat client logic lives inline in `templates/rooms/server_detail.html` and `templates/rooms/room_detail.html`.

**Local Run**
- `manage.py` defaults to `config.settings.development`.
- `config/asgi.py` defaults to `config.settings.production`; for any local Daphne run, set `DJANGO_SETTINGS_MODULE=config.settings.development` first.
- `python manage.py runserver --settings=config.settings.development` is HTTP-only. Any chat/video/WebSocket work must be verified with Daphne:
```bash
source venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```
- For local HTTPS/WebRTC testing, use:
```bash
DJANGO_SETTINGS_MODULE=config.settings.development daphne -e ssl:8443:privateKey=ssl.key:certKey=ssl.crt config.asgi:application
```
- `./deploy.sh` bootstraps `venv`, Redis, migrations, and seeds `test1` / `test2` with password `Tester123.`, but it finishes on `runserver`, so it does not exercise WebSockets.

**Services And Deploy**
- Redis is required for WebSockets, rate limiting, and `/healthz/`. Channel layer uses Redis DB 0; cache/rate limits use DB 1.
- `docker-compose.yml` is the production/external-services path: it expects `.env` plus external Postgres, Redis, and S3.
- `allinone/docker-compose.yml` bundles PostgreSQL 16 + Redis and serves HTTPS with a self-signed cert on `https://localhost:8000`.

**Tests And Verification**
- Use Django's test runner, not pytest.
- Full suite:
```bash
source venv/bin/activate
python manage.py test --settings=config.settings.development --keepdb
```
- Focused runs:
```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_server_chat_accepts_member_and_sends_history --settings=config.settings.development
```
- Do not use `--parallel`; this repo hits a Python 3.13 pickle error.
- There is no repo lint/typecheck/pre-commit config to mirror; practical verification is focused Django tests plus manual WebSocket/UI checks for the path you changed.
- Consumer tests need Redis and use `TransactionTestCase`; existing tests often call `transaction.commit()` before `WebsocketCommunicator.connect()` so setup data is visible to the consumer thread.

**Repo-Specific Constraints**
- Keep dependencies lean: no new pip dependencies unless there is a strong, verified need.
- Optimize assistant output for low token usage: use short, informative sentences; report only key actions/results instead of step-by-step narration.
- When touching Channels code, use `database_sync_to_async` for ORM work. `sync_to_async` is for non-ORM sync helpers like `is_rate_limited()`.
- Presence is an in-process `_presence` dict in `apps/rooms/consumers.py`; it resets on restart and only powers server chat online state.
- Chat messages are soft-deleted via `deleted_at` and editable for 15 minutes; preserve that DB/WebSocket contract when changing chat behavior.
- Static files are served by `staticfiles_urlpatterns()` in development and WhiteNoise manifest storage in non-debug modes. Do not add `ASGIStaticFilesHandler`; it breaks hashed static files in production/all-in-one.
- Trust code/config over prose if they disagree; migrations currently go through `0013` in `apps/rooms/migrations/`.
- Do not use git-worktrees from superpowers.
