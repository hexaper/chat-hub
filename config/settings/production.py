from .base import *
import os

DEBUG = False
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
SECRET_KEY = os.environ['SECRET_KEY']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'koyebdb',
        'USER': 'koyeb-adm',
        'PASSWORD': 'npg_nDIwW9eE6jxA',
        'HOST': 'ep-misty-fog-alok1dzh.c-3.eu-central-1.pg.koyeb.app',
        'OPTIONS': {'sslmode': 'require'},
    }
}

_redis_url = os.environ.get('REDIS_URL', '')
_redis_host = os.environ.get('REDIS_HOST', 'localhost')
_redis_port = int(os.environ.get('REDIS_PORT', 6379))

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [_redis_url] if _redis_url else [(_redis_host, _redis_port)],
        },
    },
}

# Static files — served by whitenoise
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# S3-compatible media storage (for avatars etc.)
if os.environ.get('AWS_STORAGE_BUCKET_NAME'):
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    }
    AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'auto')
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', '')
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '')
    AWS_DEFAULT_ACL = 'public-read'
    AWS_QUERYSTRING_AUTH = False
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    elif AWS_S3_ENDPOINT_URL:
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/'

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
