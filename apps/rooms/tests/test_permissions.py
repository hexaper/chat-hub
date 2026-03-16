from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.rooms.models import Server, Room

User = get_user_model()


class PermissionTests(TestCase):
    """Test permissions: non-members get 403, hosts have control, etc."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')
        self.other_user = User.objects.create_user(username='other', password='Tester123.')
        self.server = Server.objects.create(name='Test Server', owner=self.other_user)
        self.room = Room.objects.create(name='Test Room', server=self.server, host=self.other_user)

    def test_non_member_cannot_access_server_detail(self):
        """Non-member cannot access server detail."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('server_detail', args=[self.server.slug]))
        self.assertEqual(response.status_code, 302)  # Redirect to server_list

    def test_non_member_cannot_access_room_detail(self):
        """Non-member cannot access room detail."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('room_detail', args=[self.server.slug, self.room.slug]))
        self.assertEqual(response.status_code, 302)  # Redirect to server_list

    def test_member_can_access_server_detail(self):
        """Member can access server detail."""
        self.server.members.add(self.user)
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('server_detail', args=[self.server.slug]))
        self.assertEqual(response.status_code, 200)

    def test_host_can_delete_room(self):
        """Room host can delete their room."""
        self.server.members.add(self.other_user)
        self.client.login(username='other', password='Tester123.')
        response = self.client.post(reverse('room_delete', args=[self.server.slug, self.room.slug]))
        self.assertEqual(response.status_code, 302)  # Redirect after delete
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_active)

    def test_non_host_cannot_delete_room(self):
        """Non-host cannot delete room (gets 404)."""
        self.server.members.add(self.user)
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('room_delete', args=[self.server.slug, self.room.slug]))
        self.assertEqual(response.status_code, 404)

    def test_open_room_accessible_without_password(self):
        """Open room (no password) is accessible to members."""
        self.server.members.add(self.user)
        self.room.password = ''  # Ensure no password
        self.room.save()
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('room_detail', args=[self.server.slug, self.room.slug]))
        self.assertEqual(response.status_code, 200)

    def test_server_owner_can_delete_server(self):
        """Server owner can delete their server."""
        self.client.login(username='other', password='Tester123.')  # owner
        response = self.client.post(reverse('server_delete', args=[self.server.slug]))
        self.assertEqual(response.status_code, 302)
        with self.assertRaises(Server.DoesNotExist):
            Server.objects.get(slug=self.server.slug)

    def test_password_protected_room_shows_password_form_to_member(self):
        """Member accessing a password-protected room sees the password form (not room detail)."""
        self.server.members.add(self.user)
        self.room.set_password('secret123')
        self.room.save()
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('room_detail', args=[self.server.slug, self.room.slug]))
        # Should render the password form page, not a redirect
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'password', response.content.lower())

    def test_non_owner_cannot_kick_member(self):
        """Non-owner POSTing to server_kick_member gets 404."""
        self.server.members.add(self.user)
        self.server.members.add(self.other_user)
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(
            reverse('server_kick_member', args=[self.server.slug]),
            {'user_id': self.other_user.id},
        )
        self.assertEqual(response.status_code, 404)

    def test_non_owner_cannot_delete_server(self):
        """Non-owner POSTing to server_delete gets 404."""
        self.server.members.add(self.user)
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_delete', args=[self.server.slug]))
        self.assertEqual(response.status_code, 404)
        # Server must still exist
        self.assertTrue(Server.objects.filter(slug=self.server.slug).exists())