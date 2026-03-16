from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


_WINDOWS = {'m': 60, 'h': 3600, 'd': 86400}

_RATE_LIMIT_MSG = 'Too many requests — please wait a moment before trying again.'


def _parse_rate(rate):
    """Parse '5/m' -> (5, 60)."""
    count, period = rate.split('/')
    return int(count), _WINDOWS[period]


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _check(cache_key, limit, window):
    """Atomically increment counter. Returns True if limit is exceeded."""
    cache.add(cache_key, 0, window)  # set to 0 with TTL only if key absent
    count = cache.incr(cache_key)
    return count > limit


def ratelimit(key, rate):
    """
    Decorator for Django view functions.

    key:  'ip'   — limit per client IP address
          'user' — limit per authenticated user (falls back to IP if anonymous)
    rate: '<count>/<period>'  e.g. '5/m', '10/m', '30/m'

    HTML views: adds a Django message and redirects back (popup via messages framework).
    JSON/AJAX views: returns JSON {'error': 'rate_limited'} with status 429.
    """
    limit, window = _parse_rate(rate)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if key == 'ip':
                identifier = _get_client_ip(request)
            else:
                identifier = (
                    str(request.user.pk)
                    if request.user.is_authenticated
                    else _get_client_ip(request)
                )
            cache_key = f'rl:{view_func.__name__}:{identifier}'
            if _check(cache_key, limit, window):
                # Detect JSON/AJAX requests by Accept header or X-Requested-With
                is_ajax = (
                    request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    or 'application/json' in request.headers.get('Accept', '')
                )
                # Use messages + redirect for HTML views only when the messages
                # middleware is active (real requests). RequestFactory-based tests
                # don't have the middleware, so fall back to JSON 429 there.
                if not is_ajax and hasattr(request, '_messages'):
                    messages.warning(request, _RATE_LIMIT_MSG)
                    return HttpResponse(status=302, headers={'Location': request.path})
                return JsonResponse({'error': 'rate_limited'}, status=429)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def is_rate_limited(scope, identifier, rate):
    """
    Standalone rate-limit check for use outside view decorators (e.g. WebSocket consumers).

    scope:      string identifying the operation, e.g. 'chat'
    identifier: unique key for the subject, e.g. user.pk
    rate:       '<count>/<period>' e.g. '30/m'

    Returns True if the limit has been exceeded (caller should drop the action).
    """
    limit, window = _parse_rate(rate)
    cache_key = f'rl:{scope}:{identifier}'
    return _check(cache_key, limit, window)
