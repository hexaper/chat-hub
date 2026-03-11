#!/usr/bin/env bash
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-*}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"

# ── Fix volume permissions ───────────────────────────────────────────────────
mkdir -p /app/mediafiles/server_avatars /app/mediafiles/avatars
chmod -R 777 /app/mediafiles

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

# ── Wait for external PostgreSQL ─────────────────────────────────────────────
echo "Waiting for Koyeb PostgreSQL..."
for i in $(seq 1 60); do
    if python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(5)
    s.connect(('ep-misty-fog-alok1dzh.c-3.eu-central-1.pg.koyeb.app', 5432))
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
        echo "FATAL: PostgreSQL not reachable after 60s" >&2
        exit 1
    fi
    sleep 1
done

# ── Redis (Upstash — no wait needed, it's a managed service) ────────────────
echo "Using Upstash Redis"

# ── Django setup ─────────────────────────────────────────────────────────────
echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating test users and server..."
python manage.py shell -c "
from apps.accounts.models import User
from apps.rooms.models import Server, ServerMember
for name in ['test1', 'test2']:
    if not User.objects.filter(username=name).exists():
        User.objects.create_user(username=name, password='Heksaper12.')
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

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
