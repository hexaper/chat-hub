# AGENTS.md

Scope: `docs/` owns roadmap material, generated codebase docs, and superpowers design/plan artifacts.

## Key Files

- `ROADMAP.md`: future direction only.
- `codebase/STACK.md`, `STRUCTURE.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `INTEGRATIONS.md`, `TESTING.md`, `CONCERNS.md`: current repository map.
- `superpowers/specs/`: approved design docs.
- `superpowers/plans/`: implementation plans.

## Rules

- Update docs in the same task when code behavior, commands, architecture, or constraints change.
- Keep `ROADMAP.md` limited to future intent; current behavior belongs in `docs/codebase/*.md`.
- Prefer linking to canonical docs over duplicating the same explanation in multiple files.
- Keep paths, commands, and ownership notes aligned with the codebase and nearest `AGENTS.md` files.

## Verify

- Re-read edited docs and confirm commands, paths, and behavior still match the codebase.
- If code changed, update the relevant `docs/codebase/*.md` file in the same task.
