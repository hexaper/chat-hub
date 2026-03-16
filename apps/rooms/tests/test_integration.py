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

    # Add more integration tests