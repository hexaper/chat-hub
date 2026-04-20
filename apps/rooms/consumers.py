import asyncio
import json
import time
from datetime import timedelta
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from utils.ratelimit import is_rate_limited
from .models import Room, RoomParticipant, Server, ServerMember, ChatMessage, RoomChatMessage

EDIT_WINDOW_SECONDS = 15 * 60  # 15 minutes

# ── In-process presence store ─────────────────────────────────────────────────
# Maps server_slug -> {channel_name: username}
# asyncio.Lock is safe here: all AsyncWebsocketConsumers share one event loop.
_presence: dict[str, dict[str, str]] = {}
_presence_lock = asyncio.Lock()


async def _presence_add(server_slug: str, channel_name: str, username: str) -> list[str]:
    async with _presence_lock:
        _presence.setdefault(server_slug, {})[channel_name] = username
        return list(set(_presence[server_slug].values()))


async def _presence_remove(server_slug: str, channel_name: str) -> list[str]:
    async with _presence_lock:
        _presence.get(server_slug, {}).pop(channel_name, None)
        return list(set(_presence.get(server_slug, {}).values()))


async def _presence_list(server_slug: str) -> list[str]:
    async with _presence_lock:
        return list(set(_presence.get(server_slug, {}).values()))


class ServerChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.server_slug = self.scope['url_route']['kwargs']['slug']
        self.chat_group = f'server_chat_{self.server_slug}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await self.is_member():
            await self.close()
            return

        await self.channel_layer.group_add(self.chat_group, self.channel_name)
        await self.accept()

        online_users = await _presence_add(self.server_slug, self.channel_name, self.user.username)

        # Broadcast online status to everyone else
        await self.channel_layer.group_send(self.chat_group, {
            'type': 'presence',
            'username': self.user.username,
            'status': 'online',
            'exclude': self.channel_name,
        })

        # Send history with current online users list
        history = await self.get_history()
        has_more = len(history) == 50
        await self.send(text_data=json.dumps({
            'type': 'history',
            'messages': history,
            'online_users': online_users,
            'has_more': has_more,
        }))

    async def disconnect(self, code):
        if not hasattr(self, 'chat_group'):
            return
        await _presence_remove(self.server_slug, self.channel_name)
        await self.channel_layer.group_discard(self.chat_group, self.channel_name)
        if hasattr(self, 'server_slug'):
            await self.channel_layer.group_send(self.chat_group, {
                'type': 'presence',
                'username': self.user.username,
                'status': 'offline',
            })

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'chat_message':
            content = data.get('content', '').strip()
            if not content:
                return
            if await sync_to_async(is_rate_limited)('chat', self.user.pk, '30/m'):
                return
            msg = await self.save_message(content)
            await self.channel_layer.group_send(self.chat_group, {
                'type': 'chat_message',
                'id': msg['id'],
                'username': msg['username'],
                'avatar_url': msg['avatar_url'],
                'content': msg['content'],
                'image_url': '',
                'video_url': '',
                'created_at': msg['created_at'],
            })

        elif msg_type == 'chat_image':
            message_id = data.get('message_id')
            if not message_id:
                return
            msg = await self.get_image_message(message_id)
            if msg:
                await self.channel_layer.group_send(self.chat_group, {
                    'type': 'chat_message',
                    'id': msg['id'],
                    'username': msg['username'],
                    'avatar_url': msg['avatar_url'],
                    'content': msg['content'],
                    'image_url': msg['image_url'],
                    'video_url': msg['video_url'],
                    'created_at': msg['created_at'],
                })

        elif msg_type == 'typing':
            await self.channel_layer.group_send(self.chat_group, {
                'type': 'user_typing',
                'username': self.user.username,
                'exclude': self.channel_name,
            })

        elif msg_type == 'edit_message':
            message_id = data.get('message_id')
            new_content = data.get('content', '').strip()
            if not message_id or not new_content:
                return
            result = await self.do_edit_message(message_id, new_content)
            if result:
                await self.channel_layer.group_send(self.chat_group, {
                    'type': 'message_edited',
                    'id': result['id'],
                    'content': result['content'],
                    'updated_at': result['updated_at'],
                })

        elif msg_type == 'delete_message':
            message_id = data.get('message_id')
            if not message_id:
                return
            if await self.do_delete_message(message_id):
                await self.channel_layer.group_send(self.chat_group, {
                    'type': 'message_deleted',
                    'id': message_id,
                })

        elif msg_type == 'load_history':
            before_id = data.get('before_id')
            if not before_id:
                return
            page = await self.get_history_page(before_id)
            await self.send(text_data=json.dumps({
                'type': 'history_page',
                'messages': page['messages'],
                'has_more': page['has_more'],
            }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'id': event['id'],
            'username': event['username'],
            'avatar_url': event['avatar_url'],
            'content': event['content'],
            'image_url': event.get('image_url', ''),
            'video_url': event.get('video_url', ''),
            'created_at': event['created_at'],
        }))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'id': event['id'],
            'content': event['content'],
            'updated_at': event['updated_at'],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'id': event['id'],
        }))

    async def user_typing(self, event):
        if event.get('exclude') == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'username': event['username'],
        }))

    async def presence(self, event):
        if event.get('exclude') == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'username': event['username'],
            'status': event['status'],
        }))

    @database_sync_to_async
    def is_member(self):
        try:
            membership = ServerMember.objects.select_related('server').get(
                server__slug=self.server_slug, user=self.user
            )
            self.server_id = membership.server_id
            return True
        except ServerMember.DoesNotExist:
            return False

    @staticmethod
    def _avatar_url(user):
        if user.avatar and hasattr(user.avatar, 'url'):
            return user.avatar.url
        return ''

    @database_sync_to_async
    def get_history(self):
        msgs = ChatMessage.objects.filter(
            server__slug=self.server_slug
        ).select_related('user').order_by('-created_at')[:50]
        result = []
        for m in reversed(list(msgs)):
            deleted = m.deleted_at is not None
            result.append({
                'id': m.id,
                'username': m.user.username,
                'avatar_url': self._avatar_url(m.user),
                'content': m.content if not deleted else '',
                'image_url': (m.image.url if m.image else '') if not deleted else '',
                'video_url': (m.video.url if m.video else '') if not deleted else '',
                'created_at': m.created_at.isoformat(),
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                'deleted_at': m.deleted_at.isoformat() if m.deleted_at else None,
            })
        return result

    @database_sync_to_async
    def get_image_message(self, message_id):
        try:
            msg = ChatMessage.objects.select_related('user').get(
                id=message_id, server_id=self.server_id, user=self.user
            )
        except ChatMessage.DoesNotExist:
            return None
        return {
            'id': msg.id,
            'username': msg.user.username,
            'avatar_url': self._avatar_url(msg.user),
            'content': msg.content,
            'image_url': msg.image.url if msg.image else '',
            'video_url': msg.video.url if msg.video else '',
            'created_at': msg.created_at.isoformat(),
        }

    @database_sync_to_async
    def save_message(self, content):
        msg = ChatMessage.objects.create(
            server_id=self.server_id, user=self.user, content=content[:2000]
        )
        return {
            'id': msg.id,
            'username': self.user.username,
            'avatar_url': self._avatar_url(self.user),
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
        }

    @database_sync_to_async
    def do_edit_message(self, message_id, new_content):
        from django.utils import timezone
        cutoff = timezone.now() - timedelta(seconds=EDIT_WINDOW_SECONDS)
        try:
            msg = ChatMessage.objects.get(
                id=message_id,
                server_id=self.server_id,
                user=self.user,
                deleted_at__isnull=True,
                created_at__gte=cutoff,
            )
        except ChatMessage.DoesNotExist:
            return None
        msg.content = new_content[:2000]
        msg.updated_at = timezone.now()
        msg.save(update_fields=['content', 'updated_at'])
        return {
            'id': msg.id,
            'content': msg.content,
            'updated_at': msg.updated_at.isoformat(),
        }

    @database_sync_to_async
    def do_delete_message(self, message_id):
        from django.utils import timezone
        try:
            msg = ChatMessage.objects.get(
                id=message_id,
                server_id=self.server_id,
                user=self.user,
                deleted_at__isnull=True,
            )
        except ChatMessage.DoesNotExist:
            return False
        msg.deleted_at = timezone.now()
        msg.save(update_fields=['deleted_at'])
        return True

    @database_sync_to_async
    def get_history_page(self, before_id):
        msgs = ChatMessage.objects.filter(
            server__slug=self.server_slug,
            id__lt=before_id,
        ).select_related('user').order_by('-created_at')[:50]
        msgs_list = list(msgs)
        result = []
        for m in reversed(msgs_list):
            deleted = m.deleted_at is not None
            result.append({
                'id': m.id,
                'username': m.user.username,
                'avatar_url': self._avatar_url(m.user),
                'content': m.content if not deleted else '',
                'image_url': (m.image.url if m.image else '') if not deleted else '',
                'video_url': (m.video.url if m.video else '') if not deleted else '',
                'created_at': m.created_at.isoformat(),
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                'deleted_at': m.deleted_at.isoformat() if m.deleted_at else None,
            })
        return {'messages': result, 'has_more': len(msgs_list) == 50}


