# AGENTS.md

Scope: `static/` owns shared browser assets served by Django staticfiles/WhiteNoise.

## Key Files

- `js/webrtc.js`: room WebRTC signaling and peer-connection behavior.
- `css/main.css`: shared styling.
- `img/server-default.svg`: default server artwork.

## Rules

- Keep `js/webrtc.js` focused on room media/signaling behavior.
- Do not move template-owned chat or room state logic into shared static JS unless the task explicitly restructures the frontend.
- Keep assets compatible with the current Django staticfiles + WhiteNoise manifest setup.
- Preserve secure-context assumptions for browser APIs used by WebRTC flows.

## Verify

- Manually test the browser flow that uses the changed asset.
- For WebRTC changes, verify with `DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application`.
- Use HTTPS/secure-context testing when the browser feature requires it.
