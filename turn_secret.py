
#!/usr/bin/env python3
import hmac
import hashlib
import time
import base64

# Configuration
TURN_SECRET = "discordclone"  # Shared secret from TURN server
TTL = 86400                        # Time-to-live in seconds (24 hours)

# Generate TURN credentials
def generate_turn_credentials(username):
    # Current timestamp
    timestamp = int(time.time()) + TTL

    # Combine timestamp with username
    turn_username = f"{timestamp}:{username}"

    # Generate password using HMAC-SHA1 and encode in Base64
    hmac_obj = hmac.new(
        TURN_SECRET.encode('utf-8'),
        turn_username.encode('utf-8'),
        hashlib.sha1
    )
    password = base64.b64encode(hmac_obj.digest()).decode('utf-8')

    return turn_username, password

# Generate and display credentials
user = "username"
turn_username, turn_password = generate_turn_credentials(user)

# Formatted output using triple-quoted string
print(f"""TURN Credentials
----------------------------------------
Username: {turn_username}
Password: {turn_password}
TTL     : {TTL} seconds
----------------------------------------

Example WebRTC ICE Configuration
{{
  "iceServers": [
    {{
      "urls": ["turn:relay1.expressturn.com:3480"],
      "username": "{turn_username}",
      "credential": "{turn_password}"
    }}
  ]
}}
""")
            