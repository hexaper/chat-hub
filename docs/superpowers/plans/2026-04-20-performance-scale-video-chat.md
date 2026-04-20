# Performance, Scale & Video Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add composite DB indexes for chat query performance, PostgreSQL connection reuse, and inline video message support in server chat.

**Architecture:** Three independent changes landed in sequence: (1) composite indexes on `ChatMessage`, `RoomChatMessage`, and `Room` turn full-table scans into index scans as message volume grows; (2) `CONN_MAX_AGE=600` in production/allinone settings reuses PostgreSQL connections instead of recreating them per operation; (3) video upload support extends the existing image upload view, adds a `video` field to `ChatMessage`, threads `video_url` through `ServerChatConsumer`, and renders a `<video>` player in `server_detail.html`.

**Tech Stack:** Django 5.2, Django Channels 4.3, Pillow (existing), Bootstrap 5, vanilla JS. No new pip packages.

**Spec:** `docs/superpowers/specs/2026-04-20-performance-scale-video-chat-design.md`

**Test runner:** `source venv/bin/activate && python manage.py test <target> --settings=config.settings.development --keepdb`

---

## File Map

| File | Change |
|---|---|
| `apps/rooms/models.py` | Add `Meta.indexes` to `ChatMessage`, `RoomChatMessage`, `Room`; add `video` FileField to `ChatMessage` |
| `apps/rooms/migrations/0011_add_indexes.py` | Create — composite indexes migration |
| `apps/rooms/migrations/0012_chatmessage_video.py` | Create — video field migration |
| `config/settings/production.py` | Add `CONN_MAX_AGE: 600` to `DATABASES['default']` |
| `config/settings/allinone.py` | Add `CONN_MAX_AGE: 600` to `DATABASES['default']` |
| `apps/rooms/views.py` | Extend `chat_image_upload` to also accept video files |
| `apps/rooms/consumers.py` | Add `video_url` to `get_image_message`, `get_history`, `get_history_page`, `chat_message` group sends and handler |
| `templates/rooms/server_detail.html` | Accept video in file input, video preview, `<video>` player in `buildContentHtml` |
| `apps/rooms/tests/test_models.py` | Add `IndexMetaTests` class |
| `apps/rooms/tests/test_views_extended.py` | Add video upload tests to `RoomViewTests` |
| `apps/rooms/tests/test_consumers.py` | Add `video_url` history key test to `ConsumerTests` |

---

### Task 1: DB Indexes

**Files:**
- Modify: `apps/rooms/models.py`
- Create: `apps/rooms/migrations/0011_add_indexes.py` (via makemigrations)
- Test: `apps/rooms/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Append a new test class to `apps/rooms/tests/test_models.py`:

```python
from apps.rooms.models import Server, Room, ChatMessage, RoomChatMessage, generate_invite_code


class IndexMetaTests(TestCase):
    """Verify composite indexes declared on model Meta are present."""

    def test_chatmessage_has_server_created_index(self):
        index_names = [idx.name for idx in ChatMessage._meta.indexes]
        self.assertIn('chat_server_created_idx', index_names)

    def test_roomchatmessage_has_room_created_index(self):
        index_names = [idx.name for idx in RoomChatMessage._meta.indexes]
        self.assertIn('roomchat_room_created_idx', index_names)

    def test_room_has_server_active_index(self):
        index_names = [idx.name for idx in Room._meta.indexes]
        self.assertIn('room_server_active_idx', index_names)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate
python manage.py test apps.rooms.tests.test_models.IndexMetaTests \
  --settings=config.settings.development --keepdb
