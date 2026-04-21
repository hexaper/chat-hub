---
name: user_profile
description: User role, workflow preferences, and collaboration style
type: user
---

The user is the sole developer on a Django + Django Channels + WebRTC project. They drive feature implementation themselves and use this agent specifically for test writing — they do not want the agent to make implementation decisions.

They provide precise, spec-style briefs when requesting tests: they list exactly which test methods to write, name them, and describe the expected behavior. Follow the spec closely.

They use a dedicated test-writing agent workflow — when implementation is done they pass the feature description and point at the relevant files. The agent should read the implementation first, cross-reference the existing test file for style, then write tests that match.

Test quality bar: tests must be diagnostic — failure messages must name the actual vs expected value. Tests must be independent (no shared mutable state between test methods).
