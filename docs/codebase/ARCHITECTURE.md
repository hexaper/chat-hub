# Architecture

## Runtime Shape

- HTTP: Django views/templates from `config/urls.py`.
- WebSocket: Channels consumers from `config/asgi.py` -> `apps/rooms/routing.py`.
- Realtime fanout: Redis channel layer.
- Media: peer-to-peer WebRTC; server relays signaling only.

## Main Flows

- Browser HTTP -> Django view -> ORM/cache -> HTML or JSON.
- Browser WS -> consumer -> ORM + channel layer group_send -> WS events.
- Room media: browser fetches ICE config -> peers exchange SDP/ICE via `RoomConsumer` -> direct media path.

## Key Modules

- `apps/rooms/views.py`: server/room pages and JSON endpoints (moderation, search, read/unread, uploads).
- `apps/rooms/consumers.py`: `RoomConsumer`, `ServerChatConsumer`, `RoomChatConsumer`.
- `apps/rooms/models.py`: membership, chat, moderation, mention, and read-state persistence.

## Current Constraints

- Presence is process-local in `apps/rooms/consumers.py` (not yet Redis-backed).
- Presence lock handling uses per-event-loop locks to avoid cross-loop runtime lock errors.
- Soft-delete and edit-window semantics are part of WS + DB contract and should stay compatible.
