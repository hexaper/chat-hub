from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.rooms.models import Server, Room, ServerMember

User = get_user_model()


class IntegrationTests(TestCase):
    """Test full user flows."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')

    def test_create_server_join_create_room(self):
        """Full flow: create server, join, create room."""
        self.client.login(username='testuser', password='Tester123.')

        # Create server
        response = self.client.post(reverse('server_create'), {
            'name': 'My Server',
            'description': 'Test server',
            'is_public': True
        })
        self.assertEqual(response.status_code, 302)
        server = Server.objects.get(name='My Server')
        self.assertTrue(ServerMember.objects.filter(server=server, user=self.user).exists())

        # Create room
        response = self.client.post(reverse('room_create', args=[server.slug]), {
            'name': 'My Room'
        })
        self.assertEqual(response.status_code, 302)
        room = Room.objects.get(name='My Room', server=server)
        self.assertEqual(room.host, self.user)
        self.assertTrue(room.is_active)

    def test_join_private_server_requires_invite(self):
        """Cannot join private server without invite."""
        server = Server.objects.create(name='Private', owner=self.user, is_public=False)
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('server_detail', args=[server.slug]))
        self.assertEqual(response.status_code, 302)  # Redirect to server_list

    def test_full_room_entry_with_password(self):
        """Wrong password fails; correct password grants access."""
        owner = User.objects.create_user(username='owner', password='Tester123.')
        server = Server.objects.create(name='PwdServer', owner=owner)
        ServerMember.objects.create(server=server, user=owner)
        ServerMember.objects.create(server=server, user=self.user)

        from apps.rooms.models import Room
        room = Room.objects.create(name='SecureRoom', server=server, host=owner)
        room.set_password('correct123')
        room.save()

        self.client.login(username='testuser', password='Tester123.')

        # Wrong password attempt
        response = self.client.post(
            reverse('room_detail', args=[server.slug, room.slug]),
            {'password': 'wrongpass'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'password', response.content.lower())

        # Correct password
        response = self.client.post(
            reverse('room_detail', args=[server.slug, room.slug]),
            {'password': 'correct123'},
        )
        # After correct password the view grants access (redirects or renders room)
        self.assertIn(response.status_code, [200, 302])
        # Verify session auth was set
        session_key = f'room_auth_{room.slug}'
        self.assertTrue(self.client.session.get(session_key))

    def test_server_invite_flow(self):
        """User A creates server → user B joins via invite code → B is now a member."""
        user_b = User.objects.create_user(username='userb', password='Tester123.')

        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(reverse('server_create'), {
            'name': 'InviteServer',
            'description': '',
            'is_public': False,
        })
        self.assertEqual(response.status_code, 302)
        server = Server.objects.get(name='InviteServer')
        invite_code = server.invite_code

        # User B joins via invite code
        client_b = self.client_class()
        client_b.login(username='userb', password='Tester123.')
        response = client_b.post(reverse('server_join'), {'invite_code': invite_code})
        self.assertEqual(response.status_code, 302)

        self.assertTrue(ServerMember.objects.filter(server=server, user=user_b).exists())