# Testing Patterns

## Test Stack

- Framework: Django test runner (`python manage.py test`).
- Realtime testing: Channels `WebsocketCommunicator`.
- Common classes: `TestCase` for most tests; `TransactionTestCase` patterns for consumer tests.

## Commands

```bash
python manage.py test --settings=config.settings.development --keepdb
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_integration --settings=config.settings.development
```

## Constraints

- Redis must be available for consumer/rate-limit coverage.
- Do not use `--parallel` in this repository.
- No committed coverage threshold/tool config is present.
