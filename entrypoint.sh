#!/usr/bin/env bash
set -euo pipefail

# ── Fix volume permissions (mounted as root) ─────────────────────────────────
chown -R appuser:appgroup /app/mediafiles 2>/dev/null || true

# ── SECRET_KEY: use env var, or generate once and persist to a volume ────────
mkdir -p /app/mediafiles
SECRET_KEY_FILE="/app/mediafiles/.secret_key"
if [ -z "${SECRET_KEY:-}" ]; then
    if [ -f "$SECRET_KEY_FILE" ]; then
        export SECRET_KEY="$(cat "$SECRET_KEY_FILE")"
        echo "Loaded SECRET_KEY from $SECRET_KEY_FILE"
    else
        export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(50))')"
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        echo "Generated new SECRET_KEY and saved to $SECRET_KEY_FILE"
    fi
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-videocall}"
export DB_USER="${DB_USER:-videocall}"
export DB_PASSWORD="${DB_PASSWORD:-videocall}"
export REDIS_HOST="${REDIS_HOST:-redis}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-*}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"

# ── Wait for PostgreSQL ──────────────────────────────────────────────────────
echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 60); do
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
    if [ "$i" -eq 60 ]; then
        echo "FATAL: PostgreSQL not reachable at ${DB_HOST}:${DB_PORT} after 60s" >&2
        exit 1
    fi
    sleep 1
done

# ── Wait for Redis ───────────────────────────────────────────────────────────
echo "Waiting for Redis at ${REDIS_HOST}:6379..."
for i in $(seq 1 60); do
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
    if [ "$i" -eq 60 ]; then
        echo "FATAL: Redis not reachable at ${REDIS_HOST}:6379 after 60s" >&2
        exit 1
    fi
    sleep 1
done

# ── Django setup (run as appuser) ─────────────────────────────────────────────
echo "Running migrations..."
su appuser -s /bin/sh -c "python manage.py migrate --noinput"

echo "Starting Daphne on 0.0.0.0:8000..."
exec su appuser -s /bin/sh -c "exec daphne -b 0.0.0.0 -p 8000 config.asgi:application"
