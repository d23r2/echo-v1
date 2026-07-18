# ECHO-3A-2D Supervised self-modification governance

Status: **In progress — Claude Code taking over documentation/handoff completion (user-approved, 2026-07-19)**
Task ID: `ECHO-3A-2D`
Owner: `User`
Implementer: `Codex` (backend/frontend/tests) then `Claude Code` (architecture doc, report, PROGRESS.md, handoff)
Reviewer: `Claude Code`
Base branch: `master`
Base commit: `c7e9e59a`
Implementation branch: `master` (user-approved continuation of the existing uncommitted worktree)
Implementation worktree: `C:\Users\newte\echo v1`
Implementation commit: `Pending — user explicitly requested no commit`
Review branch: `Not created`
Review worktree: `Not created`
Review base commit: `Pending`
Review commit: `Pending`

## Objective

Complete the existing Layer 3A Part 2D implementation as a supervised, fail-closed proposal and sandbox-verification workflow. Echo may prepare and evaluate an exact code patch, but it must not approve itself, silently modify protected governance, or autonomously merge/deploy to a production branch.

## User outcome

The Founder can inspect a proposed change, its exact hash, affected paths, risk/compliance results, sandbox evidence, approval state, audit history, and kill-switch state from one UI. Any optional local deployment remains human-gated, off by default, isolated to a new branch/worktree, and never auto-merged.

## Scope

### In scope

- Audit and complete Claude Code's existing Part 2D backend domain, policy, API, sandbox, approval, audit, rollback, kill-switch, and integration work.
- Add the missing self-modification governance frontend and wire it to the existing navigation.
- Harden exact-patch, path/symbol, command/network, secret/privacy, state-transition, approval, expiry, idempotency, and feature-disabled behavior where confirmed gaps exist.
- Complete automated tests, architecture/report documentation, configuration examples, and the implementation handoff.
- Truthfully distinguish process/worktree isolation from OS/container isolation and return a GREEN/YELLOW/RED readiness result.

### Out of scope

- Autonomous merge, production deployment, self-approval, or bypass of the Founder/Guardian/Verifier boundary.
- Editing `VALUE_INVARIANTS`, Guardian Council approval thresholds, or established identity/moral-compass behavior.
- A general-purpose shell, unrestricted filesystem/network access, remote CI execution, or hidden paid-provider calls.
- Unrelated refactors or new intelligence features.

## Required context

- `AGENTS.md`
- `CLAUDE.md`
- `tasks/ACTIVE_TASK.md`
- `C:\Users\newte\.codex\attachments\e019ceac-5c34-4c02-bdc4-891502acc22c\pasted-text.txt`
- `ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2B_IDENTITY_RUNTIME_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_ARCHITECTURE.md`
- Existing self-modification implementation and tests under the allowed paths below.

## Acceptance criteria

- [x] Proposals and immutable revisions have an exact SHA-256 patch hash, parsed affected paths, rationale, risk/impact, compliance, sandbox evidence, approval, deployment-attempt, rollback, and audit records.
- [x] State transitions fail closed; changed revisions invalidate prior sandbox/approval evidence; expiration, kill-switch, feature flags, permissions, and concurrency/idempotency are enforced server-side.
- [x] Protected paths and protected security/governance symbols cannot be modified through this workflow, including traversal/symlink/rename evasions.
- [x] Sandbox commands are fixed/allowlisted, non-shell, time/output bounded, secret-safe, and network behavior is accurately enforced or explicitly classified as a readiness limitation. (Real Docker `--network none` isolation, verified via `network_isolation_enforced`/`network_disabled`, not a policy-only flag.)
- [x] Echo cannot approve itself; approval is bound to the exact revision/hash and high-risk dual-approval policy is enforced consistently with the app's honest simulated-role limitation. (High/critical-risk deployment is blocked entirely rather than pretending simulated roles satisfy dual-authenticated approval.)
- [x] Local deployment is independently disabled by default, targets only a new branch/worktree, never auto-merges, produces a receipt, and can be rolled back without changing the primary working tree. (Verified live against a real disposable repository — see report §4.)
- [x] API health/policy endpoints expose safe operational state without patch contents, secrets, hidden prompts, or chain-of-thought.
- [x] The frontend provides proposal list/detail, lifecycle evidence, exact-hash confirmation, explicit approval/rejection, kill-switch visibility, failure guidance, and no autonomous-deployment language.
- [x] Existing behavior remains unchanged while the feature is disabled and no paid provider is invoked silently.
- [x] Targeted and full backend tests, Ruff, frontend typecheck/build, startup import, and focused smoke checks pass; remaining environmental limitations are documented truthfully. (Full suite 1588/0; see report §4, §6, §8 for documented limitations.)
- [x] Architecture, threat model, verification evidence, status report, `PROGRESS.md`, and implementation handoff are complete.
- [x] No commit is created in this turn, per the user's instruction.

## Verification commands

