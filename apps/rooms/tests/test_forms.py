from django.test import TestCase
from apps.rooms.forms import ServerForm, RoomForm, RoomPasswordForm
from django.contrib.auth import get_user_model

User = get_user_model()


class RoomFormValidationTests(TestCase):
    """Test form validation for rooms."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='Tester123.')

    def test_server_form_valid(self):
        """Server form accepts valid data."""
        form = ServerForm(data={
            'name': 'Test Server',
            'description': 'A test server',
            'is_public': True
        })
        self.assertTrue(form.is_valid())

    def test_server_form_blank_name(self):
        """Server form rejects blank name."""
        form = ServerForm(data={
            'name': '',
            'description': 'A test server',
            'is_public': True
        })
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_room_form_valid(self):
        """Room form accepts valid data."""
        form = RoomForm(data={
            'name': 'Test Room',
            'password': ''
        })
        self.assertTrue(form.is_valid())

    def test_room_form_blank_name(self):
        """Room form rejects blank name."""
        form = RoomForm(data={
            'name': '',
            'password': 'secret'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_room_password_form_valid(self):
        """Room password form accepts password."""
        form = RoomPasswordForm(data={'password': 'secret123'})
        self.assertTrue(form.is_valid())

    def test_room_password_form_blank(self):
        """Room password form rejects blank password."""
        form = RoomPasswordForm(data={'password': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)