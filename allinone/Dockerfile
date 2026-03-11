FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install PostgreSQL, Redis, and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    libpq-dev libjpeg-dev zlib1g-dev \
    gnupg2 curl lsb-release && \
    rm -rf /var/lib/apt/lists/*

# Install PostgreSQL 16 from official repo
RUN curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && apt-get install -y --no-install-recommends postgresql-16 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' allinone/entrypoint.sh && chmod +x allinone/entrypoint.sh

# Create media directories for uploads (avatars, etc.)
RUN mkdir -p /app/mediafiles/server_avatars /app/mediafiles/avatars

# Collect static files at build time
RUN SECRET_KEY=build-placeholder \
    DJANGO_SETTINGS_MODULE=config.settings.allinone \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["./allinone/entrypoint.sh"]
