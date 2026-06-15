# Review Process

This is a personal project, so the review is a self-review before merging to `main`.

## Steps

1. **Diff sweep.** `git diff main...HEAD` and read every change top to bottom. Look for accidental files (`.env`, `db.sqlite`, screenshots).
2. **Run the checklist.** Work through `docs/review/checklist.md` line by line.
3. **Run tests.** `uv run pytest tests/ -v`. No skips, no xfails left unexplained.
4. **Smoke the backend.** `uv run python -m stake_watch.main`, hit `/api/status`, confirm the scheduler tick logs.
5. **Smoke the frontend** (if UI changed). `cd frontend && npm run dev`, exercise the touched pages.
6. **Squash or fast-forward merge** into `main`, then delete the topic branch.

## When to ask for outside review

- Changes to the risk engine's rule evaluation or cooldown logic.
- New chain integration (RPC handling, signing, address parsing).
- Anything touching how alerts are dispatched (don't want silent failures).

Open a draft PR and ping someone instead of merging straight to `main` in those cases.
