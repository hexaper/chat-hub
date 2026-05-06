# AGENTS.md

Scope: `apps/accounts/` owns the custom user model, auth/account forms, account views, URLs, and app-local tests.

## Key Files

- `models.py`: custom user model.
- `forms.py`: registration and account forms.
- `views.py`: auth and account settings views.
- `urls.py`: account routes.
- `tests/test_forms.py`, `tests/test_views.py`, `tests/test_ratelimit.py`: focused regression coverage.

## Rules

- Keep identity and auth behavior in this app instead of leaking it into `apps/rooms` or `utils`.
- Follow existing Django form/view patterns; avoid API-style abstractions unless the task requires them.
- Reuse `utils/` only for truly cross-cutting helpers.

## Verify

- Run `python manage.py test apps.accounts.tests --settings=config.settings.development` after changing forms, views, or auth flows.
- Update `templates/accounts/*.html` only when the view change requires it.
