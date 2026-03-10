#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VideoCall — Production Deployment Script
#
# Installs all system dependencies, configures PostgreSQL, Redis, Nginx,
# and sets up the Django Channels + Daphne application as a systemd service.
#
# Usage:
#   chmod +x deploy.sh
#   sudo ./deploy.sh
#
# Tested on: Ubuntu 22.04 / 24.04, Debian 12
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Must run as root ─────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

# ── Configuration (edit these or export before running) ──────────────────────
APP_USER="${APP_USER:-videocall}"
APP_DIR="${APP_DIR:-/opt/videocall}"
DOMAIN="${DOMAIN:-$(hostname -I | awk '{print $1}')}"
DB_NAME="${DB_NAME:-videocall}"
DB_USER="${DB_USER:-videocall}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 32)}"
SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(50))')}"
PYTHON_VERSION="python3"

echo "═══════════════════════════════════════════════════════════════"
echo "  VideoCall Deployment"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Domain/IP:    $DOMAIN"
echo "  App dir:      $APP_DIR"
echo "  App user:     $APP_USER"
echo "  DB name:      $DB_NAME"
echo "  DB user:      $DB_USER"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. System packages ──────────────────────────────────────────────────────
echo "[1/9] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib libpq-dev \
    redis-server \
    nginx \
    certbot python3-certbot-nginx \
    git curl rsync build-essential \
    libjpeg-dev zlib1g-dev libffi-dev \
    > /dev/null
sudo apt-get install wget ca-certificates
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" >> /etc/apt/sources.list.d/pgdg.list'
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
echo "  ✓ System packages installed"

# ── 2. Create application user ──────────────────────────────────────────────
echo "[2/9] Setting up application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "$APP_DIR" --create-home "$APP_USER"
    echo "  ✓ User '$APP_USER' created"
else
    echo "  ✓ User '$APP_USER' already exists"
fi

# ── 3. Copy project files ───────────────────────────────────────────────────
echo "[3/9] Copying project files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
    mkdir -p "$APP_DIR"
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='db.sqlite3' --exclude='venv' --exclude='.venv' \
          --exclude='node_modules' --exclude='staticfiles' --exclude='mediafiles' \
          "$SCRIPT_DIR/" "$APP_DIR/"
    echo "  ✓ Files copied to $APP_DIR"
else
    echo "  ✓ Already in $APP_DIR"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── 4. Python virtual environment & dependencies ────────────────────────────
echo "[4/9] Setting up Python virtual environment..."
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    $PYTHON_VERSION -m venv venv
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel -q
    pip install -r requirements.txt -q
    pip install gunicorn psycopg2-binary -q
"
echo "  ✓ Python dependencies installed"

# ── 5. PostgreSQL setup ─────────────────────────────────────────────────────
echo "[5/9] Configuring PostgreSQL..."
systemctl enable --now postgresql > /dev/null 2>&1

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" > /dev/null

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" > /dev/null

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" > /dev/null 2>&1

echo "  ✓ PostgreSQL configured (db=$DB_NAME, user=$DB_USER)"

# ── 6. Redis setup ──────────────────────────────────────────────────────────
echo "[6/9] Configuring Redis..."
systemctl enable --now redis-server > /dev/null 2>&1
echo "  ✓ Redis running"

# ── 7. Environment file & Django setup ───────────────────────────────────────
echo "[7/9] Configuring Django..."

cat > "$APP_DIR/.env" <<ENVEOF
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432
ENVEOF

chmod 600 "$APP_DIR/.env"
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"

# Run migrations and collect static
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    source venv/bin/activate
    set -a; source .env; set +a

    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
"

# Create media directory
mkdir -p "$APP_DIR/mediafiles"
chown "$APP_USER:$APP_USER" "$APP_DIR/mediafiles"

echo "  ✓ Django configured, migrations applied, static files collected"

# ── 8. Systemd service (Daphne ASGI server) ─────────────────────────────────
echo "[8/9] Creating systemd service..."

cat > /etc/systemd/system/videocall.service <<SVCEOF
[Unit]
Description=VideoCall Daphne ASGI Server
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/daphne -b 127.0.0.1 -p 8001 config.asgi:application
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/mediafiles $APP_DIR/staticfiles

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now videocall
echo "  ✓ Daphne service created and started"

# ── 9. Nginx reverse proxy ──────────────────────────────────────────────────
echo "[9/9] Configuring Nginx..."

cat > /etc/nginx/sites-available/videocall <<NGXEOF
upstream daphne {
    server 127.0.0.1:8001;
}

server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 10M;

    # Static files
    location /static/ {
        alias $APP_DIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files (avatars, uploads)
    location /media/ {
        alias $APP_DIR/mediafiles/;
        expires 7d;
    }

    # WebSocket — must come before the generic proxy
    location /ws/ {
        proxy_pass http://daphne;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    # Django application
    location / {
        proxy_pass http://daphne;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGXEOF

# Enable site, disable default
ln -sf /etc/nginx/sites-available/videocall /etc/nginx/sites-enabled/videocall
rm -f /etc/nginx/sites-enabled/default

nginx -t -q
systemctl enable --now nginx
systemctl reload nginx

echo "  ✓ Nginx configured"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  App running at:    http://$DOMAIN"
echo "  Daphne service:    systemctl status videocall"
echo "  App logs:          journalctl -u videocall -f"
echo "  Env file:          $APP_DIR/.env"
echo ""
echo "  Database password:  $DB_PASSWORD"
echo "  (save this — it won't be shown again)"
echo ""
echo "  ─── Next steps ───"
echo "  1. Create a superuser:"
echo "     sudo -u $APP_USER bash -c 'cd $APP_DIR && source venv/bin/activate && set -a && source .env && set +a && python manage.py createsuperuser'"
echo ""
echo "  2. Set up HTTPS with Let's Encrypt:"
echo "     sudo certbot --nginx -d $DOMAIN"
echo ""
echo "  3. (Optional) Add a TURN server for WebRTC behind strict NATs:"
echo "     sudo apt install coturn"
echo "     Then configure in /etc/turnserver.conf and update ICE_SERVERS in static/js/webrtc.js"
echo ""
echo "═══════════════════════════════════════════════════════════════"
