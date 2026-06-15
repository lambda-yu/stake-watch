# Commit Conventions

This project uses **Conventional Commits** with a Claude co-author trailer on AI-assisted commits.

## Format

```
<type>(<optional-scope>): <short summary>

<optional body — what / why, wrapped at ~72 chars>

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>
```

## Allowed types

| Type      | When to use                                                |
| --------- | ---------------------------------------------------------- |
| `feat`    | New user-visible feature (new collector, new endpoint, UI page). |
| `fix`     | Bug fix.                                                   |
| `refactor`| Code change with no behaviour change.                      |
| `perf`    | Performance improvement.                                   |
| `test`    | Add or fix tests only.                                     |
| `docs`    | Docs only (this file, `claude.md`, READMEs).               |
| `chore`   | Tooling, deps, config that doesn't touch `src/` or `tests/`. |
| `build`   | Build / package changes (`pyproject.toml`, `package.json`). |

## Scope (optional)

Use the top-level module name: `collectors`, `risk`, `api`, `storage`, `scheduler`, `alerts`, `frontend`, `tests`.

## Examples

```
feat(collectors): add Kamino lending collector

Pulls position health factor and supply APY from the Kamino API.
Registered via collectors/registry.py.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>
```

```
fix(risk): respect cooldown when rule re-fires on same tick

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>
```

```
docs: add claude.md and mandatory project documentation

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>
```

## Rules

- Subject line: imperative mood, no trailing period, <= 72 chars.
- One logical change per commit. Split unrelated edits.
- Always use a HEREDOC for multi-line messages so the trailer formats correctly:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat(api): expose /alerts/test endpoint

  Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>
  EOF
  )"
  ```
- Never `--amend` after a failed hook — fix and make a new commit.
- Never `--no-verify`.
