# Codebase Structure

## Top Level

- `apps/accounts/`: custom user/auth forms and views.
- `apps/rooms/`: servers, rooms, chat models/views/consumers/routing.
- `apps/devices/`: device registration model + endpoint.
- `config/`: settings, URLs, ASGI/WSGI entrypoints.
- `templates/`: server-rendered HTML.
- `static/`: JS/CSS assets (notably `static/js/webrtc.js`).
- `utils/`: shared helpers (`ratelimit.py`, `turn.py`).
- `docs/`: roadmap, plans/specs, generated codebase docs.

## Entrypoints

- Management/dev: `manage.py`.
- ASGI runtime: `config/asgi.py`.
- HTTP routes: `config/urls.py`.
- WS routes: `apps/rooms/routing.py`.
- Container startup: `entrypoint.sh`, `allinone/entrypoint.sh`.

## Module Boundaries

- Keep account identity/auth in `apps/accounts`.
- Keep room/server/chat domain logic in `apps/rooms`.
- Keep cross-cutting reusable helpers in `utils`.
- Keep browser behavior in templates/static, not models.
