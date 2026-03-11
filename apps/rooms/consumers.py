import json
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Room, RoomParticipant, Server, ServerMember, ChatMessage


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

        # Send recent message history
        history = await self.get_history()
        await self.send(text_data=json.dumps({
            'type': 'history',
            'messages': history,
        }))

    async def disconnect(self, code):
        if hasattr(self, 'chat_group'):
            await self.channel_layer.group_discard(self.chat_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('type') != 'chat_message':
            return

        content = data.get('content', '').strip()
        if not content:
            return

        msg = await self.save_message(content)

        await self.channel_layer.group_send(self.chat_group, {
            'type': 'chat_message',
            'id': msg['id'],
            'username': msg['username'],
            'content': msg['content'],
            'created_at': msg['created_at'],
        })

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'id': event['id'],
            'username': event['username'],
            'content': event['content'],
            'created_at': event['created_at'],
        }))

    @database_sync_to_async
    def is_member(self):
        return ServerMember.objects.filter(
            server__slug=self.server_slug, user=self.user
        ).exists()

    @database_sync_to_async
    def get_history(self):
        msgs = ChatMessage.objects.filter(
            server__slug=self.server_slug
        ).select_related('user').order_by('-created_at')[:50]
        return [
            {
                'id': m.id,
                'username': m.user.username,
                'content': m.content,
                'created_at': m.created_at.isoformat(),
            }
            for m in reversed(msgs)
        ]

    @database_sync_to_async
    def save_message(self, content):
        server = Server.objects.get(slug=self.server_slug)
        msg = ChatMessage.objects.create(
            server=server, user=self.user, content=content[:2000]
        )
        return {
            'id': msg.id,
            'username': self.user.username,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
        }


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

        await self.channel_layer.group_send(self.room_group, {
            'type': 'user_joined',
            'username': self.user.username,
            'channel': self.channel_name,
            'seq': self.join_seq,
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
            await self.channel_layer.send(target, {
                'type': 'signal',
                'signal_type': msg_type,
                'payload': data.get('payload'),
                'sender': self.channel_name,
                'username': self.user.username,
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
