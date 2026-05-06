# Phase 1 Trust and Core UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add minimum viable server trust controls (roles + moderation), mentions, unread tracking, and basic chat search to make servers safe and usable for real communities.

**Architecture:** Extend existing `apps.rooms` models and consumers with small, explicit primitives: role field on `ServerMember`, moderation tables, mention/read-state tables, and server/room search endpoints. Keep WebSocket payload shape backward-compatible by only adding optional keys. Reuse current Django + Channels patterns (`database_sync_to_async`, server-rendered templates, focused Django tests).

**Tech Stack:** Django 5.2, Django Channels, Redis channel layer/cache, PostgreSQL/SQLite, vanilla JS in templates.

---

## Scope Check

The approved design spec contains three phases. This plan intentionally covers only **Phase 1** (trust + core UX) so it stays implementable and testable in one cycle. Create separate plans for Phase 2 and Phase 3 after this lands.

## File Structure

- Modify: `apps/rooms/models.py` (roles, moderation records, mentions, read-state)
- Create: `apps/rooms/permissions.py` (server permission helpers)
- Modify: `apps/rooms/views.py` (moderation endpoints, search endpoints, unread markers)
- Modify: `apps/rooms/urls.py` (new moderation/search routes)
- Modify: `apps/rooms/consumers.py` (mute/ban enforcement and mention metadata)
- Modify: `templates/rooms/server_settings.html` (role + moderation controls)
- Modify: `templates/rooms/server_detail.html` (mentions/unread badges/search UI hooks)
- Modify: `templates/rooms/room_detail.html` (mentions/unread badges/search UI hooks)
- Modify: `apps/rooms/tests/test_models.py`
- Modify: `apps/rooms/tests/test_permissions.py`
- Modify: `apps/rooms/tests/test_views_extended.py`
- Modify: `apps/rooms/tests/test_consumers.py`
- Create migration in `apps/rooms/migrations/`

### Task 1: Data Model Foundation (Roles, Moderation, Mentions, Read State)

**Files:**
- Modify: `apps/rooms/tests/test_models.py`
- Modify: `apps/rooms/models.py`
- Create: `apps/rooms/migrations/0013_phase1_trust_and_read_state.py`

- [ ] **Step 1: Write failing model tests**

```python
def test_server_member_defaults_to_member_role(self):
    member = ServerMember.objects.create(server=self.server, user=self.user)
    self.assertEqual(member.role, 'member')

def test_server_member_can_be_admin(self):
    member = ServerMember.objects.create(server=self.server, user=self.user, role='admin')
    self.assertEqual(member.role, 'admin')

def test_server_ban_blocks_duplicate_active_ban(self):
    ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.owner)
    with self.assertRaises(Exception):
        ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.owner)

def test_chat_read_state_stores_last_read_message(self):
    msg = ChatMessage.objects.create(server=self.server, user=self.user, content='hello')
    state = ChatReadState.objects.create(server=self.server, user=self.user, last_read_message=msg)
    self.assertEqual(state.last_read_message_id, msg.id)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_models --settings=config.settings.development`
Expected: FAIL with missing model/field errors for `role`, `ServerBan`, or `ChatReadState`.

- [ ] **Step 3: Implement model changes**

```python
class ServerMember(models.Model):
    ROLE_MEMBER = 'member'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = ((ROLE_MEMBER, 'Member'), (ROLE_ADMIN, 'Admin'))

    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    muted_until = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

class ServerBan(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='bans')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    banned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='issued_bans')
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
        (ACTION_BAN, 'Ban'), (ACTION_UNBAN, 'Unban'),
        (ACTION_MUTE, 'Mute'), (ACTION_UNMUTE, 'Unmute'),
        (ACTION_KICK, 'Kick'),
    )

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='moderation_actions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_actions_made')
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_actions_received')
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ChatMention(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='mentions')
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class RoomChatMention(models.Model):
    message = models.ForeignKey(RoomChatMessage, on_delete=models.CASCADE, related_name='mentions')
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

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
```

- [ ] **Step 4: Create and inspect migration**

Run: `source venv/bin/activate && python manage.py makemigrations rooms --settings=config.settings.development`
Expected: creates `apps/rooms/migrations/0013_phase1_trust_and_read_state.py` with added fields/models and constraints.

