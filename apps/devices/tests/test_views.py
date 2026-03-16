import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.devices.models import Device

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

    def test_register_device_creates_device(self):
        """POST to register_device with valid JSON creates a device and returns 200."""
        self.client.login(username='testuser', password='Tester123.')
        payload = {'deviceId': 'abc123', 'label': 'Camera', 'deviceType': 'camera'}
        response = self.client.post(
            reverse('register_device'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('id', data)
        self.assertTrue(Device.objects.filter(user=self.user, device_id='abc123').exists())

    def test_register_device_microphone(self):
        """POST to register_device with microphone type creates microphone device."""
        self.client.login(username='testuser', password='Tester123.')
        payload = {'deviceId': 'mic001', 'label': 'My Microphone', 'deviceType': 'microphone'}
        response = self.client.post(
            reverse('register_device'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Device.objects.filter(user=self.user, device_id='mic001', device_type='microphone').exists())

    def test_register_device_missing_device_id_returns_400(self):
        """POST to register_device with missing deviceId returns 400."""
        self.client.login(username='testuser', password='Tester123.')
        payload = {'label': 'Camera', 'deviceType': 'camera'}
        response = self.client.post(
            reverse('register_device'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_register_device_invalid_device_type_returns_400(self):
        """POST to register_device with invalid deviceType returns 400."""
        self.client.login(username='testuser', password='Tester123.')
        payload = {'deviceId': 'xyz', 'label': 'Something', 'deviceType': 'videoinput'}
        response = self.client.post(
            reverse('register_device'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_register_device_invalid_json_returns_400(self):
        """POST to register_device with invalid JSON body returns 400."""
        self.client.login(username='testuser', password='Tester123.')
        response = self.client.post(
            reverse('register_device'),
            data='not-valid-json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)