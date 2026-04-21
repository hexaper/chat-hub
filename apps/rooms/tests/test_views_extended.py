from asgiref.sync import async_to_sync
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image

from apps.rooms.consumers import ServerChatConsumer
from apps.rooms.models import (
    ChatMention,
    ChatMessage,
    ChatReadState,
    ModerationAction,
    Room,
    Server,
    ServerBan,
    ServerMember,
)

User = get_user_model()


def create_test_image(format='PNG'):
    bio = BytesIO()
    img = Image.new('RGB', (10, 10), color='blue')
    img.save(bio, format=format)
    bio.seek(0)
    return bio


class RoomViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='testuser@example.com', password='Tester123.')
        self.other_user = User.objects.create_user(username='other', email='other@example.com', password='Tester123.')
        self.server = Server.objects.create(name='Server', owner=self.other_user)
        ServerMember.objects.create(server=self.server, user=self.other_user)
        self.room = Room.objects.create(name='Room', server=self.server, host=self.other_user)

    def test_register_view_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'Tester123.',
            'password2': 'Tester123.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_login_view_with_next_redirects_safely(self):
        self.user.set_password('Tester123.')
        self.user.save()
        target = reverse('server_list')
        response = self.client.post(f"{reverse('login')}?next={target}", {
            'username': 'testuser',
            'password': 'Tester123.',
        })
        self.assertRedirects(response, target)

    def test_server_join_invalid_code(self):
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_join'), {'invite_code': 'invalid'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServerMember.objects.filter(server=self.server, user=self.user).exists())

    def test_server_join_valid_code(self):
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_join'), {'invite_code': self.server.invite_code})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ServerMember.objects.filter(server=self.server, user=self.user).exists())

    def test_banned_user_cannot_rejoin_server_with_invite_code(self):
        ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.other_user)

        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_join'), {'invite_code': self.server.invite_code})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('server_list'))
        self.assertFalse(ServerMember.objects.filter(server=self.server, user=self.user).exists())

    def test_banned_former_member_cannot_rejoin_server_with_invite_code(self):
        ServerMember.objects.create(server=self.server, user=self.user)
        ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.other_user)
        ServerMember.objects.filter(server=self.server, user=self.user).delete()

        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_join'), {'invite_code': self.server.invite_code})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('server_list'))
        self.assertFalse(ServerMember.objects.filter(server=self.server, user=self.user).exists())

    def test_server_settings_only_owner(self):
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('server_settings', args=[self.server.slug]))
        self.assertEqual(response.status_code, 404)

        self.client.login(username='other', password='Tester123.')
        response = self.client.post(reverse('server_settings', args=[self.server.slug]), {
            'name': 'Updated',
            'description': 'Desc',
            'is_public': True,
        })
        self.assertEqual(response.status_code, 302)
        self.server.refresh_from_db()
        self.assertEqual(self.server.name, 'Updated')

    def test_server_kick_member(self):
        self.server.members.add(self.user)
        self.client.login(username='other', password='Tester123.')
        response = self.client.post(reverse('server_kick_member', args=[self.server.slug]), {'user_id': self.user.id})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServerMember.objects.filter(server=self.server, user=self.user).exists())

    def test_server_regenerate_invite(self):
        old_code = self.server.invite_code
        self.client.login(username='other', password='Tester123.')
        response = self.client.post(reverse('server_regenerate_invite', args=[self.server.slug]))
        self.assertEqual(response.status_code, 302)
        self.server.refresh_from_db()
        self.assertNotEqual(old_code, self.server.invite_code)

    def test_admin_can_ban_member(self):
        admin_user = User.objects.create_user(username='adminx', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=admin_user, role=ServerMember.ROLE_ADMIN)
        ServerMember.objects.create(server=self.server, user=self.user)

        self.client.login(username='adminx', password='Tester123.')
        response = self.client.post(reverse('server_ban_member', args=[self.server.slug]), {
            'user_id': self.user.id,
            'reason': 'spam',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ServerBan.objects.filter(server=self.server, user=self.user, lifted_at__isnull=True).exists())
        self.assertFalse(ServerMember.objects.filter(server=self.server, user=self.user).exists())
        self.assertTrue(ModerationAction.objects.filter(
            server=self.server,
            actor=admin_user,
            target=self.user,
            action=ModerationAction.ACTION_BAN,
            reason='spam',
        ).exists())

    def test_banned_user_cannot_open_server_detail(self):
        ServerMember.objects.create(server=self.server, user=self.user)
        ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.other_user)

        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('server_detail', args=[self.server.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('server_list'))

    def test_owner_cannot_be_muted(self):
        admin_user = User.objects.create_user(username='adminmute', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=admin_user, role=ServerMember.ROLE_ADMIN)

        self.client.login(username='adminmute', password='Tester123.')
        response = self.client.post(reverse('server_mute_member', args=[self.server.slug]), {
            'user_id': self.other_user.id,
            'minutes': '15',
            'reason': 'nope',
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('server_settings', args=[self.server.slug]))
        owner_membership = ServerMember.objects.get(server=self.server, user=self.other_user)
        self.assertIsNone(owner_membership.muted_until)
        self.assertFalse(ModerationAction.objects.filter(
            server=self.server,
            actor=admin_user,
            target=self.other_user,
            action=ModerationAction.ACTION_MUTE,
        ).exists())

    def test_owner_mute_attempt_is_rejected_even_without_owner_membership_row(self):
        admin_user = User.objects.create_user(username='adminmute2', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=admin_user, role=ServerMember.ROLE_ADMIN)
        ServerMember.objects.filter(server=self.server, user=self.other_user).delete()

        self.client.login(username='adminmute2', password='Tester123.')
        response = self.client.post(reverse('server_mute_member', args=[self.server.slug]), {
            'user_id': self.other_user.id,
            'minutes': '15',
            'reason': 'nope',
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('server_settings', args=[self.server.slug]))
        self.assertFalse(ModerationAction.objects.filter(
            server=self.server,
            actor=admin_user,
            target=self.other_user,
            action=ModerationAction.ACTION_MUTE,
        ).exists())

    def test_server_message_creates_mentions_for_existing_members(self):
        ServerMember.objects.create(server=self.server, user=self.user)
        outsider = User.objects.create_user(username='outsider', password='Tester123.')
        consumer = ServerChatConsumer()
        consumer.user = self.other_user
        consumer.server_id = self.server.id

        async_to_sync(consumer.save_message)('hi @testuser @outsider @missing @testuser')

        message = ChatMessage.objects.get(server=self.server, user=self.other_user)
        mentioned_usernames = list(
            ChatMention.objects.filter(message=message)
            .order_by('mentioned_user__username')
            .values_list('mentioned_user__username', flat=True)
        )

        self.assertEqual(mentioned_usernames, ['testuser'])
        self.assertFalse(ChatMention.objects.filter(message=message, mentioned_user=outsider).exists())

    def test_mark_server_read_updates_last_read_message(self):
        ServerMember.objects.create(server=self.server, user=self.user)
        older_message = ChatMessage.objects.create(server=self.server, user=self.other_user, content='first')
        newer_message = ChatMessage.objects.create(server=self.server, user=self.other_user, content='hello')
        ChatReadState.objects.create(server=self.server, user=self.user, last_read_message=older_message)

        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_mark_read', args=[self.server.slug]), {'message_id': newer_message.id})

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'ok': True})
        read_state = ChatReadState.objects.get(server=self.server, user=self.user)
        self.assertEqual(read_state.last_read_message_id, newer_message.id)

    def test_server_leave_owner_forbidden(self):
        self.client.login(username='other', password='Tester123.')
        response = self.client.post(reverse('server_leave', args=[self.server.slug]))
        self.assertEqual(response.status_code, 302)

    def test_chat_image_upload_requires_member(self):
        upload_user = User.objects.create_user(username='uploaduser_nm', email='uploaduser_nm@example.com', password='Tester123.')
        self.client.login(username='uploaduser_nm', password='Tester123.')
        image = SimpleUploadedFile('test.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(reverse('chat_image_upload', args=[self.server.slug]), {'image': image})
        self.assertEqual(response.status_code, 403)

    def test_chat_image_upload_success(self):
        upload_user = User.objects.create_user(username='uploaduser_ok', email='uploaduser_ok@example.com', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=upload_user)
        self.client.login(username='uploaduser_ok', password='Tester123.')
        image = SimpleUploadedFile('test.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(reverse('chat_image_upload', args=[self.server.slug]), {'image': image})
        self.assertEqual(response.status_code, 200)
        self.assertIn('image_url', response.json())

    # ── Video upload tests ────────────────────────────────────────────────────

    def test_video_upload_success(self):
        """Video within 25 MB is accepted; response includes message_id and media_type."""
        # Use a fresh user to avoid hitting the rate limit when running the full test class
        video_user = User.objects.create_user(username='videouser', email='videouser@example.com', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=video_user)
        self.client.login(username='videouser', password='Tester123.')
        # Minimal MP4 header: 4-byte size + 'ftyp' + 'mp42' + 4-byte version + 'mp42'
        mp4_header = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2'
        video = SimpleUploadedFile('clip.mp4', mp4_header + b'\x00' * 512, content_type='video/mp4')
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
        video_user2 = User.objects.create_user(username='videouser2', email='videouser2@example.com', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=video_user2)
        self.client.login(username='videouser2', password='Tester123.')
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
        video_user3 = User.objects.create_user(username='videouser3', email='videouser3@example.com', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=video_user3)
        self.client.login(username='videouser3', password='Tester123.')
        bad = SimpleUploadedFile('script.exe', b'\x00' * 512, content_type='application/octet-stream')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'video': bad},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'unsupported_file_type')

    def test_video_mime_spoofing_rejected(self):
        """A file with spoofed video/mp4 Content-Type but non-video magic bytes is rejected."""
        ServerMember.objects.create(server=self.server, user=self.user)
        self.client.login(username='testuser', password='Tester123.')
        # Fake MP4: has the right MIME type but wrong magic bytes (just null bytes)
        fake_mp4 = SimpleUploadedFile('fake.mp4', b'\x00' * 512, content_type='video/mp4')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'video': fake_mp4},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'unsupported_file_type')

    def test_image_upload_still_returns_media_type(self):
        """Existing image upload now also returns media_type='image'."""
        img_user = User.objects.create_user(username='imguser_mt', email='imguser_mt@example.com', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=img_user)
        self.client.login(username='imguser_mt', password='Tester123.')
        image = SimpleUploadedFile('pic.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(
            reverse('chat_image_upload', args=[self.server.slug]),
            {'image': image},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['media_type'], 'image')
