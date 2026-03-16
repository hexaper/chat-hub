"""
Integration tests for rate limiting on accounts views.

Verifies that:
  - /accounts/login/ enforces a 5/m limit per client IP
  - /accounts/register/ enforces a 5/m limit per client IP
  - Different IPs are tracked independently (one IP being limited does not
    affect another IP)

Redis (DB 1) must be running. cache.clear() is called in setUp.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

_LOGIN_URL = '/accounts/login/'
_REGISTER_URL = '/accounts/register/'


class LoginRateLimitTest(TestCase):
    """Rate limiting on the login view: 5 requests/minute per IP."""

    @classmethod
    def setUpTestData(cls):
        cls.existing_user = User.objects.create_user(
            username='rl_login_user',
            password='Tester123.',
        )

    def setUp(self):
        cache.clear()

    def _post_login(self, ip, username='wrong', password='wrong'):
        return self.client.post(
            _LOGIN_URL,
            data={'username': username, 'password': password},
            REMOTE_ADDR=ip,
        )

    def test_five_requests_within_limit_are_not_rejected(self):
        """Five consecutive POST requests to login (even with bad creds) must not return 429."""
        for i in range(5):
            response = self._post_login('10.0.0.10')
            self.assertNotEqual(
                response.status_code, 429,
                msg=f"Request #{i + 1}/5 to login should not be rate-limited (got 429)",
            )

    def test_sixth_request_returns_429(self):
        """The 6th POST to login from the same IP within a minute must return 429."""
        for _ in range(5):
            self._post_login('10.0.0.11')
        response = self._post_login('10.0.0.11')
        self.assertEqual(
            response.status_code, 429,
            msg="6th login request from the same IP should be rate-limited (expected 429)",
        )

    def test_different_ips_are_tracked_separately(self):
        """Exhausting the limit for IP A must not affect IP B."""
        for _ in range(5):
            self._post_login('10.0.1.1')
        self._post_login('10.0.1.1')  # now limited

        response = self._post_login('10.0.1.2')
        self.assertNotEqual(
            response.status_code, 429,
            msg="IP 10.0.1.2 should not be rate-limited when only 10.0.1.1 is exhausted",
        )

    def test_get_request_is_not_rate_limited(self):
        """GET requests also go through the decorator; 5 GETs should not trigger 429."""
        for i in range(5):
            response = self.client.get(_LOGIN_URL, REMOTE_ADDR='10.0.2.1')
            self.assertNotEqual(
                response.status_code, 429,
                msg=f"GET request #{i + 1} to login page should not be rate-limited",
            )

    def test_successful_login_counted_toward_limit(self):
        """Even successful logins count toward the per-IP rate limit."""
        for _ in range(5):
            self._post_login(
                '10.0.3.1',
                username=self.existing_user.username,
                password='Tester123.',
            )
        response = self._post_login('10.0.3.1')
        self.assertEqual(
            response.status_code, 429,
            msg="Successful logins should still count toward the IP rate limit",
        )


class RegisterRateLimitTest(TestCase):
    """Rate limiting on the register view: 5 requests/minute per IP."""

    def setUp(self):
        cache.clear()

    def _post_register(self, ip, **overrides):
        data = {
            'username': 'newuser',
            'password1': 'StrongPass99!',
            'password2': 'StrongPass99!',
        }
        data.update(overrides)
        return self.client.post(_REGISTER_URL, data=data, REMOTE_ADDR=ip)

    def test_five_requests_within_limit_are_not_rejected(self):
        """Five POST requests to register (with varying usernames) must not return 429."""
        for i in range(5):
            response = self._post_register('10.1.0.10', username=f'user_reg_{i}')
            self.assertNotEqual(
                response.status_code, 429,
                msg=f"Request #{i + 1}/5 to register should not be rate-limited (got 429)",
            )

    def test_sixth_request_returns_429(self):
        """The 6th POST to register from the same IP within a minute must return 429."""
        for i in range(5):
            self._post_register('10.1.0.11', username=f'reg_user_{i}')
        response = self._post_register('10.1.0.11', username='reg_user_over')
        self.assertEqual(
            response.status_code, 429,
            msg="6th register request from the same IP should be rate-limited (expected 429)",
        )

    def test_different_ips_are_tracked_separately(self):
        """Exhausting the limit for IP A must not affect IP B."""
        for i in range(5):
            self._post_register('10.1.1.1', username=f'sep_user_{i}')
        self._post_register('10.1.1.1', username='sep_user_over')  # now limited

        response = self._post_register('10.1.1.2', username='sep_user_b')
        self.assertNotEqual(
            response.status_code, 429,
            msg="IP 10.1.1.2 should not be rate-limited when only 10.1.1.1 is exhausted",
        )
