# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Primary style: feature-oriented Django application with layered internals.
- Why this classification: code is grouped into feature apps under apps/, while each app then splits work across models, forms, views, and consumers.
- Primary constraints: real-time features run through Django Channels over Redis; browser media is peer-to-peer WebRTC rather than server-relayed media; deployment is designed around a small dependency set and container-friendly settings modules.

### 2) System Flow

```text
Browser HTTP request -> config/urls.py -> Django view in apps/*/views.py -> ORM/cache/helpers -> template or JSON response
Browser WebSocket -> config/asgi.py -> apps.rooms.routing -> apps.rooms.consumers -> Redis channel layer and ORM -> JSON WebSocket event
Room media session -> browser fetches ICE config -> RoomConsumer relays signaling -> peers establish direct WebRTC media paths
```

Evidence-backed flow summary:

1. HTTP traffic enters through Django URL configuration in config/urls.py and is routed into feature views under apps/accounts/views.py, apps/devices/views.py, or apps/rooms/views.py.
2. Standard page views render templates, while a few endpoints return JSON directly, such as healthz, ice_servers, and device/chat upload endpoints.
3. WebSocket traffic enters through config/asgi.py, which wraps the websocket router with AllowedHostsOriginValidator and AuthMiddlewareStack.
4. apps/rooms/routing.py maps the three websocket paths to ServerChatConsumer, RoomConsumer, and RoomChatConsumer.
5. Consumers combine Redis-backed group messaging with ORM reads/writes to persist chat state, room membership, and presence-related side effects.
6. Media transport does not traverse the Django server after signaling; static/js/webrtc.js uses ICE config and browser WebRTC APIs to negotiate peer connections directly.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| config | Startup wiring, settings inheritance, route registration | Domain-specific room/account behavior | config/asgi.py, config/urls.py, config/settings/base.py |
| apps.accounts | User schema, auth forms, auth/session views | Server/room chat state | apps/accounts/models.py, apps/accounts/forms.py, apps/accounts/views.py |
| apps.rooms.views | Server/room CRUD, membership checks, media upload, admin-panel HTML flows | WebSocket protocol handling | apps/rooms/views.py |
| apps.rooms.consumers | Signaling protocol, real-time chat protocol, presence handling, room participant state | HTML rendering | apps/rooms/consumers.py |
| apps.rooms.models | Persistent server/room/chat membership and content data | Network transport decisions | apps/rooms/models.py |
| utils | Cross-cutting helper logic reused by multiple entry points | Feature-specific UI behavior | utils/ratelimit.py, utils/turn.py |
| static/js/webrtc.js | Browser-side WebRTC/session behavior | Persistent database writes | static/js/webrtc.js |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Settings inheritance | config/settings/development.py, config/settings/production.py, config/settings/allinone.py | Share one base configuration while varying storage, database, and security by environment |
| Decorators for cross-cutting rules | utils/ratelimit.py, apps/rooms/views.py | Apply rate limiting and admin gating without duplicating checks in every view |
| Through models for memberships | apps/rooms/models.py | Persist extra data and uniqueness rules on server and room memberships |
| Channel group broadcast with self-exclusion marker | apps/rooms/consumers.py | Fan out websocket events while suppressing echoes to the sender when needed |
| In-process shared state guarded by asyncio.Lock | apps/rooms/consumers.py | Track chat presence per server without database writes |

### 5) Known Architectural Risks

- Presence is stored in a module-level Python dictionary, so online state is local to a single process and will diverge across multiple Daphne instances.
- apps/rooms/consumers.py and apps/rooms/views.py each combine several responsibilities in large files, which raises change risk and makes isolated refactoring harder.

### 6) Evidence

- config/asgi.py
- config/urls.py
- apps/rooms/routing.py
- apps/rooms/consumers.py
- apps/rooms/views.py
- apps/rooms/models.py
- apps/accounts/views.py
- static/js/webrtc.js
- utils/ratelimit.py
- utils/turn.py
