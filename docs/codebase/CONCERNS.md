# Codebase Concerns

## High Priority

- Presence is process-local in `apps/rooms/consumers.py`; multi-instance deployments can report inconsistent online state.
- No CI workflow currently runs Django tests; only CodeQL automation is present.

## Medium Priority

- `apps/rooms/consumers.py` and `apps/rooms/views.py` remain high-churn, multi-responsibility files.
- Upload error responses are not fully normalized across media branches.

## Operational Guidance

- Treat realtime and deployment changes as high-risk; pair with focused tests and manual websocket checks.
- Keep roadmap docs aligned with implemented behavior to avoid stale planning assumptions.
