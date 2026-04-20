# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type (API/DB/Queue/etc) | Purpose | Auth model | Criticality | Evidence |
|--------|---------------------------|---------|------------|-------------|----------|
| PostgreSQL | Database | Primary relational store in production and all-in-one modes | Database user/password from env vars | High | config/settings/production.py, config/settings/allinone.py |
| SQLite | Database | Local development database | Local file, no external auth | Medium | config/settings/development.py |
| Redis | Cache + pub/sub/channel layer | Channel layer backend and cache/rate-limit storage | Connection URL/host from settings or local defaults | High | config/settings/base.py, config/settings/production.py, config/settings/allinone.py |
| S3-compatible object storage | Object storage | Production media storage for uploaded files | AWS access key + secret key via env vars | Medium | config/settings/production.py |
| Google STUN server | Network service | Default ICE discovery for WebRTC | No application credential in code | Medium | config/urls.py |
| coturn-compatible TURN service | Network service | Relay media for users behind restrictive NAT/firewalls | Either HMAC-generated short-lived credentials (TURN_SECRET) or static long-term credentials (TURN_USERNAME/TURN_PASSWORD) | Medium | config/urls.py, utils/turn.py, docker-compose.yml |
| GitHub Actions CodeQL | CI/security scanning | Static analysis on push, PR, and schedule | GitHub Actions permissions | Low | .github/workflows/codeql.yml |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| PostgreSQL | Production persistence for users, servers, rooms, devices, and chat messages | Django ORM via apps/*/models.py | Connection/env misconfiguration or DB availability outage stops core app features | config/settings/production.py, apps/rooms/models.py |
| SQLite | Development persistence | Django ORM | Divergence from PostgreSQL behavior is possible in local-only testing | config/settings/development.py |
| Redis DB 0 | Channels pub/sub | CHANNEL_LAYERS configuration and consumers | Real-time features fail if Redis is unavailable | config/settings/base.py, apps/rooms/consumers.py |
| Redis DB 1 | Cache and rate limiting | Django cache API and utils/ratelimit.py | Rate limiting and health checks depend on cache availability | config/settings/base.py, utils/ratelimit.py, config/urls.py |
| S3 bucket | Production media files | Django STORAGES config | Misconfigured bucket or credentials breaks user-upload media | config/settings/production.py |
| Local filesystem under mediafiles/ | Dev/all-in-one media storage | Django FileSystemStorage and entrypoint setup | Container permissions or disk growth can affect uploads | config/settings/base.py, config/settings/allinone.py, entrypoint.sh |

### 3) Secrets and Credentials Handling

- Credential sources: environment variables in production/all-in-one settings and compose files; base.py can generate a secret key file when none is provided.
- Hardcoding checks: inspected settings files do not hardcode cloud/database secrets, but compose examples and entrypoints assume many secrets are supplied through env vars.
- Rotation or lifecycle notes: TURN supports short-lived HMAC credentials and static credentials; broader secret-rotation policy is [TODO].

### 4) Reliability and Failure Behavior

- Retry/backoff behavior: no explicit retry/backoff policy was found for database, Redis, S3, or TURN-related integrations.
- Timeout policy: [TODO] No explicit application-level timeout configuration was found for external integrations beyond container health checks.
- Circuit-breaker or fallback behavior: healthz surfaces DB/cache failures; TURN falls back to STUN-only when TURN is disabled; no circuit-breaker implementation was found.

### 5) Observability for Integrations

- Logging around external calls: limited; production.py configures console error logging, and healthz exposes DB/cache status via HTTP.
- Metrics/tracing coverage: no metrics or tracing integration was found.
- Missing visibility gaps: no structured logs for S3/Redis/TURN operations, no latency metrics, and no explicit alerting configuration were found.

### 6) Evidence

- config/settings/base.py
- config/settings/development.py
- config/settings/production.py
- config/settings/allinone.py
- config/urls.py
- utils/turn.py
- utils/ratelimit.py
- docker-compose.yml
- entrypoint.sh
- .github/workflows/codeql.yml
