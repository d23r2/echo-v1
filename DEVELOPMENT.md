# Development

Quick reference for running quality checks locally. Everything here is free and local —
no paid services, no CI required. See [DAILY_SMOKE_TEST.md](DAILY_SMOKE_TEST.md) for a
manual click-through checklist to run alongside these automated checks.

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
2026-07-13 this surfaces 17 findings, all cosmetic (2 import-order, 15 Python
3.11+ `datetime.UTC` alias suggestions) and all fixable with `--fix`.

**mypy** is configured gently (`ignore_missing_imports`, `check_untyped_defs = false` —
see `[tool.mypy]` in `pyproject.toml`). It's genuinely useful here (14 findings as of
2026-07-13 — mostly a plain `str` passed where a narrower Pydantic `Literal` type is
expected, plus a few `str | None` vs `str` narrowing gaps in provider classes where a
separate `available()` call — not visible to mypy — already guarantees the value is set
before `chat()` runs) but is **not wired into CI or a required gate** — treat it as an
optional second opinion, not a blocker.

**pytest**: 386 tests as of 2026-07-14, all passing, no real external API calls anywhere
(every provider is a fake/mock — see `tests/fake_providers.py` and `tests/README.md`).
The no-billing web/wiki/RSS search system (`app/search_intent.py`, `app/web_search.py`)
is covered the same way — `tests/fake_http.py` fakes `httpx.get()` with real (but
offline) `httpx.Response` objects, so `test_search_intent.py`/`test_web_search.py`/
`test_persona_search_injection.py` never touch a real SearXNG/Wikipedia/RSS endpoint.

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
isn't set up today; don't assume `npm run lint` exists. There's also no `npm run test`
(no Vitest/Jest configured) — frontend correctness is currently verified by the type
checker plus manual/browser testing, not an automated test suite.

`npm install` reports 8 known vulnerabilities in transitive dependencies (2 moderate, 6
high) as of 2026-07-13 — pre-existing, not introduced by any recent work. Run `npm audit`
for details before deciding whether `npm audit fix` is worth the risk of a breaking
transitive version bump; it hasn't been applied here since it wasn't tested.

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
