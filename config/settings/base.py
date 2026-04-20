from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

import os as _os

def _get_or_create_secret_key():
    key_file = BASE_DIR / '.secret_key'
    if key_file.exists():
        return key_file.read_text().strip()
    import secrets
    key = secrets.token_hex(50)
    key_file.write_text(key)
    return key

SECRET_KEY = _os.environ.get('SECRET_KEY') or _get_or_create_secret_key()

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'channels',
    'crispy_forms',
    'crispy_bootstrap5',
    # Local
    'apps.accounts',
    'apps.rooms',
    'apps.devices',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [('127.0.0.1', 6379)]},
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',  # DB 1 — channel layers use DB 0
    }
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
    message_constants.WARNING: 'warning',
    message_constants.SUCCESS: 'success',
    message_constants.INFO: 'info',
    message_constants.DEBUG: 'secondary',
}

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ── TURN server ───────────────────────────────────────────────────────────────
# Set TURN_ENABLED=True and supply TURN_HOST plus either:
# - TURN_SECRET (coturn HMAC REST API), or
# - TURN_USERNAME + TURN_PASSWORD (static long-term credentials)
# to relay traffic for users behind symmetric NAT or strict firewalls.
# Leave disabled in development — STUN-only is fine on a local network.
TURN_ENABLED = False
TURN_HOST = ''      # hostname or IP of the coturn server, e.g. "turn.example.com"
TURN_SECRET = ''    # shared secret configured in coturn's use-auth-secret
TURN_USERNAME = ''  # static TURN username (used when TURN_SECRET is not provided)
TURN_PASSWORD = ''  # static TURN password (used when TURN_SECRET is not provided)
TURN_TTL = 3600     # credential lifetime in seconds (1 hour)
