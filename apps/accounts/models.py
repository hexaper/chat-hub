from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class NullableEmailUserManager(UserManager):
    """
    Custom manager that keeps email as NULL (not '') when no email is supplied.

    Django's default normalize_email converts None → "" which violates the
    UNIQUE constraint on our nullable email column in SQLite.  We override it
    so that a missing email stays as NULL and multiple no-email users can
    coexist.
    """

    @classmethod
    def normalize_email(cls, email):
        if not email:
            return None
        return super().normalize_email(email)


class User(AbstractUser):
    objects = NullableEmailUserManager()

    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    email = models.EmailField(unique=True, blank=True, null=True)

    def __str__(self):
        return self.username
