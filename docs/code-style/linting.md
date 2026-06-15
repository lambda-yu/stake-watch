# Linting

No linter is configured yet. This is a known gap; lint manually with the rules below.

## Manual checks

- Unused imports / variables — remove them.
- Async functions must be awaited; never call an `async def` without `await`.
- No bare `except:`; catch specific exceptions and log them.
- Type-hint all public functions and Pydantic model fields.
- No `print()` in `src/`; use the logging module.
- React: no unused props, no missing `key` on list items, exhaustive deps on `useEffect`.

## Planned setup (not yet enabled)

- **Python:** `ruff check` with rules `E`, `F`, `I`, `B`, `UP`, `ASYNC`.
- **TypeScript:** `eslint` with `@typescript-eslint` and `eslint-plugin-react-hooks`.

When adding either, wire it into a pre-commit hook and the test command so it can't drift.
