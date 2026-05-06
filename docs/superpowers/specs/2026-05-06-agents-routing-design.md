# AGENTS.md Context Routing Design

**Goal:** Reduce token usage and repo exploration overhead by replacing the current root-heavy agent guidance with concise root routing plus module-local `AGENTS.md` files in the main project boundaries.

## Current State

- The repository has one root `AGENTS.md` that mixes global rules with module-specific behavior.
- Reliable module boundaries already exist in code and docs: `config/`, `apps/accounts/`, `apps/rooms/`, `apps/devices/`, `templates/`, `static/`, `utils/`, `docs/`, and `allinone/`.
- Agents currently need to read the root file, `CLAUDE.md`, and often multiple docs before they know where to work safely.

## Scope

This change will:

- Rewrite the root `AGENTS.md` into a concise repository entrypoint.
- Add one `AGENTS.md` file to each major module directory.
- Keep guidance focused on navigation, invariants, and verification commands.
- Prefer links to `CLAUDE.md` and `docs/codebase/*.md` over repeated prose.

This change will not:

- Add deeper `AGENTS.md` files inside subdirectories such as `templates/rooms/` or `apps/rooms/tests/`.
- Change runtime code, tests, deployment behavior, or product features.
- Duplicate large sections of existing documentation.

## Design

### Root `AGENTS.md`

The root file becomes a thin router with only repository-wide rules:

- Stack summary and core entrypoints.
- Fast run/test command index.
- Hard safety constraints that apply everywhere.
- A module map listing each module-level `AGENTS.md` path.
- A short reminder that the closest `AGENTS.md` wins.

The root file should stay concise enough to be read on nearly every task without carrying module-specific detail.

### Module `AGENTS.md` Files

Each module file should answer four questions quickly:

1. What part of the repo does this directory own?
2. Which files are the main entrypoints here?
3. What local rules or invariants must be preserved?
4. How should changes in this area be verified?

Each module file should stay within roughly 120-220 words and avoid repeating global rules already covered at the root.

## Planned Module Files

### `config/AGENTS.md`

- Scope: settings, URL routing, ASGI/WSGI entrypoints.
- Key files: `settings/base.py`, `settings/development.py`, `settings/production.py`, `asgi.py`, `urls.py`.
- Local constraints: local Daphne runs must set `DJANGO_SETTINGS_MODULE=config.settings.development`; avoid introducing static handling that conflicts with WhiteNoise.
- Verification: run focused Django commands relevant to config changes.

### `apps/accounts/AGENTS.md`

- Scope: auth models, forms, views, URLs, and account tests.
- Key files: `models.py`, `forms.py`, `views.py`, `urls.py`, `tests/`.
- Local constraints: keep auth concerns inside this app; preserve existing Django form/view patterns.
- Verification: focused account tests.

### `apps/rooms/AGENTS.md`

- Scope: server/room/chat domain models, views, consumers, routing, management commands, and tests.
- Key files: `models.py`, `views.py`, `consumers.py`, `routing.py`, `permissions.py`, `tests/test_consumers.py`.
- Local constraints: use `database_sync_to_async` for ORM in consumers, preserve soft-delete and edit-window semantics, keep sender self-exclusion behavior, treat presence as process-local unless explicitly redesigned.
- Verification: focused room and consumer tests; manual Daphne checks for websocket behavior when relevant.

### `apps/devices/AGENTS.md`

- Scope: device model, device registration endpoints, and tests.
- Key files: `models.py`, `views.py`, `urls.py`, `tests/test_views.py`.
- Local constraints: keep this app narrowly focused on device registration behavior.
- Verification: focused device tests.

### `templates/AGENTS.md`

- Scope: server-rendered HTML templates and inline browser behavior embedded in templates.
- Key files: `base.html`, `landing.html`, `templates/rooms/*.html`, `templates/accounts/*.html`, `templates/devices/*.html`.
- Local constraints: preserve server-rendered approach; remember that server and room chat client logic lives inline in room templates while WebRTC-specific logic does not.
- Verification: manual UI checks and any focused Django tests covering affected views.

### `static/AGENTS.md`

- Scope: static browser assets.
- Key files: `js/webrtc.js` and any future shared assets under `static/`.
- Local constraints: keep `webrtc.js` limited to room WebRTC/signaling responsibilities and avoid moving server/room chat template logic into it unless the architecture intentionally changes.
- Verification: manual browser checks, especially WebRTC/signaling paths.

### `utils/AGENTS.md`

- Scope: cross-cutting helpers reused across apps.
- Key files: `ratelimit.py`, `turn.py`, `tests.py`.
- Local constraints: keep helpers generic and avoid leaking room-specific or account-specific domain rules into shared utilities.
- Verification: focused tests touching the helper behavior or dependent app tests when no dedicated helper test exists.

### `docs/AGENTS.md`

- Scope: roadmap, codebase docs, and superpowers specs/plans.
- Key files: `ROADMAP.md`, `codebase/*.md`, `superpowers/specs/`, `superpowers/plans/`.
- Local constraints: update docs in the same task when code behavior, architecture, commands, or constraints change; keep roadmap limited to future intent.
- Verification: ensure referenced files and commands still match the codebase.

### `allinone/AGENTS.md`

- Scope: bundled local self-host deployment path.
- Key files: `docker-compose.yml`, `Dockerfile`, `entrypoint.sh`.
- Local constraints: preserve the all-in-one responsibility of bundled Postgres, Redis, and self-signed HTTPS; avoid conflating it with the top-level production compose path.
- Verification: validate compose and entrypoint changes with the smallest relevant container command or config review.

## Content Rules

- Prefer commands, invariants, and links over explanation.
- Do not copy the same stack summary into every module file.
- Do not restate broad repo safety rules in module files unless a local restatement prevents mistakes.
- Keep examples concrete and path-specific.
- Reference `CLAUDE.md` and `docs/codebase/*.md` instead of duplicating architecture prose.

## Expected Benefits

- Lower token cost on routine tasks because most work can stop at root plus one local file.
- Faster navigation to the correct directory and entrypoints.
- Fewer redundant tool calls to rediscover local constraints.
- Better separation between global rules and local implementation caveats.

## Risks And Mitigations

- Risk: module files drift from code reality.
  - Mitigation: keep them short, path-based, and tied to existing docs and commands.
- Risk: root file becomes too sparse and loses critical global constraints.
  - Mitigation: keep universally applicable run/test/safety rules at the root.
- Risk: module boundaries become too granular later.
  - Mitigation: start with major modules only and add deeper files only when repeated misses justify them.

## Acceptance Criteria

- Root `AGENTS.md` is concise and routes to every module-level file.
- Each listed major module has an `AGENTS.md`.
- No module file duplicates large sections of root guidance.
- Commands and invariants match current repo behavior.
- The new layout makes local navigation possible with fewer file reads than today.
