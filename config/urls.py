from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('devices/', include('apps.devices.urls')),
    path('', include('apps.rooms.urls')),
]

# Serve uploaded media (avatars, etc.) regardless of DEBUG setting
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
