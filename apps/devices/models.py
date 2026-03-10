from django.db import models
from django.conf import settings


class Device(models.Model):
    DEVICE_TYPES = [
        ('camera', 'Camera'),
        ('microphone', 'Microphone'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices')
    device_id = models.CharField(max_length=255)  # browser MediaDevices deviceId
    label = models.CharField(max_length=255, blank=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    is_default = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'device_id')

    def __str__(self):
        return f"{self.user.username} — {self.label or self.device_id} ({self.device_type})"
