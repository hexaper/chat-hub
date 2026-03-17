import asyncio
import json
from datetime import timedelta
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.rooms import routing
from apps.rooms.models import Server, ServerMember, ChatMessage, Room, RoomParticipant, RoomChatMessage

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

    # ------------------------------------------------------------------
    # edit_message tests
    # ------------------------------------------------------------------

    def test_edit_message_success(self):
        """Author can edit their own message within 15 minutes and receives message_edited broadcast."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='original')
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)
        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run():
            await comm1.connect()
            await comm2.connect()
            # drain history for both
            await comm1.receive_from(timeout=20)
            await comm2.receive_from(timeout=20)

            await comm1.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'edited content',
            })

            raw = await comm1.receive_from(timeout=20)
            response = json.loads(raw)
            self.assertEqual(response.get('type'), 'message_edited',
                             msg=f"Expected 'message_edited' from author's socket, got: {response}")
            self.assertEqual(response.get('id'), msg.id,
                             msg=f"Expected message id={msg.id}, got: {response.get('id')}")
            self.assertEqual(response.get('content'), 'edited content',
                             msg=f"Expected content='edited content', got: {response.get('content')}")
            self.assertIsNotNone(response.get('updated_at'),
                                 msg="message_edited broadcast must include updated_at")

            # The other connected member should also receive the broadcast
            raw2 = await comm2.receive_from(timeout=20)
            response2 = json.loads(raw2)
            self.assertEqual(response2.get('type'), 'message_edited',
                             msg=f"Expected 'message_edited' broadcast to second member, got: {response2}")
            self.assertEqual(response2.get('id'), msg.id)
            self.assertEqual(response2.get('content'), 'edited content')

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_edit_message_updates_db(self):
        """After a successful edit, content and updated_at are persisted to the database."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='before edit')
        self.assertIsNone(msg.updated_at, msg="updated_at should be NULL before any edit")
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'after edit',
            })
            await communicator.receive_from(timeout=20)  # message_edited broadcast

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'after edit',
                         msg=f"DB content should be 'after edit', got: '{msg.content}'")
        self.assertIsNotNone(msg.updated_at,
                             msg="DB updated_at must be set after a successful edit")

    def test_edit_message_past_window(self):
        """Edit is silently rejected when message was created more than 15 minutes ago."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        old_created_at = timezone.now() - timedelta(minutes=16)
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='old message')
        # Force created_at back in time to simulate an expired edit window
        ChatMessage.objects.filter(pk=msg.pk).update(created_at=old_created_at)
        msg.refresh_from_db()
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'attempt to edit old message',
            })

            # No broadcast should arrive — consumer silently ignores the request
            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="edit_message past the 15-minute window must produce no broadcast")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'old message',
                         msg="DB content must be unchanged when edit is rejected due to expired window")
        self.assertIsNone(msg.updated_at,
                          msg="DB updated_at must remain NULL when edit is rejected")

    def test_edit_message_wrong_owner(self):
        """A user cannot edit a message that belongs to another user."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)
        # message owned by self.other
        msg = ChatMessage.objects.create(server=self.server, user=self.other, content='others message')
        transaction.commit()

        # self.user (not the owner) attempts the edit
        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'attempted hijack',
            })

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="edit_message for another user's message must be silently ignored")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'others message',
                         msg="DB content must be unchanged when edit attempt is made by wrong owner")

    def test_edit_message_deleted_message(self):
        """A user cannot edit a message that has already been soft-deleted."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        msg = ChatMessage.objects.create(
            server=self.server,
            user=self.user,
            content='will be deleted',
            deleted_at=timezone.now(),
        )
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'trying to edit deleted message',
            })

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="edit_message on a deleted message must be silently ignored")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'will be deleted',
                         msg="DB content must not change when editing a deleted message")

    # ------------------------------------------------------------------
    # delete_message tests
    # ------------------------------------------------------------------

    def test_delete_message_success(self):
        """Author can delete their own message and all members receive message_deleted broadcast."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='to be deleted')
        transaction.commit()

        headers1 = self._get_cookie_header(self.user)
        headers2 = self._get_cookie_header(self.other)
        comm1 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers1)
        comm2 = WebsocketCommunicator(self.application, f'/ws/chat/{self.server.slug}/', headers=headers2)

        async def run():
            await comm1.connect()
            await comm2.connect()
            await comm1.receive_from(timeout=20)  # drain history
            await comm2.receive_from(timeout=20)  # drain history

            await comm1.send_json_to({'type': 'delete_message', 'message_id': msg.id})

            raw1 = await comm1.receive_from(timeout=20)
            response1 = json.loads(raw1)
            self.assertEqual(response1.get('type'), 'message_deleted',
                             msg=f"Expected 'message_deleted' from author's socket, got: {response1}")
            self.assertEqual(response1.get('id'), msg.id,
                             msg=f"Expected message id={msg.id} in broadcast, got: {response1.get('id')}")

            raw2 = await comm2.receive_from(timeout=20)
            response2 = json.loads(raw2)
            self.assertEqual(response2.get('type'), 'message_deleted',
                             msg=f"Expected 'message_deleted' broadcast to second member, got: {response2}")
            self.assertEqual(response2.get('id'), msg.id)

            await comm1.disconnect()
            await comm2.disconnect()

        asyncio.run(run())

    def test_delete_message_sets_deleted_at(self):
        """After a successful delete, deleted_at is persisted in the database."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        msg = ChatMessage.objects.create(server=self.server, user=self.user, content='will be soft-deleted')
        self.assertIsNone(msg.deleted_at, msg="deleted_at should be NULL before deletion")
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({'type': 'delete_message', 'message_id': msg.id})
            await communicator.receive_from(timeout=20)  # message_deleted broadcast

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertIsNotNone(msg.deleted_at,
                             msg="DB deleted_at must be set after a successful delete")

    def test_delete_message_wrong_owner(self):
        """A user cannot delete a message that belongs to another user."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        ServerMember.objects.get_or_create(server=self.server, user=self.other)
        # message owned by self.other
        msg = ChatMessage.objects.create(server=self.server, user=self.other, content='others message')
        transaction.commit()

        # self.user (not the owner) attempts the delete
        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({'type': 'delete_message', 'message_id': msg.id})

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="delete_message for another user's message must be silently ignored")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertIsNone(msg.deleted_at,
                          msg="DB deleted_at must remain NULL when delete attempt is made by wrong owner")

    def test_delete_message_already_deleted(self):
        """Deleting an already soft-deleted message is silently ignored; no second broadcast."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        first_deleted_at = timezone.now()
        msg = ChatMessage.objects.create(
            server=self.server,
            user=self.user,
            content='already gone',
            deleted_at=first_deleted_at,
        )
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({'type': 'delete_message', 'message_id': msg.id})

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="delete_message on an already-deleted message must produce no broadcast")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.deleted_at, first_deleted_at,
                         msg="deleted_at must not be overwritten on a repeated delete attempt")

    # ------------------------------------------------------------------
    # history field tests
    # ------------------------------------------------------------------

    def test_history_includes_updated_at_and_deleted_at_fields(self):
        """History messages always include updated_at and deleted_at keys."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        # A normal unedited, non-deleted message
        ChatMessage.objects.create(server=self.server, user=self.user, content='plain message')
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            raw = await communicator.receive_from(timeout=20)
            history = json.loads(raw)

            self.assertEqual(history.get('type'), 'history',
                             msg=f"First message on connect must be 'history', got: {history.get('type')}")
            messages = history.get('messages', [])
            self.assertGreater(len(messages), 0, msg="History must contain at least one message")

            for entry in messages:
                self.assertIn('updated_at', entry,
                              msg=f"History entry missing 'updated_at' key: {entry}")
                self.assertIn('deleted_at', entry,
                              msg=f"History entry missing 'deleted_at' key: {entry}")

            # For an unedited, non-deleted message both fields should be null/None
            plain = messages[-1]
            self.assertIsNone(plain['updated_at'],
                              msg="updated_at must be null for a message that has never been edited")
            self.assertIsNone(plain['deleted_at'],
                              msg="deleted_at must be null for a message that has not been deleted")

            await communicator.disconnect()

        asyncio.run(run())

    def test_history_deleted_message_has_empty_content_and_image_url(self):
        """Deleted messages in history have empty string for content and image_url, and a non-null deleted_at."""
        ServerMember.objects.get_or_create(server=self.server, user=self.user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        image_file = SimpleUploadedFile('test.png', b'PNGDATA', content_type='image/png')
        msg = ChatMessage.objects.create(
            server=self.server,
            user=self.user,
            content='secret content',
            image=image_file,
            deleted_at=timezone.now(),
        )
        transaction.commit()

        headers = self._get_cookie_header(self.user)
        communicator = WebsocketCommunicator(
            self.application, f'/ws/chat/{self.server.slug}/', headers=headers
        )

        async def run():
            await communicator.connect()
            raw = await communicator.receive_from(timeout=20)
            history = json.loads(raw)

            self.assertEqual(history.get('type'), 'history')
            messages = history.get('messages', [])
            target = next((m for m in messages if m['id'] == msg.id), None)
            self.assertIsNotNone(target,
                                 msg=f"Deleted message id={msg.id} must still appear in history")
            self.assertEqual(target['content'], '',
                             msg="Deleted message content must be empty string in history")
            self.assertEqual(target['image_url'], '',
                             msg="Deleted message image_url must be empty string in history")
            self.assertIsNotNone(target['deleted_at'],
                                 msg="Deleted message must have a non-null deleted_at in history")

            await communicator.disconnect()

        asyncio.run(run())


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


class RoomChatConsumerTests(TransactionTestCase):
    """Tests for RoomChatConsumer — in-room text chat with edit and delete support.

    RoomChatConsumer requires the connecting user to be a RoomParticipant on an
    active Room.  Each test creates that participant record explicitly and calls
    transaction.commit() before entering any async block, so the consumer thread
    can see the data.
    """

    def setUp(self):
        self.author = User.objects.create_user(username='rc_author', password='Tester123.')
        self.other = User.objects.create_user(username='rc_other', password='Tester123.')
        self.server = Server.objects.create(name='RCServer', owner=self.author)
        ServerMember.objects.create(server=self.server, user=self.author)
        ServerMember.objects.create(server=self.server, user=self.other)
        self.room = Room.objects.create(name='RCRoom', server=self.server, host=self.author)
        # Both users are participants so they can connect to RoomChatConsumer.
        RoomParticipant.objects.create(room=self.room, user=self.author)
        RoomParticipant.objects.create(room=self.room, user=self.other)

        self.application = AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns))

    def _get_cookie_header(self, user):
        from django.test import Client
        client = Client()
        client.login(username=user.username, password='Tester123.')
        sessionid = client.cookies.get('sessionid')
        if not sessionid:
            return []
        return [(b'cookie', f'sessionid={sessionid.value}'.encode())]

    def _room_chat_url(self):
        return f'/ws/room-chat/{self.room.slug}/'

    # ------------------------------------------------------------------
    # edit_message tests
    # ------------------------------------------------------------------

    def test_room_chat_edit_message_success(self):
        """Author edits their own message within the 15-minute window; all participants
        receive a message_edited broadcast with the updated content and updated_at."""
        msg = RoomChatMessage.objects.create(room=self.room, user=self.author, content='original')
        transaction.commit()

        headers_author = self._get_cookie_header(self.author)
        headers_other = self._get_cookie_header(self.other)
        comm_author = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_author)
        comm_other = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_other)

        async def run():
            await comm_author.connect()
            await comm_other.connect()
            await comm_author.receive_from(timeout=20)  # drain history
            await comm_other.receive_from(timeout=20)   # drain history

            await comm_author.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'edited content',
            })

            # Author receives the broadcast
            raw_author = await comm_author.receive_from(timeout=20)
            resp_author = json.loads(raw_author)
            self.assertEqual(resp_author.get('type'), 'message_edited',
                             msg=f"Author's socket expected 'message_edited', got: {resp_author}")
            self.assertEqual(resp_author.get('id'), msg.id,
                             msg=f"Broadcast must carry message id={msg.id}, got: {resp_author.get('id')}")
            self.assertEqual(resp_author.get('content'), 'edited content',
                             msg=f"Broadcast content must be 'edited content', got: {resp_author.get('content')}")
            self.assertIsNotNone(resp_author.get('updated_at'),
                                 msg="message_edited broadcast must include a non-null updated_at")

            # Other participant also receives the broadcast
            raw_other = await comm_other.receive_from(timeout=20)
            resp_other = json.loads(raw_other)
            self.assertEqual(resp_other.get('type'), 'message_edited',
                             msg=f"Other participant expected 'message_edited' broadcast, got: {resp_other}")
            self.assertEqual(resp_other.get('id'), msg.id)
            self.assertEqual(resp_other.get('content'), 'edited content')

            await comm_author.disconnect()
            await comm_other.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'edited content',
                         msg="DB content must be updated after a successful edit")
        self.assertIsNotNone(msg.updated_at,
                             msg="DB updated_at must be set after a successful edit")

    def test_room_chat_edit_message_past_window(self):
        """Edit is silently dropped when message was created more than 15 minutes ago;
        no broadcast is sent and the DB content is unchanged."""
        msg = RoomChatMessage.objects.create(room=self.room, user=self.author, content='old message')
        # Force created_at back to 16 minutes ago to exceed the edit window
        RoomChatMessage.objects.filter(pk=msg.pk).update(
            created_at=timezone.now() - timedelta(minutes=16)
        )
        msg.refresh_from_db()
        transaction.commit()

        headers = self._get_cookie_header(self.author)
        communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'attempted late edit',
            })

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="edit_message past the 15-minute window must produce no broadcast")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'old message',
                         msg="DB content must be unchanged when edit is rejected due to expired window")
        self.assertIsNone(msg.updated_at,
                          msg="DB updated_at must remain NULL when edit is rejected due to expired window")

    def test_room_chat_edit_message_wrong_owner(self):
        """A user cannot edit a RoomChatMessage that belongs to another participant;
        the request is silently ignored and the DB is unchanged."""
        # Message owned by self.other; self.author will attempt the edit
        msg = RoomChatMessage.objects.create(room=self.room, user=self.other, content='others message')
        transaction.commit()

        headers = self._get_cookie_header(self.author)
        communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({
                'type': 'edit_message',
                'message_id': msg.id,
                'content': 'attempted hijack',
            })

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="edit_message on another user's message must be silently ignored")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertEqual(msg.content, 'others message',
                         msg="DB content must be unchanged when edit is attempted by the wrong owner")
        self.assertIsNone(msg.updated_at,
                          msg="DB updated_at must remain NULL when edit is attempted by the wrong owner")

    # ------------------------------------------------------------------
    # delete_message tests
    # ------------------------------------------------------------------

    def test_room_chat_delete_message_success(self):
        """Author soft-deletes their own message; all participants receive
        message_deleted broadcast and deleted_at is persisted."""
        msg = RoomChatMessage.objects.create(room=self.room, user=self.author, content='to be deleted')
        self.assertIsNone(msg.deleted_at, msg="deleted_at must be NULL before deletion")
        transaction.commit()

        headers_author = self._get_cookie_header(self.author)
        headers_other = self._get_cookie_header(self.other)
        comm_author = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_author)
        comm_other = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_other)

        async def run():
            await comm_author.connect()
            await comm_other.connect()
            await comm_author.receive_from(timeout=20)  # drain history
            await comm_other.receive_from(timeout=20)   # drain history

            await comm_author.send_json_to({'type': 'delete_message', 'message_id': msg.id})

            raw_author = await comm_author.receive_from(timeout=20)
            resp_author = json.loads(raw_author)
            self.assertEqual(resp_author.get('type'), 'message_deleted',
                             msg=f"Author's socket expected 'message_deleted', got: {resp_author}")
            self.assertEqual(resp_author.get('id'), msg.id,
                             msg=f"Broadcast must carry message id={msg.id}, got: {resp_author.get('id')}")

            raw_other = await comm_other.receive_from(timeout=20)
            resp_other = json.loads(raw_other)
            self.assertEqual(resp_other.get('type'), 'message_deleted',
                             msg=f"Other participant expected 'message_deleted' broadcast, got: {resp_other}")
            self.assertEqual(resp_other.get('id'), msg.id)

            await comm_author.disconnect()
            await comm_other.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertIsNotNone(msg.deleted_at,
                             msg="DB deleted_at must be set after a successful delete")

    def test_room_chat_delete_message_wrong_owner(self):
        """A user cannot delete a RoomChatMessage that belongs to another participant;
        the request is silently ignored and deleted_at remains NULL."""
        # Message owned by self.other; self.author attempts the delete
        msg = RoomChatMessage.objects.create(room=self.room, user=self.other, content='others message')
        transaction.commit()

        headers = self._get_cookie_header(self.author)
        communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

        async def run():
            await communicator.connect()
            await communicator.receive_from(timeout=20)  # drain history

            await communicator.send_json_to({'type': 'delete_message', 'message_id': msg.id})

            received_something = False
            try:
                await communicator.receive_from(timeout=0.3)
                received_something = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(received_something,
                             msg="delete_message on another user's message must be silently ignored")

            await communicator.disconnect()

        asyncio.run(run())

        msg.refresh_from_db()
        self.assertIsNone(msg.deleted_at,
                          msg="DB deleted_at must remain NULL when delete is attempted by the wrong owner")

    # ------------------------------------------------------------------
    # typing indicator tests
    # ------------------------------------------------------------------

    def test_room_chat_typing_indicator(self):
        """When a user sends a typing event, other connected participants receive
        a user_typing message containing their username; the sender does NOT
        receive their own typing event (exclude filter)."""
        transaction.commit()

        headers_author = self._get_cookie_header(self.author)
        headers_other = self._get_cookie_header(self.other)
        comm_author = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_author)
        comm_other = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers_other)

        async def run():
            await comm_author.connect()
            await comm_other.connect()
            await comm_author.receive_from(timeout=20)  # drain history
            await comm_other.receive_from(timeout=20)   # drain history

            await comm_author.send_json_to({'type': 'typing'})

            # Other participant must receive user_typing
            raw_other = await comm_other.receive_from(timeout=20)
            resp_other = json.loads(raw_other)
            self.assertEqual(resp_other.get('type'), 'user_typing',
                             msg=f"Other participant expected 'user_typing', got: {resp_other}")
            self.assertEqual(resp_other.get('username'), self.author.username,
                             msg=f"user_typing must carry the sender's username '{self.author.username}', "
                                 f"got: '{resp_other.get('username')}'")

            # Sender must NOT receive their own typing event
            sender_received = False
            try:
                await comm_author.receive_from(timeout=0.3)
                sender_received = True
            except asyncio.TimeoutError:
                pass

            self.assertFalse(sender_received,
                             msg="Sender must not receive their own user_typing event (exclude filter)")

            await comm_author.disconnect()
            await comm_other.disconnect()

        asyncio.run(run())

    # ------------------------------------------------------------------
    # history field tests
    # ------------------------------------------------------------------

    def test_room_chat_history_includes_edit_delete_fields(self):
        """History messages sent on connect always include both updated_at and
        deleted_at keys.  For a brand-new message both fields must be null."""
        RoomChatMessage.objects.create(room=self.room, user=self.author, content='plain message')
        transaction.commit()

        headers = self._get_cookie_header(self.author)
        communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

        async def run():
            await communicator.connect()
            raw = await communicator.receive_from(timeout=20)
            history = json.loads(raw)

            self.assertEqual(history.get('type'), 'history',
                             msg=f"First message after connect must be 'history', got: {history.get('type')}")
            messages = history.get('messages', [])
            self.assertGreater(len(messages), 0,
                               msg="History must contain at least the one message created in this test")

            for entry in messages:
                self.assertIn('updated_at', entry,
                              msg=f"History entry missing 'updated_at' key: {entry}")
                self.assertIn('deleted_at', entry,
                              msg=f"History entry missing 'deleted_at' key: {entry}")

            # The message created above has never been edited or deleted
            plain = messages[-1]
            self.assertIsNone(plain['updated_at'],
                              msg="updated_at must be null for a message that has never been edited")
            self.assertIsNone(plain['deleted_at'],
                              msg="deleted_at must be null for a message that has not been deleted")

            await communicator.disconnect()

        asyncio.run(run())

    def test_room_chat_history_deleted_message_has_empty_content(self):
        """Deleted RoomChatMessages appear in history with content='' and a
        non-null deleted_at; the original text is not exposed."""
        msg = RoomChatMessage.objects.create(
            room=self.room,
            user=self.author,
            content='secret content',
            deleted_at=timezone.now(),
        )
        transaction.commit()

        headers = self._get_cookie_header(self.author)
        communicator = WebsocketCommunicator(self.application, self._room_chat_url(), headers=headers)

        async def run():
            await communicator.connect()
            raw = await communicator.receive_from(timeout=20)
            history = json.loads(raw)

            self.assertEqual(history.get('type'), 'history')
            messages = history.get('messages', [])
            target = next((m for m in messages if m['id'] == msg.id), None)
            self.assertIsNotNone(target,
                                 msg=f"Deleted message id={msg.id} must still appear in history")
            self.assertEqual(target['content'], '',
                             msg="Deleted message content must be empty string in history")
            self.assertIsNotNone(target['deleted_at'],
                                 msg="Deleted message must have a non-null deleted_at in history")

            await communicator.disconnect()

        asyncio.run(run())
