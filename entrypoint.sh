#!/usr/bin/env bash
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-videocall}"
export DB_USER="${DB_USER:-videocall}"
export DB_PASSWORD="${DB_PASSWORD:-videocall}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-*}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"

# ── Fix volume permissions ───────────────────────────────────────────────────
mkdir -p /app/mediafiles
chown -R appuser:appgroup /app/mediafiles 2>/dev/null || true

# ── SECRET_KEY: use env var, or generate once and persist ────────────────────
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

# ── Start bundled PostgreSQL if DB_HOST is localhost ─────────────────────────
if [ "$DB_HOST" = "localhost" ] || [ "$DB_HOST" = "127.0.0.1" ]; then
    echo "Starting bundled PostgreSQL..."
    PG_BIN="/usr/lib/postgresql/16/bin"
    PG_DATA="/var/lib/postgresql/16/main"

    mkdir -p /run/postgresql /var/log/postgresql "$PG_DATA"
    chown -R postgres:postgres /run/postgresql /var/log/postgresql /var/lib/postgresql

    # Initialize DB cluster on first run
    if [ ! -f "$PG_DATA/PG_VERSION" ]; then
        su postgres -c "$PG_BIN/initdb -D $PG_DATA"
    fi

    # Start PostgreSQL and wait for it
    su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/postgresql/postgresql.log start -w"

    # Create user and database if they don't exist
    su postgres -c "$PG_BIN/psql -v ON_ERROR_STOP=1" <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '$(echo "$DB_PASSWORD" | sed "s/'/''/g")';
    END IF;
END
\$\$;
SQL
    su postgres -c "$PG_BIN/psql -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"" | grep -q 1 || \
        su postgres -c "$PG_BIN/createdb -O ${DB_USER} ${DB_NAME}"

    echo "  PostgreSQL ready"
else
    # Wait for external PostgreSQL
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
fi

# ── Start bundled Redis if REDIS_HOST is localhost ───────────────────────────
if [ "$REDIS_HOST" = "localhost" ] || [ "$REDIS_HOST" = "127.0.0.1" ]; then
    echo "Starting bundled Redis..."
    redis-server --daemonize yes
    echo "  Redis ready"
else
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
fi

# ── Django setup (run as appuser) ────────────────────────────────────────────
echo "Running migrations..."
su appuser -s /bin/sh -p -c "python manage.py migrate --noinput"

echo "Starting Daphne on 0.0.0.0:8000..."
exec su appuser -s /bin/sh -p -c "exec daphne -b 0.0.0.0 -p 8000 config.asgi:application"
