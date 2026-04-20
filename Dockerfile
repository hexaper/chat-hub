FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update && apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends redis-server libpq-dev libjpeg-dev zlib1g-dev gnupg2 curl lsb-release openssl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Create media directories for uploads (avatars, etc.)
RUN mkdir -p /app/mediafiles/server_avatars /app/mediafiles/avatars

# Collect static files at build time
RUN SECRET_KEY=build-placeholder \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    ALLOWED_HOSTS=localhost \
    POSTGRES_NAME=x POSTGRES_USER=x POSTGRES_PASS=x POSTGRES_HOST=x \
    REDIS_HOST=redis://localhost:6379 \
    AWS_STORAGE_BUCKET_NAME=x AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=x \
    python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/healthz/ || exit 1

ENTRYPOINT ["./entrypoint.sh"]
