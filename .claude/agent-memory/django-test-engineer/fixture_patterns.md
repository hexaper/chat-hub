---
name: fixture_patterns
description: Reusable fixture structures for consumer and view tests in this codebase
type: project
---

## Minimal server-chat fixture (ConsumerTests.setUp)
```python
self.user = User.objects.create_user(username='user1', password='Tester123.')
self.other = User.objects.create_user(username='user2', password='Tester123.')
self.server = Server.objects.create(name='Server', owner=self.other)
ServerMember.objects.create(server=self.server, user=self.other)
```
- `self.user` is NOT a member by default — individual tests add membership with `get_or_create`.
- `self.other` IS a member (and owner).
- Standard password: `'Tester123.'` (meets complexity requirements).

## Fully membered server for broadcast tests
```python
ServerMember.objects.get_or_create(server=self.server, user=self.user)
ServerMember.objects.get_or_create(server=self.server, user=self.other)
transaction.commit()
```

## Room fixture (RoomConsumerTests.setUp)
```python
self.host = User.objects.create_user(username='host', password='Tester123.')
self.peer = User.objects.create_user(username='peer', password='Tester123.')
self.server = Server.objects.create(name='TestServer', owner=self.host)
ServerMember.objects.create(server=self.server, user=self.host)
ServerMember.objects.create(server=self.server, user=self.peer)
self.room = Room.objects.create(name='TestRoom', server=self.server, host=self.host)
```

## ChatMessage with image (for history/image tests)
```python
from django.core.files.uploadedfile import SimpleUploadedFile
image_file = SimpleUploadedFile('test.png', b'PNGDATA', content_type='image/png')
msg = ChatMessage.objects.create(server=self.server, user=self.user, content='hello', image=image_file)
```

## ChatMessage with past created_at (for edit window tests)
```python
old_created_at = timezone.now() - timedelta(minutes=16)
msg = ChatMessage.objects.create(server=self.server, user=self.user, content='old')
ChatMessage.objects.filter(pk=msg.pk).update(created_at=old_created_at)
msg.refresh_from_db()
transaction.commit()
```

## Already-deleted ChatMessage
```python
msg = ChatMessage.objects.create(
    server=self.server,
    user=self.user,
    content='gone',
    deleted_at=timezone.now(),
)
```

## RoomChatConsumer fixture (RoomChatConsumerTests.setUp)
RoomChatConsumer checks `RoomParticipant` on connect — both users must be participants, and
`room.is_active` must be True (it defaults True on Room creation).
```python
self.author = User.objects.create_user(username='rc_author', password='Tester123.')
self.other  = User.objects.create_user(username='rc_other',  password='Tester123.')
self.server = Server.objects.create(name='RCServer', owner=self.author)
ServerMember.objects.create(server=self.server, user=self.author)
ServerMember.objects.create(server=self.server, user=self.other)
self.room = Room.objects.create(name='RCRoom', server=self.server, host=self.author)
RoomParticipant.objects.create(room=self.room, user=self.author)
RoomParticipant.objects.create(room=self.room, user=self.other)
```
- `RoomChatMessage` (not `ChatMessage`) is the model; must be imported from `apps.rooms.models`.
- The consumer stores `self.room_id` (set inside `is_participant()`); all DB queries scope by `room_id`.

## RoomChatMessage with past created_at (for edit window tests)
```python
msg = RoomChatMessage.objects.create(room=self.room, user=self.author, content='old')
RoomChatMessage.objects.filter(pk=msg.pk).update(created_at=timezone.now() - timedelta(minutes=16))
msg.refresh_from_db()
transaction.commit()
```

## URL patterns
- Server chat consumer: `/ws/chat/<server.slug>/`
- Room consumer: `/ws/rooms/<room.slug>/`
- Room chat consumer: `/ws/room-chat/<room.slug>/`
