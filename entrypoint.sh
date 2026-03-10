#!/usr/bin/env bash
set -euo pipefail

# ── Start PostgreSQL ─────────────────────────────────────────────────────────
echo "Starting PostgreSQL..."
PG_BIN="/usr/lib/postgresql/16/bin"
PG_DATA="/var/lib/postgresql/16/main"

mkdir -p /run/postgresql
chown postgres:postgres /run/postgresql

# Initialize DB cluster if first run
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    mkdir -p "$PG_DATA"
    chown -R postgres:postgres /var/lib/postgresql
    su postgres -c "$PG_BIN/initdb -D $PG_DATA"
fi

su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/postgresql.log start -w"

# Create database and user if they don't exist
su postgres -c "$PG_BIN/psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER:-videocall}'\" | grep -q 1" || \
    su postgres -c "$PG_BIN/psql -c \"CREATE USER ${DB_USER:-videocall} WITH PASSWORD '${DB_PASSWORD:-videocall}';\""

su postgres -c "$PG_BIN/psql -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME:-videocall}'\" | grep -q 1" || \
    su postgres -c "$PG_BIN/psql -c \"CREATE DATABASE ${DB_NAME:-videocall} OWNER ${DB_USER:-videocall};\""

echo "  PostgreSQL ready"

# ── Start Redis ──────────────────────────────────────────────────────────────
echo "Starting Redis..."
redis-server --daemonize yes
echo "  Redis ready"

# ── Django setup ─────────────────────────────────────────────────────────────
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export SECRET_KEY="${SECRET_KEY:-$(python -c 'import secrets; print(secrets.token_hex(50))')}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-*}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-videocall}"
export DB_USER="${DB_USER:-videocall}"
export DB_PASSWORD="${DB_PASSWORD:-videocall}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
