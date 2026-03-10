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
    PG_DATA="/tmp/pgdata"
    PG_RUN="/tmp/pgrun"
    PG_LOG="/tmp/pg.log"

    mkdir -p "$PG_DATA" "$PG_RUN"

    # Initialize DB cluster on first run
    if [ ! -f "$PG_DATA/PG_VERSION" ]; then
        "$PG_BIN/initdb" -D "$PG_DATA" --auth=trust --no-locale --encoding=UTF8
    fi

    # Configure to use /tmp sockets and listen on localhost
    cat > "$PG_DATA/postgresql.conf" <<PGCONF
listen_addresses = 'localhost'
port = 5432
unix_socket_directories = '$PG_RUN'
shared_buffers = 128MB
dynamic_shared_memory_type = posix
max_connections = 50
log_destination = 'stderr'
logging_collector = off
PGCONF

    cat > "$PG_DATA/pg_hba.conf" <<PGHBA
local   all   all                 trust
host    all   all   127.0.0.1/32  trust
host    all   all   ::1/128       trust
PGHBA

    # Start PostgreSQL
    "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" start -w -t 30 || {
        echo "FATAL: PostgreSQL failed to start. Log output:" >&2
        cat "$PG_LOG" >&2
        exit 1
    }

    export PGHOST="$PG_RUN"

    # Create user and database if they don't exist
    "$PG_BIN/psql" -h "$PG_RUN" -p 5432 -U "$(whoami)" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '$(echo "$DB_PASSWORD" | sed "s/'/''/g")';
    END IF;
END
\$\$;
SQL
    "$PG_BIN/psql" -h "$PG_RUN" -p 5432 -U "$(whoami)" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
        "$PG_BIN/createdb" -h "$PG_RUN" -p 5432 -U "$(whoami)" -O "${DB_USER}" "${DB_NAME}"

    # Set DB_HOST to the socket dir so Django connects via unix socket
    export DB_HOST="$PG_RUN"

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
    redis-server --daemonize yes --dir /tmp --save ""
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

# ── Django setup ─────────────────────────────────────────────────────────────
echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
