# Coding Conventions

## Core Sections (Required)

### 1) Naming Rules

| Item | Rule | Example | Evidence |
|------|------|---------|----------|
| Files | Python modules use snake_case names | apps/rooms/views.py, utils/ratelimit.py | apps/rooms/views.py |
| Functions/methods | Functions and methods use snake_case | `server_detail`, `generate_turn_credentials`, `check_room_password` | apps/rooms/views.py, utils/turn.py, apps/rooms/models.py |
| Types/interfaces | Django models, forms, and consumers use PascalCase class names | `Server`, `RegisterForm`, `RoomChatConsumer` | apps/rooms/models.py, apps/accounts/forms.py, apps/rooms/consumers.py |
| Constants/env vars | Module constants and environment variable names use UPPER_SNAKE_CASE | `EDIT_WINDOW_SECONDS`, `TURN_TTL`, `AWS_ACCESS_KEY_ID` | apps/rooms/consumers.py, config/settings/production.py |

### 2) Formatting and Linting

- Formatter: [TODO] No dedicated formatter config file was found in inspected repository files.
- Linter: [TODO] No dedicated linter config file was found in inspected repository files.
- Most relevant enforced rules: import grouping is manually consistent, Django view decorators are stacked directly above view functions, and settings files use uppercase names for configuration constants.
- Run commands: [TODO] No repository lint or format command was documented in inspected files.

### 3) Import and Module Conventions

- Import grouping/order: standard-library imports appear before third-party and local imports in representative modules such as apps/rooms/views.py and apps/rooms/consumers.py.
- Alias vs relative import policy: absolute imports from apps.* and utils.* are preferred; same-package relative imports are used sparingly for forms or models.
- Public exports/barrel policy: [TODO] No barrel-export or explicit public API module pattern was found in inspected Python packages.

### 4) Error and Logging Conventions

- Error strategy by layer: HTTP views commonly return redirects plus Django messages for UI flows, or JsonResponse with explicit status codes for AJAX/API-style flows; consumers usually drop malformed or unauthorized websocket messages without raising outward-facing errors.
- Logging style and required context fields: production.py configures console logging at WARNING/ERROR levels for root and Django loggers.
- Sensitive-data redaction rules: [TODO] No explicit redaction policy or structured logging schema was found in inspected files.

### 5) Testing Conventions

- Test file naming/location rule: app tests live under each app's tests/ package and usually use test_*.py names; utils/tests.py is a standalone module-level exception.
- Mocking strategy norm: tests favor Django test client, RequestFactory, and Channels WebsocketCommunicator over heavy mocking.
- Coverage expectation: [TODO] No coverage threshold or coverage-report command was found in inspected files.

### 6) Evidence

- apps/rooms/views.py
- apps/rooms/consumers.py
- apps/rooms/models.py
- apps/accounts/forms.py
- config/settings/production.py
- apps/rooms/tests/test_consumers.py
- utils/tests.py
