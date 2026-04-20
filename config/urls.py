from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse


def healthz(request):
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception as e:
        return JsonResponse({'status': 'error', 'db': str(e)}, status=503)
    try:
        cache.set('healthz', 1, timeout=5)
    except Exception as e:
        return JsonResponse({'status': 'error', 'cache': str(e)}, status=503)
    return JsonResponse({'status': 'ok'})


@login_required
def ice_servers(request):
    from utils.turn import generate_turn_credentials
    ice = [{'urls': 'stun:stun.l.google.com:19302'}]
    if getattr(settings, 'TURN_ENABLED', False) and getattr(settings, 'TURN_HOST', ''):
        host = settings.TURN_HOST
        static_username = getattr(settings, 'TURN_USERNAME', '').strip()
        static_password = getattr(settings, 'TURN_PASSWORD', '').strip()

        if static_username and static_password:
            username = static_username
            credential = static_password
        elif getattr(settings, 'TURN_SECRET', '').strip():
            username, credential = generate_turn_credentials(
                settings.TURN_SECRET,
                str(request.user.pk),
                settings.TURN_TTL,
            )
        else:
            return JsonResponse({'iceServers': ice})

        ice.append({
            'urls': [
                f'turn:{host}:3478?transport=udp',
                f'turn:{host}:3478?transport=tcp',
                f'turns:{host}:5349',
            ],
            'username': username,
            'credential': credential,
        })
    return JsonResponse({'iceServers': ice})


urlpatterns = [
    path('healthz/', healthz),
    path('api/ice-servers/', ice_servers),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('devices/', include('apps.devices.urls')),
    path('', include('apps.rooms.urls')),
]

# Serve static + media locally in development
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()

if settings.DEBUG or getattr(settings, 'SERVE_MEDIA_LOCALLY', False):
    from django.views.static import serve
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
