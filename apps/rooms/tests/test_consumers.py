import asyncio
import json
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model

from apps.rooms import routing
from apps.rooms.models import Server, ServerMember, ChatMessage

User = get_user_model()


class ConsumerTests(TransactionTestCase):
    """Tests for WebSocket consumers."""

    def setUp(self):
        self.user = User.objects.create_user(username='user1', password='Tester123.')
        self.other = User.objects.create_user(username='user2', password='Tester123.')
        self.server = Server.objects.create(name='Server', owner=self.other)
        ServerMember.objects.create(server=self.server, user=self.other)

        # ASGI application for testing
        self.application = AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns))

    def _get_cookie_header(self, user):
        """Create an auth cookie header for a logged-in user."""
        # Use Django test client to get the session cookie
        from django.test import Client
        client = Client()
        client.login(username=user.username, password='Tester123.')
        sessionid = client.cookies.get('sessionid')
        if not sessionid:
            return []
        return [(b'cookie', f'sessionid={sessionid.value}'.encode())]

    def test_server_chat_rejects_unauthenticated(self):
        communicator = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/')

        async def run():
            connected, _ = await communicator.connect()
            return connected

        connected = asyncio.run(run())
        self.assertFalse(connected)

        # If connection was accepted, close it; otherwise, just ensure no error
        if connected:
            asyncio.run(communicator.disconnect())

    def test_server_chat_accepts_member_and_sends_history(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ChatMessage.objects.create(server=self.server, user=self.user, content='hello')

        # Ensure DB changes are visible to the consumer thread
        from django.db import transaction
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/chat/{self.server.slug}/',
            headers=headers,
        )

        async def run():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Should receive history message immediately
            raw = await communicator.receive_from(timeout=20)
            response = json.loads(raw)
            self.assertEqual(response.get('type'), 'history')
            self.assertEqual(response['messages'][0]['content'], 'hello')

            await communicator.disconnect()

        asyncio.run(run())

    def test_server_chat_broadcasts_messages(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)

        # Ensure DB changes are visible to the consumer threads
        from django.db import transaction
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)

        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run():
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Consume history messages
            await comm1.receive_from(timeout=20)
            await comm2.receive_from(timeout=20)

            # Send chat message from user1
            await comm1.send_json_to({'type': 'chat_message', 'content': 'hi'})
            raw = await comm2.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg.get('type'), 'chat_message')
            self.assertEqual(msg.get('content'), 'hi')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_server_chat_image_message_sent_by_owner(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)

        # Prepare a message with an image attached
        from django.core.files.uploadedfile import SimpleUploadedFile
        image_file = SimpleUploadedFile('test.png', b'PNGDATA', content_type='image/png')
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='hello', image=image_file)

        # Ensure DB changes are visible to the consumer thread
        from django.db import transaction
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/chat/{self.server.slug}/',
            headers=headers,
        )

        async def run_image_owner():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Consume history
            await communicator.receive_from(timeout=20)

            # Request image for a message the user owns
            await communicator.send_json_to({'type': 'chat_image', 'message_id': msg.id})
            raw = await communicator.receive_from(timeout=20)
            response = json.loads(raw)
            self.assertEqual(response.get('type'), 'chat_message')
            self.assertTrue(response.get('image_url'))

            await communicator.disconnect()

        asyncio.run(run_image_owner())

    def test_server_chat_image_message_not_sent_for_other_user(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)

        # Prepare a message with an image attached by user1
        from django.core.files.uploadedfile import SimpleUploadedFile
        image_file = SimpleUploadedFile('test.png', b'PNGDATA', content_type='image/png')
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='hello', image=image_file)

        # Ensure DB changes are visible to the consumer thread
        from django.db import transaction
        transaction.commit()

        headers = self._get_cookie_header(self.other)
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/chat/{self.server.slug}/',
            headers=headers,
        )

        async def run_image_other():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Consume history
            await communicator.receive_from(timeout=20)

            # Request image for a message the user does NOT own
            await communicator.send_json_to({'type': 'chat_image', 'message_id': msg.id})

            with self.assertRaises(asyncio.TimeoutError):
                await communicator.receive_from(timeout=1)

            # Other user should not receive a message; disconnect gracefully.
            try:
                await communicator.disconnect()
            except asyncio.CancelledError:
                pass

        asyncio.run(run_image_other())

    def test_server_chat_disconnect_stops_receiving_messages(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)

        # Ensure DB changes are visible to the consumer threads
        from django.db import transaction
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)

        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run_disconnect():
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Consume history messages
            await comm1.receive_from(timeout=20)
            await comm2.receive_from(timeout=20)

            # Send first message from user1
            await comm1.send_json_to({'type': 'chat_message', 'content': 'first'})
            raw = await comm2.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg.get('type'), 'chat_message')
            self.assertEqual(msg.get('content'), 'first')

            # Disconnect user2
            await comm2.disconnect()

            # Send second message from user1
            await comm1.send_json_to({'type': 'chat_message', 'content': 'second'})

            # User2 should not receive the second message (timeout)
            with self.assertRaises(asyncio.TimeoutError):
                await comm2.receive_from(timeout=1)

            await comm1.disconnect()

        asyncio.run(run_disconnect())

    def test_server_chat_empty_message_ignored(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)

        # Ensure DB changes are visible to the consumer threads
        from django.db import transaction
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)

        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run_empty():
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Consume history messages
            await comm1.receive_from(timeout=20)
            await comm2.receive_from(timeout=20)

            # Send empty message from user1
            await comm1.send_json_to({'type': 'chat_message', 'content': ''})

            # Send whitespace-only message
            await comm1.send_json_to({'type': 'chat_message', 'content': '   '})

            # User2 should not receive any message (timeout)
            with self.assertRaises(asyncio.TimeoutError):
                await comm2.receive_from(timeout=1)

            await comm1.disconnect()
            try:
                await comm2.disconnect()
            except asyncio.CancelledError:
                pass

        asyncio.run(run_empty())

    def test_server_chat_long_message_truncated(self):
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)

        # Ensure DB changes are visible to the consumer threads
        from django.db import transaction
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)

        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run_long():
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Consume history messages
            await comm1.receive_from(timeout=20)
            await comm2.receive_from(timeout=20)

            # Send very long message (over 2000 chars)
            long_content = 'a' * 2500
            await comm1.send_json_to({'type': 'chat_message', 'content': long_content})
            raw = await comm2.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg.get('type'), 'chat_message')
            self.assertEqual(len(msg.get('content')), 2000)  # Truncated to 2000
            self.assertEqual(msg.get('content'), 'a' * 2000)

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run_long())
