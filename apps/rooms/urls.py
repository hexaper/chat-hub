from django.urls import path
from . import views

urlpatterns = [
    # Server URLs
    path('', views.server_list, name='server_list'),
    path('servers/create/', views.server_create, name='server_create'),
    path('servers/join/', views.server_join, name='server_join'),
    path('servers/<uuid:server_slug>/', views.server_detail, name='server_detail'),
    path('servers/<uuid:server_slug>/settings/', views.server_settings, name='server_settings'),
    path('servers/<uuid:server_slug>/settings/kick/', views.server_kick_member, name='server_kick_member'),
    path('servers/<uuid:server_slug>/settings/regenerate-invite/', views.server_regenerate_invite, name='server_regenerate_invite'),
    path('servers/<uuid:server_slug>/leave/', views.server_leave, name='server_leave'),
    path('servers/<uuid:server_slug>/delete/', views.server_delete, name='server_delete'),

    # Room URLs (nested under server)
    path('servers/<uuid:server_slug>/rooms/create/', views.room_create, name='room_create'),
    path('servers/<uuid:server_slug>/rooms/<uuid:slug>/', views.room_detail, name='room_detail'),
    path('servers/<uuid:server_slug>/rooms/<uuid:slug>/leave/', views.room_leave, name='room_leave'),
    path('servers/<uuid:server_slug>/rooms/<uuid:slug>/delete/', views.room_delete, name='room_delete'),
]
