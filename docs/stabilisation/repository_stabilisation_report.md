# ECHO Repository Stabilisation Report — Pass 1 of 3

## Overall Status

**GREEN.**

The audit found no incomplete implementations, no broken imports/routes/migrations/schemas, no
disconnected frontend/backend wiring, and no API-schema mismatches. Every TODO/FIXME/placeholder-style
marker in application code turned out to be an intentional, honestly-labeled placeholder already handled
correctly (see `repository_stabilisation_plan.md` §3). The repository was already in a stable, tested
state before this pass began — this pass's real work was a small set of genuine, previously-flagged
repository-hygiene gaps, plus full re-verification of the test/build baseline.

## Repository State Before Work

- Branch `master` at `083ebc49`, clean working tree, in sync with `origin/master`, no stashes, no
  merge/rebase state, no conflict markers. Full detail in `repository_stabilisation_plan.md` §1.

## Incomplete Work Found

None that blocks startup, build, or tests. Full classification in `repository_stabilisation_plan.md`
§3 (intentional placeholders) and §4 (obsolete-but-harmless dead files).

## Work Completed

1. **Added `.gitattributes`** (`* text=auto` plus explicit binary markers) — closes a CRLF/LF
   normalization gap `PROGRESS.md` flagged across four separate check-ins (2026-07-16 through
   2026-07-19) and never fixed. No existing file line endings were touched (tree was already clean;
   renormalizing now would only add unrelated diff noise for zero behavior change).
2. **Corrected `.github/workflows/ci.yml`'s header comment**, which falsely claimed the workflow "has
   NOT been pushed to GitHub" — it has been on `origin/master` since `ec2ac484`. Comment now states the
   true, current, safe status (lint/test/typecheck/build/config-validate only, no deploy job, no
   secrets required).
3. **Fixed `README.md`'s dev-server port** — it documented `http://localhost:5173` (Vite's bare
   default), but `frontend/vite.config.ts` explicitly configures `port: 5174`, and every other doc/config
   in the repo (`.env.example`'s `CORS_ORIGINS`, `VITE_API_BASE_URL`) already agrees on 5174. This was a
   real, user-facing inaccuracy that would have sent a reader to the wrong URL.
4. **Ran the complete available baseline** (below) to obtain current, exact pass/fail evidence rather
   than trusting prior reports' numbers as still current.

## Work Deferred

- Deleting `frontend/src/components/chat/ReasoningTrace.tsx` /
  `frontend/src/components/chat/AtlasNotes.tsx` (confirmed dead, zero references anywhere) — cosmetic,
  zero-risk, left for the owner per "prefer the smallest reliable correction."
- Renormalizing existing tracked files under the new `.gitattributes` — no current diff noise to fix.
- Local cleanup of the gitignored, untracked `Echo_Code_Review.zip` — outside git's tracked tree.
- All genuinely-new feature work listed in `PROGRESS.md`'s "Gaps / next up" (ComfyUI real generation,
  Groq/OpenRouter providers, Schedule notifications, `npm audit fix`, ESLint) — explicitly out of scope
  for a stabilisation pass.

## Files Added

- `.gitattributes`
- `docs/stabilisation/repository_stabilisation_plan.md`
- `docs/stabilisation/repository_stabilisation_report.md`

## Files Modified

- `.github/workflows/ci.yml` — comment correction only, no behavioral change.
- `README.md` — one port number correction (5173 → 5174).

## Migrations

No schema change was made this pass. `CURRENT_SCHEMA_VERSION` remains `12`. The additive,
idempotent `init_db()` migration path (see plan §2) was exercised directly — imported `app.main`,
called `init_db()` against the real dev database, zero errors, 278 routes registered — and is exercised
continuously by all ~1,655 backend tests, each against a fresh isolated SQLite database.

## Backend Results

| Command | Result |
|---|---|
| `python -m pytest -q` (full suite) | **1655 passed, 0 failed** (921.73s / 0:15:21) |
| `python -m pytest tests/test_supervised_maintenance*.py -q` | **67 passed** |
| `python -m ruff check app tests` | All checks passed |
| `python -c "from app.main import app; from app.db import init_db; init_db()"` | OK — 278 routes, no error |

