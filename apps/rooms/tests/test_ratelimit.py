"""
Integration tests for rate limiting on rooms views and the chat consumer.

Covers:
  - chat_image_upload view: 10/m per authenticated user (key='user')
  - ServerChatConsumer.receive(): 30/m per user; messages beyond limit are
    silently dropped (not broadcast to the group)

Redis (DB 1 for cache, DB 0 for channel layer) must be running.
Consumer tests use TransactionTestCase because the consumer runs in a
separate thread that cannot see uncommitted TestCase transactions.
"""
import asyncio
import json
import uuid
from io import BytesIO

from PIL import Image
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from django.db import transaction

from apps.rooms import routing
from apps.rooms.models import Server, ServerMember

User = get_user_model()


def _make_valid_image(filename='test.png', fmt='PNG'):
    """Return a SimpleUploadedFile containing a valid minimal PNG image."""
    buf = BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read(), content_type='image/png')


class ChatImageUploadRateLimitTest(TestCase):
    """
    chat_image_upload enforces 10 requests/minute per authenticated user (key='user').

    The limit is per-user, so two different users have independent counters.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='rl_upload_user',
            password='Tester123.',
        )
        cls.other_user = User.objects.create_user(
            username='rl_upload_other',
            password='Tester123.',
        )
        cls.server = Server.objects.create(name='UploadServer', owner=cls.user)
        ServerMember.objects.create(server=cls.server, user=cls.user)
        ServerMember.objects.create(server=cls.server, user=cls.other_user)

    def setUp(self):
        cache.clear()
        self.client.login(username='rl_upload_user', password='Tester123.')
        self._url = f'/servers/{self.server.slug}/chat/upload/'

    def _post_image(self):
        """POST a valid image to the upload endpoint (AJAX-style, expects JSON)."""
        return self.client.post(
            self._url,
            data={'image': _make_valid_image()},
            format='multipart',
            HTTP_ACCEPT='application/json',
        )

    def test_ten_uploads_within_limit_are_not_rejected(self):
        """Ten consecutive image uploads must not return 429."""
        for i in range(10):
            response = self._post_image()
            self.assertNotEqual(
                response.status_code, 429,
                msg=f"Upload #{i + 1}/10 should not be rate-limited (got {response.status_code})",
            )

    def test_eleventh_upload_returns_429(self):
        """The 11th upload within a minute must return 429."""
        for _ in range(10):
            self._post_image()
        response = self._post_image()
        self.assertEqual(
            response.status_code, 429,
            msg="11th image upload should be rate-limited (expected 429)",
        )

    def test_different_users_tracked_independently(self):
        """Exhausting user1's upload limit must not affect user2."""
        for _ in range(10):
            self._post_image()
        over = self._post_image()
        self.assertEqual(over.status_code, 429, msg="user1 should be rate-limited")

        # Switch to other_user
        self.client.login(username='rl_upload_other', password='Tester123.')
        response = self._post_image()
        self.assertNotEqual(
            response.status_code, 429,
            msg="other_user should have its own counter and not be blocked by user1's limit",
        )

    def test_unauthenticated_upload_returns_302_not_429(self):
        """Unauthenticated requests are intercepted by @login_required before rate limiting."""
        self.client.logout()
        response = self._post_image()
        # @login_required redirects (302) before the rate limit is ever checked
        self.assertEqual(
            response.status_code, 302,
            msg="Unauthenticated upload should redirect to login, not return 429",
        )
        self.assertIn('/accounts/login/', response['Location'])


