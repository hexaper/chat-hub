# AGENTS.md Context Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the root-heavy agent guidance with a concise root router and major-module `AGENTS.md` files that reduce token usage and speed up navigation.

**Architecture:** Keep the root `AGENTS.md` limited to repo-wide commands, constraints, and a module map, then add one concise `AGENTS.md` to each major project boundary. Each local file should only describe scope, key entrypoints, invariants, and verification for that directory so agents can stop reading after the nearest relevant file.

**Tech Stack:** Markdown documentation, Django 5.2, Channels, Redis, server-rendered templates, vanilla JavaScript.

---

## File Structure

- Modify: `AGENTS.md` (repo-wide router only)
- Create: `config/AGENTS.md` (settings and entrypoint guidance)
- Create: `apps/accounts/AGENTS.md` (auth app guidance)
- Create: `apps/rooms/AGENTS.md` (chat/realtime domain guidance)
- Create: `apps/devices/AGENTS.md` (device app guidance)
- Create: `templates/AGENTS.md` (server-rendered UI guidance)
- Create: `static/AGENTS.md` (shared browser asset guidance)
- Create: `utils/AGENTS.md` (cross-cutting helper guidance)
- Create: `docs/AGENTS.md` (documentation routing guidance)
- Create: `allinone/AGENTS.md` (bundled local deployment guidance)

### Task 1: Rewrite Root Router and Add Core Runtime Module Files

**Files:**
- Modify: `AGENTS.md`
- Create: `config/AGENTS.md`
- Create: `apps/accounts/AGENTS.md`
- Create: `apps/rooms/AGENTS.md`
- Create: `apps/devices/AGENTS.md`

- [ ] **Step 1: Replace the root `AGENTS.md` with a thin router**

