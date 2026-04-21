from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.rooms.models import Server, Room, ServerMember
from apps.rooms.permissions import (
    can_moderate_server,
    get_membership,
    is_server_admin,
    is_server_owner,
)

User = get_user_model()


class PermissionTests(TestCase):
    """Test permissions: non-members get 403, hosts have control, etc."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')
        self.other_user = User.objects.create_user(username='other', password='Tester123.')
        self.staff_user = User.objects.create_user(username='staff', password='Tester123.', is_staff=True)
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

    def test_admin_member_can_open_server_settings(self):
        """Admin server members can access server settings."""
        ServerMember.objects.create(server=self.server, user=self.user, role=ServerMember.ROLE_ADMIN)
        self.client.login(username='testuser', password='Tester123.')

        response = self.client.get(reverse('server_settings', args=[self.server.slug]))

        self.assertEqual(response.status_code, 200)

    def test_admin_member_cannot_update_server_settings(self):
        """Admin members can view settings but cannot update core server config."""
        ServerMember.objects.create(server=self.server, user=self.user, role=ServerMember.ROLE_ADMIN)
        self.client.login(username='testuser', password='Tester123.')

        response = self.client.post(
            reverse('server_settings', args=[self.server.slug]),
            {
                'name': 'Updated Server',
                'description': 'Updated description',
                'is_public': 'on',
            },
        )

        self.assertEqual(response.status_code, 404)
        self.server.refresh_from_db()
        self.assertEqual(self.server.name, 'Test Server')

    def test_admin_settings_page_hides_owner_controls(self):
        """Admin view of settings omits owner-only configuration controls."""
        target_user = User.objects.create_user(username='memberx', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=self.user, role=ServerMember.ROLE_ADMIN)
        ServerMember.objects.create(server=self.server, user=target_user)
        self.client.login(username='testuser', password='Tester123.')

        response = self.client.get(reverse('server_settings', args=[self.server.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Save Changes')
        self.assertNotContains(response, 'Regenerate Code')
        self.assertNotContains(response, 'Delete Server')
        self.assertContains(response, 'title="Set admin"')

    def test_admin_member_can_change_member_role(self):
        """Admin members can promote a normal member through the role endpoint."""
        target_user = User.objects.create_user(username='membery', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=self.user, role=ServerMember.ROLE_ADMIN)
        target_membership = ServerMember.objects.create(server=self.server, user=target_user)
        self.client.login(username='testuser', password='Tester123.')

        response = self.client.post(
            reverse('server_set_role', args=[self.server.slug]),
            {
                'user_id': target_user.id,
                'role': ServerMember.ROLE_ADMIN,
            },
        )

        self.assertEqual(response.status_code, 302)
        target_membership.refresh_from_db()
        self.assertEqual(target_membership.role, ServerMember.ROLE_ADMIN)

    def test_member_cannot_change_roles(self):
        """Regular members cannot update other members' roles."""
        ServerMember.objects.create(server=self.server, user=self.user)
        target_membership = ServerMember.objects.create(server=self.server, user=self.other_user)
        self.client.login(username='testuser', password='Tester123.')

        response = self.client.post(
            reverse('server_set_role', args=[self.server.slug]),
            {
                'user_id': self.other_user.id,
                'role': ServerMember.ROLE_ADMIN,
            },
        )

        self.assertEqual(response.status_code, 404)
        target_membership.refresh_from_db()
        self.assertEqual(target_membership.role, ServerMember.ROLE_MEMBER)

    def test_staff_can_open_server_settings(self):
        """Staff users can moderate server settings without membership."""
        self.client.login(username='staff', password='Tester123.')

        response = self.client.get(reverse('server_settings', args=[self.server.slug]))

        self.assertEqual(response.status_code, 200)

    def test_cannot_change_owner_role(self):
        """Owner membership role remains immutable through the role endpoint."""
        admin_user = User.objects.create_user(username='admin_user', password='Tester123.')
        ServerMember.objects.create(server=self.server, user=admin_user, role=ServerMember.ROLE_ADMIN)
        owner_membership, _ = ServerMember.objects.get_or_create(server=self.server, user=self.other_user)
        self.client.login(username='admin_user', password='Tester123.')

        response = self.client.post(
            reverse('server_set_role', args=[self.server.slug]),
            {
                'user_id': self.other_user.id,
                'role': ServerMember.ROLE_ADMIN,
            },
        )

        self.assertEqual(response.status_code, 302)
        owner_membership.refresh_from_db()
        self.assertEqual(owner_membership.role, ServerMember.ROLE_MEMBER)

    def test_permission_helpers_reflect_membership_roles(self):
        """Helper functions distinguish owner, admin, and regular members."""
        admin_membership = ServerMember.objects.create(
            server=self.server,
            user=self.user,
            role=ServerMember.ROLE_ADMIN,
        )

        self.assertEqual(get_membership(self.server, self.user), admin_membership)
        self.assertTrue(is_server_admin(self.server, self.user))
        self.assertFalse(is_server_owner(self.server, self.user))
        self.assertTrue(can_moderate_server(self.server, self.user))
        self.assertTrue(is_server_owner(self.server, self.other_user))
        self.assertTrue(can_moderate_server(self.server, self.staff_user))
