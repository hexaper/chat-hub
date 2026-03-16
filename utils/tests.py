"""
Unit tests for utils/ratelimit.py.

Tests observable behavior of the rate-limiting primitives:
  - _parse_rate: correct parsing of rate strings
  - is_rate_limited: counter increments, limit enforcement, isolation by scope/identifier
  - ratelimit decorator: 429 on excess, pass-through below limit, IP vs user key resolution

Redis (DB 1) must be running. cache.clear() is called in setUp so tests don't
bleed counter state into each other.
"""
import uuid

from django.core.cache import cache
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from utils.ratelimit import _parse_rate, is_rate_limited, ratelimit

User = get_user_model()


def _unique_scope():
    """Return a fresh scope string so each test uses an isolated cache key."""
    return f'test_{uuid.uuid4().hex}'


class ParseRateTest(TestCase):
    """_parse_rate correctly splits rate strings into (count, window_seconds)."""

    def test_parse_per_minute(self):
        count, window = _parse_rate('5/m')
        self.assertEqual(count, 5, msg="_parse_rate('5/m') should return count=5")
        self.assertEqual(window, 60, msg="_parse_rate('5/m') should return window=60")

    def test_parse_per_hour(self):
        count, window = _parse_rate('10/h')
        self.assertEqual(count, 10, msg="_parse_rate('10/h') should return count=10")
        self.assertEqual(window, 3600, msg="_parse_rate('10/h') should return window=3600")

    def test_parse_per_day(self):
        count, window = _parse_rate('100/d')
        self.assertEqual(count, 100, msg="_parse_rate('100/d') should return count=100")
        self.assertEqual(window, 86400, msg="_parse_rate('100/d') should return window=86400")

    def test_parse_large_count(self):
        count, window = _parse_rate('30/m')
        self.assertEqual(count, 30)
        self.assertEqual(window, 60)


class IsRateLimitedTest(TestCase):
    """
    is_rate_limited returns False for the first N calls and True on N+1.
    Each test uses a unique scope so cache keys never collide across tests.
    """

    def setUp(self):
        cache.clear()

    def test_first_call_not_limited(self):
        scope = _unique_scope()
        result = is_rate_limited(scope, 'user1', '3/m')
        self.assertFalse(result, msg="First call should not be rate-limited")

    def test_calls_within_limit_not_limited(self):
        scope = _unique_scope()
        for i in range(3):
            result = is_rate_limited(scope, 'user1', '3/m')
            self.assertFalse(
                result,
                msg=f"Call #{i + 1} of 3 should not be rate-limited",
            )

    def test_call_over_limit_is_limited(self):
        scope = _unique_scope()
        for _ in range(3):
            is_rate_limited(scope, 'user1', '3/m')
        result = is_rate_limited(scope, 'user1', '3/m')
        self.assertTrue(result, msg="4th call when limit is 3 should be rate-limited")

    def test_different_identifiers_tracked_separately(self):
        scope = _unique_scope()
        # Exhaust limit for user1
        for _ in range(3):
            is_rate_limited(scope, 'user1', '3/m')
        is_rate_limited(scope, 'user1', '3/m')  # over limit

        # user2 should still have a clean counter for the same scope
        result = is_rate_limited(scope, 'user2', '3/m')
        self.assertFalse(
            result,
            msg="A different identifier should have its own counter, not be affected by user1 being limited",
        )

    def test_different_scopes_tracked_separately(self):
        scope1 = _unique_scope()
        scope2 = _unique_scope()
        # Exhaust scope1 for identifier
        for _ in range(3):
            is_rate_limited(scope1, 'shared_id', '3/m')
        is_rate_limited(scope1, 'shared_id', '3/m')  # over limit

        # Same identifier under a different scope should be unaffected
        result = is_rate_limited(scope2, 'shared_id', '3/m')
        self.assertFalse(
            result,
            msg="A different scope should maintain its own counter independently",
        )

    def test_limit_exactly_at_boundary(self):
        """The Nth call (equal to limit) is allowed; the (N+1)th is rejected."""
        scope = _unique_scope()
        limit = 5
        rate = f'{limit}/m'
        for i in range(limit):
            result = is_rate_limited(scope, 'u', rate)
            self.assertFalse(result, msg=f"Call {i + 1}/{limit} should be allowed")
        over = is_rate_limited(scope, 'u', rate)
        self.assertTrue(over, msg=f"Call {limit + 1} should be rejected (limit={limit})")

    def test_cache_clear_resets_counter(self):
        """After cache.clear(), the counter resets and calls are allowed again."""
        scope = _unique_scope()
        for _ in range(2):
            is_rate_limited(scope, 'user1', '2/m')
        exceeded = is_rate_limited(scope, 'user1', '2/m')
        self.assertTrue(exceeded, msg="Should be limited before cache clear")

        cache.clear()

        result = is_rate_limited(scope, 'user1', '2/m')
        self.assertFalse(result, msg="After cache.clear(), counter should reset and first call should pass")