```md
# AGENTS.md

Use this file for repo-wide rules only. When working inside a subdirectory, load the closest `AGENTS.md` first.

## Repo Snapshot

- Stack: Django 5.2, Channels, Daphne, Redis, PostgreSQL/SQLite, server-rendered templates, vanilla JS.
- HTTP entrypoint: `config/urls.py`.
- ASGI entrypoint: `config/asgi.py`.
- WebSocket routes: `apps/rooms/routing.py`.
- WebRTC signaling lives in `static/js/webrtc.js`; server and room chat client logic stays inline in `templates/rooms/*.html`.

## Fast Commands

```bash
source venv/bin/activate
python manage.py runserver --settings=config.settings.development
DJANGO_SETTINGS_MODULE=config.settings.development daphne -b 0.0.0.0 -p 8000 config.asgi:application
python manage.py test --settings=config.settings.development --keepdb
```

## Global Rules

- Use Django's test runner, not pytest.
- Do not use `--parallel` for tests in this repo.
- Redis is required for WebSockets, rate limits, and `/healthz/`.
- Use `database_sync_to_async` for ORM work in async consumers.
- Preserve websocket sender self-exclusion and chat soft-delete/edit-window behavior unless the task explicitly changes them.
- Keep dependencies lean and do not add a frontend build step.
- Trust code and settings over prose if they disagree.

## Module Map

- `config/AGENTS.md`: settings, URLs, ASGI/WSGI, deployment entrypoints.
- `apps/accounts/AGENTS.md`: auth models, forms, views, tests.
- `apps/rooms/AGENTS.md`: servers, rooms, chat models/views/consumers/tests.
- `apps/devices/AGENTS.md`: device registration app.
- `templates/AGENTS.md`: server-rendered UI and inline page scripts.
- `static/AGENTS.md`: shared browser assets, especially `js/webrtc.js`.
- `utils/AGENTS.md`: shared helpers.
- `docs/AGENTS.md`: roadmap, codebase docs, specs, plans.
- `allinone/AGENTS.md`: bundled local self-host deployment path.
```

- [ ] **Step 2: Create `config/AGENTS.md` with local runtime rules**

```md
# AGENTS.md

Scope: `config/` owns settings, URL wiring, and ASGI/WSGI entrypoints.

## Entry Points

- `settings/base.py`: shared defaults.
- `settings/development.py`: local development settings.
- `settings/production.py`: production defaults.
- `settings/allinone.py`: bundled self-host settings.
- `urls.py`: top-level HTTP routes.
- `asgi.py`: Channels/Daphne entrypoint.
- `wsgi.py`: WSGI entrypoint.

## Rules

- `manage.py` defaults to `config.settings.development`.
- `config/asgi.py` defaults to `config.settings.production`; set `DJANGO_SETTINGS_MODULE=config.settings.development` for local Daphne runs.
- Keep static handling compatible with WhiteNoise manifest storage; do not add `ASGIStaticFilesHandler`.
- Keep environment-driven settings and avoid hardcoding secrets.

## Verify

- Run `python manage.py check --settings=config.settings.development` for settings or URL changes.
- For websocket or ASGI changes, also run Daphne locally with `DJANGO_SETTINGS_MODULE=config.settings.development`.
- Update `CLAUDE.md` or `docs/codebase/*.md` when runtime behavior changes.
```

- [ ] **Step 3: Create `apps/accounts/AGENTS.md` and `apps/devices/AGENTS.md`**

```md
# AGENTS.md

Scope: `apps/accounts/` owns the custom user model, auth forms, account views, URLs, and account-side tests.

## Key Files

- `models.py`: custom user model.
- `forms.py`: registration and account forms.
- `views.py`: auth and settings views.
- `urls.py`: account routes.
- `tests/test_forms.py`, `tests/test_views.py`, `tests/test_ratelimit.py`: focused regression coverage.

## Rules

- Keep identity and auth behavior inside this app instead of leaking it into `apps/rooms` or `utils`.
- Follow existing Django form/view patterns; do not add API-style abstractions unless the task requires them.
- Reuse shared helpers from `utils/` only for truly cross-cutting behavior.

## Verify

- Run `python manage.py test apps.accounts.tests --settings=config.settings.development` after changing forms, views, or auth flows.
- Update `templates/accounts/*.html` only when the view change requires it.
```

```md
# AGENTS.md

Scope: `apps/devices/` owns device registration persistence, endpoints, and app-local tests.

## Key Files

- `models.py`: device records.
- `views.py`: device registration behavior.
- `urls.py`: device routes.
- `tests/test_views.py`: focused regression coverage.

## Rules

- Keep this app narrowly focused on device registration and listing behavior.
- Avoid reintroducing old room-domain device logic here; current room chat behavior lives in `apps/rooms/`.
- Prefer simple Django views and models over new abstraction layers.

## Verify

- Run `python manage.py test apps.devices.tests --settings=config.settings.development` after changing this app.
- Update docs if API shape or operational setup changes.
```

- [ ] **Step 4: Create `apps/rooms/AGENTS.md` for the high-risk chat domain**

```md
# AGENTS.md

Scope: `apps/rooms/` owns servers, rooms, chat, moderation, realtime consumers, routing, forms, permissions, management commands, and the largest test surface in the repo.

## Key Files

- `models.py`: memberships, chat, moderation, mentions, read state.
- `views.py`: room/server pages and JSON endpoints.
- `consumers.py`: realtime room/server consumers.
- `routing.py`: websocket routes.
- `permissions.py`: access-control helpers.
- `tests/test_consumers.py`, `tests/test_views_extended.py`, `tests/test_permissions.py`, `tests/test_ratelimit.py`: focused regression coverage.

## Rules

- Use `database_sync_to_async` for ORM work in async consumers and `sync_to_async` only for non-ORM helpers.
- Preserve sender self-exclusion in websocket broadcasts.
- Preserve soft-delete and 15-minute edit-window behavior unless the task explicitly changes the contract.
- Presence is currently process-local and resets on restart; do not treat it as multi-instance safe unless the task redesigns it.
- Treat `consumers.py` and `views.py` as high-churn files and keep changes as small as possible.

## Verify

- Run focused room tests first, then broaden only if needed.
- For consumer changes, use Daphne locally and keep Redis running.
- Do not use `--parallel`; consumer tests rely on sequential Django execution.
```

- [ ] **Step 5: Verify file layout and commit Task 1**

Run: `git diff --check`
Expected: no output.

Run: `python manage.py check --settings=config.settings.development`
Expected: `System check identified no issues`.

```bash
git add AGENTS.md config/AGENTS.md apps/accounts/AGENTS.md apps/rooms/AGENTS.md apps/devices/AGENTS.md
git commit -m "docs: route agent guidance by module"
```

### Task 2: Add UI, Asset, Utility, and Documentation Module Files

**Files:**
- Create: `templates/AGENTS.md`
- Create: `static/AGENTS.md`
- Create: `utils/AGENTS.md`
- Create: `docs/AGENTS.md`

- [ ] **Step 1: Create `templates/AGENTS.md` for server-rendered UI work**

```md
# AGENTS.md

Scope: `templates/` owns server-rendered HTML for landing, accounts, devices, rooms, and inline page scripts that are specific to those pages.

## Key Files

- `base.html`: shared shell.
- `landing.html`: marketing/entry page.
- `accounts/*.html`: auth and profile templates.
- `devices/*.html`: device list UI.
- `rooms/server_detail.html` and `rooms/room_detail.html`: inline chat client behavior.

## Rules

- Preserve the server-rendered approach; do not introduce a frontend build pipeline.
- Keep page-specific chat behavior inline in the room templates unless the architecture is intentionally changing.
- Remember that `static/js/webrtc.js` only covers room WebRTC signaling, not general chat UI state.
- Match the existing template structure and naming instead of creating a new UI organization scheme.

## Verify

- Manually load affected pages in the browser.
- Run the focused Django tests for the views that render the changed templates.
- If the change affects chat or video flows, verify it under Daphne instead of `runserver`.
```

- [ ] **Step 2: Create `static/AGENTS.md` and `utils/AGENTS.md`**

```md
# AGENTS.md

Scope: `static/` owns shared browser assets served directly by Django/WhiteNoise.

## Key Files

- `js/webrtc.js`: room WebRTC signaling and peer-connection behavior.

## Rules

- Keep `webrtc.js` focused on room media signaling.
- Do not move server chat or room chat template logic into shared static JS unless the task explicitly restructures the frontend.
- Keep assets compatible with the current staticfiles and WhiteNoise setup.

## Verify

- Manually test the browser flow that uses the changed asset.
- For WebRTC work, verify over Daphne and HTTPS when the browser requires secure context behavior.
```

```md
# AGENTS.md

Scope: `utils/` owns cross-cutting helpers shared across apps.

## Key Files

- `ratelimit.py`: shared rate-limit helpers.
- `turn.py`: ICE/TURN helper logic.
- `tests.py`: utility-level tests.

## Rules

- Keep helpers generic and reusable; app-specific rules belong in the owning app.
- Avoid pulling room-domain or account-domain state into shared helpers unless more than one app truly needs it.
- Keep dependencies minimal and prefer straightforward functions over frameworks or service layers.

## Verify

- Run `python manage.py test utils --settings=config.settings.development` if utility tests exist for the changed behavior.
- Otherwise run the focused app tests that exercise the helper path.
```

- [ ] **Step 3: Create `docs/AGENTS.md` for doc routing and update policy**

```md
# AGENTS.md

Scope: `docs/` owns roadmap material, generated codebase docs, and superpowers design/plan artifacts.

## Key Files

- `ROADMAP.md`: future direction only.
- `codebase/STACK.md`, `STRUCTURE.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `INTEGRATIONS.md`, `TESTING.md`, `CONCERNS.md`: current repository map.
- `superpowers/specs/`: approved design docs.
- `superpowers/plans/`: implementation plans.

## Rules

- Update docs in the same task when code behavior, commands, architecture, or constraints change.
- Keep `ROADMAP.md` limited to future intent; do not describe current behavior there.
- Prefer linking to canonical docs over duplicating the same explanation in multiple files.

## Verify

- Re-read the edited docs and confirm commands, paths, and behavior still match the codebase.
- If code changed, update the relevant `docs/codebase/*.md` file alongside the implementation.
```

- [ ] **Step 4: Verify file layout and commit Task 2**

Run: `git diff --check`
Expected: no output.

Run: `python manage.py check --settings=config.settings.development`
Expected: `System check identified no issues`.

```bash
git add templates/AGENTS.md static/AGENTS.md utils/AGENTS.md docs/AGENTS.md
git commit -m "docs: add scoped agent routing files"
```

### Task 3: Add Deployment Routing and Final Cross-File Consistency Pass

**Files:**
- Create: `allinone/AGENTS.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Create `allinone/AGENTS.md` for bundled local deployment**

```md
# AGENTS.md

Scope: `allinone/` owns the bundled local self-host deployment path with its own container wiring and entrypoint.

## Key Files

- `docker-compose.yml`: bundled Postgres, Redis, and app runtime.
- `Dockerfile`: container image definition.
- `entrypoint.sh`: container startup flow.

## Rules

- Preserve the all-in-one role as the bundled local deployment path, separate from the top-level production-oriented `docker-compose.yml`.
- Keep HTTPS and self-signed certificate behavior intact unless the task explicitly changes local TLS setup.
- Avoid assuming this path exercises the same runtime as `python manage.py runserver`; websocket verification still needs Daphne-aware behavior.

## Verify

- Review compose, Dockerfile, and entrypoint changes together because they are tightly coupled.
- Run the smallest relevant Docker or compose validation command for the changed files.
```

- [ ] **Step 2: Add the final module-map cross-check to root `AGENTS.md`**

```md
## Module Map

- `config/AGENTS.md`: settings, URLs, ASGI/WSGI, deployment entrypoints.
- `apps/accounts/AGENTS.md`: auth models, forms, views, tests.
- `apps/rooms/AGENTS.md`: servers, rooms, chat models/views/consumers/tests.
- `apps/devices/AGENTS.md`: device registration app.
- `templates/AGENTS.md`: server-rendered UI and inline page scripts.
- `static/AGENTS.md`: shared browser assets, especially `js/webrtc.js`.
- `utils/AGENTS.md`: shared helpers.
- `docs/AGENTS.md`: roadmap, codebase docs, specs, plans.
- `allinone/AGENTS.md`: bundled local self-host deployment path.
```

- [ ] **Step 3: Run final verification commands**

Run: `git diff --check`
Expected: no output.

Run: `python manage.py check --settings=config.settings.development`
Expected: `System check identified no issues`.

Run: `git status --short`
Expected: only the intended `AGENTS.md` documentation files are listed.

- [ ] **Step 4: Commit Task 3**

```bash
git add allinone/AGENTS.md AGENTS.md
git commit -m "docs: finish agent context routing map"
```

## Self-Review

- Spec coverage: the tasks rewrite the root file, add every planned module file, preserve major-modules-only scope, and include verification for each group.
- Placeholder scan: no `TODO`, `TBD`, or implied content remains; each file has concrete text.
- Consistency: the same module paths and local rules are used across all tasks and match the approved design.
