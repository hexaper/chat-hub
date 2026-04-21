import uuid
import string
import secrets
from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password


def generate_invite_code():
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


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
    ROLE_MEMBER = 'member'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = (
        (ROLE_MEMBER, 'Member'),
        (ROLE_ADMIN, 'Admin'),
    )

    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    muted_until = models.DateTimeField(null=True, blank=True)
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

    class Meta:
        indexes = [
            models.Index(fields=['server', 'is_active'], name='room_server_active_idx'),
        ]

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
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    video = models.FileField(upload_to='chat_videos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['server', '-created_at'], name='chat_server_created_idx'),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.content[:50]}"


class RoomChatMessage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='chat_messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', '-created_at'], name='roomchat_room_created_idx'),
        ]

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


class ServerBan(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='bans')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='issued_server_bans',
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['server', 'user'],
                condition=models.Q(lifted_at__isnull=True),
                name='uniq_active_server_ban',
            )
        ]


class ModerationAction(models.Model):
    ACTION_BAN = 'ban'
    ACTION_UNBAN = 'unban'
    ACTION_MUTE = 'mute'
    ACTION_UNMUTE = 'unmute'
    ACTION_KICK = 'kick'
    ACTION_CHOICES = (
        (ACTION_BAN, 'Ban'),
        (ACTION_UNBAN, 'Unban'),
        (ACTION_MUTE, 'Mute'),
        (ACTION_UNMUTE, 'Unmute'),
        (ACTION_KICK, 'Kick'),
    )

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='moderation_actions')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='moderation_actions_made',
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='moderation_actions_received',
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ChatMention(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='mentions')
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'mentioned_user')


class RoomChatMention(models.Model):
    message = models.ForeignKey(RoomChatMessage, on_delete=models.CASCADE, related_name='mentions')
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'mentioned_user')


class ChatReadState(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='chat_read_states')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_read_message = models.ForeignKey(ChatMessage, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('server', 'user')


class RoomChatReadState(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='chat_read_states')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_read_message = models.ForeignKey(RoomChatMessage, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('room', 'user')