class ChatConsumerRateLimitTest(TransactionTestCase):
    """
    ServerChatConsumer enforces 30 chat_message events per minute per user.

    The 31st message is silently dropped: it is not broadcast to other
    connected clients. This test verifies the observable outcome (no
    broadcast) rather than testing internal cache key details.

    Uses TransactionTestCase because the consumer runs in a separate
    thread that cannot see uncommitted TestCase transactions.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='rl_chat_user',
            password='Tester123.',
        )
        self.observer = User.objects.create_user(
            username='rl_chat_observer',
            password='Tester123.',
        )
        self.server = Server.objects.create(name='RLChatServer', owner=self.user)
        ServerMember.objects.create(server=self.server, user=self.user)
        ServerMember.objects.create(server=self.server, user=self.observer)

        # Commit so consumer thread sees the data
        transaction.commit()

        self.application = AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns))

    def _get_cookie_header(self, user):
        from django.test import Client
        c = Client()
        c.login(username=user.username, password='Tester123.')
        sessionid = c.cookies.get('sessionid')
        if not sessionid:
            return []
        return [(b'cookie', f'sessionid={sessionid.value}'.encode())]

    def _chat_url(self):
        return f'/ws/chat/{self.server.slug}/'

    def test_thirty_messages_all_broadcast(self):
        """
        Sending exactly 30 chat_message events must result in all 30 being
        broadcast to an observing client.
        """
        headers_sender = self._get_cookie_header(self.user)
        headers_observer = self._get_cookie_header(self.observer)
        comm_sender = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_sender
        )
        comm_observer = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_observer
        )

        async def run():
            connected_s, _ = await comm_sender.connect()
            self.assertTrue(connected_s, msg="Sender should connect successfully")
            connected_o, _ = await comm_observer.connect()
            self.assertTrue(connected_o, msg="Observer should connect successfully")

            # Drain history from both
            await comm_sender.receive_from(timeout=20)
            await comm_observer.receive_from(timeout=20)

            # Send 30 messages
            for i in range(30):
                await comm_sender.send_json_to({
                    'type': 'chat_message',
                    'content': f'msg {i}',
                })

            # Observer must receive all 30
            received = 0
            for _ in range(30):
                raw = await comm_observer.receive_from(timeout=20)
                msg = json.loads(raw)
                if msg.get('type') == 'chat_message':
                    received += 1

            self.assertEqual(
                received, 30,
                msg=f"Observer should receive all 30 messages, got {received}",
            )

            await comm_sender.disconnect()
            await comm_observer.disconnect()

        asyncio.run(run())

    def test_thirty_first_message_is_silently_dropped(self):
        """
        The 31st chat_message from the same user must be silently dropped —
        the observer receives nothing for it (TimeoutError on receive).
        """
        headers_sender = self._get_cookie_header(self.user)
        headers_observer = self._get_cookie_header(self.observer)
        comm_sender = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_sender
        )
        comm_observer = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_observer
        )

        async def run():
            connected_s, _ = await comm_sender.connect()
            self.assertTrue(connected_s, msg="Sender should connect successfully")
            connected_o, _ = await comm_observer.connect()
            self.assertTrue(connected_o, msg="Observer should connect successfully")

            # Drain history
            await comm_sender.receive_from(timeout=20)
            await comm_observer.receive_from(timeout=20)

            # Exhaust the 30-message limit
            for i in range(30):
                await comm_sender.send_json_to({
                    'type': 'chat_message',
                    'content': f'msg {i}',
                })

            # Drain all 30 from observer so the queue is empty
            for _ in range(30):
                await comm_observer.receive_from(timeout=20)

            # Send the 31st message — should be silently dropped
            await comm_sender.send_json_to({
                'type': 'chat_message',
                'content': 'this should be dropped',
            })

            # Observer must NOT receive it
            with self.assertRaises(asyncio.TimeoutError,
                                   msg="31st message should be silently dropped — observer must receive nothing"):
                await comm_observer.receive_from(timeout=0.5)

            await comm_sender.disconnect()
            try:
                await comm_observer.disconnect()
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_rate_limit_is_per_user_not_per_connection(self):
        """
        A second user connecting to the same chat group has its own independent
        rate-limit counter.  Exhausting user1's limit must not affect user2.
        """
        headers_sender = self._get_cookie_header(self.user)
        headers_observer = self._get_cookie_header(self.observer)
        comm_sender = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_sender
        )
        comm_observer = WebsocketCommunicator(
            self.application, self._chat_url(), headers=headers_observer
        )

        async def run():
            await comm_sender.connect()
            await comm_observer.connect()

            # Drain history
            await comm_sender.receive_from(timeout=20)
            await comm_observer.receive_from(timeout=20)

            # Exhaust sender's limit (30 messages)
            for i in range(30):
                await comm_sender.send_json_to({'type': 'chat_message', 'content': f'm{i}'})

            # Drain all 30 from both participants (the group broadcast goes to everyone)
            for _ in range(30):
                await comm_observer.receive_from(timeout=20)
            for _ in range(30):
                await comm_sender.receive_from(timeout=20)

            # Now observer sends a message — should succeed (own fresh counter)
            await comm_observer.send_json_to({'type': 'chat_message', 'content': 'observer msg'})

            # Sender should receive observer's message
            raw = await comm_sender.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(
                msg.get('type'), 'chat_message',
                msg="Sender should receive observer's message even after sender's own limit is exhausted",
            )
            self.assertEqual(
                msg.get('content'), 'observer msg',
                msg="Content of observer's message should be 'observer msg'",
            )

            await comm_sender.disconnect()
            await comm_observer.disconnect()

        asyncio.run(run())
