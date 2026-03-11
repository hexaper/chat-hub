#!/usr/bin/env bash
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.allinone}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"
export DB_NAME="${DB_NAME:-videocall}"
export DB_USER="${DB_USER:-videocall}"
export DB_PASSWORD="${DB_PASSWORD:-videocall}"

# ── Fix volume permissions ───────────────────────────────────────────────────
mkdir -p /app/mediafiles/server_avatars /app/mediafiles/avatars
chmod -R u+rwX,go+rX /app/mediafiles

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

# ── Start bundled PostgreSQL ─────────────────────────────────────────────────
echo "Starting bundled PostgreSQL..."
PG_BIN="/usr/lib/postgresql/16/bin"
PG_DATA="/tmp/pgdata"
PG_RUN="/tmp/pgrun"
PG_LOG="/tmp/pg.log"

mkdir -p "$PG_DATA" "$PG_RUN"
chown -R postgres:postgres "$PG_DATA" "$PG_RUN" 2>/dev/null || chown -R postgres "$PG_DATA" "$PG_RUN"
touch "$PG_LOG"
chown postgres "$PG_LOG"

# Initialize DB cluster on first run
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    su postgres -s /bin/sh -c "$PG_BIN/initdb -D $PG_DATA --auth=peer --no-locale --encoding=UTF8"
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
local   all   postgres            peer
local   all   all                 scram-sha-256
host    all   all   127.0.0.1/32  scram-sha-256
host    all   all   ::1/128       scram-sha-256
PGHBA

chown postgres "$PG_DATA/postgresql.conf" "$PG_DATA/pg_hba.conf"

# Start PostgreSQL
su postgres -s /bin/sh -c "$PG_BIN/pg_ctl -D $PG_DATA -l $PG_LOG start -w -t 30" || {
    echo "FATAL: PostgreSQL failed to start. Log output:" >&2
    cat "$PG_LOG" >&2
    exit 1
}

# Create user and database if they don't exist
su postgres -s /bin/sh -c "$PG_BIN/psql -h $PG_RUN -p 5432 -d postgres -v ON_ERROR_STOP=1" <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '$(echo "$DB_PASSWORD" | sed "s/'/''/g")';
    END IF;
END
\$\$;
SQL
su postgres -s /bin/sh -c "$PG_BIN/psql -h $PG_RUN -p 5432 -d postgres -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"" | grep -q 1 || \
    su postgres -s /bin/sh -c "$PG_BIN/createdb -h $PG_RUN -p 5432 -O ${DB_USER} ${DB_NAME}"

echo "  PostgreSQL ready"

# ── Start bundled Redis ──────────────────────────────────────────────────────
echo "Starting bundled Redis..."
redis-server --daemonize yes --dir /tmp --save ""
echo "  Redis ready"

# ── Django setup ─────────────────────────────────────────────────────────────
echo "Running migrations..."
python manage.py migrate --noinput

# Create seed data if TEST_USER_PASSWORD is set
if [ -n "${TEST_USER_PASSWORD:-}" ]; then
    echo "Creating test users and server..."
    python manage.py shell -c "
from apps.accounts.models import User
from apps.rooms.models import Server, ServerMember
import os
pw = os.environ['TEST_USER_PASSWORD']
for name in ['test1', 'test2']:
    if not User.objects.filter(username=name).exists():
        User.objects.create_user(username=name, password=pw)
        print(f'  Created user: {name}')
    else:
        print(f'  User {name} already exists')
test1 = User.objects.get(username='test1')
test2 = User.objects.get(username='test2')
server, created = Server.objects.get_or_create(name='Test Server', defaults={'owner': test1, 'is_public': True})
if created:
    print('  Created Test Server')
ServerMember.objects.get_or_create(server=server, user=test1)
ServerMember.objects.get_or_create(server=server, user=test2)
"
fi

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
