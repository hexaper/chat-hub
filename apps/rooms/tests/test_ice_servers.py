from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


User = get_user_model()


class IceServersViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ice-user',
            email='ice-user@example.com',
            password='Tester123.',
        )
        self.client.force_login(self.user)
        self.url = '/api/ice-servers/'

    @override_settings(TURN_ENABLED=False)
    def test_stun_only_when_turn_disabled(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'iceServers': [
                {'urls': 'stun:stun.l.google.com:19302'},
            ]
        })

    @override_settings(
        TURN_ENABLED=True,
        TURN_HOST='turn.example.com',
        TURN_SECRET='unused-secret',
        TURN_USERNAME='relay-user',
        TURN_PASSWORD='relay-pass',
        TURN_TTL=3600,
    )
    def test_static_turn_credentials_take_precedence(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['iceServers']), 2)

        turn_server = payload['iceServers'][1]
        self.assertEqual(turn_server['urls'], [
            'turn:turn.example.com:3478?transport=udp',
            'turn:turn.example.com:3478?transport=tcp',
            'turns:turn.example.com:5349',
        ])
        self.assertEqual(turn_server['username'], 'relay-user')
        self.assertEqual(turn_server['credential'], 'relay-pass')

    @override_settings(
        TURN_ENABLED=True,
        TURN_HOST='turn.example.com',
        TURN_SECRET='hmac-secret',
        TURN_USERNAME='',
        TURN_PASSWORD='',
        TURN_TTL=3600,
    )
    def test_hmac_turn_credentials_used_when_static_creds_missing(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['iceServers']), 2)

        turn_server = payload['iceServers'][1]
        username = turn_server['username']

        self.assertIn(':', username)
        expiry, identifier = username.split(':', 1)
        self.assertTrue(expiry.isdigit())
        self.assertEqual(identifier, str(self.user.pk))
        self.assertTrue(turn_server['credential'])
