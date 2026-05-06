# AGENTS.md

Scope: `config/` owns settings, URL wiring, and ASGI/WSGI entrypoints.

## Key Files

- `settings/base.py`: shared defaults.
- `settings/development.py`: local development settings.
- `settings/production.py`: production defaults.
- `settings/allinone.py`: bundled local deployment settings.
- `urls.py`: top-level HTTP routes.
- `asgi.py`: Channels/Daphne entrypoint.
- `wsgi.py`: WSGI entrypoint.

## Rules

- `manage.py` defaults to `config.settings.development`.
- `config/asgi.py` defaults to `config.settings.production`; set `DJANGO_SETTINGS_MODULE=config.settings.development` for local Daphne runs.
- Keep WhiteNoise/staticfiles behavior compatible with manifest storage; do not add `ASGIStaticFilesHandler`.
- Keep settings environment-driven; never hardcode secrets.

## Verify

- Run `python manage.py check --settings=config.settings.development` after settings or URL changes.
- For ASGI/websocket changes, also verify with local Daphne under `DJANGO_SETTINGS_MODULE=config.settings.development`.
- Update `CLAUDE.md` or `docs/codebase/*.md` when runtime behavior changes.