class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['slug']
        self.room_group = f'room_{self.room_slug}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        self.join_seq = int(time.monotonic() * 1000)

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        # Room is no longer empty
        await self.clear_last_empty_at()

        # Tell this client its own channel name before the group broadcast
        await self.send(text_data=json.dumps({
            'type': 'my_channel',
            'channel': self.channel_name,
        }))

        avatar_url = self.user.avatar.url if self.user.avatar else None
        await self.channel_layer.group_send(self.room_group, {
            'type': 'user_joined',
            'username': self.user.username,
            'channel': self.channel_name,
            'seq': self.join_seq,
            'avatar_url': avatar_url,
        })

    async def disconnect(self, code):
        if not hasattr(self, 'room_group') or not self.user.is_authenticated:
            return

        await self.channel_layer.group_discard(self.room_group, self.channel_name)
        await self.channel_layer.group_send(self.room_group, {
            'type': 'user_left',
            'username': self.user.username,
            'channel': self.channel_name,
            'seq': self.join_seq,
        })
        await self.remove_self()
        await self.check_room_empty()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type in ('offer', 'answer', 'ice-candidate'):
            target = data.get('target')
            if not target:
                return
            avatar_url = self.user.avatar.url if self.user.avatar else None
            await self.channel_layer.send(target, {
                'type': 'signal',
                'signal_type': msg_type,
                'payload': data.get('payload'),
                'sender': self.channel_name,
                'username': self.user.username,
                'avatar_url': avatar_url,
                'seq': self.join_seq,
            })

        elif msg_type == 'device_update':
            await self.save_device_selection(data)

        elif msg_type == 'media_state':
            await self.channel_layer.group_send(self.room_group, {
                'type': 'media_state',
                'channel': self.channel_name,
                'mic': data.get('mic'),
                'cam': data.get('cam'),
            })

        elif msg_type == 'kick':
            if await self.is_host():
                target_channel = data.get('target_channel')
                target_username = data.get('username')
                await self.remove_participant(target_username)
                await self.channel_layer.send(target_channel, {'type': 'kicked'})
                await self.channel_layer.group_send(self.room_group, {
                    'type': 'user_left',
                    'username': target_username,
                    'channel': target_channel,
                    'seq': 0,
                })

        elif msg_type == 'mute_user':
            if await self.is_host():
                target_channel = data.get('target_channel')
                await self.channel_layer.send(target_channel, {'type': 'force_mute'})

    # ---- group message handlers ----

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'username': event['username'],
            'channel': event['channel'],
            'seq': event['seq'],
            'avatar_url': event.get('avatar_url'),
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'username': event['username'],
            'channel': event['channel'],
            'seq': event['seq'],
        }))

    async def signal(self, event):
        await self.send(text_data=json.dumps({
            'type': event['signal_type'],
            'payload': event['payload'],
            'sender': event['sender'],
            'username': event['username'],
            'avatar_url': event.get('avatar_url'),
            'seq': event.get('seq'),
        }))

    async def kicked(self, event):
        await self.send(text_data=json.dumps({'type': 'kicked'}))
        await self.close()

    async def force_mute(self, event):
        await self.send(text_data=json.dumps({'type': 'force_mute'}))

    async def media_state(self, event):
        await self.send(text_data=json.dumps({
            'type': 'media_state',
            'channel': event['channel'],
            'mic': event['mic'],
            'cam': event['cam'],
        }))

    async def room_closed(self, event):
        await self.send(text_data=json.dumps({'type': 'room_closed'}))
        await self.close()

    # ---- helpers ----

    @database_sync_to_async
    def is_host(self):
        return Room.objects.filter(slug=self.room_slug, host=self.user).exists()

    @database_sync_to_async
    def remove_participant(self, username):
        RoomParticipant.objects.filter(
            room__slug=self.room_slug, user__username=username
        ).delete()

    @database_sync_to_async
    def remove_self(self):
        RoomParticipant.objects.filter(
            room__slug=self.room_slug, user=self.user
        ).delete()

    @database_sync_to_async
    def save_device_selection(self, data):
        camera_id = str(data.get('cameraId', ''))[:255]
        mic_id = str(data.get('microphoneId', ''))[:255]
        RoomParticipant.objects.filter(
            room__slug=self.room_slug, user=self.user
        ).update(
            camera_device_id=camera_id,
            microphone_device_id=mic_id,
        )

    @database_sync_to_async
    def clear_last_empty_at(self):
        Room.objects.filter(slug=self.room_slug).update(last_empty_at=None)

    @database_sync_to_async
    def check_room_empty(self):
        from django.utils import timezone
        room = Room.objects.filter(slug=self.room_slug, is_active=True).first()
        if room and not RoomParticipant.objects.filter(room=room).exists():
            room.last_empty_at = timezone.now()
            room.save(update_fields=['last_empty_at'])


class RoomChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['slug']
        self.chat_group = f'room_chat_{self.room_slug}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await self.is_participant():
            await self.close()
            return

        await self.channel_layer.group_add(self.chat_group, self.channel_name)
        await self.accept()

        history = await self.get_history()
        await self.send(text_data=json.dumps({
            'type': 'history',
            'messages': history,
            'has_more': len(history) == 50,
        }))

    async def disconnect(self, code):
        if hasattr(self, 'chat_group'):
            await self.channel_layer.group_discard(self.chat_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'chat_message':
            content = data.get('content', '').strip()
            if not content:
                return
            if await sync_to_async(is_rate_limited)('room_chat', self.user.pk, '30/m'):
                return
            msg = await self.save_message(content)
            await self.channel_layer.group_send(self.chat_group, {
                'type': 'chat_message',
                'id': msg['id'],
                'username': msg['username'],
                'avatar_url': msg['avatar_url'],
                'content': msg['content'],
                'created_at': msg['created_at'],
            })

        elif msg_type == 'typing':
            await self.channel_layer.group_send(self.chat_group, {
                'type': 'user_typing',
                'username': self.user.username,
                'exclude': self.channel_name,
            })

        elif msg_type == 'edit_message':
            message_id = data.get('message_id')
            new_content = data.get('content', '').strip()
            if not message_id or not new_content:
                return
            result = await self.do_edit_message(message_id, new_content)
            if result:
                await self.channel_layer.group_send(self.chat_group, {
                    'type': 'message_edited',
                    'id': result['id'],
                    'content': result['content'],
                    'updated_at': result['updated_at'],
                })

        elif msg_type == 'delete_message':
            message_id = data.get('message_id')
            if not message_id:
                return
            if await self.do_delete_message(message_id):
                await self.channel_layer.group_send(self.chat_group, {
                    'type': 'message_deleted',
                    'id': message_id,
                })

        elif msg_type == 'load_history':
            before_id = data.get('before_id')
            if not before_id:
                return
            page = await self.get_history_page(before_id)
            await self.send(text_data=json.dumps({
                'type': 'history_page',
                'messages': page['messages'],
                'has_more': page['has_more'],
            }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'id': event['id'],
            'username': event['username'],
            'avatar_url': event['avatar_url'],
            'content': event['content'],
            'created_at': event['created_at'],
        }))

    async def user_typing(self, event):
        if event.get('exclude') == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'username': event['username'],
        }))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'id': event['id'],
            'content': event['content'],
            'updated_at': event['updated_at'],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'id': event['id'],
        }))

    @database_sync_to_async
    def is_participant(self):
        try:
            rp = RoomParticipant.objects.select_related('room').get(
                room__slug=self.room_slug, user=self.user, room__is_active=True
            )
            self.room_id = rp.room_id
            return True
        except RoomParticipant.DoesNotExist:
            return False

    @staticmethod
    def _avatar_url(user):
        if user.avatar and hasattr(user.avatar, 'url'):
            return user.avatar.url
        return ''

    @database_sync_to_async
    def get_history(self):
        msgs = RoomChatMessage.objects.filter(
            room__slug=self.room_slug
        ).select_related('user').order_by('-created_at')[:50]
        result = []
        for m in reversed(list(msgs)):
            deleted = m.deleted_at is not None
            result.append({
                'id': m.id,
                'username': m.user.username,
                'avatar_url': self._avatar_url(m.user),
                'content': m.content if not deleted else '',
                'created_at': m.created_at.isoformat(),
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                'deleted_at': m.deleted_at.isoformat() if m.deleted_at else None,
            })
        return result

    @database_sync_to_async
    def save_message(self, content):
        msg = RoomChatMessage.objects.create(
            room_id=self.room_id, user=self.user, content=content[:2000]
        )
        return {
            'id': msg.id,
            'username': self.user.username,
            'avatar_url': self._avatar_url(self.user),
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
        }

    @database_sync_to_async
    def do_edit_message(self, message_id, new_content):
        from django.utils import timezone
        cutoff = timezone.now() - timedelta(seconds=EDIT_WINDOW_SECONDS)
        try:
            msg = RoomChatMessage.objects.get(
                id=message_id,
                room_id=self.room_id,
                user=self.user,
                deleted_at__isnull=True,
                created_at__gte=cutoff,
            )
        except RoomChatMessage.DoesNotExist:
            return None
        msg.content = new_content[:2000]
        msg.updated_at = timezone.now()
        msg.save(update_fields=['content', 'updated_at'])
        return {
            'id': msg.id,
            'content': msg.content,
            'updated_at': msg.updated_at.isoformat(),
        }

    @database_sync_to_async
    def do_delete_message(self, message_id):
        from django.utils import timezone
        try:
            msg = RoomChatMessage.objects.get(
                id=message_id,
                room_id=self.room_id,
                user=self.user,
                deleted_at__isnull=True,
            )
        except RoomChatMessage.DoesNotExist:
            return False
        msg.deleted_at = timezone.now()
        msg.save(update_fields=['deleted_at'])
        return True

    @database_sync_to_async
    def get_history_page(self, before_id):
        msgs = RoomChatMessage.objects.filter(
            room__slug=self.room_slug,
            id__lt=before_id,
        ).select_related('user').order_by('-created_at')[:50]
        msgs_list = list(msgs)
        result = []
        for m in reversed(msgs_list):
            deleted = m.deleted_at is not None
            result.append({
                'id': m.id,
                'username': m.user.username,
                'avatar_url': self._avatar_url(m.user),
                'content': m.content if not deleted else '',
                'created_at': m.created_at.isoformat(),
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                'deleted_at': m.deleted_at.isoformat() if m.deleted_at else None,
            })
        return {'messages': result, 'has_more': len(msgs_list) == 50}
