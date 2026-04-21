---
name: security_coverage
description: Security vectors tested vs. still missing coverage, per feature area
type: project
---

## ServerChatConsumer — COVERED
- Unauthenticated connection rejected (close, no accept).
- Non-member authenticated user rejected.
- `chat_image` — returns image only to the message owner; other members get nothing (IDOR).
- `edit_message` — rejects wrong owner (IDOR/authorization).
- `edit_message` — rejects expired edit window (>15 min).
- `edit_message` — rejects soft-deleted messages.
- `delete_message` — rejects wrong owner (IDOR/authorization).
- `delete_message` — idempotent on already-deleted (no double broadcast).
- History: deleted message content/image_url redacted.

## ServerChatConsumer — NOT YET COVERED
- `edit_message` with empty or whitespace-only `content` — the consumer returns early (line 85: `not new_content`), no broadcast. No explicit test.
- `edit_message` with `message_id` belonging to a different server (cross-server IDOR) — the `server_id=self.server_id` filter in `do_edit_message` prevents this, but no test exercises it.
- `delete_message` with `message_id` from a different server — same filter protection, no test.
- Rate limiting on chat_message (Phase 1.2 — deferred).

## RoomConsumer — COVERED
- Unauthenticated connection rejected.
- Non-member: no explicit test (RoomConsumer does not check membership — it checks server membership only via the URL room slug lookup implicitly via group name; this may be a security gap).
- Host-only `kick` — non-host kick silently ignored.
- Host-only `mute_user` — non-host mute silently ignored.

## RoomConsumer — POTENTIAL GAP
- `RoomConsumer.connect()` does NOT check server membership — it only checks `is_authenticated`. Any authenticated user who knows a room slug can connect. This appears to be an intentional design choice (rooms are in servers, but the consumer doesn't verify the connecting user is a server member). This should be confirmed or a test added if membership enforcement is desired.

## Accounts — COVERED (in apps/accounts/tests/)
- Registration/login form validation, auth boundaries on profile/settings views.

## Devices — COVERED (in apps/devices/tests/)
- Auth boundaries on device registration endpoint.

## RoomChatConsumer — COVERED (added 2026-03-16, RoomChatConsumerTests class)
- `edit_message` — author can edit own message within 15-minute window; both sockets receive broadcast.
- `edit_message` — edit past the 15-minute window silently dropped, DB unchanged.
- `edit_message` — wrong owner (IDOR/authorization): silently ignored, DB unchanged.
- `delete_message` — author can soft-delete own message; both sockets receive broadcast, deleted_at set.
- `delete_message` — wrong owner (IDOR/authorization): silently ignored, deleted_at stays NULL.
- `typing` — sender excluded from their own user_typing broadcast (exclude filter verified).
- History includes `updated_at` and `deleted_at` keys on every message entry.
- History: deleted message content redacted to empty string.

## RoomChatConsumer — NOT YET COVERED
- Unauthenticated connection rejected (no test added — analogous to ServerChatConsumer, low risk, deferred).
- Non-participant authenticated user rejected (is_participant check — no test).
- `edit_message` with empty/whitespace `content` — consumer returns early, no broadcast. No explicit test.
- `edit_message` on already-deleted message — consumer rejects (deleted_at__isnull=True filter). No test.
- Cross-room IDOR: `message_id` belonging to a different room — `room_id=self.room_id` filter prevents it, no test.
- Rate limiting on room chat_message (Phase 1.2 — deferred).

## Image Upload (HTTP, rooms/views.py)
- Rate limiting: 10/m per user (Phase 1.2, not yet implemented/tested).
