FROM python:3.12-slim
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev sudo libjpeg-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*
RUN sh deploy.sh
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY . .
RUN python manage.py collectstatic --noinput
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
