# ECHO Stabilisation Release Report

## Overall Status

**GREEN.**

## Final Branch

`master`

## Final Commit

`cf82b027` (`docs(stabilisation): Pass 1 repository audit — plan + report, GREEN`) prior to this
report's own commit — see the Files and Commits section below for the exact final hash after this
document and the break checklist are committed and pushed.

## Remote Push Status

Pending — see the end of this pass's work for the exact pushed commit hash and verification. Target
remote: `origin` → `https://github.com/d23r2/echo-v1.git`, branch `master`, fast-forward push (no
force required — `master` is cleanly 2 commits ahead of `origin/master` with no divergence).

## Work Completed

- **Pass 1 (this session, earlier today)**: full repository audit — no incomplete implementations, no
  broken imports/routes/migrations found; fixed three real, previously-flagged hygiene gaps
  (`.gitattributes`, a stale CI-workflow comment, a wrong port number in `README.md`); re-ran the
  complete baseline for current evidence. Full detail: `docs/stabilisation/repository_stabilisation_plan.md`,
  `docs/stabilisation/repository_stabilisation_report.md`.
- **Pass 2 (this session, earlier today)**: mobile voice input/output diagnosis and fix. Full detail:
  `docs/audio/mobile_audio_test_plan.md`, `docs/audio/mobile_audio_test_report.md`.
- **Pass 3 (this document)**: final integration/security/regression verification, documentation
  consolidation, final commits, and push.

## Supervised Maintenance Status

- **Highest safe capability mode**: `HUMAN_APPROVED_LOCAL_COMMIT` is implemented and tested, but every
  flag governing it (`supervised_maintenance_enabled`, `supervised_analysis_enabled`,
  `supervised_proposals_enabled`, `self_modification_sandbox_enabled`,
  `self_modification_deployment_enabled`) defaults to `false` in `backend/app/config.py` — the feature
  is fully **disabled by default** and requires explicit owner opt-in via `.env`, one flag at a time,
  in dependency order.
- **Disabled capabilities (structurally, not just by default flag)**: ECHO cannot approve its own
  proposals — re-confirmed this pass by grepping every call site of `approve_revision()` in the
  codebase: the only caller is the HTTP router, reached solely by the human-operated frontend approval
  UI; there is no tool-registry, `local_intelligence_engine.py`, or `action_system.py` reference to
  `approve_revision`, local-commit creation, or any other human-only maintenance endpoint anywhere —
  meaning there is no function-calling path by which the model itself could invoke approval or commit,
  independent of any permission check. Push, merge, and deployment remain unimplemented capabilities,
  not merely disabled ones. `public_push_enabled` defaults to `False` in code (not just `.env.example`).
- **Safety test status**: 67/67 dedicated Supervised Maintenance tests passing (re-run this session,
  see Backend Test Results). Kill switch (`_check_kill_switch()`) gates proposal creation, sandbox
  entry, and approval, and its own activation/reset requires
  `permission_center.check("self_modification_kill_switch")`.
- **Cloud disclosure**: `backend/app/services/maintenance_analysis.py` makes zero calls to any model
  provider — analysis is fully deterministic (path/pattern/AST-adjacent checks), so there is no code
  path by which source content could reach a cloud provider through this feature at all; any subsequent
  conversation *about* a finding goes through the normal chat pipeline with whatever provider the user
  has already configured and consented to, identical to any other chat message.
- **Residual risks** (unchanged from the existing Phase 8 report, not newly discovered): no audit
  hash-chaining exists anywhere in this codebase (shared, disclosed limitation of the underlying Part 2D
  governance infrastructure this feature reuses, not something added or skipped by Supervised
  Maintenance specifically); symbol-level protection is text-search-based, not full AST analysis.

## Mobile Audio Status

- **Voice input**: browser `SpeechRecognition`/`webkitSpeechRecognition` only — zero
  `MediaRecorder`/`getUserMedia`/`MediaStream` references anywhere in `frontend/src` (re-confirmed via
  repo-wide grep this pass), meaning the app never captures a raw audio stream at all; capture is
  handled entirely inside the browser's own implementation. The mic control now always renders with an
  explicit reason (unsupported / insecure context / off in Settings / available) instead of silently
  vanishing.
