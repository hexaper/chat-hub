from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image

from apps.rooms.models import Server, ServerMember, Room

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
