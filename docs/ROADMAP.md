# Roadmap

This file tracks product direction at a high signal-to-noise ratio. Code is the source of truth for implemented behavior.

## Current Reality

- Core chat/video stack is implemented (Django + Channels + WebRTC signaling).
- Trust/Core UX Phase 1 is implemented in `apps/rooms`:
  - server roles (`admin`/`member`, owner authority), mute windows
  - moderation records (`ServerBan`, `ModerationAction`)
  - mention and read-state persistence
  - server chat search, mark-read, unread-summary endpoints
  - consumer-level ban/mute enforcement and mention payload support
- Presence remains in-process and process-local (not multi-instance-safe yet).

## Next Priority (Phase 2)

1. Move presence to Redis-backed ephemeral storage.
2. Add reconnect catch-up (`after_id`/cursor based) for chat consumers.
3. Refine websocket rate-limit feedback (event-specific user feedback).

## Later Priority (Phase 3)

1. Direct messages and friend graph.
2. Privacy/abuse boundaries for private messaging.
3. Group DMs after 1:1 reliability is solid.

## Guardrails

- Keep stack direction: Django + Channels + Redis + PostgreSQL/SQLite.
- Avoid new dependencies unless necessary.
- Preserve chat contract: soft delete + 15-minute edit window.
- Keep WebRTC media peer-to-peer until measured evidence requires SFU.
