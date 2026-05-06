# AGENTS.md

Use this file for repo-wide rules only. When working inside a subdirectory, load the closest `AGENTS.md` first.

## Repo Snapshot

- Stack: Django 5.2, Channels, Daphne, Redis, PostgreSQL/SQLite, server-rendered templates, vanilla JS.
- HTTP entrypoint: `config/urls.py`.
- ASGI entrypoint: `config/asgi.py`.
- WebSocket routes: `apps/rooms/routing.py`.
- WebRTC signaling lives in `static/js/webrtc.js`; chat client behavior stays inline in `templates/rooms/*.html`.

## Fast Commands

```bash
source venv/bin/activate
python manage.py runserver --settings=config.settings.development
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
python manage.py test --settings=config.settings.development --keepdb
python manage.py check --settings=config.settings.development
```

## Global Rules

- Use Django's test runner, not pytest, and never use `--parallel` here.
- Redis is required for WebSockets, rate limits, and `/healthz/`.
- Use `database_sync_to_async` for ORM work in async consumers.
- Preserve websocket sender self-exclusion and chat soft-delete/edit-window behavior unless the task explicitly changes them.
- Keep dependencies lean and do not add a frontend build step.
- Trust code/config over prose if they disagree.
- Do not use git-worktrees from superpowers.

## Token Efficiency

- Return only important, decision-relevant information.
- Prefer links and file paths over repeated prose.
- Load only the context needed for the current task.

## Tool and Read Optimization

- Minimize tool calls while preserving correctness.
- Prefer targeted reads/searches over broad scans.
- Batch independent reads when useful; avoid duplicate exploration.

## AGENTS.md Maintenance

- Keep AGENTS files concise, accurate, and scoped.
- Update the nearest relevant `AGENTS.md` when behavior, commands, constraints, or ownership changes.
- Remove stale instructions promptly.

## Scope Precedence

- Nearest `AGENTS.md` wins over broader guidance.
- Direct user instructions and code truth override AGENTS prose.

## Module Map

- `config/AGENTS.md`: settings, URLs, ASGI/WSGI, runtime entrypoints.
- `apps/accounts/AGENTS.md`: auth models, forms, views, URLs, tests.
- `apps/rooms/AGENTS.md`: chat/server/room models, views, consumers, routing, tests.
- `apps/devices/AGENTS.md`: device registration app.
- `templates/AGENTS.md`: server-rendered UI and inline page scripts.
- `static/AGENTS.md`: shared browser assets, especially `js/webrtc.js`.
- `utils/AGENTS.md`: shared helpers.
- `docs/AGENTS.md`: roadmap, codebase docs, specs, plans.
- `allinone/AGENTS.md`: bundled local self-host deployment path.
