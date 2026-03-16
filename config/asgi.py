import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import apps.rooms.routing

application = ProtocolTypeRouter({
    'http': ASGIStaticFilesHandler(get_asgi_application()),
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(apps.rooms.routing.websocket_urlpatterns))
    ),
})