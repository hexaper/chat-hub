---
name: feedback_test_style
description: Conventions the user expects in test code — style, assertion verbosity, class placement
type: feedback
---

Match the existing file's style exactly — do not introduce new patterns unless adding a genuinely new test category.

**Why:** Consistency makes the test file scannable and reduces cognitive load during review.

**How to apply:**
- New consumer tests go into the existing `ConsumerTests` class unless they test a distinct consumer (`RoomConsumer` → `RoomConsumerTests`).
- Use `asyncio.run(inner_async_fn())` pattern — not `async def test_*` — because `TransactionTestCase` is synchronous.
- Define the async body as an inner `async def run()` or with a descriptive name when the test scenario is long.
- Assertion `msg=` parameters: always include the actual value received (f-string interpolation) so failures are self-diagnosing without needing a debugger.
- Short silence timeout: `0.3` seconds (not `0.5`, not `1`). This matches the codebase's established pattern.
- History drain comment: `# drain history` inline comment on the `receive_from` line.
- `transaction.commit()` always appears immediately before the communicator is constructed, after all fixture DB writes.
- Import `SimpleUploadedFile` inline inside the test method that needs it (matches existing `test_server_chat_image_message_sent_by_owner` style).
- Do NOT use `assertRaises(asyncio.TimeoutError)` for silence checks — use the explicit `try/except` pattern with `received_something` flag.
