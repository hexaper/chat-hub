from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class AuthBoundaryTests(TestCase):
    """Test auth boundaries: views require login, non-members get 403, etc."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')
        self.other_user = User.objects.create_user(username='other', password='Tester123.')

    def test_login_required_for_profile(self):
        """Profile view requires login."""
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_accessible_when_logged_in(self):
        """Profile view redirects to settings when logged in."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/settings/', response['Location'])

    def test_settings_accessible_when_logged_in(self):
        """Settings view works when logged in."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 200)

    def test_logout_requires_login(self):
        """Logout view requires login."""
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_server_list_requires_login(self):
        """Server list requires login."""
        response = self.client.get(reverse('server_list'))
        self.assertEqual(response.status_code, 302)

    def test_server_create_requires_login(self):
        """Server create requires login."""
        response = self.client.get(reverse('server_create'))
        self.assertEqual(response.status_code, 302)

    def test_device_list_requires_login(self):
        """Device list requires login."""
        response = self.client.get(reverse('device_list'))
        self.assertEqual(response.status_code, 302)

    def test_admin_panel_requires_staff(self):
        """Admin panel requires staff (redirects non-staff)."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('admin_panel'))
        self.assertEqual(response.status_code, 302)

    def test_server_join_requires_login(self):
        """Server join requires login."""
        response = self.client.get(reverse('server_join'))
        self.assertEqual(response.status_code, 302)

    def test_server_leave_requires_login(self):
        """Server leave requires login."""
        dummy_slug = '12345678-1234-5678-9012-123456789012'  # Valid UUID format
        response = self.client.post(reverse('server_leave', args=[dummy_slug]))
        self.assertEqual(response.status_code, 302)

    def test_room_create_requires_login(self):
        """Room create requires login."""
        dummy_slug = '12345678-1234-5678-9012-123456789012'
        response = self.client.get(reverse('room_create', args=[dummy_slug]))
        self.assertEqual(response.status_code, 302)

    def test_room_leave_requires_login(self):
        """Room leave requires login."""
        dummy_slug = '12345678-1234-5678-9012-123456789012'
        response = self.client.post(reverse('room_leave', args=[dummy_slug, dummy_slug]))
        self.assertEqual(response.status_code, 302)

    # Add more tests for other views that require auth