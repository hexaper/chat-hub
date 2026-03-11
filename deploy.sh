#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VideoCall — Local Development Setup
#
# Sets up a Python venv, installs dependencies, ensures Redis is running,
# runs migrations, creates test users, and starts the dev server.
# Uses SQLite — no PostgreSQL or Nginx needed.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Prerequisites: Python 3.10+, Redis (installed or installable via apt/brew)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# ── Helpers ───────────────────────────────────────────────────────────────────
install_redis() {
    echo "  Redis not found. Attempting to install..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq redis-server > /dev/null
        sudo service redis-server start 2>/dev/null || true
    elif command -v brew &>/dev/null; then
        brew install redis
        brew services start redis
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y redis > /dev/null
        sudo systemctl start redis
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm redis > /dev/null
        sudo systemctl start redis
    else
        echo "ERROR: Cannot install Redis automatically. Please install Redis and retry."
        exit 1
    fi
}

start_redis() {
    if command -v systemctl &>/dev/null && systemctl list-unit-files redis-server.service &>/dev/null; then
        sudo systemctl start redis-server 2>/dev/null || sudo systemctl start redis 2>/dev/null || true
    elif command -v service &>/dev/null; then
        sudo service redis-server start 2>/dev/null || true
    elif command -v brew &>/dev/null; then
        brew services start redis 2>/dev/null || true
    else
        redis-server --daemonize yes --dir /tmp --save ""
    fi
}

echo "═══════════════════════════════════════════════════════════════"
echo "  VideoCall — Local Development Setup"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. Python ─────────────────────────────────────────────────────────────────
echo "[1/5] Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3 is required but not found. Install it and retry."
    exit 1
fi

echo "  Found: $("$PYTHON" --version)"

# ── 2. Virtual environment & dependencies ─────────────────────────────────────
echo "[2/5] Setting up virtual environment..."

# Ensure venv module is available (Debian/Ubuntu ship it separately)
if ! "$PYTHON" -m venv --help &>/dev/null; then
    echo "  Installing python3-venv..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv > /dev/null
    else
        echo "ERROR: Python venv module not found. Install python3-venv and retry."
        exit 1
    fi
fi

if [[ ! -d "venv" ]]; then
    "$PYTHON" -m venv venv
    echo "  Created venv/"
else
    echo "  venv/ already exists"
fi

source venv/bin/activate
pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q
echo "  Dependencies installed"

# ── 3. Redis ──────────────────────────────────────────────────────────────────
echo "[3/5] Checking Redis..."
if ! command -v redis-cli &>/dev/null; then
    install_redis
fi

if ! redis-cli ping &>/dev/null 2>&1; then
    echo "  Starting Redis..."
    start_redis
    sleep 1
fi

if ! redis-cli ping &>/dev/null 2>&1; then
    echo "ERROR: Redis is not running and could not be started."
    echo "       Please start Redis manually (redis-server) and retry."
    exit 1
fi
echo "  Redis is running"

# ── 4. Django setup ───────────────────────────────────────────────────────────
echo "[4/5] Configuring Django..."
export DJANGO_SETTINGS_MODULE="config.settings.development"

python manage.py migrate --noinput
echo "  Migrations applied (SQLite)"

echo "  Creating test users and server..."
python manage.py shell -c "
from apps.accounts.models import User
from apps.rooms.models import Server, ServerMember
for name in ['test1', 'test2']:
    if not User.objects.filter(username=name).exists():
        User.objects.create_user(username=name, password='Tester123.')
        print(f'    Created: {name}')
    else:
        print(f'    Exists:  {name}')
test1 = User.objects.get(username='test1')
test2 = User.objects.get(username='test2')
server, created = Server.objects.get_or_create(name='Test Server', defaults={'owner': test1, 'is_public': True})
if created:
    print('    Created Test Server')
ServerMember.objects.get_or_create(server=server, user=test1)
ServerMember.objects.get_or_create(server=server, user=test2)
"

# ── 5. Start dev server ──────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Ready!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  URL:           http://0.0.0.0:8000"
echo "  Test accounts: test1 / test2  (password: Tester123.)"
echo "  Database:      db.sqlite3"
echo "  Settings:      config.settings.development"
echo "  Stop:          Ctrl+C"
echo ""

echo "[5/5] Starting server..."
python manage.py runserver 0.0.0.0:8000