class RatelimitDecoratorTest(TestCase):
    """
    The @ratelimit view decorator returns HTTP 200 for calls within the limit
    and HTTP 429 once the limit is exceeded.
    """

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f'rl_user_{uuid.uuid4().hex[:8]}',
            password='pass',
        )

    def _make_ip_view(self, rate):
        @ratelimit(key='ip', rate=rate)
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')
        return view

    def _make_user_view(self, rate):
        @ratelimit(key='user', rate=rate)
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')
        return view

    def test_requests_within_limit_pass_through(self):
        view = self._make_ip_view('3/m')
        for i in range(3):
            request = self.factory.post('/fake/', REMOTE_ADDR='10.0.0.1')
            response = view(request)
            self.assertEqual(
                response.status_code, 200,
                msg=f"Request #{i + 1} of 3 should pass through (expected 200, got {response.status_code})",
            )

    def test_request_over_limit_returns_429(self):
        view = self._make_ip_view('3/m')
        for _ in range(3):
            request = self.factory.post('/fake/', REMOTE_ADDR='10.0.0.2')
            view(request)
        request = self.factory.post('/fake/', REMOTE_ADDR='10.0.0.2')
        response = view(request)
        self.assertEqual(
            response.status_code, 429,
            msg="4th request when limit is 3 should return HTTP 429",
        )

    def test_ip_key_uses_remote_addr(self):
        """Two different REMOTE_ADDR values are tracked with independent counters."""
        view = self._make_ip_view('2/m')
        # Exhaust IP A
        for _ in range(2):
            view(self.factory.post('/fake/', REMOTE_ADDR='192.168.1.1'))
        response_a = view(self.factory.post('/fake/', REMOTE_ADDR='192.168.1.1'))
        self.assertEqual(
            response_a.status_code, 429,
            msg="IP 192.168.1.1 should be rate-limited after 2 calls",
        )

        # IP B should still be allowed
        response_b = view(self.factory.post('/fake/', REMOTE_ADDR='192.168.1.2'))
        self.assertEqual(
            response_b.status_code, 200,
            msg="IP 192.168.1.2 should not be affected by IP 192.168.1.1's counter",
        )

    def test_ip_key_uses_x_forwarded_for_when_present(self):
        """X-Forwarded-For header takes precedence over REMOTE_ADDR for IP extraction."""
        view = self._make_ip_view('2/m')
        for _ in range(2):
            request = self.factory.post(
                '/fake/',
                REMOTE_ADDR='10.0.0.99',
                HTTP_X_FORWARDED_FOR='203.0.113.5, 10.0.0.99',
            )
            view(request)
        # Third request: same X-Forwarded-For IP should be limited
        request = self.factory.post(
            '/fake/',
            REMOTE_ADDR='10.0.0.99',
            HTTP_X_FORWARDED_FOR='203.0.113.5, 10.0.0.99',
        )
        response = view(request)
        self.assertEqual(
            response.status_code, 429,
            msg="Rate limit should track the X-Forwarded-For IP, not REMOTE_ADDR",
        )

    def test_user_key_uses_user_pk_for_authenticated(self):
        """key='user' tracks by user.pk for authenticated users."""
        view = self._make_user_view('2/m')
        for _ in range(2):
            request = self.factory.post('/fake/', REMOTE_ADDR='1.2.3.4')
            request.user = self.user
            view(request)
        request = self.factory.post('/fake/', REMOTE_ADDR='1.2.3.4')
        request.user = self.user
        response = view(request)
        self.assertEqual(
            response.status_code, 429,
            msg="Authenticated user should be rate-limited by user.pk",
        )

    def test_user_key_falls_back_to_ip_for_anonymous(self):
        """key='user' falls back to REMOTE_ADDR for anonymous users."""
        view = self._make_user_view('2/m')
        anon = AnonymousUser()
        for _ in range(2):
            request = self.factory.post('/fake/', REMOTE_ADDR='5.6.7.8')
            request.user = anon
            view(request)
        request = self.factory.post('/fake/', REMOTE_ADDR='5.6.7.8')
        request.user = anon
        response = view(request)
        self.assertEqual(
            response.status_code, 429,
            msg="Anonymous user should be rate-limited by IP when key='user'",
        )

    def test_two_authenticated_users_tracked_independently(self):
        """Two distinct authenticated users do not share a rate-limit counter."""
        other = User.objects.create_user(
            username=f'rl_other_{uuid.uuid4().hex[:8]}',
            password='pass',
        )
        view = self._make_user_view('2/m')

        # Exhaust user1
        for _ in range(2):
            request = self.factory.post('/fake/')
            request.user = self.user
            view(request)
        response_user1 = view(self._req_for_user(self.user))
        self.assertEqual(response_user1.status_code, 429, msg="user1 should be rate-limited")

        # user2 should be unaffected
        response_user2 = view(self._req_for_user(other))
        self.assertEqual(
            response_user2.status_code, 200,
            msg="user2 should have its own counter and not be blocked by user1's limit",
        )

    def _req_for_user(self, user):
        request = self.factory.post('/fake/', REMOTE_ADDR='9.9.9.9')
        request.user = user
        return request
