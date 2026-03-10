#!/usr/bin/env bash
set -euo pipefail

# ── Validate required environment variables ──────────────────────────────────
if [ -z "${SECRET_KEY:-}" ]; then
    echo "FATAL: SECRET_KEY environment variable is not set. Refusing to start." >&2
    exit 1
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-videocall}"
export DB_USER="${DB_USER:-videocall}"
export DB_PASSWORD="${DB_PASSWORD:-videocall}"
export REDIS_HOST="${REDIS_HOST:-redis}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost,127.0.0.1}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-true}"

# ── Wait for PostgreSQL ──────────────────────────────────────────────────────
echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 30); do
    if python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect(('${DB_HOST}', ${DB_PORT}))
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; then
        echo "  PostgreSQL ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "FATAL: PostgreSQL not reachable at ${DB_HOST}:${DB_PORT} after 30s" >&2
        exit 1
    fi
    sleep 1
done

# ── Wait for Redis ───────────────────────────────────────────────────────────
echo "Waiting for Redis at ${REDIS_HOST}:6379..."
for i in $(seq 1 30); do
    if python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect(('${REDIS_HOST}', 6379))
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; then
        echo "  Redis ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "FATAL: Redis not reachable at ${REDIS_HOST}:6379 after 30s" >&2
        exit 1
    fi
    sleep 1
done

# ── Django setup ─────────────────────────────────────────────────────────────
echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
