from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<slug>[^/]+)/$', consumers.ServerChatConsumer.as_asgi()),
    re_path(r'ws/rooms/(?P<slug>[^/]+)/$', consumers.RoomConsumer.as_asgi()),
]
