# Performance, Scale & Video Chat — Design Spec

**Date:** 2026-04-20
**Scope:** Phase 3-A — DB indexes, PostgreSQL connection tuning, video messages in server chat
**Target deployment:** Single-server, single Daphne process, thousands of concurrent users

---

## Context

Chat Hub is a Django + Django Channels + WebRTC application. The real-time layer runs over Redis. This spec addresses the three highest-impact changes for handling thousands of concurrent users:

1. Composite DB indexes on the hot chat history query paths
2. PostgreSQL persistent connection reuse (`CONN_MAX_AGE`)
3. Video file uploads in server chat (alongside existing image support), capped at 25 MB

No new pip dependencies. No new infrastructure beyond what is already in place.

---

## 1. DB Indexes

### Problem

The two most frequent DB queries in the consumer layer are full-table scans at scale:

```python
# get_history()
ChatMessage.objects.filter(server__slug=...).order_by('-created_at')[:50]

# get_history_page()
ChatMessage.objects.filter(server__slug=..., id__lt=...).order_by('-created_at')[:50]
```

Without a composite index on `(server_id, created_at)`, both queries scan the entire `chat_messages` table as message volume grows. Same pattern applies to `RoomChatMessage`.

### Changes

**`apps/rooms/models.py`** — add `Meta.indexes` to three models:

```python
class ChatMessage(models.Model):
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['server', '-created_at'], name='chat_server_created_idx'),
        ]

class RoomChatMessage(models.Model):
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', '-created_at'], name='roomchat_room_created_idx'),
        ]

class Room(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['server', 'is_active'], name='room_server_active_idx'),
        ]
```

**Migration:** `apps/rooms/migrations/0011_add_indexes.py`

`ServerMember` and `RoomParticipant` already have composite indexes from `unique_together` — no changes.

---

## 2. PostgreSQL Connection Tuning

### Problem

Django's default `CONN_MAX_AGE=0` opens and closes a PostgreSQL connection on every database operation. Under thousands of concurrent users, this creates constant TCP + PG auth overhead.

### Changes

Add `CONN_MAX_AGE` to `config/settings/production.py` and `config/settings/allinone.py`:

```python
DATABASES = {
    'default': {
        # ... existing fields ...
        'CONN_MAX_AGE': 600,  # reuse connections for up to 10 minutes
    }
}
```

- **Not added to `development.py`** — SQLite ignores it; explicit scoping is cleaner.
- **600 seconds** — long enough to amortise connection setup across many requests; short enough that idle connections don't accumulate.
- No migration required. No new dependencies.

---

## 3. Video Messages in Server Chat

### Problem

Chat currently supports image uploads only (5 MB cap). Users want to send short video clips in server chat alongside images, displayed inline with a video player.

### Constraints

- Video files capped at **25 MB**
- Images retain their existing **5 MB** cap
- Accepted video MIME types: `video/mp4`, `video/webm`, `video/ogg`
- No new pip dependencies
- Storage: S3 in production (existing `chat_videos/` prefix), local filesystem in allinone

### Model

New field on `ChatMessage`, migration `0012`:

```python
video = models.FileField(upload_to='chat_videos/', blank=True, null=True)
```

A message has at most one media field (`image` or `video`) populated. Text `content` may coexist with either (caption). The `image` field is unchanged.

### Upload Endpoint (`/servers/<uuid>/chat/upload/`)

Extended to accept video files alongside images. Branching logic:

| File type | Size limit | Saved to |
|---|---|---|
| `image/*` | 5 MB | `msg.image` |
| `video/mp4`, `video/webm`, `video/ogg` | 25 MB | `msg.video` |
| anything else | — | 400 rejected |

Response gains a `media_type` field:
```json
{"message_id": 42, "media_type": "image"}
{"message_id": 43, "media_type": "video"}
```

Error responses (JSON, matching existing pattern):

| Condition | Status | Body |
|---|---|---|
| File exceeds limit | 400 | `{"error": "file_too_large"}` |
| Unsupported MIME type | 400 | `{"error": "unsupported_file_type"}` |
| Rate limit | 429 | `{"error": "rate_limited"}` |

### WebSocket Protocol

No new message types. The existing `chat_image` send flow is reused for video:
1. Client uploads file via HTTP POST → receives `message_id`
2. Client sends `{type: "chat_image", message_id: ...}` via WebSocket
3. Server looks up the `ChatMessage` record and broadcasts to the group

The broadcast payload gains one field:

```json
{
  "type": "chat_message",
  "id": 43,
  "username": "alice",
  "avatar_url": "...",
  "content": "",
  "image_url": "",
  "video_url": "https://...",
  "created_at": "..."
}
```

Exactly one of `image_url` / `video_url` is non-empty per media message. Both fields are included in `history` and `history_page` payloads.

### Consumer Changes

- `get_image_message()` — returns `video_url` alongside `image_url`
- `get_history()` — includes `video_url` in each message dict
- `get_history_page()` — same
- `chat_message` group event handler — forwards `video_url`

### Frontend (`server_detail.html`)

Three targeted changes to the existing inline script:

1. **Upload input** — `accept` attribute extended:
   ```
   image/jpeg,image/png,image/gif,image/webp,video/mp4,video/webm,video/ogg
   ```
   Client-side size check branches on file type: 5 MB for images, 25 MB for video. Error shown via `showToast()`.

2. **Preview area** — images show existing `<img>` preview; videos show a muted `<video>` element as preview before upload.

3. **`buildContentHtml()`** — extended to render video:
   ```javascript
   if (msg.video_url) {
       html += `<video controls style="max-width:100%;border-radius:var(--radius-sm)">
                  <source src="${escapeHtml(msg.video_url)}">
                </video>`;
   }
   ```

---

## 4. Testing

Handled by `django-test-engineer` agent after implementation. Key coverage:

- Migration `0011` applies cleanly; indexes exist in schema
- Migration `0012` applies cleanly; `video` field exists on `ChatMessage`
- `CONN_MAX_AGE` present in production and allinone settings
- Video upload accepted within 25 MB
- Video upload rejected above 25 MB (`{"error": "file_too_large"}`)
- Image upload still enforced at 5 MB
- Unsupported MIME type returns 400 `{"error": "unsupported_file_type"}`
- Consumer `get_history()` includes `video_url` key on all messages
- `chat_image` broadcast includes non-empty `video_url` for video messages

---

## Migrations

| Number | File | Content |
|---|---|---|
| `0011` | `apps/rooms/migrations/0011_add_indexes.py` | Composite indexes on `ChatMessage`, `RoomChatMessage`, `Room` |
| `0012` | `apps/rooms/migrations/0012_chatmessage_video.py` | `video` field on `ChatMessage` |

---

## Out of Scope

- Video in room chat (`RoomChatMessage`) — can be added in a follow-up; same pattern applies
- Video transcoding / thumbnail generation — requires background task infrastructure not in this stack
- Direct-to-S3 browser uploads — 25 MB through Django is acceptable; revisit if upload latency becomes an issue
- PgBouncer — recommended follow-on if PostgreSQL `max_connections` becomes a bottleneck
- Redis membership caching — recommended follow-on if WS connect latency becomes measurable
