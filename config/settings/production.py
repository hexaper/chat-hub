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
_s3_region = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
_s3_bucket = os.environ['AWS_STORAGE_BUCKET_NAME']
_s3_endpoint = os.environ.get('AWS_S3_ENDPOINT_URL') or None
_s3_custom_domain = os.environ.get('AWS_S3_CUSTOM_DOMAIN') or None

STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        'OPTIONS': {
            'bucket_name': _s3_bucket,
            'region_name': _s3_region,
            'endpoint_url': _s3_endpoint,
            'custom_domain': _s3_custom_domain,
            'default_acl': 'public-read',
            'querystring_auth': False,
            'signature_version': 's3v4',
        },
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# S3 credentials
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
AWS_S3_REGION_NAME = _s3_region

if _s3_custom_domain:
    MEDIA_URL = f'https://{_s3_custom_domain}/'
else:
    MEDIA_URL = f'https://{_s3_bucket}.s3.{_s3_region}.amazonaws.com/'


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

# Logging — print errors to stdout so they appear in container logs
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
