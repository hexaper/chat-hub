import asyncio
import json
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.rooms import routing
from apps.rooms.models import Server, ServerMember, ChatMessage, Room, RoomParticipant

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
                await communicator.receive_from(timeout=0.3)

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
                await comm2.receive_from(timeout=0.3)

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
                await comm2.receive_from(timeout=0.3)

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

    def test_server_chat_rejects_non_member(self):
        """Authenticated user who is NOT a server member is rejected."""
        # self.user is not a member of self.server (only self.other is added in setUp)
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/chat/{self.server.slug}/',
            headers=headers,
        )

        async def run():
            connected, _ = await communicator.connect()
            return connected

        connected = asyncio.run(run())
        self.assertFalse(connected)


class RoomConsumerTests(TransactionTestCase):
    """Tests for RoomConsumer WebRTC signaling."""

    def setUp(self):
        self.host = User.objects.create_user(username='host', password='Tester123.')
        self.peer = User.objects.create_user(username='peer', password='Tester123.')
        self.server = Server.objects.create(name='TestServer', owner=self.host)
        ServerMember.objects.create(server=self.server, user=self.host)
        ServerMember.objects.create(server=self.server, user=self.peer)
        self.room = Room.objects.create(name='TestRoom', server=self.server, host=self.host)

        self.application = AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns))

    def _get_cookie_header(self, user):
        from django.test import Client
        client = Client()
        client.login(username=user.username, password='Tester123.')
        sessionid = client.cookies.get('sessionid')
        if not sessionid:
            return []
        return [(b'cookie', f'sessionid={sessionid.value}'.encode())]

    def _room_url(self):
        return f'/ws/rooms/{self.room.slug}/'

    def test_room_rejects_unauthenticated(self):
        """Unauthenticated user cannot connect to room."""
        transaction.commit()

        communicator = WebsocketCommunicator(self.application, self._room_url())

        async def run():
            connected, _ = await communicator.connect()
            return connected

        connected = asyncio.run(run())
        self.assertFalse(connected)

    def test_room_authenticated_receives_my_channel(self):
        """Authenticated user connects and receives my_channel message."""
        transaction.commit()

        headers = self._get_cookie_header(self.host)
        communicator = WebsocketCommunicator(
            self.application, self._room_url(), headers=headers
        )

        async def run():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            raw = await communicator.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'my_channel')
            self.assertIn('channel', msg)
            self.assertIsNotNone(msg['channel'])

            await communicator.disconnect()

        asyncio.run(run())

    def test_room_two_users_both_receive_user_joined(self):
        """When two users connect, both receive user_joined events."""
        transaction.commit()

        headers1 = self._get_cookie_header(self.host)
        headers2 = self._get_cookie_header(self.peer)
        comm1 = WebsocketCommunicator(self.application, self._room_url(), headers=headers1)
        comm2 = WebsocketCommunicator(self.application, self._room_url(), headers=headers2)

        async def run():
            connected1, _ = await comm1.connect()
            self.assertTrue(connected1)
            # host gets my_channel + user_joined (for themselves)
            msg = json.loads(await comm1.receive_from(timeout=20))
            self.assertEqual(msg['type'], 'my_channel')
            msg = json.loads(await comm1.receive_from(timeout=20))
            self.assertEqual(msg['type'], 'user_joined')
            self.assertEqual(msg['username'], self.host.username)

            connected2, _ = await comm2.connect()
            self.assertTrue(connected2)
            # peer gets my_channel + user_joined (for themselves)
            msg = json.loads(await comm2.receive_from(timeout=20))
            self.assertEqual(msg['type'], 'my_channel')
            msg = json.loads(await comm2.receive_from(timeout=20))
            self.assertEqual(msg['type'], 'user_joined')
            self.assertEqual(msg['username'], self.peer.username)

            # host also gets a user_joined notification about peer
            msg = json.loads(await comm1.receive_from(timeout=20))
            self.assertEqual(msg['type'], 'user_joined')
            self.assertEqual(msg['username'], self.peer.username)

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_room_offer_relayed_to_target(self):
        """Peer1 sends offer to peer2 channel; peer2 receives it."""
        transaction.commit()

        headers1 = self._get_cookie_header(self.host)
        headers2 = self._get_cookie_header(self.peer)
        comm1 = WebsocketCommunicator(self.application, self._room_url(), headers=headers1)
        comm2 = WebsocketCommunicator(self.application, self._room_url(), headers=headers2)

        async def run():
            await comm1.connect()
            # consume my_channel + user_joined for comm1
            await comm1.receive_from(timeout=20)
            await comm1.receive_from(timeout=20)

            await comm2.connect()
            # consume my_channel for comm2
            raw = await comm2.receive_from(timeout=20)
            peer2_channel = json.loads(raw)['channel']
            # consume user_joined for comm2
            await comm2.receive_from(timeout=20)

            # comm1 receives user_joined about peer
            await comm1.receive_from(timeout=20)

            # peer1 sends offer to peer2
            await comm1.send_json_to({
                'type': 'offer',
                'target': peer2_channel,
                'payload': {'sdp': 'v=0...'},
            })

            raw = await comm2.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'offer')
            self.assertIn('payload', msg)
            self.assertEqual(msg['payload']['sdp'], 'v=0...')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_room_answer_relayed_to_target(self):
        """Peer2 sends answer to peer1 channel; peer1 receives it."""
        transaction.commit()

        headers1 = self._get_cookie_header(self.host)
        headers2 = self._get_cookie_header(self.peer)
        comm1 = WebsocketCommunicator(self.application, self._room_url(), headers=headers1)
        comm2 = WebsocketCommunicator(self.application, self._room_url(), headers=headers2)

        async def run():
            await comm1.connect()
            raw = await comm1.receive_from(timeout=20)
            peer1_channel = json.loads(raw)['channel']
            await comm1.receive_from(timeout=20)  # user_joined self

            await comm2.connect()
            await comm2.receive_from(timeout=20)  # my_channel
            await comm2.receive_from(timeout=20)  # user_joined self
            await comm1.receive_from(timeout=20)  # comm1 gets user_joined for peer

            await comm2.send_json_to({
                'type': 'answer',
                'target': peer1_channel,
                'payload': {'sdp': 'answer...'},
            })

            raw = await comm1.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'answer')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_room_ice_candidate_relayed_to_target(self):
        """ice-candidate message is relayed to target channel."""
        transaction.commit()

        headers1 = self._get_cookie_header(self.host)
        headers2 = self._get_cookie_header(self.peer)
        comm1 = WebsocketCommunicator(self.application, self._room_url(), headers=headers1)
        comm2 = WebsocketCommunicator(self.application, self._room_url(), headers=headers2)

        async def run():
            await comm1.connect()
            await comm1.receive_from(timeout=20)  # my_channel
            await comm1.receive_from(timeout=20)  # user_joined self

            await comm2.connect()
            raw = await comm2.receive_from(timeout=20)
            peer2_channel = json.loads(raw)['channel']
            await comm2.receive_from(timeout=20)  # user_joined self
            await comm1.receive_from(timeout=20)  # comm1 gets user_joined for peer

            await comm1.send_json_to({
                'type': 'ice-candidate',
                'target': peer2_channel,
                'payload': {'candidate': 'candidate:0...'},
            })

            raw = await comm2.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'ice-candidate')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_room_media_state_broadcast(self):
        """media_state message is broadcast to the room group."""
        transaction.commit()

        headers1 = self._get_cookie_header(self.host)
        headers2 = self._get_cookie_header(self.peer)
        comm1 = WebsocketCommunicator(self.application, self._room_url(), headers=headers1)
        comm2 = WebsocketCommunicator(self.application, self._room_url(), headers=headers2)

        async def run():
            await comm1.connect()
            await comm1.receive_from(timeout=20)  # my_channel
            await comm1.receive_from(timeout=20)  # user_joined self

            await comm2.connect()
            await comm2.receive_from(timeout=20)  # my_channel
            await comm2.receive_from(timeout=20)  # user_joined self
            await comm1.receive_from(timeout=20)  # comm1 gets user_joined for peer

            await comm1.send_json_to({'type': 'media_state', 'mic': True, 'cam': False})

            # both comm1 and comm2 should receive media_state
            raw1 = await comm1.receive_from(timeout=20)
            msg1 = json.loads(raw1)
            self.assertEqual(msg1['type'], 'media_state')
            self.assertTrue(msg1['mic'])
            self.assertFalse(msg1['cam'])

            raw2 = await comm2.receive_from(timeout=20)
            msg2 = json.loads(raw2)
            self.assertEqual(msg2['type'], 'media_state')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_room_host_can_kick(self):
        """Host sends kick → target receives kicked message."""
        transaction.commit()

        headers_host = self._get_cookie_header(self.host)
        headers_peer = self._get_cookie_header(self.peer)
        comm_host = WebsocketCommunicator(self.application, self._room_url(), headers=headers_host)
        comm_peer = WebsocketCommunicator(self.application, self._room_url(), headers=headers_peer)

        async def run():
            await comm_host.connect()
            await comm_host.receive_from(timeout=20)  # my_channel
            await comm_host.receive_from(timeout=20)  # user_joined self

            await comm_peer.connect()
            raw = await comm_peer.receive_from(timeout=20)
            peer_channel = json.loads(raw)['channel']
            await comm_peer.receive_from(timeout=20)  # user_joined self
            await comm_host.receive_from(timeout=20)  # host gets user_joined for peer

            await comm_host.send_json_to({
                'type': 'kick',
                'target_channel': peer_channel,
                'username': self.peer.username,
            })

            # peer should get kicked message
            raw = await comm_peer.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'kicked')

            await comm_host.disconnect()
            try:
                await comm_peer.disconnect()
            except Exception:
                pass

        asyncio.run(run())

    def test_room_non_host_kick_is_ignored(self):
        """Non-host sending kick is silently ignored; target receives nothing."""
        transaction.commit()

        headers_host = self._get_cookie_header(self.host)
        headers_peer = self._get_cookie_header(self.peer)
        comm_host = WebsocketCommunicator(self.application, self._room_url(), headers=headers_host)
        comm_peer = WebsocketCommunicator(self.application, self._room_url(), headers=headers_peer)

        async def run():
            await comm_host.connect()
            raw = await comm_host.receive_from(timeout=20)
            host_channel = json.loads(raw)['channel']
            await comm_host.receive_from(timeout=20)  # user_joined self

            await comm_peer.connect()
            await comm_peer.receive_from(timeout=20)  # my_channel
            await comm_peer.receive_from(timeout=20)  # user_joined self
            await comm_host.receive_from(timeout=20)  # host gets user_joined for peer

            # peer (non-host) tries to kick host
            await comm_peer.send_json_to({
                'type': 'kick',
                'target_channel': host_channel,
                'username': self.host.username,
            })

            # host should receive nothing (timeout)
            received_something = False
            try:
                await comm_host.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something, "Non-host kick should be ignored")

            try:
                await comm_host.disconnect()
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await comm_peer.disconnect()
            except (asyncio.CancelledError, Exception):
                pass

        asyncio.run(run())

    def test_room_host_can_mute_user(self):

        """Host sends mute_user → target receives force_mute."""
        transaction.commit()

        headers_host = self._get_cookie_header(self.host)
        headers_peer = self._get_cookie_header(self.peer)
        comm_host = WebsocketCommunicator(self.application, self._room_url(), headers=headers_host)
        comm_peer = WebsocketCommunicator(self.application, self._room_url(), headers=headers_peer)

        async def run():
            await comm_host.connect()
            await comm_host.receive_from(timeout=20)  # my_channel
            await comm_host.receive_from(timeout=20)  # user_joined self

            await comm_peer.connect()
            raw = await comm_peer.receive_from(timeout=20)
            peer_channel = json.loads(raw)['channel']
            await comm_peer.receive_from(timeout=20)  # user_joined self
            await comm_host.receive_from(timeout=20)  # host gets user_joined for peer

            await comm_host.send_json_to({
                'type': 'mute_user',
                'target_channel': peer_channel,
            })

            raw = await comm_peer.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'force_mute')

            await comm_host.disconnect()
            await comm_peer.disconnect()

        asyncio.run(run())

    def test_room_non_host_mute_is_ignored(self):
        """Non-host sending mute_user is silently ignored."""
        transaction.commit()

        headers_host = self._get_cookie_header(self.host)
        headers_peer = self._get_cookie_header(self.peer)
        comm_host = WebsocketCommunicator(self.application, self._room_url(), headers=headers_host)
        comm_peer = WebsocketCommunicator(self.application, self._room_url(), headers=headers_peer)

        async def run():
            await comm_host.connect()
            raw = await comm_host.receive_from(timeout=20)
            host_channel = json.loads(raw)['channel']
            await comm_host.receive_from(timeout=20)  # user_joined self

            await comm_peer.connect()
            await comm_peer.receive_from(timeout=20)  # my_channel
            await comm_peer.receive_from(timeout=20)  # user_joined self
            await comm_host.receive_from(timeout=20)  # host gets user_joined for peer

            # peer (non-host) tries to mute host
            await comm_peer.send_json_to({
                'type': 'mute_user',
                'target_channel': host_channel,
            })

            # host should receive nothing (timeout)
            received_something = False
            try:
                await comm_host.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something, "Non-host mute should be ignored")

            try:
                await comm_host.disconnect()
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await comm_peer.disconnect()
            except (asyncio.CancelledError, Exception):
                pass

        asyncio.run(run())

    def test_room_disconnect_broadcasts_user_left(self):
        """When a user disconnects, remaining peers receive user_left."""
        transaction.commit()

        headers_host = self._get_cookie_header(self.host)
        headers_peer = self._get_cookie_header(self.peer)
        comm_host = WebsocketCommunicator(self.application, self._room_url(), headers=headers_host)
        comm_peer = WebsocketCommunicator(self.application, self._room_url(), headers=headers_peer)

        async def run():
            await comm_host.connect()
            await comm_host.receive_from(timeout=20)  # my_channel
            await comm_host.receive_from(timeout=20)  # user_joined self

            await comm_peer.connect()
            await comm_peer.receive_from(timeout=20)  # my_channel
            await comm_peer.receive_from(timeout=20)  # user_joined self
            await comm_host.receive_from(timeout=20)  # host gets user_joined for peer

            # peer disconnects
            await comm_peer.disconnect()

            # host should receive user_left for peer
            raw = await comm_host.receive_from(timeout=20)
            msg = json.loads(raw)
            self.assertEqual(msg['type'], 'user_left')
            self.assertEqual(msg['username'], self.peer.username)

            await comm_host.disconnect()

        asyncio.run(run())

    def test_room_last_empty_at_set_when_room_becomes_empty(self):
        """When the last user disconnects, last_empty_at is set on the Room."""
        transaction.commit()

        headers = self._get_cookie_header(self.host)
        communicator = WebsocketCommunicator(
            self.application, self._room_url(), headers=headers
        )

        async def run():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_from(timeout=20)  # my_channel
            await communicator.receive_from(timeout=20)  # user_joined

            await communicator.disconnect()

        asyncio.run(run())

        self.room.refresh_from_db()
        self.assertIsNotNone(self.room.last_empty_at)
