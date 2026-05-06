# AGENTS.md

Scope: `utils/` owns cross-cutting helpers shared across apps.

## Key Files

- `ratelimit.py`: shared rate-limit helpers.
- `turn.py`: ICE/TURN helper logic.
- `tests.py`: utility-level tests.

## Rules

- Keep helpers generic and reusable; app-specific behavior belongs in the owning app.
- Do not pull room-domain or account-domain state into `utils/` unless more than one app truly needs it.
- Keep dependencies minimal and prefer straightforward functions over service layers or framework-style abstractions.
- Prefer absolute imports from `apps.*` and `utils.*` when shared helpers are consumed elsewhere.

## Verify

- Run `python manage.py test utils --settings=config.settings.development` when utility tests cover the changed behavior.
- Otherwise run the focused app tests that exercise the helper path.
