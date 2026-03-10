#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Start Redis if not running
if ! redis-cli ping &>/dev/null 2>&1; then
    echo "Starting Redis..."
    sudo service redis-server start
fi

# Activate venv if it exists
if [[ -d "venv" ]]; then
    source venv/bin/activate
elif [[ -d ".venv" ]]; then
    source .venv/bin/activate
fi

# Load .env if it exists
if [[ -f ".env" ]]; then
    set -a; source .env; set +a
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.development}"

# Run migrations
python manage.py migrate --noinput

# Start Daphne
echo "Starting server at http://0.0.0.0:8000"
daphne -b 0.0.0.0 -p 8000 config.asgi:application
