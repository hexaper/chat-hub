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
        self.user = User.objects.create_user(username='testuser', password='Tester123.')
        self.other_user = User.objects.create_user(username='other', password='Tester123.')
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
        self.client.login(username='testuser', password='Tester123.')
        image = SimpleUploadedFile('test.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(reverse('chat_image_upload', args=[self.server.slug]), {'image': image})
        self.assertEqual(response.status_code, 403)

    def test_chat_image_upload_success(self):
        self.server.members.add(self.user)
        self.client.login(username='testuser', password='Tester123.')
        image = SimpleUploadedFile('test.png', create_test_image().read(), content_type='image/png')
        response = self.client.post(reverse('chat_image_upload', args=[self.server.slug]), {'image': image})
        self.assertEqual(response.status_code, 200)
        self.assertIn('image_url', response.json())
