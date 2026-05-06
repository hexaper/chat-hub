# AGENTS.md

Scope: `allinone/` owns the bundled local self-host deployment path with its own container wiring and entrypoint.

## Key Files

- `docker-compose.yml`: bundled app runtime with local PostgreSQL and Redis.
- `Dockerfile`: container image definition.
- `entrypoint.sh`: bundled service startup, migrations, TLS, and Daphne launch.

## Rules

- Preserve the all-in-one role as the bundled local deployment path, separate from the top-level production-oriented `docker-compose.yml`.
- Keep HTTPS and self-signed certificate behavior intact unless the task explicitly changes local TLS setup.
- Treat this path as Daphne/ASGI-aware runtime behavior, not equivalent to `python manage.py runserver`.
- Keep secrets and runtime settings environment-driven or persisted through the existing entrypoint flow.

## Verify

- Review `docker-compose.yml`, `Dockerfile`, and `entrypoint.sh` together because they are tightly coupled.
- Run the smallest relevant Docker or compose validation command for the changed files.
