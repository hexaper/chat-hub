import uuid
import string
import random
from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password


def generate_invite_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


class Server(models.Model):
    name = models.CharField(max_length=255)
    slug = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_servers'
    )
    avatar = models.ImageField(upload_to='server_avatars/', blank=True, null=True)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    invite_code = models.CharField(max_length=8, unique=True, default=generate_invite_code)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='ServerMember', related_name='joined_servers'
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('server_detail', kwargs={'server_slug': self.slug})

    def regenerate_invite_code(self):
        self.invite_code = generate_invite_code()
        self.save(update_fields=['invite_code'])


class ServerMember(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('server', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.server.name}"


class Room(models.Model):
    name = models.CharField(max_length=255)
    slug = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='rooms', null=True)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hosted_rooms'
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='RoomParticipant', related_name='joined_rooms'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    password = models.CharField(max_length=255, blank=True)
    last_empty_at = models.DateTimeField(null=True, blank=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password) if raw_password else ''

    def check_room_password(self, raw_password):
        return check_password(raw_password, self.password)

    @property
    def is_password_protected(self):
        return bool(self.password)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('room_detail', kwargs={
            'server_slug': self.server.slug,
            'slug': self.slug,
        })


class ChatMessage(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username}: {self.content[:50]}"


class RoomParticipant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    camera_device_id = models.CharField(max_length=255, blank=True)
    microphone_device_id = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('room', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"
