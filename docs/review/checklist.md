# Review Checklist

Use this before merging any branch into `main` (even self-review).

## Correctness

- [ ] Tests written **before** the implementation, and they actually exercise the new behaviour.
- [ ] Full suite green: `uv run pytest tests/ -v`.
- [ ] Edge cases covered: empty results, network failures, rate limits, decimals/precision.
- [ ] Async code awaited everywhere; no fire-and-forget tasks left dangling.

## Architecture

- [ ] New collectors subclass `BaseCollector` and are registered via `collectors/registry.py`.
- [ ] Data flows through `Position` / `ProtocolStats` / `Alert` models — no ad-hoc dicts leaking into storage.
- [ ] Risk rules read from the latest stored snapshot; cooldowns respected.
- [ ] No new config keys hardcoded — extend the DB config table and the frontend instead.

## Quality

- [ ] No secrets in code or commits.
- [ ] Logging uses the logging module at appropriate levels (debug for trace, info for lifecycle, warning/error for problems).
- [ ] Naming matches `docs/code-style/naming.md`.
- [ ] No dead code, no commented-out blocks.

## Docs

- [ ] If the public API or schema changed, `docs/api/endpoints.md` is updated.
- [ ] If a new collector was added, the list in `claude.md` is updated.