- [ ] **Step 5: Run model tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_models --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/models.py apps/rooms/tests/test_models.py apps/rooms/migrations/0013_phase1_trust_and_read_state.py
git commit -m "feat: add trust and read-state data models"
```

### Task 2: Server Permission Helpers and Role Management

**Files:**
- Create: `apps/rooms/permissions.py`
- Modify: `apps/rooms/tests/test_permissions.py`
- Modify: `apps/rooms/views.py`
- Modify: `apps/rooms/urls.py`

- [ ] **Step 1: Write failing permission tests**

```python
def test_admin_member_can_open_server_settings(self):
    membership = ServerMember.objects.create(server=self.server, user=self.user, role='admin')
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('server_settings', args=[self.server.slug]))
    self.assertEqual(response.status_code, 200)

def test_member_cannot_change_roles(self):
    self.server.members.add(self.user)
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.post(reverse('server_set_role', args=[self.server.slug]), {
        'user_id': self.other_user.id,
        'role': 'admin',
    })
    self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run permission tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_permissions --settings=config.settings.development`
Expected: FAIL because `server_set_role` route/helper behavior does not exist.

- [ ] **Step 3: Add permission helpers**

```python
# apps/rooms/permissions.py
from .models import ServerMember

def get_membership(server, user):
    if not user.is_authenticated:
        return None
    return ServerMember.objects.filter(server=server, user=user).first()

def is_server_owner(server, user):
    return user.is_authenticated and server.owner_id == user.id

def is_server_admin(server, user):
    membership = get_membership(server, user)
    return bool(membership and membership.role == ServerMember.ROLE_ADMIN)

def can_moderate_server(server, user):
    return is_server_owner(server, user) or is_server_admin(server, user) or user.is_staff
