# Codebase Structure

## Core Sections (Required)

### 1) Top-Level Map

| Path | Purpose | Evidence |
|------|---------|----------|
| apps/ | Source applications grouped by feature area (`accounts`, `rooms`, `devices`) | apps/accounts/models.py, apps/rooms/models.py, apps/devices/models.py |
| config/ | Global Django settings, URL routing, ASGI/WSGI bootstrap | config/settings/base.py, config/urls.py, config/asgi.py |
| templates/ | Server-rendered HTML templates grouped by app/feature | templates/base.html, templates/rooms/server_detail.html, templates/accounts/login.html |
| static/ | Frontend assets served by Django/WhiteNoise | static/js/webrtc.js, static/css/main.css |
| utils/ | Cross-cutting helpers such as rate limiting and TURN credential generation | utils/ratelimit.py, utils/turn.py |
| docs/ | Product roadmap, specs, and generated codebase documentation | docs/ROADMAP.md, docs/superpowers/specs/2026-04-20-performance-scale-video-chat-design.md |
| allinone/ | Self-hosted single-container deployment assets | allinone/Dockerfile, allinone/docker-compose.yml, allinone/entrypoint.sh |
| Dockerfile / docker-compose.yml | Production-style container build and compose setup | Dockerfile, docker-compose.yml |
| deploy.sh | Local developer bootstrap script | deploy.sh |
| mediafiles/ | Runtime-uploaded media and persisted local assets | config/settings/base.py, allinone/entrypoint.sh |

### 2) Entry Points

- Main runtime entry: manage.py for management commands and local runserver; config/asgi.py for deployed HTTP/WebSocket serving.
- Secondary entry points (worker/cli/jobs): entrypoint.sh, allinone/entrypoint.sh, deploy.sh, and the cleanup management command path at apps/rooms/management/commands.
- How entry is selected (script/config): DJANGO_SETTINGS_MODULE defaults to config.settings.development in manage.py, config.settings.production in config/asgi.py, config.settings.production in entrypoint.sh, and config.settings.allinone in allinone/entrypoint.sh.

### 3) Module Boundaries

| Boundary | What belongs here | What must not be here |
|----------|-------------------|------------------------|
| apps/accounts | Custom user model, login/register/settings forms and views | Room/server business logic |
| apps/rooms | Core server, room, chat, and WebSocket behavior | Account model ownership unrelated to rooms |
| apps/devices | Persisted camera/microphone device metadata and related views | Chat or signaling logic |
| config | Global framework wiring and environment-specific settings | Feature-specific domain rules |
| utils | Reusable helpers shared across features | App-specific view rendering |
| templates + static | Presentation and browser-side behavior | ORM persistence rules |

### 4) Naming and Organization Rules

- File naming pattern: snake_case for Python modules such as apps/rooms/views.py and utils/ratelimit.py; test files follow test_*.py except the single-module utils/tests.py.
- Directory organization pattern: top level is split by responsibility, while application code under apps/ is primarily feature-based.
- Import aliasing or path conventions: imports are mostly absolute project imports such as `from apps.rooms.models import ...` and `from utils.ratelimit import ...`; no alias system was found in inspected Python files.

### 5) Evidence

- manage.py
- config/asgi.py
- config/urls.py
- apps/accounts/models.py
- apps/rooms/models.py
- apps/devices/models.py
- utils/ratelimit.py
- deploy.sh
- entrypoint.sh
- allinone/entrypoint.sh
