# Strict Code Reviewer - Project Memory

## Project: Django WebRTC Video Conferencing

### Architecture
- Django 4.2 + Django Channels 4.x + Daphne (ASGI)
- Redis-backed channel layer (127.0.0.1:6379)
- Custom auth user model: `accounts.User`
- Room slugs are UUIDs (routing.py uses `[^/]+` regex, not `<uuid:...>`)
- Settings split: base / development / production (base has hardcoded SECRET_KEY)
- No application-level tests exist at all

### Key Files
- `static/js/webrtc.js` — monolithic WebRTC+WebSocket client (362 lines)
- `apps/rooms/consumers.py` — AsyncWebsocketConsumer
- `templates/rooms/room_detail.html` — room page
- `config/asgi.py` — uses AuthMiddlewareStack
- `apps/devices/views.py` — REST endpoint for device registration

### Confirmed Patterns & Anti-Patterns
- Race condition: `user_left` can arrive after a new `user_joined` for the same username (tab reopen), corrupting `userChannels` map
- XSS: `username` injected raw into innerHTML in `addParticipantToList()` (webrtc.js:338) and `addRemoteVideo()` (webrtc.js:318)
- XSS: `room.slug`, `request.user.username`, `p.user.username` output with `{{ }}` (not `escapejs`) inside `<script>` block in room_detail.html
- Memory leak: `AudioContext` objects in `vadAnalysers` are never closed when a peer disconnects in `removePeer()` — wait, stopVAD IS called in removePeer; the audio element MediaStream is a separate MediaStream not tracked in remoteStreams
- Memory leak: `<audio>` element created per peer in `ontrack` (webrtc.js:277) but the inner `audioStream = new MediaStream([track])` is a new stream not stored anywhere — it lives only via the audio element's srcObject
- Memory leak: `blackCanvas` / `blackVideoTrack` never stopped on page unload
- Memory leak: `localStream` tracks never stopped on page unload; no `beforeunload` handler
- Memory leak: `vadLoop()` runs forever via `requestAnimationFrame` even before any peers join
- No error handling on WebSocket `socket.onmessage` JSON.parse (will throw on malformed data)
- `disconnect()` in consumer does not guard against unauthenticated users (user may be AnonymousUser if connect() closed early)
- consumer `receive()` does no input validation — target channel accepted blindly from client (SSRF-style channel layer abuse)
- Room password stored in plaintext (`CharField max_length=255`) in Room model
- `WS_URL` hardcoded to `ws://` — breaks in production over HTTPS (should be `wss://`)
- `device_update` handler stores arbitrary client-supplied string into DB without length/format validation
- `enumerateDevices()` fires a POST per device with no rate limiting or deduplication guard at the HTTP level
- `getCookie` URL-decodes nothing — cookie values with `=` in them will be truncated
- No ICE restart logic on connection failure
- `createOffer` / `handleOffer` create a brand-new peer connection without checking for an existing one for that channel (duplicate peer risk on rejoin)
- `startBtn` is hidden (`d-none`) but still present in DOM — misleading
- `base.html` loads Bootstrap JS and CSS from CDN with no SRI hashes
- Production settings: `SECURE_HSTS_SECONDS`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS` not set
- `development.py`: `ALLOWED_HOSTS = ['*']` — acceptable for dev only

### Style Conventions
- JavaScript: camelCase functions and variables, module-level globals (no ES modules)
- Python: standard Django/PEP 8
- Templates: Bootstrap 5 utility classes throughout
