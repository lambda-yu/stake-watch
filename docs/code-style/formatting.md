# Formatting

No formatter is wired into CI yet. Keep formatting consistent by hand.

## Python

- 4-space indentation, no tabs.
- Line length: aim for ~100 chars, hard cap 120.
- One import per line; group stdlib / third-party / local with blank lines between.
- Trailing commas in multi-line collections and function signatures.
- Use f-strings for interpolation.
- Future intent: adopt `ruff format` (Black-compatible). Until then, match the surrounding file's style.

## TypeScript / React (`frontend/`)

- Vite defaults; no custom Prettier config.
- 2-space indentation.
- Single quotes for strings; double quotes inside JSX attributes.
- Trailing commas where valid.
- Prefer named exports; default-export only for page components.

## YAML (`config/seed.yaml`)

- 2-space indentation, no tabs.
- Keep keys in stable order so diffs stay small.
