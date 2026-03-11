from django.contrib import admin
from .models import Server, ServerMember, Room, RoomParticipant

admin.site.register(Server)
admin.site.register(ServerMember)
admin.site.register(Room)
admin.site.register(RoomParticipant)
