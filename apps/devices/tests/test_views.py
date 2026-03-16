from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class DeviceViewTests(TestCase):
    """Test device-related views."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Tester123.')

    def test_device_list_requires_login(self):
        """Device list requires login."""
        response = self.client.get(reverse('device_list'))
        self.assertEqual(response.status_code, 302)

    def test_device_list_accessible_when_logged_in(self):
        """Device list works when logged in."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.get(reverse('device_list'))
        self.assertEqual(response.status_code, 200)

    def test_register_device_requires_login(self):
        """Register device requires login."""
        response = self.client.post(reverse('register_device'), {'deviceId': 'test', 'label': 'Test', 'deviceType': 'camera'})
        self.assertEqual(response.status_code, 302)

    # Add more device tests