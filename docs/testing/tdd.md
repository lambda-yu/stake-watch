# Test-Driven Development

The suite uses `pytest` + `pytest-asyncio`. 87 tests pass today; target 80%+ coverage and don't let it slide.

## Workflow

1. **Write the failing test first.** Place it in `tests/` mirroring the source layout (e.g., a new collector goes in `tests/collectors/test_<name>.py`).
2. **Run it and watch it fail** for the right reason:
   ```bash
   uv run pytest tests/path/to/test_thing.py -v
   ```
3. **Implement the minimum** code to make it pass.
4. **Refactor** with the test green.
5. **Run the full suite** before committing:
   ```bash
   uv run pytest tests/ -v
   ```
6. **Check coverage** before merging:
   ```bash
   uv run pytest tests/ --cov=stake_watch
   ```

## Async patterns

- Mark async tests with `@pytest.mark.asyncio` (or rely on auto mode if configured).
- Use async fixtures for the SQLAlchemy async session, the FastAPI test client, and HTTP mocks.
- Mock external IO (`httpx`, RPC, Telegram) with `respx`, `pytest-httpx`, or a hand-rolled fixture — never hit the network in tests.

## What to test

- **Collectors:** given a recorded API response, the collector emits the expected `Position` / `ProtocolStats` rows.
- **Risk engine:** given a snapshot, the expected rule fires (and doesn't fire when under threshold or in cooldown).
- **API:** each endpoint round-trips through the FastAPI test client against a temp SQLite DB.
- **Storage:** migrations / schema changes have a smoke test that creates the table and inserts a row.

## What not to test

- Third-party libraries (FastAPI, SQLAlchemy, Pydantic) — trust them.
- Trivial getters with no logic.

## Coverage discipline

- New modules must ship with tests.
- A drop below 80% on a PR is a blocker — either add tests or justify the gap in the commit body.
