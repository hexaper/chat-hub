# Testing Patterns

## Core Sections (Required)

### 1) Test Stack and Commands

- Primary test framework: Django test runner via `python manage.py test`; Channels test support is used for websocket coverage.
- Assertion/mocking tools: Django TestCase and TransactionTestCase assertions, Django test client, RequestFactory, and Channels WebsocketCommunicator.
- Commands:

```bash
python manage.py test --settings=config.settings.development --keepdb
python manage.py test apps.rooms.tests.test_consumers.ConsumerTests --settings=config.settings.development
python manage.py test apps.rooms.tests.test_consumers.RoomChatConsumerTests --settings=config.settings.development
[TODO] No separate coverage command found in inspected files.
```

### 2) Test Layout

- Test file placement pattern: tests are primarily grouped under each app's tests/ package, with one utility test module at utils/tests.py.
- Naming convention: most test files follow test_*.py and test classes use descriptive `*Tests` names.
- Setup files and where they run: no dedicated global test setup module was found; setup is handled inside test classes via setUp and setUpTestData.

### 3) Test Scope Matrix

| Scope | Covered? | Typical target | Notes |
|-------|----------|----------------|-------|
| Unit | Yes | Utility helpers and forms | utils/tests.py exercises rate-limit primitives directly |
| Integration | Yes | Full Django view and user flows | apps/rooms/tests/test_integration.py covers multi-step server/room flows |
| E2E | No | [TODO] | No browser-driven end-to-end suite was found |

### 4) Mocking and Isolation Strategy

- Main mocking approach: low-mock integration-style testing with Django fixtures/helpers and Channels communicators.
- Isolation guarantees: many tests create fresh DB state per case; utils/tests.py clears the cache in setUp to avoid rate-limit counter leakage.
- Common failure mode in tests: consumer tests require TransactionTestCase-style semantics and a running Redis instance; command notes explicitly warn that `--parallel` is broken in this environment.

### 5) Coverage and Quality Signals

- Coverage tool + threshold: [TODO] No coverage tool or threshold config was found in inspected files.
- Current reported coverage: [TODO]
- Known gaps/flaky areas: no E2E suite was found; test execution depends on Redis availability; only CodeQL is automated in CI from the inspected workflow set.

### 6) Evidence

- apps/rooms/tests/test_consumers.py
- apps/rooms/tests/test_integration.py
- apps/accounts/tests/test_views.py
- utils/tests.py
- CLAUDE.md
- .github/workflows/codeql.yml
