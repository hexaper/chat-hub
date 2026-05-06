# Coding Conventions

## Naming

- Python modules/functions: snake_case.
- Classes (models/forms/consumers): PascalCase.
- Constants/env vars: UPPER_SNAKE_CASE.

## Imports and Layout

- Prefer absolute imports from `apps.*` and `utils.*`.
- Keep standard library, third-party, local import grouping clean.
- Keep feature logic in its owning app; avoid cross-app leakage.

## Realtime Rules

- Use `database_sync_to_async` for ORM inside async consumers.
- Use `sync_to_async` only for non-ORM sync helpers.
- Preserve sender self-exclusion WS pattern (`exclude` channel name in events).

## Testing Norms

- Django test runner only.
- Consumer tests use `TransactionTestCase` patterns and Redis-backed execution.
- Add/adjust focused tests for behavior changes in views/consumers/templates.

## Tooling

- No committed formatter/linter config in repo; follow existing style and keep diffs small.
