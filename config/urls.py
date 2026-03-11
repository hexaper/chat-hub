from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('devices/', include('apps.devices.urls')),
    path('', include('apps.rooms.urls')),
]

# Serve uploaded media (avatars, etc.) — in production consider a reverse proxy
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
