from django.test import TestCase
from apps.accounts.forms import RegisterForm, ProfileForm
from django.contrib.auth import get_user_model

User = get_user_model()


class FormValidationTests(TestCase):
    """Test form validation: invalid inputs, duplicates, etc."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')

    def test_register_form_duplicate_username(self):
        """Register form rejects duplicate username."""
        User.objects.create_user(username='existing', password='Tester123.')
        form = RegisterForm(data={
            'username': 'existing',
            'email': 'existing@example.com',
            'password1': 'Tester123.',
            'password2': 'Tester123.'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_register_form_password_mismatch(self):
        """Register form rejects mismatched passwords."""
        form = RegisterForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'Tester123.',
            'password2': 'different'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_register_form_valid(self):
        """Register form accepts valid data."""
        form = RegisterForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'Tester123.',
            'password2': 'Tester123.'
        })
        self.assertTrue(form.is_valid())

    def test_profile_form_valid(self):
        """Profile form accepts valid data."""
        form = ProfileForm(data={
            'email': 'new@example.com',
            'bio': 'Test bio'
        }, instance=self.user)
        self.assertTrue(form.is_valid())

    # Add more form tests