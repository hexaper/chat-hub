# AGENTS.md

Scope: `templates/` owns server-rendered HTML for landing, accounts, devices, rooms, and page-specific inline scripts.

## Key Files

- `base.html`: shared shell.
- `landing.html`: entry/marketing page.
- `accounts/*.html`: auth and profile templates.
- `devices/device_list.html`: device UI.
- `rooms/server_detail.html` and `rooms/room_detail.html`: inline chat client behavior.

## Rules

- Preserve the server-rendered approach; do not add a frontend build pipeline.
- Keep room/server chat UI behavior inline in the room templates unless the architecture is intentionally changing.
- Treat `static/js/webrtc.js` as WebRTC signaling/media support only, not the general chat client.
- Match existing template names and layout structure instead of inventing a new organization scheme.
- When injecting template values into JS, preserve the current escaping/CSRF patterns already used in this repo.

## Verify

- Manually load affected pages in the browser.
- Run the focused Django tests for views rendering the changed templates.
- If chat or video behavior changes, verify under `DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application`.