```

- [ ] **Step 4: Add role update endpoint and route**

```python
# apps/rooms/views.py
@login_required
@require_post_method
def server_set_role(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not can_moderate_server(server, request.user):
        return get_object_or_404(Server, slug='00000000-0000-0000-0000-000000000000')
    target = get_object_or_404(ServerMember, server=server, user_id=request.POST.get('user_id'))
    role = request.POST.get('role')
    if role not in {ServerMember.ROLE_MEMBER, ServerMember.ROLE_ADMIN}:
        messages.error(request, 'Invalid role.')
        return redirect('server_settings', server_slug=server.slug)
    if target.user_id == server.owner_id:
        messages.error(request, 'Owner role cannot be changed.')
        return redirect('server_settings', server_slug=server.slug)
    target.role = role
    target.save(update_fields=['role'])
    messages.success(request, 'Role updated.')
    return redirect('server_settings', server_slug=server.slug)

# apps/rooms/urls.py
path('servers/<uuid:server_slug>/settings/role/', views.server_set_role, name='server_set_role'),
```

- [ ] **Step 5: Run tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_permissions --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/permissions.py apps/rooms/views.py apps/rooms/urls.py apps/rooms/tests/test_permissions.py
git commit -m "feat: add server role permissions and role management endpoint"
```

### Task 3: Moderation Endpoints and Audit Trail

**Files:**
- Modify: `apps/rooms/tests/test_views_extended.py`
- Modify: `apps/rooms/views.py`
- Modify: `apps/rooms/urls.py`
- Modify: `templates/rooms/server_settings.html`

- [ ] **Step 1: Write failing moderation view tests**

```python
def test_admin_can_ban_member(self):
    admin_user = User.objects.create_user(username='adminx', password='Tester123.')
    ServerMember.objects.create(server=self.server, user=admin_user, role='admin')
    ServerMember.objects.create(server=self.server, user=self.user)
    self.client.login(username='adminx', password='Tester123.')
    response = self.client.post(reverse('server_ban_member', args=[self.server.slug]), {
        'user_id': self.user.id,
        'reason': 'spam',
    })
    self.assertEqual(response.status_code, 302)
    self.assertTrue(ServerBan.objects.filter(server=self.server, user=self.user, lifted_at__isnull=True).exists())

def test_banned_user_cannot_open_server_detail(self):
    ServerMember.objects.create(server=self.server, user=self.user)
    ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.other_user)
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('server_detail', args=[self.server.slug]))
    self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests --settings=config.settings.development`
Expected: FAIL with missing moderation routes/models/logic.

- [ ] **Step 3: Implement moderation actions in views**

```python
@login_required
@require_post_method
def server_ban_member(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not can_moderate_server(server, request.user):
        raise Http404()
    target_user = get_object_or_404(User, id=request.POST.get('user_id'))
    if target_user.id == server.owner_id:
        messages.error(request, 'Owner cannot be banned.')
        return redirect('server_settings', server_slug=server.slug)
    ServerBan.objects.get_or_create(
        server=server,
        user=target_user,
        lifted_at__isnull=True,
        defaults={'banned_by': request.user, 'reason': request.POST.get('reason', '')[:255]},
    )
    ServerMember.objects.filter(server=server, user=target_user).delete()
    ModerationAction.objects.create(server=server, actor=request.user, target=target_user, action='ban', reason=request.POST.get('reason', '')[:255])
    messages.success(request, 'Member banned.')
    return redirect('server_settings', server_slug=server.slug)

@login_required
@require_post_method
def server_mute_member(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not can_moderate_server(server, request.user):
        raise Http404()
    target = get_object_or_404(ServerMember, server=server, user_id=request.POST.get('user_id'))
    minutes = max(1, min(1440, int(request.POST.get('minutes', '15'))))
    target.muted_until = timezone.now() + timedelta(minutes=minutes)
    target.save(update_fields=['muted_until'])
    ModerationAction.objects.create(server=server, actor=request.user, target=target.user, action='mute', reason=request.POST.get('reason', '')[:255])
    messages.success(request, 'Member muted.')
    return redirect('server_settings', server_slug=server.slug)
```

- [ ] **Step 4: Add moderation routes and settings UI controls**

```python
# apps/rooms/urls.py
path('servers/<uuid:server_slug>/settings/ban/', views.server_ban_member, name='server_ban_member'),
path('servers/<uuid:server_slug>/settings/mute/', views.server_mute_member, name='server_mute_member'),
```

```html
<!-- templates/rooms/server_settings.html inside each member row -->
<form method="post" action="{% url 'server_set_role' server_slug=server.slug %}" class="d-inline">
  {% csrf_token %}
  <input type="hidden" name="user_id" value="{{ m.user.id }}">
  <button name="role" value="admin" class="btn btn-sm btn-outline-primary">Make admin</button>
  <button name="role" value="member" class="btn btn-sm btn-outline-secondary">Make member</button>
</form>
<form method="post" action="{% url 'server_mute_member' server_slug=server.slug %}" class="d-inline">
  {% csrf_token %}
  <input type="hidden" name="user_id" value="{{ m.user.id }}">
  <input type="hidden" name="minutes" value="15">
  <button class="btn btn-sm btn-outline-warning">Mute 15m</button>
</form>
<form method="post" action="{% url 'server_ban_member' server_slug=server.slug %}" class="d-inline">
  {% csrf_token %}
  <input type="hidden" name="user_id" value="{{ m.user.id }}">
  <button class="btn btn-sm btn-outline-danger">Ban</button>
</form>
```

- [ ] **Step 5: Run view tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/views.py apps/rooms/urls.py templates/rooms/server_settings.html apps/rooms/tests/test_views_extended.py
git commit -m "feat: add moderation actions and audit trail"
```

### Task 4: Enforce Ban/Mute in WebSocket Consumers

**Files:**
- Modify: `apps/rooms/tests/test_consumers.py`
- Modify: `apps/rooms/consumers.py`

- [ ] **Step 1: Add failing consumer tests**

```python
def test_banned_member_connection_rejected(self):
    ServerMember.objects.get_or_create(server=self.server, user=self.user)
    ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.other)
    transaction.commit()
    headers = self._get_cookie_header(self.user)
    communicator = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers)
    connected = asyncio.run(communicator.connect())[0]
    self.assertFalse(connected)

def test_muted_member_chat_message_is_dropped(self):
    membership = ServerMember.objects.create(server=self.server, user=self.user)
    membership.muted_until = timezone.now() + timedelta(minutes=5)
    membership.save(update_fields=['muted_until'])
    ServerMember.objects.get_or_create(server=self.server, user=self.other)
    transaction.commit()
    # connect two clients and verify receiver gets no chat_message when muted user sends
```

- [ ] **Step 2: Run consumer tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development`
Expected: FAIL because consumers do not check active bans/mute windows.

- [ ] **Step 3: Implement moderation checks in consumers**