## Frontend Results

| Command | Result |
|---|---|
| `npm run build` (`tsc -b && vite build`) | Clean — 329 modules, pre-existing >500 kB chunk-size warning only (unrelated, informational) |
| `npm run test -- --run` | **10 passed** (2 test files) |

## Integration Results

- `docker compose config --quiet` — valid (matches the CI `config-validation` job).
- Backend startup and Docker health-check/non-root-user configuration reviewed in
  `backend/Dockerfile` — `USER echo`, `HEALTHCHECK` both present.
- Live backend (port 8000, Docker) + frontend dev server (port 5174) integration, Governance Center,
  Supervised Maintenance Analyse-Only mode, and normal chat path were already directly verified earlier
  in this same session (mobile-audio live-browser verification pass) — not re-run a second time this
  pass since nothing backend- or frontend-routing-relevant changed since then.
- Mobile audio capability detection: re-confirmed via source inspection this pass (see Security Review
  below) rather than re-running the live browser check, since no audio-relevant code changed since the
  mobile-audio pass completed and was verified.

## Security Review

- `scripts/check_secrets.ps1` (repo's own scanner): 15 findings, **all inside `backend/tests/*.py`**,
  each individually confirmed by direct file inspection to be a synthetic fixture value that exists
  specifically to test the app's own secret-redaction/detection logic (e.g.
  `assert "sk-should-never-be-in-registry-output" not in serialized`). **No real secret found.**
- `.env` confirmed gitignored and untracked (backend and frontend). `.env.example` (both) contain
  placeholder/empty values only — read directly, not assumed.
- No tracked `.db`/`.sqlite` file. No tracked file over 5 MB. `.self_mod_sandboxes/`,
  `.claude/worktrees/`, and all local venv/cache/build directories confirmed correctly gitignored.
- Voice input/output architecture re-confirmed via repo-wide grep: **zero** references to
  `MediaRecorder`, `getUserMedia`, or `MediaStream` anywhere in `frontend/src` — voice capture is
  handled entirely inside the browser's native `SpeechRecognition` implementation, never exposing a raw
  audio stream to application code, which structurally rules out "leaked raw recording,"
  "persistent MediaStream track," and "recording continues after stop" as live concerns for this
  architecture. The two `createObjectURL` call sites that do exist
  (`MemoryCenterView.tsx`, `PersonalityView.tsx`) are unrelated data-export blob URLs, not audio.
  `result[0].transcript` (the only "transcript" reference in the frontend) flows directly into the
  existing chat-message text state — no separate transcript-logging endpoint exists (confirmed: no
  `/api/*voice*`, `/api/*audio*`, or `/api/*speech*` route anywhere).

## Known Failures

None.

## Environment Limitations

- This session has no physical mobile device — mobile-audio real-device verification remains the
  responsibility of the repository owner, as already documented in
  `docs/audio/mobile_audio_test_report.md` from earlier in this session.
- Windows Tauri desktop build was not re-verified this pass (last verified per `PROGRESS.md`'s
  2026-07-12 entry); out of scope for a stabilisation pass focused on backend/frontend/web correctness.

## Remaining Risks

- The obsolete `ReasoningTrace.tsx`/`AtlasNotes.tsx` files remain in the tree (harmless — confirmed
  zero references, so they cannot affect runtime behavior, only add a small amount of dead-code
  surface).
- No repository-wide line-ending renormalization was performed; a future contributor whose local git
  config doesn't already match this repo's LF-on-disk convention could still reintroduce noisy diffs
  until they next touch each affected file (the new `.gitattributes` prevents this going forward for
  any file touched after this commit, but doesn't retroactively fix files no one has edited yet).

## Recommended Next Step

Proceed to the mobile-audio real-device verification the owner already committed to doing (per
`docs/audio/mobile_audio_test_report.md`), then Stabilisation Pass 3 (final integration/security/
regression/push verification).
