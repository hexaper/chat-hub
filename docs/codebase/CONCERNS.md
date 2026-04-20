# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| high | Presence state is process-local rather than shared across instances | apps/rooms/consumers.py | Multi-instance deployments can show incorrect online/offline status and inconsistent presence bars | Move presence state into Redis or another shared store, or explicitly scope deployment to one real-time process |
| high | No automated test workflow was found beyond CodeQL scanning | .github/workflows/codeql.yml, CLAUDE.md | Regressions can reach the default branch without test execution in CI | Add a GitHub Actions workflow that provisions Redis and runs the Django test suite |
| medium | apps/rooms/consumers.py is large and owns multiple protocols plus presence state | apps/rooms/consumers.py | Changes to signaling, server chat, and room chat are tightly coupled and harder to review safely | Split consumer responsibilities into smaller modules or shared mixins |
| medium | apps/rooms/views.py mixes server CRUD, room flows, chat uploads, and admin-panel behavior | apps/rooms/views.py | Permissions and response-shape changes can regress unrelated features | Separate admin, media-upload, and room/server flows into smaller view modules |
| medium | Chat upload error responses are inconsistent between image and video branches | apps/rooms/views.py | Frontend clients must handle multiple incompatible error schemas for the same endpoint | Normalize upload errors to one stable machine-readable format |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Mixed responsibilities in room views | Feature growth accumulated in one module | apps/rooms/views.py | Permission and UI flow changes remain high-risk | Extract server, room, upload, and admin concerns into separate modules |
| Mixed responsibilities in websocket consumers | Three protocols plus presence live in one file | apps/rooms/consumers.py | Real-time bugs become harder to isolate | Split consumers or shared helpers by protocol concern |
| Inconsistent test file placement | Most tests live under app-local tests/, but utils uses a flat module | utils/tests.py | Discoverability is slightly uneven | Decide whether utility tests should move to utils/tests/ for consistency |
| Missing formatter/linter configuration | No config files were found in inspected repo files | repository root | Style drift and review overhead increase over time | Add and document a formatter/linter policy if the team wants automated enforcement |

### 3) Security Concerns

| Risk | OWASP category (if applicable) | Evidence | Current mitigation | Gap |
|------|--------------------------------|----------|--------------------|-----|
| All-in-one deployment accepts any host value by default | A05 Security Misconfiguration | config/settings/allinone.py | Optional TLS and secure cookies follow SECURE_SSL_REDIRECT | Host allow-listing is not enforced in that mode |
| Limited observability around auth, upload, and integration failures | A09 Security Logging and Monitoring Failures | config/settings/production.py, apps/rooms/views.py | Error-level console logging exists; healthz checks DB/cache | No structured security logging or alerting config was found |
| Upload validation protects type/size but no broader content-scanning policy was found | A08 Software and Data Integrity Failures | apps/rooms/views.py | Image verification and video magic-byte checks are implemented | No antivirus/moderation/quarantine workflow was found |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| Presence uses in-memory state | apps/rooms/consumers.py | Works only inside one process | Horizontal scaling will fragment online-user state | Back the presence store with Redis |
| WebRTC remains peer-to-peer mesh | static/js/webrtc.js, docs/ROADMAP.md | Fine for small rooms | Large rooms increase client CPU/bandwidth costs non-linearly | Keep measuring room sizes and introduce an SFU only if usage requires it |
| High-churn files are also among the larger source files | apps/rooms/consumers.py, apps/rooms/views.py, static/js/webrtc.js | These files already carry multiple responsibilities | Future changes will be fragile and review-heavy | Refactor incrementally behind tests |

### 5) Fragile/High-Churn Areas

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| entrypoint.sh | Production startup, migrations, seed data, secret handling all meet here | High churn called out in recent-history scan used during documentation | Change with container boot verification and health-check validation |
| config/settings/production.py | Storage, Redis, DB, security headers, and logging are centralized here | High churn called out in recent-history scan used during documentation | Change one concern at a time and re-check deploy env vars |
| apps/rooms/consumers.py | Signaling, chat, presence, and moderation events all live together | High churn called out in recent-history scan used during documentation | Pair each change with targeted consumer tests |
| apps/rooms/views.py | Server, room, upload, and admin flows share one file | High churn called out in recent-history scan used during documentation | Add or update view tests before refactoring |

### 6) `[ASK USER]` Questions

1. [ASK USER] Is the long-term deployment target a single Daphne process, or should presence and other real-time state be made multi-instance-safe now?
2. [ASK USER] Do you want one normalized API error schema for chat uploads, or is the current mixed human-readable and machine-readable response format intentional?
3. [ASK USER] Should the self-hosted all-in-one mode continue to allow `ALLOWED_HOSTS = ['*']`, or do you want that mode tightened for non-local deployments?

### 7) Evidence

- apps/rooms/consumers.py
- apps/rooms/views.py
- config/settings/allinone.py
- config/settings/production.py
- static/js/webrtc.js
- .github/workflows/codeql.yml
- CLAUDE.md
- docs/ROADMAP.md
