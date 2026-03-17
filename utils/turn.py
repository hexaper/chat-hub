import hashlib
import hmac
import time
from base64 import b64encode


def generate_turn_credentials(secret, identifier, ttl):
    """
    Generate short-lived TURN credentials using coturn's HMAC REST API mechanism.

    username = "<expiry_unix_timestamp>:<identifier>"
    password = base64(HMAC-SHA1(username, shared_secret))

    coturn validates: current_time < expiry AND HMAC matches.
    """
    expiry = int(time.time()) + ttl
    username = f'{expiry}:{identifier}'
    password = b64encode(
        hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    ).decode()
    return username, password