```python
@database_sync_to_async
def is_member(self):
    if ServerBan.objects.filter(server__slug=self.server_slug, user=self.user, lifted_at__isnull=True).exists():
        return False
    membership = ServerMember.objects.select_related('server').filter(server__slug=self.server_slug, user=self.user).first()
    if not membership:
        return False
    self.server_id = membership.server_id
    self.membership_id = membership.id
    return True

@database_sync_to_async
def is_muted(self):
    from django.utils import timezone
    return ServerMember.objects.filter(
        id=self.membership_id,
        muted_until__isnull=False,
        muted_until__gt=timezone.now(),
    ).exists()

# in receive() before chat_message save
if await self.is_muted():
    return
```

- [ ] **Step 4: Return mention metadata in payloads**

```python
# include mentions in history/chat payload as optional list
{
    'id': m.id,
    'content': m.content,
    'mentions': [u.username for u in m.mentions.select_related('mentioned_user')],
}
```

- [ ] **Step 5: Run consumer tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/consumers.py apps/rooms/tests/test_consumers.py
git commit -m "feat: enforce chat moderation in websocket consumers"
```

### Task 5: Mentions and Read-State Write Path

**Files:**
- Modify: `apps/rooms/tests/test_views_extended.py`
- Modify: `apps/rooms/views.py`
- Modify: `apps/rooms/consumers.py`

- [ ] **Step 1: Add failing tests for mention extraction and read marker updates**

```python
def test_server_message_creates_mentions_for_existing_members(self):
    # send message "hi @other" and assert ChatMention created for @other only

def test_mark_server_read_updates_last_read_message(self):
    self.client.login(username='testuser', password='Tester123.')
    msg = ChatMessage.objects.create(server=self.server, user=self.other_user, content='hello')
    response = self.client.post(reverse('server_mark_read', args=[self.server.slug]), {'message_id': msg.id})
    self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests --settings=config.settings.development`
Expected: FAIL with missing mention/read APIs.

- [ ] **Step 3: Implement mention parsing and persistence**

```python
MENTION_RE = re.compile(r'@([A-Za-z0-9_]{1,150})')

def _extract_mentions(content: str) -> set[str]:
    return {m.group(1) for m in MENTION_RE.finditer(content or '')}

def _save_server_mentions(message: ChatMessage):
    usernames = _extract_mentions(message.content)
    if not usernames:
        return
    members = User.objects.filter(
        username__in=usernames,
        id__in=ServerMember.objects.filter(server=message.server).values_list('user_id', flat=True),
    )
    ChatMention.objects.bulk_create([
        ChatMention(message=message, mentioned_user=u) for u in members
    ], ignore_conflicts=True)
