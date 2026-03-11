# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

Only the latest version on the `main` branch receives security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue.
2. Email the maintainer directly or use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository.
3. Include a description of the vulnerability, steps to reproduce, and the potential impact.
4. You can expect an initial response within **72 hours** and a fix or mitigation plan within **7 days** for critical issues.

## Security Considerations

### Authentication & Authorization

- Admin access is controlled via Django's `is_staff` flag, not by username.
- All mutating endpoints require `POST` with CSRF protection.
- Logout requires a `POST` request to prevent CSRF-based session termination.
- Login redirects are validated against the request host to prevent open redirects.
- Room passwords are hashed using Django's `make_password` / `check_password`.

### WebSocket Security

- All WebSocket consumers verify `user.is_authenticated` on connect.
- `ServerChatConsumer` verifies server membership before accepting connections.
- Chat messages and image uploads are validated server-side.

### File Uploads

- Uploaded images are validated using Pillow (magic byte verification), not just the `Content-Type` header.
- Maximum upload size is 5 MB.
- Accepted formats: JPEG, PNG, GIF, WEBP.
- Production deployments should use S3 for media storage rather than local filesystem.

### Secrets & Configuration

- `SECRET_KEY` is required via environment variable in production (no fallback).
- `ALLOWED_HOSTS` must be explicitly set in production (no wildcard default).
- Invite codes are generated using Python's `secrets` module (cryptographically secure).
- The `.env` file is in `.gitignore` and must never be committed.

### Production Hardening

- HTTPS is enforced via `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, and `CSRF_COOKIE_SECURE`.
- HSTS is enabled with a 1-year max age.
- `X-Frame-Options: DENY` and `SECURE_CONTENT_TYPE_NOSNIFF` are set.
- Media files are served via S3 in production, not `django.views.static.serve`.
- Static files are served via WhiteNoise with compressed manifest storage.

### Docker

- Media directory permissions are set to `u+rwX,go+rX` (not world-writable).
- The all-in-one PostgreSQL uses `scram-sha-256` authentication (not `trust`).
- Container logs are configured to output to stdout/stderr for centralized log collection.
