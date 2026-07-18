# ECHO Layer 3A Part 2D — Supervised Self-Modification: Verification Report

**Final status: GREEN** — supervised, sandbox-only self-modification (proposal → checks → Docker
sandbox → explicit human approval → optional local-branch apply → rollback) is implemented, verified,
and ready for controlled testing. Production deployment remains safely gated: no code path reaches it
at all, and local-branch deployment itself stays off by default behind two independent feature flags.

**Nothing in this milestone has been committed.** Per explicit user instruction (recorded in
`tasks/ACTIVE_TASK.md`), all work here remains in the working tree, uncommitted, pending explicit
review and a separate commit authorization.

## 1. Summary

This was a two-implementer collaborative session in one shared working tree: Claude Code built the
initial domain model, governance service, git-worktree sandbox, router, and test suite; Codex then
continued that uncommitted work with substantial security hardening (a real Docker execution boundary,
default-deny path allowlisting, protected-symbol detection, self-approval prevention, deploy-time
re-verification against five independent snapshotted fingerprints, patch secret-scanning and
test-weakening detection) and built the frontend. Claude Code then independently re-verified the
combined result end-to-end (not just Codex's own claims), found and fixed three concrete issues
surfaced only by running the actual test suite, and wrote this document plus the accompanying
architecture doc.

## 2. Files created

Backend:
- `backend/app/services/self_modification_governance.py` — proposal lifecycle, scope/risk policy, constitutional pre-check, kill switch, audit recording.
- `backend/app/services/self_modification_sandbox.py` — git-worktree isolation + Docker-based check execution.
- `backend/selfmod_runner.py` — fixed, allowlisted command dispatcher baked into the sandbox image.
- `backend/selfmod.Dockerfile` — local-only, explicitly-built sandbox image definition.
- `backend/app/routers/self_modification.py` — `/api/self-modification/*` API surface.
- `backend/tests/test_layer3a_selfmod_governance.py`, `test_layer3a_selfmod_sandbox.py`, `test_layer3a_selfmod_api.py` — 73 tests total.

Frontend:
- `frontend/src/components/self-modification/SelfModificationView.tsx` — the governance review workspace.

Docs:
- `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`, this report.

## 3. Files modified

- `backend/app/models.py` — 11 new tables (§3 of the architecture doc).
- `backend/app/schemas.py` — corresponding Pydantic Read/Create schemas, plus a fix: added
  `"governance"` to the pre-existing `ActionCategory` Literal (see §5, finding #3).
- `backend/app/config.py` — 6 new settings, all default-safe (§12 of the architecture doc).
- `backend/app/db.py` — schema v9→v10, additive `_ensure_column()` calls for `HumanApproval`'s and
  `SandboxExecution`'s newer fields, `_seed_self_modification_governance()`.
- `backend/app/core/feature_flags.py` — 4 new flag entries with dependency chains (deployment requires
  sandbox requires supervised-self-mod).
- `backend/app/main.py` — router registration.
- `backend/app/services/permission_center.py` — 6 new `self_modification_*` permission keys.
- `backend/app/services/action_system.py` — 5 new `governance`-category `ActionSpec` entries
  (propose/sandbox-run/request-review/deploy/rollback), each delegating to the governance service so
  a model-triggered call is bound by the identical fail-closed checks as a direct API call.
- `backend/.env.example` — documented the 6 new settings.
- `backend/tests/test_layer3a_identity_compatibility.py` — fixed a hardcoded `schema_version == 8`
  assertion to import `CURRENT_SCHEMA_VERSION` dynamically (see §5, finding #1).
- `.gitignore` — excludes `.self_mod_sandboxes/` (the sandbox scratch directory) from `git status`
  noise on the real repository.
- `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx` — new route/nav entry under
  Governance.

## 4. Test results — exact commands and outcomes

| Command | Result |
|---|---|
| `pytest tests/test_layer3a_selfmod_governance.py tests/test_layer3a_selfmod_sandbox.py tests/test_layer3a_selfmod_api.py -q` | **73 passed** |
| `pytest tests/test_layer3a_identity_compatibility.py -q` | **16 passed** |
| `pytest tests/test_layer3a_persona_engine.py -q` | **41 passed** |
| `pytest tests/test_action_reliability_integration.py -q` | **14 passed** |
| `pytest -q` (full suite, final confirmation run) | **1588 passed, 0 failed** (10:32) |
| `ruff check app tests` | **All checks passed** |
| `mypy app` | 88 pre-existing errors across 14 files unrelated to this milestone (see §5); **zero in any Part 2D file** |
| `python -c "from app.main import app; print(app.title)"` | Imports and starts cleanly |
| `npm run typecheck` | Clean |
| `npm run build` | Clean production build (328 modules; pre-existing >500 kB chunk-size warning only) |

Live, direct verification of the deployment safety guarantee (not just unit-tested): against a
disposable `git init` fixture repository, `deploy_to_local_branch()` was run, then `git status --short`
and `current_head()` on the primary tree were confirmed unchanged, then `rollback_local_branch()` was
run and the branch/worktree confirmed fully removed — deployment and rollback do not touch the primary
working tree at any point.

## 5. Findings during independent review, and their resolution

1. **Stale hardcoded schema version in a pre-existing test.** `test_layer3a_identity_compatibility.py`
   asserted `schema_version == 8`; the intentional v9→v10 migration for this milestone's new tables
   made that assertion fail. **Fixed by Codex** (observed mid-review) to import and compare against
   `CURRENT_SCHEMA_VERSION` dynamically. Not a regression — an expected, correct consequence of adding
   tables.
2. **Unrelated Part 2C test failure** (`test_current_no_sarcasm_and_no_emoji_override_durable_settings`)
   seen on the first full-suite run. **Fixed by Codex** (observed mid-review, unrelated to Part 2D
   scope) — confirmed passing on isolated re-run and in the final full-suite pass.
3. **`ActionCategory` schema didn't accept the new `"governance"` action category.** Codex's five new
   `ActionSpec` entries use `category="governance"`, but `schemas.py`'s `ActionCategory` Literal
   (used by `ActionDefinitionOut`, which `GET /api/actions` returns) didn't include that value —
   every call to `GET /api/actions` 500'd with a `ResponseValidationError` once those actions were
   registered. **Fixed by Claude Code**: added `"governance"` to the Literal (one line). Confirmed via
   the previously-failing `test_action_reliability_integration.py::test_actions_endpoint_lists_registered_actions`
   (14/14 passed) and a clean ruff run.

All three were caught by actually running the verification commands end-to-end, not by inspecting the
diff alone — this is why the full-suite run (not just the focused Part 2D tests) matters for a
milestone like this.

## 6. mypy: pre-existing, unrelated debt (not a Part 2D regression)

88 errors across 14 files — `tasks.py`, `memory_candidates.py`, `human_persona.py`, `cognitive.py`,
`router.py`, `persona.py`, `memory_consolidation.py`, `projects.py`, `mission_control.py`,
`orchestration_engine.py`, `evaluation_lab.py`, `memory.py`, `chat.py`, `intelligence.py` — none of
which this milestone touched. This repository treats mypy as optional/non-blocking tooling by design
(see `self_improvement_verify.py`'s own graceful "mypy is not installed — skipped (optional tool)"
handling, and Layer 0's ruff-first, mypy-advisory convention). Zero mypy errors exist in any file this
milestone created or modified.

## 7. Security review

- **No secrets committed or logged.** `selfmod_runner.py` reconstructs its process environment from
  scratch; `_clean_error()` sanitizes every subprocess/exception message before it reaches a client or
  an audit row; `contains_likely_secret()` rejects a patch outright at submission if it contains
  private-key/API-key-shaped content.
- **Permissions remain enforced.** Every mutating governance call routes through
  `permission_center.check()` with a dedicated key; none bypass it.
- **Safety systems were not bypassed or weakened.** `VALUE_INVARIANTS`, Guardian Council approval
  thresholds, and every other pre-existing protected system are on the `PROTECTED_PATHS`/
  `PROTECTED_SYMBOL_PATTERNS` denylist for this workflow itself, and this milestone's own code changed
  nothing about them.
- **No hidden reasoning exposed.** `GET /policy` and `GET /health` return only structural metadata
  (protected-path lists, flag states, counts) — never patch contents, never chain-of-thought.
- **No accidental generated files or local databases staged.** `.self_mod_sandboxes/` is gitignored;
  no `.db` files are part of this change set.

## 8. Recommended next steps (not implemented — out of this milestone's scope)

- A real second-authenticated-human approval mechanism, so high/critical-risk deployment could someday
  be safely re-enabled rather than unconditionally blocked.
- Tamper-evident audit logging (hash-chained or append-only at the storage layer) — a genuine gap
  documented honestly in §9/§13 of the architecture doc.
- AST-level (not regex-level) protected-symbol detection, to close the "obfuscated rename/indirection"
  gap noted as a known limitation.
- CI-based build/publish pipeline for the sandbox image, so it isn't a manual local-only step.
- Tuning sandbox resource limits against real-world dependency-heavy patches once this has real usage
  history.

## 9. Final verdict

**GREEN.** Every verification command specified in `tasks/ACTIVE_TASK.md` was actually run and passed
(full suite 1588/0, ruff clean, frontend typecheck/build clean, startup clean); the three issues found
during independent review were fixed and re-verified, not merely reported; the deployment safety
guarantee was verified live against a real repository, not just asserted; and every honest limitation
this system has is documented rather than glossed over. Nothing was committed or pushed, per explicit
user instruction — that remains a separate, later decision.
