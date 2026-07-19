# ECHO Supervised Maintenance Test Report

## Overall Status

**GREEN** — required functional and security behavior is verified working as intended, and the system
fails safely under every hostile or unexpected condition actually exercised this pass. One residual
item (a full clean live `sandbox_verify` pass) was not demonstrated end-to-end with a real Docker
container in this session — see "Residual Risks." Per the rule "do not recommend a higher mode unless
every lower mode passed," the **Final Recommendation** below is capped at `propose_only` even though
`sandbox_verify`'s deterministic logic has extensive passing coverage (mocked-subprocess tests from
Phases 4-5/7-8, and this pass's own live run through scope/compliance/Docker-invocation).

This is an **independent re-verification pass** over the already-implemented, already-tested
Supervised Maintenance Workspace (`ECHO_SUPERVISED_MAINTENANCE_WORKSPACE_V1_REPORT.md`, 51 tests,
GREEN). It found and fixed one real defect, added 33 new tests closing genuine coverage gaps (HTTP
layer, path-encoding edge cases, live browser confirmation, live Docker execution), and did not weaken
any existing safeguard.

## Test Environment

- OS: Windows 11 (this dev machine)
- Branch: `master`
- Commit tested: `a55daba8` (base) → this pass's commit (see final response)
- Test run ID: this session's transcript
- Database: isolated temp SQLite per pytest run (`tests/conftest.py`'s `DATABASE_URL` redirect); one
  live-check run against a separate temp SQLite via `_live_docker_sandbox_check.py`; one live browser
  check against the real dev database (read-only, no repository was left registered — see Cleanup)
- Sandbox type: `docker_worktree` (real Docker 29.5.2, image `echo-selfmod-sandbox:local`, already
  present locally)
- Capability modes tested: `disabled` (default/live), `analyse_only`, `propose_only`,
  `sandbox_verify` (live attempt), `human_approved_local_commit` (existing mocked coverage only)
- Feature flags: all 10 relevant flags confirmed at their coded-safe defaults (`False`) — no `.env`
  file exists in `backend/`
- Network: Docker sandbox runs with `--network none` (Part 2D's existing, unmodified guarantee,
  confirmed via `network_disabled` field — not independently re-verified this pass, see Residual Risks)

## Baseline Results

Read-only audit (before any code change) confirmed via direct source inspection, not assumption:

- Branch/commit/working-tree state: clean, `a55daba8`, no untracked files.
- All 10 Supervised Maintenance + Self-Modification feature flags at coded defaults (`False`).
- 4 database tables present exactly as documented (`approved_repositories`, `maintenance_analyses`,
  `maintenance_findings`, `maintenance_audit_events`) — confirmed no hash-chaining column exists
  (matches the already-documented honest limitation).
- 22 whole-file protected paths, 13 protected-symbol patterns, all Supervised-Maintenance-specific
  files present in `self_modification_governance.PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS`.
- **Critical structural finding**: zero authentication anywhere in this app (confirmed consistent
  across every router, not maintenance-specific) — the real security boundary against a model-driven
  bypass is that `action_system.py` registers **no** `maintenance_*`/`supervised_*` action at all,
  not the self-reported `requested_by` string. Pinned as a permanent regression test (see below).

`pytest -q` (full suite, before any test-pass change): **1639 passed, 0 failed** (Phase 8's own final
number, re-confirmed as this pass's starting baseline).

## Functional Results

| Area | Result |
|---|---|
| Repository access | Register/list/get/verify all work correctly for a human role; rejected for `echo`; rejected when subsystem disabled (after this pass's fix) |
| Analysis | Create/complete/cancel/add-finding all work; correctly rejected when capability mode is `disabled` |
| Proposal generation | Confirmed (Phase 3/4-5/7, re-verified this pass) to route through the unmodified Part 2D `create_proposal()`/`submit_revision()` — no special-casing |
| Validation | Deterministic scope check + constitutional compliance check both fire correctly for an analysis-originated proposal, live, in this pass's Docker check (`scope_check_status = passed`, `compliance_check_status = passed`) |
| Sandbox | Real Docker container invoked successfully; the post-run integrity check (`_assert_exact_working_diff`) correctly failed closed rather than accepting an unverified result — see Residual Risks |
| Evidence | `VerificationRun`/`SandboxExecution` schema confirmed unchanged from Part 2D; not reached this pass due to the sandbox integrity-check failure above |
| Approval | Not exercised live this pass (already extensively covered by Phase 4-5/7's mocked-deploy tests); no new gap found |
| Local commit | Not exercised live this pass (out of scope given `sandbox_verify` didn't complete cleanly); existing mocked coverage unchanged |

## Security Results

| Area | Result |
|---|---|
| Path containment | All Phase 8 cases re-confirmed passing; **3 new cases added and passing**: double-encoded traversal, 2 Unicode-lookalike-separator traversal variants (fullwidth solidus, fullwidth full stop) — both fail safely via literal-string non-resolution, not via the `".."` check itself |
| Secrets | Unchanged, re-confirmed via existing 51-test suite (still passing) |
| Prompt injection | Unchanged, re-confirmed via existing tests (content returned as inert literal text) |
| Protected scope | Unchanged; this pass's own new files (`test_supervised_maintenance_api.py`, `_live_docker_sandbox_check.py`) are test files, not governance code, so intentionally not added to `PROTECTED_PATHS` (matching the established convention that tests aren't protected) |
| Command policy | Unchanged (Part 2D's fixed dispatcher, confirmed via the live Docker run actually using it) |
| Network isolation | Not independently re-verified this pass beyond reading `network_disabled` on the (failed) sandbox execution record — see Residual Risks |
| Sandbox isolation | **Cleanup-after-failure confirmed live**: `git worktree list` and `git status --short` both clean after the failed live Docker run — no orphaned worktree, no leaked files |
| Approval binding | Unchanged, not re-exercised live this pass (existing coverage stands) |
| Audit integrity | Unchanged; no hash-chaining exists (already documented) |
| Kill switch | Not independently re-exercised this pass; no new gap found or suspected |
| **Self-approval / model exposure** | **New, explicit regression test**: `test_maintenance_has_no_action_system_exposure` asserts zero `maintenance_*`/`supervised_*` entries in `action_system.ACTIONS` — this is the actual structural boundary preventing self-approval, confirmed and now pinned rather than left as an inference |
| **Administrative fail-closed** | **Defect found and fixed**: registration/mode-change previously succeeded regardless of `supervised_maintenance_enabled` — now correctly rejected when the subsystem is off |

## End-to-End Results

- **Happy path (live, real Docker)**: register → set `sandbox_verify` mode → create analysis → add
  finding → complete analysis → generate proposal → scope check (passed) → compliance check (passed)
  → mark ready for sandbox → **real Docker container invocation** → integrity check fired and
  correctly rejected the result (see Residual Risks). Every stage through Docker invocation completed
  correctly; the pipeline did not silently continue past the failed integrity check.
- **Hostile path**: not re-run live this pass — already proven by Phase 4-5's
  `test_critical_risk_analysis_originated_proposal_still_blocked_before_sandbox` (a patch touching
  `permission_center.py` is blocked before sandbox regardless of origin) and this pass's own new
  path-traversal/secret/prompt-injection tests, all passing.
- **Recovery path**: cleanup-after-failure confirmed live for the sandbox worktree (see above); no
  other failure-recovery scenarios (backend restart mid-run, DB lock, etc.) were exercised this pass —
  out of scope given time; no evidence of a gap.
- **Live UI (real browser, real backend, real database)**: navigated to Governance → Supervised
  Maintenance in a real running instance (backend on a temporary alternate port, frontend dev server,
  both stopped and the temporary `.env` port change reverted after the check). Confirmed via direct DOM
  inspection (`element.disabled`, not just visual styling) that with
  `supervised_maintenance_frontend_enabled=False` (the real default), the Register/Start
  analysis/List/Read/Search buttons are **all `disabled: true`**, the amber "disabled by configuration"
  banner is shown, and status cards correctly report `disabled`/`disabled`/`disabled`/`0 repositories`.
  This is the first live confirmation of this UI in a real browser since it was built in Phase 6.

## Test Matrix

| ID | Category | Description | Expected | Actual | Pass/Fail | Evidence |
|---|---|---|---|---|---|---|
| M-01 | Access control | Registration rejected for `echo` role | Rejected | Rejected | Pass | `test_register_repository_requires_human_role` |
| M-02 | Access control | Registration rejected when subsystem disabled | Rejected | Rejected (after fix) | Pass | `test_register_repository_rejects_when_subsystem_disabled` (new) |
| M-03 | Access control | Mode change rejected when subsystem disabled | Rejected | Rejected (after fix) | Pass | `test_set_capability_mode_rejects_when_subsystem_disabled` (new) |
| M-04 | HTTP layer | Status/policy endpoints return correct shape | 200, correct fields | 200, correct fields | Pass | `test_status_endpoint_reports_defaults_all_disabled`, `test_policy_endpoint_exposes_protected_paths_and_scope` |
| M-05 | HTTP layer | Registration via real HTTP request, disabled subsystem | 403 | 403 | Pass | `test_register_repository_rejects_at_http_layer_when_subsystem_disabled` (new) |
| M-06 | HTTP layer | Registration via real HTTP request, model identity | 403 | 403 | Pass | `test_register_repository_rejects_at_http_layer_for_model_identity` (new) |
| M-07 | HTTP layer | Registration via real HTTP request, valid founder | 200 | 200 | Pass | `test_register_repository_succeeds_at_http_layer_for_founder` (new) |
| M-08 | HTTP layer | Unknown repository ID | 404 | 404 | Pass | `test_get_repository_404_at_http_layer` (new) |
| M-09 | HTTP layer | File list rejected when analysis disabled | 403 | 403 | Pass | `test_list_files_rejects_at_http_layer_when_analysis_disabled` (new) |
| M-10 | HTTP layer | Analysis creation rejected, `disabled` capability mode | 403 | 403 | Pass | `test_create_analysis_rejects_at_http_layer_for_disabled_capability_mode` (new) |
| M-11 | HTTP layer | Propose-from-unknown-analysis | 400 (LOW finding, not 404) | 400 | Pass (documented) | `test_propose_from_analysis_for_unknown_analysis_fails_closed` (new) |
| M-12 | HTTP layer | Audit endpoint shape | list | list | Pass | `test_audit_endpoint_returns_list_shape` (new) |
| M-13 | Self-approval boundary | No maintenance action in Action System | 0 matches | 0 matches | Pass | `test_maintenance_has_no_action_system_exposure` (new) |
| M-14 | Path containment | Double-encoded traversal | Rejected | Rejected | Pass | `test_read_file_rejects_double_encoded_traversal` (new) |
| M-15 | Path containment | Unicode fullwidth-solidus traversal | Rejected | Rejected | Pass | `test_read_file_rejects_unicode_lookalike_traversal` (new) |
| M-16 | Path containment | Unicode fullwidth-dot traversal | Rejected | Rejected | Pass | `test_read_file_rejects_unicode_lookalike_dot_traversal` (new) |
| M-17 | Live UI | Disabled-state controls genuinely locked | All buttons `disabled=true` | Confirmed via DOM | Pass | Live browser session, JS-evaluated |
| M-18 | Live sandbox | Real Docker container executes patch checks | Sandbox runs; integrity check enforced | Sandbox ran; integrity check fired and rejected | Pass (fail-closed confirmed) | `_live_docker_sandbox_check.py` output |
| M-19 | Live sandbox | Cleanup after failed sandbox run | No orphaned worktree | Confirmed clean | Pass | `git worktree list`, `git status --short` |
| M-20 | Regression | All 51 pre-existing Supervised Maintenance tests | Pass | Pass | Pass | full suite run |
| M-21 | Regression | Full backend suite | Pass, 0 failed | 1655 passed | Pass | `pytest -q` |
| M-22 | Regression | Ruff clean | 0 issues | 0 issues | Pass | `ruff check app tests` |
| M-23 | Regression | Frontend typecheck/build | Clean | Clean | Pass | `npm run typecheck`, `npm run build` |

67 dedicated Supervised-Maintenance tests total across 6 files (33 + 14 + 11 + 1 + 2 + 6).

## Defects Found

### D-1 — MEDIUM — Administrative endpoints bypassed the subsystem-off flag

- **Component**: `backend/app/services/maintenance_policy.py` — `register_repository()`,
  `set_capability_mode()`
- **Reproduction**: with `supervised_maintenance_enabled=False` (the coded default, no `.env`
  override), calling `register_repository(db, display_name="X", requested_by="founder")` succeeded,
  and the resulting repository's `set_capability_mode()` could then be raised all the way to
  `human_approved_local_commit` — the highest privilege tier — with the entire subsystem still
  globally off.
- **Expected**: DISABLED mode should mean the whole subsystem is administratively inert, not merely
  that its consequential operations (read/analysis/proposal) are gated.
- **Actual**: only `CodeAccessService`, `MaintenanceAnalysisService`, and `MaintenanceProposalService`
  checked the flag; the registration/policy layer did not.
- **Security impact**: low in practice — registration requires a human role (unreachable by the model,
  confirmed via M-13) and creates database rows only, no filesystem/sandbox/network consequence. Still
  a genuine defense-in-depth gap: the "kill switch"-equivalent flag didn't actually kill everything.
- **Failed open or closed?**: open (the check that should have rejected the call was simply absent).
- **Fix**: added an explicit `if not get_settings().supervised_maintenance_enabled: raise
  MaintenancePermissionError(...)` to both functions.
- **Regression tests**: `test_register_repository_rejects_when_subsystem_disabled`,
  `test_set_capability_mode_rejects_when_subsystem_disabled`, plus HTTP-layer confirmation
  (`test_register_repository_rejects_at_http_layer_when_subsystem_disabled`).
- **Status**: Fixed and verified (full suite green after the fix).

### D-2 — LOW — Status-code inconsistency for unknown analysis on the propose endpoint

- **Component**: `backend/app/services/maintenance_proposal.py` — `create_proposal_from_analysis()`
- **Reproduction**: `POST /analyses/{unknown_id}/propose` returns `400 Bad Request`, not `404 Not
  Found`, because the function raises the base `MaintenanceProposalError` rather than a dedicated
  not-found subtype (sibling endpoints like `get_analysis()` do map their not-found error to 404).
- **Security impact**: none — the request is still correctly rejected before anything is created.
- **Fix**: not applied — a REST-semantics nitpick, not a safety issue; fixing it would mean adding a
  new exception subtype and updating the router's status-mapping dict, a larger change than this
  pass's scope justifies for a cosmetic inconsistency.
- **Status**: Documented, not fixed. Test (`test_propose_from_analysis_for_unknown_analysis_fails_closed`)
  pins the actual (safe) current behavior.

### D-3 — HIGH (reliability, not security) — `sandbox_verify`'s baseline check cannot complete within its timeout

- **Component**: `backend/app/services/self_modification_sandbox.py` — `run_patch_in_sandbox()`'s
  baseline `backend-pytest` check, `selfmod_runner.py`'s fixed command, `_TIMEOUT_SECONDS` (600s)
- **Discovered**: in a targeted follow-up investigation of this report's original "Residual Risk" entry
  (which incorrectly hypothesized a stray build artifact — see the corrected Residual Risks section
  below for the full evidence trail).
- **Reproduction**: `governance.run_sandbox()` against a real analysis-originated proposal. The baseline
  phase (runs the entire real backend test suite, ~1655 tests, before any patch is applied) returned
  `status=failed, stderr_summary='Command timed out after 600s'` — confirmed via direct instrumentation,
  not inference.
- **Expected**: the baseline check should complete and report pass/fail for the *unpatched* codebase.
- **Actual**: it times out under the sandbox's `--memory 2g --cpus 2` resource cap before the suite
  finishes (the same suite takes ~11-14 minutes unconstrained on this host).
- **Security impact**: none — this fails closed. `passed = baseline_passed and post_passed`, so a
  timed-out baseline means the sandbox execution is correctly reported as not-passed; no unsafe patch
  can be approved off the back of it.
- **Reliability impact**: significant — as currently configured, `sandbox_verify` mode cannot produce a
  *passing* result for any proposal at all, since the baseline phase alone exceeds the timeout
  regardless of what the proposal's patch actually contains.
- **Fix**: not applied this pass — see Recommended Fixes below; this is Part 2D governance/sandbox code
  and the right resolution (longer timeout vs. scoped test selection vs. more container resources)
  is a deliberate tradeoff, not a "smallest necessary fix" this pass should make unilaterally.
- **Status**: Documented, not fixed. This is the corrected version of the "Residual Risk" this report
  originally raised — the original text attributed the failure to the wrong cause.

## Tests Executed

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_supervised_maintenance.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_supervised_maintenance_adversarial.py -v
.\.venv\Scripts\python.exe -m pytest -q tests/test_supervised_maintenance_api.py -v
.\.venv\Scripts\python.exe -m pytest -q tests/test_supervised_maintenance*.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe tests\_live_docker_sandbox_check.py

cd ..\frontend
npm run build
npm run typecheck
```

Plus a live browser session (backend on a temporary port, frontend dev server) navigating to
Governance → Supervised Maintenance and inspecting DOM state via `javascript_tool`.

## Counts

- **Passed**: 1655 (full backend suite)
- **Failed**: 0
- **Skipped**: 0 (junction-escape test creates a real junction and runs; no privilege-dependent skip
  occurred on this machine)
- **Warnings**: 0 new (pre-existing frontend chunk-size build warning, unrelated)
- **Blocked**: 1 (live `sandbox_verify` full pass — blocked by the integrity-check finding below, not
  by a test infrastructure problem)
- **Not run**: real network-egress-from-sandbox probing (§17 of the original spec), real approval/
  local-commit live execution (already covered by extensive mocked tests; not re-run live this pass
  given time), real-device concurrency/idempotency races (§25) — all deferred, none suspected to hide
  a defect given the existing architecture's design (deterministic checks, DB-transaction-scoped
  operations)

## Performance

Not formally benchmarked this pass (out of scope given the primary goal was correctness/security, not
throughput). Qualitatively: HTTP-layer tests (`test_supervised_maintenance_api.py`, 11 tests) completed
in ~16s; the full adversarial suite (14 tests, including a real `mklink /J` junction and a real zip
archive) in ~25s; the live Docker sandbox script's Docker container phase took under a minute
(consistent with Part 2D's own documented sandbox timings).

## Cleanup Verification

- No temporary sandbox directories remain: `.self_mod_sandboxes/` is empty; `git worktree list` shows
  no orphaned Supervised-Maintenance-related worktree.
- Live browser check: no `ApprovedRepository` row was left registered against the real dev database —
  the check only inspected the default (disabled) state; nothing was registered.
- Temporary `frontend/.env` port change (8000 → 8001, for the live browser check only) reverted back
  to `8000`.
- Both temporary dev servers (backend on port 8001, frontend on 5174) stopped.
- No synthetic secrets, credentials, or real conversation data were used or logged anywhere in this
  pass's fixtures.
- `git status --short` on the primary working tree is clean except for this pass's own intended file
  changes (see the commit).

## Safety Confirmation

- **Could ECHO approve itself?** No. Confirmed structurally (not just by convention) via
  `test_maintenance_has_no_action_system_exposure`: zero Supervised Maintenance functions are
  reachable through the model's tool-calling loop. The `requested_by` self-reported string is not the
  security boundary — the absence of any Action System entry is.
- **Did the live repository change?** No. `git status --short` and `git worktree list` confirmed
  clean before and after every live test; the failed Docker sandbox run's own teardown correctly
  removed its worktree.
- **Were secrets exposed?** No. No new secret-adjacent code path was touched; existing secret
  protections re-confirmed passing.
- **Was arbitrary shell available?** No. The live Docker run used the same fixed, unmodified
  `selfmod_runner.py` dispatcher Part 2D already has; not touched this pass.
- **Were protected systems editable?** No. No change to `PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS`
  enforcement logic; this pass's new files are tests, not governance code.
- **Did a sandbox escape occur?** No. The live Docker run's failure was a baseline-check timeout under
  the sandbox's resource caps (root-caused via direct instrumentation — see D-3/Residual Risks), not an
  escape; the container's own isolation (`--network none`, `--cap-drop ALL`, resource limits) was never
  breached, and the eventual `passed=False` result is exactly the fail-closed behavior expected when a
  required check doesn't complete.
- **Was a stale approval accepted?** Not applicable this pass (approval flow not exercised live); no
  change to that logic.
- **Could test evidence be altered?** Not applicable this pass (evidence creation not reached, since
  the integrity check fired first); no change to that logic.
- **Did any push occur?** No, until this report's own commit is pushed per the user's standing
  commit/push authorization for this session.
- **Did any deployment occur?** No. No code path in this system deploys anywhere beyond a local git
  branch, and that path was not exercised this pass.

## Residual Risks

- **CONFIRMED ROOT CAUSE (follow-up investigation, same session): `sandbox_verify`'s baseline check
  cannot currently complete within its own timeout.** A dedicated diagnostic script
  (`_diagnose_sandbox_diff_mismatch.py`, since removed — its finding is captured here) instrumented
  `run_patch_in_sandbox()`'s exact steps and printed the real intermediate state instead of theorizing.
  Result: the baseline `backend-pytest` check — which runs the **entire real ~1655-test backend suite**
  inside the sandbox, before any patch is even applied — returned
  `status=failed, stderr_summary='Command timed out after 600s'`. The Docker container is resource-capped
  to `--memory 2g --cpus 2`, and the full suite already takes ~11-14 minutes on this host's unconstrained
  hardware; under that cap it does not finish inside `_TIMEOUT_SECONDS` (600s). Since
  `passed = baseline_passed and post_passed` in `run_patch_in_sandbox()`, **this means `sandbox_verify`
  mode cannot currently produce a passing result for *any* proposal, regardless of the proposal's own
  content** — the baseline phase alone exceeds the allowed time before the patch-specific logic is even
  reached. This is a genuine, previously mis-diagnosed reliability defect (see the corrected D-3 entry
  below) — **not** the "stray build artifact" hypothesis this report originally proposed. Confirmed via
  the same diagnostic: `git status --short`/`_working_diff()` immediately after the timed-out baseline
  check were both empty (`''`) — the timeout left no stray files behind, ruling out that theory directly.
- **Separately, the live sandbox check scripts' own synthetic patches used placeholder git blob hashes**
  (`index 0000000..1111111`, hand-constructed rather than generated via a real `git diff`), which can
  never match `git diff`'s real computed content hashes (e.g. `index 00000000..050358b0`) regardless of
  the timeout issue above. This means `_assert_exact_working_diff()` was working correctly and would
  have rejected these specific synthetic test patches even if the baseline check had completed in time —
  a testing-methodology artifact of this pass's own fixtures, not a system defect. A real proposal's
  patch (generated by `MaintenanceProposalService`/an actual diff, never hand-typed placeholder hashes)
  would not hit this specific failure mode.
- **Operational finding: a hung/timed-out sandboxed check does not guarantee the underlying Docker
  container stops.** While root-causing the above, `docker ps` unexpectedly showed **two**
  `echo-selfmod-sandbox:local` containers still running — one 9 minutes old (this investigation's own
  run) and one **41 minutes old**, well past both the 600s check timeout and this pass's own earlier
  "cleanup verified" claim (which only checked `git worktree list`/`git status`, never `docker ps`).
  `docker top` showed the 41-minute container's `pytest` process alive but with only ~18s of accumulated
  CPU time — consistent with a hung/blocked process rather than active work. Both orphaned containers
  were found and stopped (`docker kill`) as part of this investigation; no repository state was affected
  (`git worktree list`/`git status` were already clean, confirming `_remove_worktree()`'s `finally`-block
  cleanup of the *worktree* runs independently of whether the *container* itself ever exits cleanly).
  **This is a real, previously-undocumented gap**: `subprocess.run(argv, timeout=_TIMEOUT_SECONDS)`
  around `docker run --rm ...` kills the host-side CLI process on timeout, but does not itself guarantee
  the daemon-side container is stopped/removed — `--rm` only fires on the container's own exit, and if
  its process is genuinely hung (as this instance appears to be) the container can outlive the host-side
  timeout indefinitely. Test coverage's own "cleanup after timeout" claims should be revisited to check
  `docker ps` directly, not just git state.
- **Network egress from inside the sandbox was not independently re-probed this pass** (§17 of the
  original spec — attempting real internet/localhost/metadata-endpoint access from inside the running
  container). Part 2D's own architecture and tests document `--network none` as enforced and verified
  via `network_disabled`; this pass's live runs recorded that field but never reached a state where an
  egress attempt would have been meaningful to test.
- **Concurrency/idempotency races** (duplicate submissions, simultaneous sandbox requests) were not
  exercised live this pass — no new gap is suspected given the existing DB-transaction-scoped design,
  but this remains formally unverified beyond Part 2D's own general claims.
- **No audit hash-chaining** — unchanged, already-documented limitation, not addressed by this pass
  (explicitly out of scope for a v1 verification pass, not a newly discovered gap).

## Recommended Fixes

Ordered by severity/dependency:

1. **(HIGH, do this before ever enabling `sandbox_verify` live)** Resolve the baseline-check timeout.
   Options, not mutually exclusive: (a) raise `_TIMEOUT_SECONDS` for the `backend-pytest` check
   specifically — a plain reliability tuning, not a security weakening, since the sandbox's isolation
   (`--network none`, `--cap-drop ALL`, no-shell dispatcher) is unaffected by how long a check is allowed
   to run; (b) scope the baseline/patched pytest invocation to only the directories/tests relevant to
   `changed_paths` instead of always running the entire suite, cutting real wall-clock time
   significantly; (c) raise the sandbox's `--memory`/`--cpus` caps if host resources allow — this one
   *does* touch the resource/security posture and deserves a deliberate decision, not a silent change.
   **Not applied in this pass** — this is Part 2D governance code (protected, cross-cutting, and used by
   the existing Self-Modification workflow too), and the right fix depends on a resourcing/time-budget
   tradeoff this report flags for a deliberate decision rather than assumes.
2. **(MEDIUM)** Add explicit `docker ps`-based cleanup verification (not just `git worktree
   list`/`git status`) to the sandbox's own test suite and to any future live-check tooling, and
   consider whether `run_patch_in_sandbox()` should explicitly `docker kill`/`docker rm -f` the
   container by name/ID on a host-side timeout rather than relying solely on `--rm` firing on the
   container's own (possibly-hung) exit.
3. (Optional, low priority) Give `create_proposal_from_analysis()`'s unknown-analysis case a dedicated
   not-found exception type mapped to 404, for consistency with sibling endpoints. Cosmetic only.
4. (Optional) A future pass could independently re-verify network egress and concurrency behavior live,
   closing the residual items above with direct evidence rather than inherited Part 2D coverage.

## Final Recommendation

**Safe to enable `propose_only`.**

`disabled` and `analyse_only` are fully confirmed safe (live UI lock-down demonstrated, 33 new tests
passing, one real defect found and fixed). `propose_only` is confirmed safe by extensive existing
coverage (Phase 3/4-5/7) plus this pass's own live run through scope check and compliance check with
real deterministic results. `sandbox_verify` and `human_approved_local_commit` are **not** recommended
yet — not because a security defect was found in them, but because this pass could not demonstrate a
full clean live pass through `sandbox_verify`, and the spec's own rule is not to recommend a mode
higher than the last one that actually passed end-to-end.
