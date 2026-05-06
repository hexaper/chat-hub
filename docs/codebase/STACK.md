# Technology Stack

## Runtime

- Python 3.12 in Docker images; local bootstrap targets Python 3.10+.
- Django project loaded via `manage.py` (dev) and `config/asgi.py` (Daphne/ASGI).
- No frontend build system; browser behavior is templates + vanilla JS.

## Core Dependencies

- `Django` 5.2.x
- `channels`, `channels-redis`, `daphne`
- `redis` client
- `psycopg2-binary`
- `whitenoise`
- `django-storages[s3]`, `boto3`
- `Pillow`
- `django-crispy-forms`, `crispy-bootstrap5`

## Data/Infra

- Dev DB: SQLite (`config.settings.development`).
- Prod/all-in-one DB: PostgreSQL.
- Redis DB 0: channel layer; Redis DB 1: cache/rate limits.
- Optional TURN integration via `/api/ice-servers/`.

## Commands

```bash
./deploy.sh
python manage.py runserver --settings=config.settings.development
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
python manage.py test --settings=config.settings.development --keepdb
docker compose up --build
docker compose -f allinone/docker-compose.yml up --build
```

## Verification Notes

- Use Django test runner (not pytest).
- Do not use `--parallel` in this repo.
- No dedicated formatter/linter config is currently committed.
