from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    email = models.EmailField(unique=True, blank=True, null=True, default=None)

    def __str__(self):
        return self.username
