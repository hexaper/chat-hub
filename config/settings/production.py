from .base import *
import os

DEBUG = False
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
SECRET_KEY = os.environ['SECRET_KEY']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['POSTGRES_NAME'],
        'USER': os.environ['POSTGRES_USER'],
        'PASSWORD': os.environ['POSTGRES_PASS'],
        'HOST': os.environ['POSTGRES_HOST'],
        'OPTIONS': {'sslmode': 'require'},
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [os.environ['REDIS_HOST']],
        },
    },
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


# Trust proxy headers (Koyeb, Railway, etc. terminate TLS at the load balancer)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [
    f'https://{h.strip()}' for h in ALLOWED_HOSTS if h.strip() and h.strip() != '*'
] + [
    o.strip() if '://' in o.strip() else f'https://{o.strip()}'
    for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]
# Wildcard: trust all HTTPS origins when ALLOWED_HOSTS=*
if '*' in ALLOWED_HOSTS:
    CSRF_TRUSTED_ORIGINS.append('https://*.koyeb.app')

_use_ssl = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() == 'true'
SECURE_SSL_REDIRECT = _use_ssl
SESSION_COOKIE_SECURE = _use_ssl
CSRF_COOKIE_SECURE = _use_ssl
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
