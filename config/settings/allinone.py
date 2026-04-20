from .base import *
import os

DEBUG = False
ALLOWED_HOSTS = ['*']

SECRET_KEY = os.environ['SECRET_KEY']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'videocall'),
        'USER': os.environ.get('DB_USER', 'videocall'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'videocall'),
        'HOST': 'localhost',
        'PORT': '5432',
        'CONN_MAX_AGE': 600,
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('localhost', 6379)],
        },
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',  # DB 1 — channel layers use DB 0
    }
}

# Static files — served by whitenoise
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Serve media from filesystem (no S3 in all-in-one mode)
SERVE_MEDIA_LOCALLY = True

# ── TURN server ───────────────────────────────────────────────────────────────
TURN_HOST = os.environ.get('TURN_HOST', '').strip()
TURN_SECRET = os.environ.get('TURN_SECRET', '').strip()
TURN_USERNAME = os.environ.get('TURN_USERNAME', '').strip()
TURN_PASSWORD = os.environ.get('TURN_PASSWORD', '').strip()
TURN_TTL = int(os.environ.get('TURN_TTL', 3600))
TURN_ENABLED = bool(TURN_HOST and ((TURN_USERNAME and TURN_PASSWORD) or TURN_SECRET))

# Security — relaxed for local/self-hosted use
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'false').lower() == 'true'
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
