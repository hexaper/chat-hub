# Technology Stack

## Core Sections (Required)

### 1) Runtime Summary

| Area | Value | Evidence |
|------|-------|----------|
| Primary language | Python | requirements.txt |
| Runtime + version | Python 3.12 in both Docker images; local setup script requires Python 3.10+ | Dockerfile, allinone/Dockerfile, deploy.sh |
| Package manager | pip with a pinned requirements file | requirements.txt |
| Module/build system | Django project loaded through manage.py and ASGI; Docker images run collectstatic during image build | manage.py, config/asgi.py, Dockerfile, allinone/Dockerfile |

### 2) Production Frameworks and Dependencies

| Dependency | Version | Role in system | Evidence |
|------------|---------|----------------|----------|
| Django | 5.2.12 | HTTP framework, ORM, auth, templates, management commands | requirements.txt |
| channels | 4.3.2 | WebSocket consumer framework layered onto Django | requirements.txt |
| channels-redis | 4.3.0 | Redis-backed channel layer for cross-consumer messaging | requirements.txt, config/settings/base.py |
| daphne | 4.2.1 | ASGI server used in container entrypoints | requirements.txt, entrypoint.sh, allinone/entrypoint.sh |
| redis | 7.3.0 | Redis client for cache and channel-layer support | requirements.txt |
| Pillow | 12.1.1 | Image validation and ImageField support | requirements.txt, apps/rooms/views.py |
| psycopg2-binary | 2.9.11 | PostgreSQL driver for production and all-in-one settings | requirements.txt, config/settings/production.py, config/settings/allinone.py |
| whitenoise | 6.12.0 | Static file serving in non-debug deployments | requirements.txt, config/settings/production.py, config/settings/allinone.py |
| django-storages[s3] | 1.14.4 | S3-compatible media storage backend in production | requirements.txt, config/settings/production.py |
| boto3 | 1.38.34 | AWS/S3 client dependency used by django-storages | requirements.txt, config/settings/production.py |
| django-crispy-forms | 2.6 | Server-rendered form helpers | requirements.txt, config/settings/base.py |
| crispy-bootstrap5 | 2026.3 | Bootstrap 5 form template pack | requirements.txt, config/settings/base.py |

### 3) Development Toolchain

| Tool | Purpose | Evidence |
|------|---------|----------|
| Django test runner | Test execution for unit, integration, and consumer tests | CLAUDE.md, apps/rooms/tests/test_consumers.py |
| Docker + Docker Compose | Local and deployment packaging | Dockerfile, docker-compose.yml, allinone/docker-compose.yml |
| GitHub CodeQL | Static analysis workflow | .github/workflows/codeql.yml |
| [TODO] | [TODO] No dedicated formatter config found in inspected files | [TODO] |
| [TODO] | [TODO] No dedicated linter config found in inspected files | [TODO] |

### 4) Key Commands

```bash
./deploy.sh
python manage.py runserver --settings=config.settings.development
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
python manage.py test --settings=config.settings.development --keepdb
docker compose up --build
docker compose -f allinone/docker-compose.yml up --build
```

### 5) Environment and Config

- Config sources: config/settings/base.py, config/settings/development.py, config/settings/production.py, config/settings/allinone.py, docker-compose.yml, allinone/docker-compose.yml
- Required env vars: SECRET_KEY, ALLOWED_HOSTS, POSTGRES_HOST, POSTGRES_NAME, POSTGRES_USER, POSTGRES_PASS, REDIS_HOST, AWS_STORAGE_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, DB_NAME, DB_USER, DB_PASSWORD, TURN_HOST, TURN_SECRET, TURN_USERNAME, TURN_PASSWORD, TURN_TTL, CSRF_TRUSTED_ORIGINS, SECURE_SSL_REDIRECT
- Deployment/runtime constraints: Redis is required for the configured channel layer and cache; production/all-in-one settings assume Daphne + ASGI rather than WSGI-only serving.

### 6) Evidence

- requirements.txt
- manage.py
- config/asgi.py
- config/settings/base.py
- config/settings/production.py
- config/settings/allinone.py
- Dockerfile
- allinone/Dockerfile
- docker-compose.yml
- allinone/docker-compose.yml
- entrypoint.sh
- allinone/entrypoint.sh
- deploy.sh
- .github/workflows/codeql.yml
