from django.test import TestCase
from django.db import IntegrityError
from apps.rooms.models import (
    Server,
    ServerMember,
    ServerBan,
    ChatReadState,
    Room,
    ChatMessage,
    RoomChatMessage,
    generate_invite_code,
)
from django.contrib.auth import get_user_model

User = get_user_model()


class ModelLogicTests(TestCase):
    """Test model logic: invite codes, passwords, cleanup, etc."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='Tester123.')

    def test_generate_invite_code_unique(self):
        """Invite codes are unique and 8 characters."""
        code1 = generate_invite_code()
        code2 = generate_invite_code()
        self.assertNotEqual(code1, code2)
        self.assertEqual(len(code1), 8)
        self.assertTrue(code1.isalnum())

    def test_server_invite_code_unique(self):
        """Server invite codes are unique."""
        server1 = Server.objects.create(name='Server1', owner=self.user)
        server2 = Server.objects.create(name='Server2', owner=self.user)
        self.assertNotEqual(server1.invite_code, server2.invite_code)

    def test_room_password_validation(self):
        """Room password set and check works."""
        room = Room.objects.create(name='Room', server=Server.objects.create(name='Server', owner=self.user), host=self.user)
        room.set_password('secret123')
        self.assertTrue(room.check_room_password('secret123'))
        self.assertFalse(room.check_room_password('wrong'))

    def test_room_is_password_protected(self):
        """Room knows if it's password protected."""
        room = Room.objects.create(name='Room', server=Server.objects.create(name='Server', owner=self.user), host=self.user)
        self.assertFalse(room.is_password_protected)
        room.set_password('secret')
        self.assertTrue(room.is_password_protected)

    def test_server_public_default(self):
        """Server is private by default."""
        server = Server.objects.create(name='Server', owner=self.user)
        self.assertFalse(server.is_public)

    def test_chat_message_creation(self):
        """ChatMessage can be created."""
        server = Server.objects.create(name='Server', owner=self.user)
        message = server.messages.create(content='Hello', user=self.user)
        self.assertEqual(message.content, 'Hello')
        self.assertEqual(message.user, self.user)

    # Add more model tests


class IndexMetaTests(TestCase):
    """Verify composite indexes declared on model Meta are present."""

    def test_chatmessage_has_server_created_index(self):
        index_names = [idx.name for idx in ChatMessage._meta.indexes]
        self.assertIn('chat_server_created_idx', index_names)

    def test_roomchatmessage_has_room_created_index(self):
        index_names = [idx.name for idx in RoomChatMessage._meta.indexes]
        self.assertIn('roomchat_room_created_idx', index_names)

    def test_room_has_server_active_index(self):
        index_names = [idx.name for idx in Room._meta.indexes]
        self.assertIn('room_server_active_idx', index_names)


class TrustAndReadStateModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='owner', password='Tester123.')
        cls.user = User.objects.create_user(username='member', password='Tester123.')
        cls.server = Server.objects.create(name='S1', owner=cls.owner)

    def test_server_member_defaults_to_member_role(self):
        member = ServerMember.objects.create(server=self.server, user=self.user)
        self.assertEqual(member.role, ServerMember.ROLE_MEMBER)

    def test_server_member_can_be_admin(self):
        member = ServerMember.objects.create(
            server=self.server,
            user=self.user,
            role=ServerMember.ROLE_ADMIN,
        )
        self.assertEqual(member.role, ServerMember.ROLE_ADMIN)

    def test_server_ban_blocks_duplicate_active_ban(self):
        ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.owner)
        with self.assertRaises(IntegrityError):
            ServerBan.objects.create(server=self.server, user=self.user, banned_by=self.owner)

    def test_chat_read_state_stores_last_read_message(self):
        msg = ChatMessage.objects.create(server=self.server, user=self.owner, content='hello')
        state = ChatReadState.objects.create(
            server=self.server,
            user=self.user,
            last_read_message=msg,
        )
        self.assertEqual(state.last_read_message_id, msg.id)
