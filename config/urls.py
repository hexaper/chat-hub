from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render

# ── Temporary error-page test views (remove before go-live) ──────────────────
def _test_404(request): return render(request, '404.html', status=404)
def _test_403(request): return render(request, '403.html', status=403)
def _test_500(request): return render(request, '500.html', status=500)
# ─────────────────────────────────────────────────────────────────────────────

urlpatterns = [
    path('test/404/', _test_404),
    path('test/403/', _test_403),
    path('test/500/', _test_500),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('devices/', include('apps.devices.urls')),
    path('', include('apps.rooms.urls')),
]

# Serve media locally in development or all-in-one mode
if settings.DEBUG or getattr(settings, 'SERVE_MEDIA_LOCALLY', False):
    from django.views.static import serve
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