- **Voice output**: browser `speechSynthesis` only. A watchdog now detects a blocked/silent `speak()`
  call (the mobile autoplay/gesture-policy failure mode) and shows a "Tap to play" recovery banner that
  re-issues the utterance from a real click gesture.
- **Browsers tested**: Chromium desktop engine only, via the in-app Browser pane's mobile-viewport
  emulation. **No real mobile browser was used.**
- **Real-device status**: **not run.** This remains the owner's responsibility per the standing
  agreement for this work (no physical device was available to this session).
- **Secure-context requirement**: most mobile browsers require HTTPS (or `localhost`) for
  `SpeechRecognition`; ECHO's own deployment is deliberately configured for plain HTTP on a LAN IP for
  mobile/LAN access (`capacitor.config.ts`'s `androidScheme: 'http'`, `vite.config.ts`'s `host: true`),
  which is a non-secure context for microphone purposes on a real phone browser (not the packaged
  Capacitor/Tauri apps, which have their own WebView origin exemptions). The mic control's
  insecure-context messaging (added in Pass 2) surfaces this honestly instead of failing silently; the
  underlying HTTP deployment choice itself was not changed, as redesigning it is out of this pass's
  scope.
- **Known, previously undocumented limitation being disclosed here for the first time**: Chrome's
  `webkitSpeechRecognition` implementation is documented (by Google, not this codebase) to route
  recognition audio through Google's own servers for online recognition — this is an inherent property
  of the browser's built-in implementation, not a choice this codebase makes, initiates, or could
  intercept, and it was not previously called out explicitly in `docs/audio/mobile_audio_test_plan.md`.
  Safari's on-device recognition may differ. This is disclosed here in the interest of not silently
  omitting a real characteristic of the feature, not because any code change is needed — there is no
  local-only STT alternative implemented or claimed anywhere in this codebase.
- **Remaining limitations**: unsupported-browser and insecure-context messaging paths were verified via
  unit test (mocked props) only, not against a real browser that actually lacks `SpeechRecognition` or
  actually runs on an insecure origin, since this harness's engine has neither condition.

## Backend Test Results

| Command | Result |
|---|---|
| `python -m pytest -q` (full suite) | **1655 passed, 0 failed** (921.73s / 0:15:21) |
| `python -m pytest tests/test_supervised_maintenance*.py -q` | **67 passed, 0 failed** |
| `python -m ruff check app tests` | All checks passed |

## Frontend Test Results

| Command | Result |
|---|---|
| `npm run test -- --run` | **10 passed, 0 failed** (2 test files) |

## Integration Results

- `docker compose config --quiet` — valid.
- Backend startup: `from app.main import app; from app.db import init_db; init_db()` — succeeded, 278
  routes registered, no error.
- `npm run build` (`tsc -b && vite build`) — clean, 329 modules, pre-existing >500 kB chunk-size warning
  only (informational, unrelated to this work).
- Live backend (Docker, port 8000) + frontend dev server (port 5174) integration, Governance Center,
  Supervised Maintenance Analyse-Only mode, and normal chat path were directly verified earlier this
  session (mobile-audio live-browser verification pass); not re-run a second time this pass since no
  backend- or frontend-routing-relevant code changed since then.

## Security Results

- Repository secret scanner (`scripts/check_secrets.ps1`): 15 findings, all confirmed by direct file
  inspection to be synthetic test fixtures inside `backend/tests/*.py` that exist specifically to test
  the app's own secret-redaction logic. **No real secret found.**
- `.env` confirmed gitignored, untracked, both backend and frontend. `.env.example` (both) contain
  placeholder/empty values only.
- Supervised Maintenance and mobile-audio invariants re-verified this pass — see the two status
  sections above for specifics and evidence, not just assertions.
- No tracked `.db`/`.sqlite` file, no tracked file over 5 MB, `.self_mod_sandboxes/` and
  `.claude/worktrees/` correctly gitignored.

## Migration Results

