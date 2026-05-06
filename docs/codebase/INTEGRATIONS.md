# External Integrations

## Systems

- PostgreSQL: primary DB in production/all-in-one.
- SQLite: development DB.
- Redis: channel layer + cache/rate-limit backend.
- S3-compatible storage: production media backend.
- STUN/TURN: ICE configuration for WebRTC (`/api/ice-servers/`).

## Secrets Source

- Runtime configuration comes from environment variables in settings/compose files.
- Secrets are not hardcoded in inspected settings files.

## Reliability Notes

- Redis outage breaks websocket fanout and rate-limit behavior.
- DB outage breaks core app behavior.
- TURN is optional but required for restrictive NAT/firewall environments.
