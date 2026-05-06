# AGENTS.md

Scope: `apps/devices/` owns device registration persistence, listing and default-device selection endpoints, and app-local tests.

## Key Files

- `models.py`: device records.
- `views.py`: device registration, listing, and default-device selection behavior.
- `urls.py`: device routes.
- `tests/test_views.py`: focused regression coverage.

## Rules

- Keep this app narrowly focused on device registration, listing, and default-device selection behavior.
- Do not reintroduce old room-domain device logic here; room chat behavior lives in `apps/rooms/`.
- Prefer simple Django models/views over new abstraction layers.

## Verify

- Run `python manage.py test apps.devices.tests --settings=config.settings.development` after changing this app.
- Update docs if endpoint shape or operational setup changes.
