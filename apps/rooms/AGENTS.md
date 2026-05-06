# AGENTS.md

Scope: `apps/rooms/` owns servers, rooms, chat, moderation, realtime consumers, routing, forms, permissions, management commands, and the largest test surface in the repo.

## Key Files

- `models.py`: memberships, chat, moderation, mentions, read state.
- `views.py`: server/room pages and JSON endpoints.
- `consumers.py`: realtime room and server chat consumers.
- `routing.py`: websocket routes.
- `permissions.py`: access-control helpers.
- `tests/test_consumers.py`, `tests/test_views_extended.py`, `tests/test_permissions.py`, `tests/test_ratelimit.py`: focused regression coverage.

## Rules

- Use `database_sync_to_async` for ORM work in async consumers and `sync_to_async` only for non-ORM helpers.
- Preserve sender self-exclusion in websocket broadcasts.
- Preserve soft-delete and the 15-minute edit window unless the task explicitly changes that contract.
- Presence is process-local and resets on restart; do not treat it as multi-instance safe unless the task redesigns it.
- Treat `consumers.py` and `views.py` as high-churn files; keep diffs small and verify carefully.

## Verify

- Run focused room tests first, then broaden only if needed.
- Keep Redis running for consumer or rate-limit coverage.
- Use Daphne, not just `runserver`, for websocket/chat/video verification.
- Do not use `--parallel`.
