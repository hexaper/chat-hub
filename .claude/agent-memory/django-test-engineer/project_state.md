---
name: project_state
description: Phase tracking, active branch, and current feature implementation status
type: project
---

Active branch: `rate-limit` (branched from master).

**Phase 1.1** — Full test suite: COMPLETE. 82 tests passing, ~35s parallel.

**Phase 1.2** — Rate limiting: IN PROGRESS.
- `utils/ratelimit.py` exists and is already imported in `consumers.py` via `is_rate_limited('chat', user.pk, '30/m')`.
- `CACHES` config (Redis DB 1) needs to be added to `base.py`.
- Rate limit targets: login+register (5/m per IP), image upload (10/m per user), chat receive (30/m per user — already wired in consumer).
- Tests for rate limiting not yet written.

**Phase 1.3** — WebSocket origin validation, custom error pages, `/healthz/` endpoint: NOT STARTED.

**ChatMessage edit/delete** — Newly added feature (as of 2026-03-16):
- `updated_at` and `deleted_at` fields on `ChatMessage` model.
- `edit_message` consumer handler: owner-only, 15-min window, `deleted_at` must be NULL.
- `delete_message` consumer handler: owner-only soft delete, idempotent (already-deleted is ignored).
- `get_history` updated: includes `updated_at`/`deleted_at`; deleted messages get empty `content` and `image_url`.
- 11 new tests written and added to `ConsumerTests` in `apps/rooms/tests/test_consumers.py`.

**Why:** Phase 1.2 is the active implementation branch; rate limit tests are the next test-writing task.
**How to apply:** When user asks about rate limiting tests, check `utils/ratelimit.py` and whether CACHES config has landed in `base.py` before writing tests.
