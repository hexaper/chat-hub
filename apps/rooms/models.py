import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password


class Room(models.Model):
    name = models.CharField(max_length=255)
    slug = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hosted_rooms')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through='RoomParticipant', related_name='joined_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    password = models.CharField(max_length=255, blank=True)

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
        return reverse('room_detail', kwargs={'slug': self.slug})


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
