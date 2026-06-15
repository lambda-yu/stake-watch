# Git Workflow

Lightweight workflow for a personal project. Keep it simple.

## Day-to-day

1. Start from an up-to-date `main`:
   ```bash
   git checkout main && git pull
   ```
2. Create a topic branch:
   ```bash
   git checkout -b feature/<slug>
   ```
3. Write the test first (see `docs/testing/tdd.md`), then implement.
4. Run the suite locally:
   ```bash
   uv run pytest tests/ -v
   ```
5. Commit in small, focused chunks (see `docs/git/commits.md`).
6. Merge into `main` (fast-forward or squash) and delete the branch.

## Rules of thumb

- Don't commit broken tests.
- Don't commit secrets (`.env`, Telegram tokens, RPC keys). Use env vars or the DB config table.
- Stage files explicitly (`git add path/...`) rather than `git add -A` to avoid sweeping in junk.
- Never bypass hooks (`--no-verify`) — fix the underlying issue.