```

Expected: 3 failures — `AssertionError: 'chat_server_created_idx' not found in []`

- [ ] **Step 3: Add indexes to models**

In `apps/rooms/models.py`, add `indexes` to the `Meta` of three models. The existing `Meta` classes only have `ordering`; add `indexes` alongside it:

```python
class ChatMessage(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
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
```

For `Room`, find its existing `Meta` (it currently has no `Meta` class — add one):

```python
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
    # ... rest of model unchanged
```

- [ ] **Step 4: Generate migration**

```bash
python manage.py makemigrations --settings=config.settings.development
```

Expected output: `Migrations for 'rooms': apps/rooms/migrations/0011_...py`

The generated file name will contain the index names. Verify it exists:

```bash
ls apps/rooms/migrations/0011_*
```

- [ ] **Step 5: Apply migration**

```bash
python manage.py migrate --settings=config.settings.development
```

Expected: `Applying rooms.0011_... OK`

- [ ] **Step 6: Run tests to verify they pass**

```bash
python manage.py test apps.rooms.tests.test_models.IndexMetaTests \
  --settings=config.settings.development --keepdb
```

Expected: `Ran 3 tests in ...s — OK`

- [ ] **Step 7: Commit**

```bash
git add apps/rooms/models.py apps/rooms/migrations/0011_*.py \
        apps/rooms/tests/test_models.py
git commit -m "perf: add composite indexes on ChatMessage, RoomChatMessage, Room"
```

---

### Task 2: PostgreSQL CONN_MAX_AGE

**Files:**
- Modify: `config/settings/production.py`
- Modify: `config/settings/allinone.py`

No unit test — this is a settings value that takes effect at runtime with a live PostgreSQL connection (not exercisable in the SQLite dev test suite).

- [ ] **Step 1: Edit production.py**

In `config/settings/production.py`, locate the `DATABASES` dict and add `'CONN_MAX_AGE': 600`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['POSTGRES_NAME'],
        'USER': os.environ['POSTGRES_USER'],
        'PASSWORD': os.environ['POSTGRES_PASS'],
        'HOST': os.environ['POSTGRES_HOST'],
        'OPTIONS': {'sslmode': 'require'},
        'CONN_MAX_AGE': 600,
    }
}
```

- [ ] **Step 2: Edit allinone.py**

In `config/settings/allinone.py`, locate the `DATABASES` dict and add `'CONN_MAX_AGE': 600`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'videocall'),
        'USER': os.environ.get('DB_USER', 'videocall'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'videocall'),
        'HOST': 'localhost',
        'PORT': '5432',
        'CONN_MAX_AGE': 600,
    }
}
```

- [ ] **Step 3: Verify**

```bash
python -c "
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'
os.environ.setdefault('SECRET_KEY', 'x')
os.environ.setdefault('POSTGRES_NAME', 'x')
os.environ.setdefault('POSTGRES_USER', 'x')
os.environ.setdefault('POSTGRES_PASS', 'x')
os.environ.setdefault('POSTGRES_HOST', 'x')
os.environ.setdefault('REDIS_HOST', 'redis://x')
os.environ.setdefault('AWS_STORAGE_BUCKET_NAME', 'x')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'x')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'x')
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['CONN_MAX_AGE'] == 600, 'MISSING'
print('production.py OK')
"
```

Expected: `production.py OK`

- [ ] **Step 4: Commit**

```bash
git add config/settings/production.py config/settings/allinone.py
git commit -m "perf: set CONN_MAX_AGE=600 for PostgreSQL connection reuse"
```

---

### Task 3: Video field + upload endpoint

**Files:**
- Modify: `apps/rooms/models.py` (add `video` field to `ChatMessage`)
- Create: `apps/rooms/migrations/0012_chatmessage_video.py` (via makemigrations)
- Modify: `apps/rooms/views.py` (extend `chat_image_upload`)
- Test: `apps/rooms/tests/test_views_extended.py`

- [ ] **Step 1: Write failing tests**

Append to `apps/rooms/tests/test_views_extended.py`, inside the existing `RoomViewTests` class (after the last existing test method):

```python
    # ── Video upload tests ────────────────────────────────────────────────────

    def test_video_upload_success(self):
        """Video within 25 MB is accepted; response includes message_id and media_type."""
        ServerMember.objects.create(server=self.server, user=self.user)
        self.client.login(username='testuser', password='Tester123.')
        video = SimpleUploadedFile('clip.mp4', b'\x00' * 1024, content_type='video/mp4')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'video': video},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['media_type'], 'video')
        self.assertIn('message_id', data)

    def test_video_upload_too_large_rejected(self):
        """Video exceeding 25 MB returns 400 with error=file_too_large."""
        ServerMember.objects.create(server=self.server, user=self.user)
        self.client.login(username='testuser', password='Tester123.')
        big = SimpleUploadedFile('big.mp4', b'\x00' * (26 * 1024 * 1024), content_type='video/mp4')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'video': big},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'file_too_large')

    def test_unsupported_mime_type_rejected(self):
        """A non-image, non-video file returns 400 with error=unsupported_file_type."""
        ServerMember.objects.create(server=self.server, user=self.user)
        self.client.login(username='testuser', password='Tester123.')
        bad = SimpleUploadedFile('script.exe', b'\x00' * 512, content_type='application/octet-stream')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'video': bad},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'unsupported_file_type')

    def test_image_upload_still_returns_media_type(self):
        """Existing image upload now also returns media_type='image'."""
        ServerMember.objects.create(server=self.server, user=self.user)
        self.client.login(username='testuser', password='Tester123.')
        image = SimpleUploadedFile('pic.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'image': image},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['media_type'], 'image')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests.test_video_upload_success \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_video_upload_too_large_rejected \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_unsupported_mime_type_rejected \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_image_upload_still_returns_media_type \
  --settings=config.settings.development --keepdb
```

Expected: 4 failures (400 or missing `media_type` key).

- [ ] **Step 3: Add video field to ChatMessage model**

In `apps/rooms/models.py`, add the `video` field to `ChatMessage` after the existing `image` field:

```python
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
```

- [ ] **Step 4: Generate and apply migration**

```bash
python manage.py makemigrations --settings=config.settings.development
python manage.py migrate --settings=config.settings.development
```

Expected: new migration `0012_chatmessage_video.py` created and applied.

- [ ] **Step 5: Extend the upload view**

Replace the entire `chat_image_upload` function in `apps/rooms/views.py` (lines ~299–335):

```python
# ── Chat media upload ─────────────────────────────────────────────────────────

_ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/ogg'}

@login_required
@require_post_method
@ratelimit(key='user', rate='10/m')
def chat_image_upload(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        return JsonResponse({'error': 'Not a member'}, status=403)

    image = request.FILES.get('image')
    video = request.FILES.get('video')

    if image:
        if image.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Image too large (max 5MB)'}, status=400)
        try:
            img = Image.open(image)
            img.verify()
            image.seek(0)
        except Exception:
            return JsonResponse({'error': 'Invalid image file'}, status=400)
        if img.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
            return JsonResponse({'error': 'Invalid image type'}, status=400)
        msg = ChatMessage.objects.create(server=server, user=request.user, image=image)
        return JsonResponse({'message_id': msg.id, 'media_type': 'image', 'image_url': msg.image.url})

    elif video:
        if video.content_type not in _ALLOWED_VIDEO_TYPES:
            return JsonResponse({'error': 'unsupported_file_type'}, status=400)
        if video.size > 25 * 1024 * 1024:
            return JsonResponse({'error': 'file_too_large'}, status=400)
        msg = ChatMessage.objects.create(server=server, user=request.user, video=video)
        return JsonResponse({'message_id': msg.id, 'media_type': 'video', 'video_url': msg.video.url})

    return JsonResponse({'error': 'No file provided'}, status=400)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests.test_video_upload_success \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_video_upload_too_large_rejected \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_unsupported_mime_type_rejected \
  apps.rooms.tests.test_views_extended.RoomViewTests.test_image_upload_still_returns_media_type \
  --settings=config.settings.development --keepdb
```

Expected: `Ran 4 tests in ...s — OK`

- [ ] **Step 7: Commit**

```bash
git add apps/rooms/models.py apps/rooms/migrations/0012_*.py \
        apps/rooms/views.py apps/rooms/tests/test_views_extended.py
git commit -m "feat: add video upload support to server chat (25 MB cap)"
```

---

### Task 4: Consumer video_url

**Files:**
- Modify: `apps/rooms/consumers.py`
- Test: `apps/rooms/tests/test_consumers.py`

- [ ] **Step 1: Write failing test**

Add to `ConsumerTests` class in `apps/rooms/tests/test_consumers.py` (after the last existing test method in that class, before `class RoomConsumerTests`):

```python
    def test_history_includes_video_url_field(self):
        """Each message in history payload must have a video_url key."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ChatMessage.objects.create(server=self.server, user=self.user, content='hello')
        from django.db import transaction
        transaction.commit()

        async def run():
            cookies = self._get_cookie_header(self.user)
            communicator = WebsocketCommunicator(
                self.application, f'/ws/chat/{self.server.slug}/'
            )
            communicator.scope['headers'] = cookies
            connected, _ = await communicator.connect()
            assert connected, 'Connection rejected'
            response = await communicator.receive_json_from()
            await communicator.disconnect()
            return response

        response = asyncio.run(run())
        self.assertEqual(response['type'], 'history')
        self.assertGreater(len(response['messages']), 0)
        for msg in response['messages']:
            self.assertIn('video_url', msg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_history_includes_video_url_field \
  --settings=config.settings.development --keepdb
```

Expected: `KeyError: 'video_url'` or `AssertionError`.

- [ ] **Step 3: Update consumers.py**

Four changes in `apps/rooms/consumers.py` inside `ServerChatConsumer`:

**3a. `get_history()`** — add `video_url` to the dict inside the loop:

```python
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
```

**3b. `get_image_message()`** — add `video_url` to the return dict:

```python
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
```

**3c. `get_history_page()`** — add `video_url`:

```python
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
```

**3d. `chat_message` group event handler** — forward `video_url`:

```python
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
```

Also add `'video_url': ''` to the `group_send` call for new text `chat_message` inside `receive()`:

```python
        if msg_type == 'chat_message':
            # ...
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
```

And add `'video_url': msg['video_url']` to the `chat_image` group_send:

```python
        elif msg_type == 'chat_image':
            # ...
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests.test_history_includes_video_url_field \
  --settings=config.settings.development --keepdb
```

Expected: `Ran 1 test in ...s — OK`

- [ ] **Step 5: Run full consumer test suite to check for regressions**

```bash
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests \
  --settings=config.settings.development --keepdb
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/rooms/consumers.py apps/rooms/tests/test_consumers.py
git commit -m "feat: thread video_url through ServerChatConsumer history and broadcast"
```

---

### Task 5: Frontend — video upload and playback

**Files:**
- Modify: `templates/rooms/server_detail.html`

No unit tests for template JS. Verified manually after server restart.

- [ ] **Step 1: Extend the file input to accept video**

In `templates/rooms/server_detail.html`, find:

```html
<input type="file" id="chatImageInput" accept="image/jpeg,image/png,image/gif,image/webp" class="d-none">
```

Replace with:

```html
<input type="file" id="chatImageInput" accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/webm,video/ogg" class="d-none">
```

- [ ] **Step 2: Update the client-side size check and preview**

In the JS block, find the `chatImageInput.addEventListener('change', ...)` handler and replace it:

```javascript
    chatImageInput.addEventListener('change', function() {
        const file = this.files[0];
        if (!file) return;
        const isVideo = file.type.startsWith('video/');
        const maxBytes = isVideo ? 25 * 1024 * 1024 : 5 * 1024 * 1024;
        const maxLabel = isVideo ? '25MB' : '5MB';
        if (file.size > maxBytes) {
            showToast(`File too large (max ${maxLabel})`, 'warning');
            this.value = '';
            return;
        }
        pendingFile = file;
        if (isVideo) {
            imagePreviewImg.style.display = 'none';
            // Show a simple video preview
            let previewVideo = imagePreview.querySelector('video');
            if (!previewVideo) {
                previewVideo = document.createElement('video');
                previewVideo.style.maxHeight = '80px';
                previewVideo.style.borderRadius = 'var(--radius-sm)';
                previewVideo.muted = true;
                imagePreview.insertBefore(previewVideo, imagePreviewImg);
            }
            previewVideo.src = URL.createObjectURL(file);
            previewVideo.style.display = '';
        } else {
            const previewVideo = imagePreview.querySelector('video');
            if (previewVideo) previewVideo.style.display = 'none';
            imagePreviewImg.style.display = '';
            imagePreviewImg.src = URL.createObjectURL(file);
        }
        imagePreview.classList.remove('d-none');
    });
```

- [ ] **Step 3: Update the preview clear handler**

Find `imagePreviewClear.addEventListener('click', ...)` and replace:

```javascript
    imagePreviewClear.addEventListener('click', function() {
        pendingFile = null;
        chatImageInput.value = '';
        imagePreview.classList.add('d-none');
        imagePreviewImg.style.display = '';
        imagePreviewImg.src = '';
        const previewVideo = imagePreview.querySelector('video');
        if (previewVideo) {
            previewVideo.src = '';
            previewVideo.style.display = 'none';
        }
    });
```

- [ ] **Step 4: Update uploadImage to use the correct form field**

Find the `async function uploadImage(file)` and replace it:

```javascript
    async function uploadImage(file) {
        const formData = new FormData();
        const isVideo = file.type.startsWith('video/');
        formData.append(isVideo ? 'video' : 'image', file);
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
        const resp = await fetch(`/servers/${SERVER_SLUG}/chat/upload/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken, 'Accept': 'application/json' },
            body: formData,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || 'Upload failed');
        }
        return resp.json();
    }
```

- [ ] **Step 5: Render video in buildContentHtml**

Find `function buildContentHtml(msg)` and replace it:

```javascript
    function buildContentHtml(msg) {
        if (msg.deleted_at) {
            return `<div class="chat-msg-content fst-italic" style="color:var(--text-muted)">Message deleted</div>`;
        }
        let html = '';
        if (msg.image_url) {
            html += `<a href="${escapeHtml(msg.image_url)}" target="_blank"><img src="${escapeHtml(msg.image_url)}" class="chat-image" alt="image"></a>`;
        }
        if (msg.video_url) {
            html += `<video controls style="max-width:100%;border-radius:var(--radius-sm);display:block;margin-top:4px">` +
                    `<source src="${escapeHtml(msg.video_url)}">` +
                    `</video>`;
        }
        if (msg.content) {
            html += `<div class="chat-msg-content">${escapeHtml(msg.content)}${msg.updated_at ? ' <small style="color:var(--text-muted)">(edited)</small>' : ''}</div>`;
        }
        return html;
    }
```

- [ ] **Step 6: Verify manually**

```bash
source venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

1. Open `http://localhost:8000`, log in, join a server
2. Click the image attachment button — file picker should accept `.mp4` files
3. Select a small `.mp4` — preview should appear
4. Send — video should appear inline in chat with controls
5. Refresh — video should still appear from history

- [ ] **Step 7: Commit**

```bash
git add templates/rooms/server_detail.html
git commit -m "feat: render video messages in server chat with inline player"
```

---

### Task 6: Full test suite

- [ ] **Step 1: Run full suite**

```bash
source venv/bin/activate
python manage.py test --settings=config.settings.development --keepdb
```

Expected: all tests pass. No regressions.

- [ ] **Step 2: If any failures, fix before proceeding**

Common causes:
- `KeyError: 'video_url'` in an existing consumer test → the `chat_message` event handler now always emits `video_url`; update any test that checks the exact dict structure.
- Image upload test checking for `'image_url'` in the response — the response still includes `image_url`; no change needed.

---

## Done

All three spec requirements are shipped:
- ✅ Composite indexes on `ChatMessage`, `RoomChatMessage`, `Room` (migration 0011)
- ✅ `CONN_MAX_AGE=600` in production and allinone settings
- ✅ Video messages in server chat: upload endpoint, model field, consumer, frontend player