```

- [ ] **Step 4: Add read marker endpoints**

```python
@login_required
@require_post_method
def server_mark_read(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        raise Http404()
    message = get_object_or_404(ChatMessage, id=request.POST.get('message_id'), server=server)
    ChatReadState.objects.update_or_create(
        server=server,
        user=request.user,
        defaults={'last_read_message': message},
    )
    return JsonResponse({'ok': True})
```

- [ ] **Step 5: Run tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/views.py apps/rooms/consumers.py apps/rooms/tests/test_views_extended.py
git commit -m "feat: add mentions and chat read-state write path"
```

### Task 6: Unread Counters and Search Endpoints

**Files:**
- Modify: `apps/rooms/tests/test_views_extended.py`
- Modify: `apps/rooms/views.py`
- Modify: `apps/rooms/urls.py`

- [ ] **Step 1: Add failing tests for search and unread summary API**

```python
def test_server_chat_search_filters_by_content_and_user(self):
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('server_chat_search', args=[self.server.slug]), {'q': 'hello'})
    self.assertEqual(response.status_code, 200)
    self.assertIn('results', response.json())

def test_unread_summary_returns_server_unread_count(self):
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('chat_unread_summary', args=[self.server.slug]))
    self.assertEqual(response.status_code, 200)
    self.assertIn('server_unread', response.json())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended.RoomViewTests --settings=config.settings.development`
Expected: FAIL because routes/views do not exist.

- [ ] **Step 3: Implement search views**

```python
@login_required
def server_chat_search(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        raise Http404()
    q = (request.GET.get('q') or '').strip()
    qs = ChatMessage.objects.filter(server=server, deleted_at__isnull=True).select_related('user').order_by('-created_at')
    if q:
        qs = qs.filter(models.Q(content__icontains=q) | models.Q(user__username__icontains=q))
    qs = qs[:50]
    return JsonResponse({'results': [
        {'id': m.id, 'username': m.user.username, 'content': m.content, 'created_at': m.created_at.isoformat()}
        for m in qs
    ]})

@login_required
def chat_unread_summary(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    state = ChatReadState.objects.filter(server=server, user=request.user).first()
    last_id = state.last_read_message_id if state else 0
    unread = ChatMessage.objects.filter(server=server, id__gt=last_id, deleted_at__isnull=True).exclude(user=request.user).count()
    return JsonResponse({'server_unread': unread})
```

- [ ] **Step 4: Add URL routes**

```python
path('servers/<uuid:server_slug>/chat/search/', views.server_chat_search, name='server_chat_search'),
path('servers/<uuid:server_slug>/chat/mark-read/', views.server_mark_read, name='server_mark_read'),
path('servers/<uuid:server_slug>/chat/unread-summary/', views.chat_unread_summary, name='chat_unread_summary'),
```

- [ ] **Step 5: Run tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development`
Expected: PASS.

```bash
git add apps/rooms/views.py apps/rooms/urls.py apps/rooms/tests/test_views_extended.py
git commit -m "feat: add server chat search and unread summary APIs"
```

### Task 7: Template Integration (Settings, Search, Unread, Mentions)

**Files:**
- Modify: `templates/rooms/server_settings.html`
- Modify: `templates/rooms/server_detail.html`
- Modify: `templates/rooms/room_detail.html`

- [ ] **Step 1: Add failing integration test for new UI elements**

```python
def test_server_detail_renders_search_input_and_unread_badge(self):
    self.server.members.add(self.user)
    self.client.login(username='testuser', password='Tester123.')
    response = self.client.get(reverse('server_detail', args=[self.server.slug]))
    self.assertContains(response, 'id="chatSearchInput"')
    self.assertContains(response, 'id="serverUnreadBadge"')
```

- [ ] **Step 2: Run integration test and verify failure**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_integration --settings=config.settings.development`
Expected: FAIL until UI ids/scripts are added.

- [ ] **Step 3: Add server chat search + unread UI hooks**

```html
<input id="chatSearchInput" class="form-control form-control-sm" placeholder="Search chat...">
<span id="serverUnreadBadge" class="badge bg-danger d-none">0</span>
```

```javascript
async function refreshUnread() {
  const res = await fetch(`/servers/${SERVER_SLUG}/chat/unread-summary/`);
  const data = await res.json();
  const badge = document.getElementById('serverUnreadBadge');
  const n = data.server_unread || 0;
  badge.textContent = n;
  badge.classList.toggle('d-none', n === 0);
}
```

- [ ] **Step 4: Add mention highlight rendering**

```javascript
function renderMentions(content) {
  return escapeHtml(content).replace(/(^|\s)@([A-Za-z0-9_]{1,150})/g, '$1<span class="chat-mention">@$2</span>');
}
```

- [ ] **Step 5: Run integration tests and commit**

Run: `source venv/bin/activate && python manage.py test apps.rooms.tests.test_integration --settings=config.settings.development`
Expected: PASS.

```bash
git add templates/rooms/server_settings.html templates/rooms/server_detail.html templates/rooms/room_detail.html apps/rooms/tests/test_integration.py
git commit -m "feat: wire moderation, unread, and search UI"
```

### Task 8: End-to-End Verification and Documentation Update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md` (only if operational notes changed)

- [ ] **Step 1: Run focused regression suites**

Run:

```bash
source venv/bin/activate && python manage.py test apps.rooms.tests.test_permissions --settings=config.settings.development
source venv/bin/activate && python manage.py test apps.rooms.tests.test_views_extended --settings=config.settings.development
source venv/bin/activate && python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
```

Expected: PASS for all three commands.

- [ ] **Step 2: Run full test suite**

Run: `source venv/bin/activate && python manage.py test --settings=config.settings.development --keepdb`
Expected: PASS with no `--parallel` usage.

- [ ] **Step 3: Update project docs for new trust/chat capabilities**

```markdown
- server roles (`owner/admin/member`) with moderation actions and audit records
- server chat mentions and unread counters
- basic server chat search endpoint and UI
```

- [ ] **Step 4: Commit docs and final code state**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: reflect phase1 trust and chat ux capabilities"
```

- [ ] **Step 5: Final status check**

Run: `git status`
Expected: clean working tree.
