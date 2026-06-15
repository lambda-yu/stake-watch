# Branch Naming

Tiny branch model for a personal project.

## Branches

| Branch       | Purpose                                                  |
| ------------ | -------------------------------------------------------- |
| `main`       | Always green. Only merge work that passes the full test suite. |
| `feature/*`  | New capability (new collector, new endpoint, UI page).   |
| `fix/*`      | Bug fix on `main`.                                       |

## Naming

- Lowercase, hyphen-separated slug after the prefix.
- Keep it short and descriptive.
- Optional ticket/issue suffix if there is one.

### Examples

```
feature/kamino-collector
feature/usdt-risk-dashboard
fix/cooldown-off-by-one
fix/morpho-decimals
```

## Lifecycle

1. Branch off `main` (which should be up to date).
2. Push only when you want a remote backup — local-only is fine.
3. Merge into `main` (fast-forward or squash) once tests pass and self-review is done.
4. Delete the branch immediately after merge:
   ```bash
   git branch -d feature/kamino-collector
   ```

## Don'ts

- No long-lived branches other than `main`.
- No work directly on `main` — always branch.
- No force-pushes to `main`.