No schema change this pass (`CURRENT_SCHEMA_VERSION` remains `12`). The additive, idempotent `init_db()`
path was exercised directly against the real dev database with no error, and continuously by all 1,655
backend tests, each against a fresh isolated SQLite database.

## Build Results

Backend startup: clean. Frontend production build: clean. Typecheck (via `tsc -b`, part of `npm run
build`): clean. Lint (`ruff`): clean. No ESLint configured for the frontend (a pre-existing, documented
gap, not something this pass silently introduced or is required to fix).

## Files and Commits

This pass's own commits (docs + this report) are listed with their hashes once created — see the final
response for the exact final local and pushed commit hash. Commits from this session prior to this pass:

| Commit | Summary |
|---|---|
| `cf82b027` | Pass 1: stabilisation plan + report docs |
| `c1a7523d` | Pass 1: `.gitattributes`, stale CI comment, README port fix |
| `083ebc49` | Pass 2: mobile voice input/output fixes |
| `e289b542` | Sandbox integrity-check root-cause correction (residual-risk deep-dive) |
| `7b085408` | Independent Supervised Maintenance security/functional test pass |
| `a55daba8` | Supervised Maintenance Phase 8 (hardening, adversarial tests, final report) |

## Known Issues

- The two obsolete, zero-reference frontend files (`ReasoningTrace.tsx`, `AtlasNotes.tsx`) remain in
  the tree — harmless, documented in Pass 1's report, left for the owner to remove at their discretion.
- No audit hash-chaining anywhere in the codebase (Supervised Maintenance's own governance base, Part
  2D, has always had this limitation — disclosed, not new).

## Deferred Work

- Real mobile-device voice testing (owner's responsibility, per standing agreement).
- Repository-wide line-ending renormalization under the new `.gitattributes` (no current noise to fix).
- All genuinely-new feature work listed in `PROGRESS.md`'s "Gaps / next up" — explicitly out of scope
  for a stabilisation pass.

## Rollback Instructions

Standard git revert, no destructive operations required:

```
git revert <commit-hash>          # revert one commit, creates a new commit
git log --oneline -10             # find the commit(s) to revert
```

No database migration was applied this pass, so no data-level rollback is needed. If a future
Supervised-Maintenance-created local commit ever needs rolling back, prefer `git revert` over
`git reset --hard` for the same reason documented in `docs/supervised_maintenance/rollback.md`.

## One-Week Safe State

- **No autonomous deployment**: confirmed — no deploy job exists anywhere in this codebase or its CI
  workflow; `self_modification_deployment_enabled` defaults `false`.
- **No autonomous push**: confirmed — `public_push_enabled` defaults `False` in `config.py`; no push
  capability exists in any agent-reachable code path; this session's own push (below) required explicit
  human-equivalent authorization under the standing session instruction, not autonomous action.
- **No autonomous self-approval**: confirmed structurally, not just by flag — see Supervised
  Maintenance Status above.
- **No production migration**: confirmed — no schema change occurred this pass; Supervised Maintenance
  cannot apply migrations to a live database (analysis/sandbox only).
- **No paid API introduced**: confirmed — no new dependency, no new provider integration, nothing in
  this pass's diff touches billing-relevant code.
- **Local-only policy preserved**: confirmed — Supervised Maintenance analysis makes zero model-provider
  calls; mobile audio remains 100% client-side browser APIs with no backend involvement.
- **Kill switch available**: confirmed present and gated by `permission_center` checks, unmodified this
  pass.
- **Audit history preserved**: confirmed — no audit record was altered, deleted, or bypassed; this
  pass's own actions (file reads, test runs, the three hygiene fixes) are ordinary git-tracked changes,
  not actions that flow through the Supervised Maintenance audit system at all.

## Recommended First Task After Break

**Real mobile-device verification of the voice input/output fixes from Pass 2** — the single largest
open item blocking a confident GREEN (rather than YELLOW) status for mobile audio. Test on at least one
real iOS Safari device and one real Android Chrome device: confirm the mic control shows a clear reason
instead of silently vanishing wherever it's unavailable, and confirm a voice reply that would previously
have failed silently now either plays normally or shows the "Tap to play" recovery banner. Do not
implement this now — it requires hardware this session doesn't have.
