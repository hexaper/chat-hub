#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for PostgreSQL..."
while ! python -c "import socket; s=socket.create_connection(('${DB_HOST:-db}', ${DB_PORT:-5432}), 2)" 2>/dev/null; do
    sleep 1
done

echo "Waiting for Redis..."
while ! python -c "import socket; s=socket.create_connection(('${REDIS_HOST:-redis}', 6379), 2)" 2>/dev/null; do
    sleep 1
done

echo "Running migrations..."
python manage.py migrate --noinput


echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
