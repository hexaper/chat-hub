---
name: consumer_test_patterns
description: Patterns specific to WebSocket consumer tests — TransactionTestCase, silence assertions, DB verification, commit discipline
type: project
---

## Class structure
- All consumer tests use `TransactionTestCase` (never `TestCase`). Channels consumer threads cannot see TestCase's uncommitted transaction.
- Fixtures are created in `setUp` (not `setUpTestData`) because TransactionTestCase truncates tables between tests — `setUpTestData` is not compatible.
- The ASGI application under test: `AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns))`, built in `setUp`.

## Auth injection
- Auth is injected via a real Django session cookie, not by patching `scope['user']`.
- Helper `_get_cookie_header(user)` logs in via `django.test.Client`, extracts `sessionid` cookie, returns `[(b'cookie', b'sessionid=<value>')]`.
- Pass headers to `WebsocketCommunicator(app, url, headers=headers)`.

## commit discipline
- Always call `transaction.commit()` after creating DB fixtures and before calling `communicator.connect()`.
- Without this, the consumer thread (running in a separate OS thread) cannot see the uncommitted rows.

## History drain
- On connect, `ServerChatConsumer` immediately sends a `history` frame.
- Tests that are not testing history must drain it first: `await communicator.receive_from(timeout=20)`.

## Silence assertions (no-broadcast cases)
- Use a short timeout (0.3s) to assert that no message was received:
  ```python
  received_something = False
  try:
      await communicator.receive_from(timeout=0.3)
      received_something = True
  except asyncio.TimeoutError:
      pass
  self.assertFalse(received_something, msg="...")
  ```
- Do NOT use `self.assertRaises(asyncio.TimeoutError)` for silence checks in consumer tests — it works but the pattern above is more self-documenting and matches the codebase style.

## DB verification after consumer actions
- Consumer DB writes happen inside the consumer's async thread. They ARE committed (TransactionTestCase uses autocommit).
- After `asyncio.run(run())` returns, call `instance.refresh_from_db()` then assert on the Python object.

## Timing: expired edit window test
- To create a message outside the 15-minute edit window, create the message normally then immediately update `created_at` via queryset:
  ```python
  old_created_at = timezone.now() - timedelta(minutes=16)
  ChatMessage.objects.filter(pk=msg.pk).update(created_at=old_created_at)
  msg.refresh_from_db()
  transaction.commit()
  ```
- `auto_now_add=True` prevents setting `created_at` on `create()`, so the queryset `.update()` is required.

## Two-communicator broadcast tests
- Connect both communicators, drain both history frames, then send from comm1.
- Both comm1 and comm2 will receive the group broadcast (group_send goes to all members including sender).
- Order within the same event loop iteration is deterministic: the sending consumer receives the echo first.