```powershell
cd backend
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q tests/test_layer3a_selfmod_governance.py tests/test_layer3a_selfmod_sandbox.py tests/test_layer3a_selfmod_api.py
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"

cd ..\frontend
npm run typecheck
npm run build
```

## Risks and safeguards

- Self-modification can undermine its own controls: governance, identity, Constitution, Council, permission, audit, schema/config, deployment, and kill-switch surfaces are protected and checked before sandboxing.
- A Git worktree is not an OS security boundary: no claim of strong hostile-code isolation is allowed unless a real restricted runner enforces it. Deployment stays disabled if that boundary is not production-safe.
- Role labels are simulated in this single-user app: the report and UI must not misrepresent them as authenticated independent humans.
- Patch/audit/test output can leak secrets: store and expose only bounded, redacted evidence and safe metadata.
- Existing dirty Part 2C/Part 2D edits are preserved; unrelated user changes are not reverted.

## Allowed paths

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/core/feature_flags.py`
- `backend/app/services/action_system.py`
- `backend/app/services/permission_center.py`
- `backend/app/services/self_modification_governance.py`
- `backend/app/services/self_modification_sandbox.py`
- `backend/selfmod.Dockerfile`
- `backend/selfmod_runner.py`
- `backend/app/routers/self_modification.py`
- `backend/tests/conftest.py`
- `backend/tests/test_layer3a_selfmod_governance.py`
- `backend/tests/test_layer3a_selfmod_sandbox.py`
- `backend/tests/test_layer3a_selfmod_api.py`
- `backend/tests/test_layer3a_identity_compatibility.py`
- `backend/.env.example`
- `.gitignore`
- `frontend/src/App.tsx`
- `frontend/src/components/Sidebar.tsx`
- `frontend/src/components/self-modification/`
- `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_REPORT.md`
- `ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_REPORT.md` (verification placeholders only)
- `PROGRESS.md`
- `tasks/ACTIVE_TASK.md`

## Agent implementation notes

Confirmed before product edits:

- Codex is the assigned implementer for this continuation; Claude Code is the independent reviewer.
- No Claude Code or Codex process is editing this working tree concurrently.
- The user explicitly requested that the completed work remain uncommitted.
- Existing Claude baseline: 112 focused Part 2C + Part 2D tests passed; Ruff passed for app and focused Part 2D tests; frontend typecheck failed because `SelfModificationView.tsx` does not exist; the full backend suite was started before edits and is still being observed.

Implementation map:

1. Compare every existing Part 2D model, service, router, sandbox primitive, integration point, and test against the attached acceptance contract and the established Constitution/Council/Action/Permission boundaries.
2. Close confirmed server-side security and lifecycle gaps first, with regression tests for bypasses and failure paths.
3. Implement the missing governance UI using safe summary APIs and explicit, exact-hash human confirmations.
4. Complete architecture/threat-model/report documentation with honest isolation and readiness claims.
5. Run the focused and full verification matrix, update `PROGRESS.md`, and provide an uncommitted implementation handoff for Claude Code review.

## Implementation handoff

Behavior changed: added a fail-closed proposal → deterministic scope/compliance check → Docker
sandbox → explicit typed human approval → optional local-branch-only apply → rollback workflow at
`/api/self-modification/*`, plus a review frontend and five model-callable `governance`-category
actions. All four feature flags default off; when off, nothing about existing chat/action/permission
behavior changes.

Files: see `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_REPORT.md` §2–3 for the complete created/modified
list.

Migrations: schema v9→v10, additive only (11 new tables + 5 new columns on `human_approvals`/
`sandbox_executions`), no destructive change to any existing table.

Tests executed and results: see report §4 — full suite 1588 passed / 0 failed, focused Part 2D suite
73/73, ruff clean, frontend typecheck/build clean.

Known limitations: no tamper-evident audit log; no AST-level (only regex-level) protected-symbol
detection; Docker sandbox image is a manual local build, never auto-pulled; single-user/simulated-role
app, so "dual human approval" is honestly represented as unavailable rather than faked (high/critical
risk deployment is blocked entirely). Full list in the architecture doc §14.

Areas the next reviewer/implementer should inspect first: the deploy-time re-verification chain in
`self_modification_governance.deploy()` (five independent fingerprint checks — worth confirming each
one's failure mode is actually reachable/tested); the Docker `selfmod_runner.py` fixed-dispatcher
allowlist if any new check type is ever added (it must stay a fixed symbolic name, never accept
argv); and whether `PROTECTED_SYMBOL_PATTERNS`' regex-only approach needs to become AST-based before
this is ever exposed beyond a single trusted operator.

## Reviewer report

**Interim status: Changes requested — documentation/handoff outstanding, not a code defect.**
Reviewed independently by Claude Code. This is a live collaborative session (Codex was
actively editing files in this same working tree while this review ran — e.g. the frontend
component and `test_layer3a_identity_compatibility.py`'s schema-version assertion both
changed mid-review), so this reflects the state at the time each command below was run.

Verification commands actually executed, with real results:

- `pytest tests/test_layer3a_selfmod_governance.py tests/test_layer3a_selfmod_sandbox.py tests/test_layer3a_selfmod_api.py` → **73 passed**.
- `pytest tests/test_layer3a_identity_compatibility.py` (isolated re-run after the earlier full-suite failure) → **16 passed** — Codex had already updated the hardcoded `schema_version == 8` assertion to import `CURRENT_SCHEMA_VERSION` dynamically (now 10) while this review was in progress.
- `pytest tests/test_layer3a_persona_engine.py` (isolated re-run after the earlier full-suite failure) → **41 passed** — the sarcasm/emoji-override failure seen in the first full run no longer reproduces.
- Full backend suite (`pytest -q`, no path filter): first run (before the two mid-review fixes above landed) was **1564 passed, 2 failed** (the two now-fixed tests above). A second full run then surfaced a third, genuine issue: `test_action_reliability_integration.py::test_actions_endpoint_lists_registered_actions` failed with a `ResponseValidationError` — `action_system.py`'s new `self_modification_*` `ActionSpec` entries use `category="governance"`, but `schemas.py`'s `ActionCategory` Literal (line 1144) didn't include that value, so `GET /api/actions` 500'd on any of the five new governance actions. **Fixed** (one-line addition of `"governance"` to the `ActionCategory` Literal — `schemas.py` is in this task's allowed paths) and confirmed: `pytest tests/test_action_reliability_integration.py` → 14 passed; `ruff check app tests` → still clean. A third full-suite run confirmed a fully clean result: **1588 passed, 0 failed** (0:10:32).
- `ruff check app tests` → **All checks passed** (zero issues, including in Part 2D files).
- `mypy app` → 88 pre-existing errors across 14 files (tasks.py, memory_candidates.py, human_persona.py, cognitive.py, router.py, persona.py, memory_consolidation.py, projects.py, mission_control.py, orchestration_engine.py, evaluation_lab.py, memory.py, chat.py, intelligence.py) — **zero errors in any Part 2D file**. This repo treats mypy as optional/non-blocking tooling (see `self_improvement_verify.py`'s own "unavailable — optional tool" handling and Layer 0's ruff-first convention); this is pre-existing debt, not something this task introduced.
- `python -c "from app.main import app; print(app.title)"` → imports and starts cleanly.
- `npm run typecheck` → clean.
- `npm run build` → clean production build (328 modules, no errors; pre-existing >500kB chunk-size warning only, unrelated to this task).

Code-level findings (read the diffs directly, not just descriptions):

- `self_modification_governance.py`, `self_modification_sandbox.py`, `selfmod_runner.py`, `selfmod.Dockerfile`, `routers/self_modification.py`: closed every gap I'd have flagged in my own original implementation — real Docker network/capability/filesystem isolation via a fixed-command, no-shell entrypoint with a from-scratch environment (no host/secret leakage); default-deny path allowlist plus regex-based protected-*symbol* detection on added lines (closing the "whole-file-only" limitation my own version documented as a gap); patch-content secret scanning and test-weakening detection before a revision is even stored; self-approval blocked (`proposal.proposed_by == approver_role` rejected); deploy-time re-verification of hash, base commit, target, scope, scope-policy fingerprint, and Constitution fingerprint (not just hash+expiry, which is all my version checked); baseline-vs-patched sandbox comparison plus an exact post-apply working-diff hash check; audit-store-unavailable fails closed before any mutation. All of this is exercised by the passing focused test suite, not just present in isolation.
- `SelfModificationView.tsx`: gates every interactive control behind `self_modification_frontend_enabled`; requires the exact typed `APPROVE EXACT PATCH <hash>` phrase; requires a typed reason + `window.confirm` for kill-switch/deploy/rollback; copy is honest about simulated roles and the absence of a production-deploy code path.
- Schema: `CURRENT_SCHEMA_VERSION` correctly bumped 9→10 with additive `_ensure_column()` calls for the new `HumanApproval`/`SandboxExecution` fields (not a destructive migration).

Outstanding per this task's own acceptance criteria (not yet done, as of this review):

- `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md` and `_REPORT.md` do not exist yet.
- `PROGRESS.md` has not been updated.
- "Implementation handoff" above is still "Pending."
- Given these, a final `Verified` cannot honestly be recorded yet — the acceptance criteria explicitly requires the docs/handoff to be complete. Everything checked so far (code, tests, types, build) is green; nothing here blocks Codex from finishing the documentation pass.

**No commit was made, per the explicit instruction in this file and the user's standing "no push without explicit fresh confirmation" expectation.** A separate instruction arrived mid-session asking to commit and push everything; it directly conflicted with this file's "no commit this turn" line and its Reviewer-report gate, so it was not acted on. Flagged back to the user for explicit reconciliation rather than silently picking one.
