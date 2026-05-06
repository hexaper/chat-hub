# MVP-First, Scale-Ready Roadmap — Design Spec

**Date:** 2026-04-20  
**Goal:** Ship the fastest stable MVP for real communities while keeping architecture ready for scale.

## Context

Chat Hub already has strong real-time foundations: server and room chat, WebRTC rooms, edit/delete, typing, pagination, media upload, rate limiting, and health checks. The largest remaining gap is product trust and usability at community scale: moderation controls, message navigation ergonomics, and multi-instance correctness for presence/reconnect behavior.

This roadmap prioritizes user-facing stability and retention first, then expands social surface area.

## Product Strategy

Recommended strategy: **Trust + Core UX + Scale Guardrails**.

- Ship features that make public/private communities safe and usable now.
- Add only high-ROI scale primitives required to avoid rework.
- Defer larger social expansion (DM ecosystem) until core server experience is reliable.

## Phase 1 — Trust And Core UX (Now)

### Scope

1. **Roles and permissions (minimum viable model)**
   - Roles: owner, admin, member.
   - Permissions: moderate chat, kick/ban members, room control actions.
   - Enforce at view and consumer boundaries.

2. **Moderation actions with audit trail**
   - Actions: ban, mute (chat-level), remove from server, message moderation hooks.
   - Persist immutable moderation events for admin accountability.

3. **Mentions and unread state**
   - `@username` mention detection in server/room chat.
   - Unread counters by server and room.
   - Read marker updates on active view and reconnect.

4. **Basic message search**
   - Filter by text and username in server/room chat.
   - Fast path focused on recent history first.

### Success Criteria

- Server owners/admins can reliably enforce community rules without manual DB actions.
- Users can re-open the app and quickly identify what changed (mentions/unreads).
- Search is good enough for recent context retrieval in active communities.

### Not In Scope

- Fine-grained role matrix and custom roles.
- Full-text search infrastructure changes or new external services.

## Phase 2 — Reliability And Scale Correctness (Next)

### Scope

1. **Redis-backed ephemeral presence**
   - Replace in-process `_presence` dependency with Redis-backed transient membership keys.
   - Preserve current semantics (online while connected; no durable `last_seen`).

2. **WebSocket reconnect gap-fill**
   - Add cursor/last-seen ID based catch-up flow.
   - Ensure clients recover missed messages after temporary disconnect.

3. **Rate-limit behavior refinement**
   - Keep Redis-based limits; tune limits by event type.
   - Add clearer client feedback where actions are intentionally dropped.

### Success Criteria

- Presence remains correct across multi-process/multi-instance deployments.
- Short network interruptions do not create silent chat gaps.
- Abuse protection remains effective without degrading normal use.

### Not In Scope

- New queue systems or stream processing infrastructure.
- Durable presence timelines.

## Phase 3 — Social Expansion (After Core Is Stable)

### Scope

1. **Direct messages (1:1)** with baseline moderation/reporting hooks.
2. **Friends graph** and private-presence visibility rules.
3. **Group DMs** only after 1:1 DM reliability is verified.

### Success Criteria

- Private messaging works with the same reliability expectations as server chat.
- Privacy and abuse boundaries are explicit and enforceable.

### Not In Scope

- Advanced social feeds or recommendation systems.

## Cross-Phase Scale Guardrails

- Enforce room-size policy and degraded-mode UX for large WebRTC mesh rooms.
- Default TURN in production environments.
- Track operational metrics: WS connect failures, consumer exceptions, fanout latency, reconnect success rate, TURN relay ratio, room-size distribution.

## Architecture Notes

- Keep current stack constraints: Django + Channels + Redis + PostgreSQL, no new pip dependencies unless strongly justified.
- Continue using `database_sync_to_async` for ORM in consumers.
- Preserve chat contracts: soft delete via `deleted_at`, 15-minute edit window, compatible WS payload evolution.

## Testing Strategy

- Use Django test runner (`manage.py test`), no `--parallel`.
- Add focused tests per phase:
  - Phase 1: permission boundaries, moderation action authorization + audit persistence, mention/unread/search behavior.
  - Phase 2: multi-connection presence correctness, reconnect catch-up invariants, rate-limit edge behavior.
  - Phase 3: DM authorization/privacy and abuse reporting boundaries.

## Delivery Order

1. Phase 1 (trust + message usability).
2. Phase 2 (multi-instance correctness + reconnect safety).
3. Phase 3 (DM/friends expansion).

This order maximizes MVP value while keeping scale risks controlled.
