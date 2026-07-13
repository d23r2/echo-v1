# Development

Quick reference for running quality checks locally. Everything here is free and local —
no paid services, no CI required.

## Backend (Python)

From `backend/` (with `.venv` active, or prefix commands with `.venv/Scripts/python.exe -m`):

```bash
pip install -r requirements.txt   # includes pytest, ruff, mypy (dev-only)

pytest                            # run the test suite (see tests/README.md)
ruff check .                      # lint
ruff check . --fix                # lint + auto-fix what's safe to auto-fix
mypy app                          # optional type check — see note below
```

**ruff** is configured in `backend/pyproject.toml` with a deliberately small rule set:
pyflakes + pycodestyle's error subset (ruff's own defaults) plus import sorting (`I`),
common bug patterns (`B`), and syntax modernization (`UP`). No docstring or
type-annotation-coverage rules — those tend to produce hundreds of warnings on a
codebase that wasn't written with them in mind, which isn't useful signal. As of
2026-07-13 this surfaces ~20 findings, all cosmetic (import order, one Python
3.11+ datetime alias) and all fixable with `--fix`.

**mypy** is configured gently (`ignore_missing_imports`, `check_untyped_defs = false` —
see `[tool.mypy]` in `pyproject.toml`). It's genuinely useful here (only ~10 real, minor
findings as of 2026-07-13 — mostly a plain `str` passed where a narrower Pydantic
`Literal` type is expected) but is **not wired into CI or a required gate** — treat it as
an optional second opinion, not a blocker.

## Frontend (TypeScript)

From `frontend/`:

```bash
npm install
npm run build       # tsc -b (type check) && vite build — this is the real gate
npm run typecheck   # tsc -b --noEmit — same type check, no build output
npm run dev         # local dev server
```

There's no ESLint configured yet — `tsc -b` (via `build` or `typecheck`) is the current
quality gate on the frontend. Adding ESLint would be a reasonable future addition but
isn't set up today; don't assume `npm run lint` exists.

## Recommended pre-commit workflow

No `pre-commit` framework is installed (would be one more dependency for a
single-developer local project) — instead, before committing:

```bash
# backend changes
cd backend && pytest && ruff check .

# frontend changes
cd frontend && npm run build
```

Fix anything ruff flags (or run `ruff check . --fix` for the safe ones) and make sure
tests/build are green before committing.

## Recommended git commit workflow

- Small, focused commits over one giant one — makes `git log`/`git blame` actually useful
  later.
- Write the *why*, not just the *what*, in the commit message body when it's not obvious
  from the diff alone.
- Run the checks above before committing, not after — cheaper to fix locally than to
  discover later.
- Don't commit `backend/data/` (SQLite + Chroma persisted state), `.env` files, or
  `node_modules/` / `.venv/` — check `.gitignore` covers these before adding new
  directories that might need the same treatment.
