# ECHO Supervised Maintenance Workspace — Test Run Plan

Read-only audit findings and the executable test plan for this pass. Written before any hostile
execution, per the test mandate's §3. This is a **verification pass over an already-implemented,
already-tested system** (51 dedicated tests from Phases 1-8, `ECHO_SUPERVISED_MAINTENANCE_WORKSPACE_
V1_REPORT.md`) — the goal here is independent, adversarial re-verification and closing any gaps that
pass didn't cover, not rebuilding the feature.

## 1. Read-only audit findings

**Repository state**: branch `master`, commit `a55daba8`, working tree clean, no untracked files, one
remote (`origin` → `https://github.com/d23r2/echo-v1.git`).

**Feature flags** (`backend/app/config.py`, confirmed by source read — no `.env` file exists in
`backend/`, so every flag is at its coded default): `supervised_maintenance_enabled`,
`supervised_analysis_enabled`, `supervised_proposals_enabled`, `supervised_sandbox_enabled`,
`supervised_local_commit_enabled`, `supervised_maintenance_frontend_enabled`,
`supervised_self_modification_enabled`, `self_modification_sandbox_enabled`,
`self_modification_deployment_enabled`, `self_modification_frontend_enabled` — **all `False`**. The
live system is in the **DISABLED** state end to end. No `ApprovedRepository` row exists yet (no
registration has ever been performed against the running dev database).

**Maintenance routes** (`backend/app/routers/supervised_maintenance.py`, prefix
`/api/governance/supervised-maintenance`): `GET /status`, `GET /policy`, `GET|POST /repositories`,
`GET /repositories/{id}`, `POST /repositories/{id}/mode`, `POST /repositories/{id}/verify`,
`GET /repositories/{id}/files`, `GET /repositories/{id}/file`, `GET /repositories/{id}/search`,
`GET /repositories/{id}/git-status`, `GET /repositories/{id}/git-diff`,
`GET|POST /analyses`, `GET /analyses/{id}`, `POST /analyses/{id}/propose`,
`GET|POST /analyses/{id}/findings`, `POST /analyses/{id}/complete`, `POST /analyses/{id}/cancel`,
`GET /audit`.

**Critical finding on the authentication boundary** (documented honestly, not glossed over): **this
router has no authentication dependency at all** — no `Depends(current_user)` or equivalent on any
route. This is confirmed **consistent with every other router in the app**, including
`self_modification.py` (checked directly), and with `main.py`'s middleware stack (only
`RequestIDMiddleware` and CORS — no auth middleware anywhere). ECHO is a single-user, local-first,
unauthenticated application by design; `requested_by`/role fields are self-reported strings, not
cryptographic identities. The real security boundary against a model-driven bypass is **not** the
`requested_by in {"founder", ...}` string check — it's that **no Supervised Maintenance function is
registered in `action_system.py` at all** (confirmed: zero matches for any `maintenance_*` symbol in
that file, and zero `category="governance"` maintenance entries), so the model has **no tool-calling
path to this router whatsoever**. Every existing governance action (propose/sandbox/approve/deploy/
rollback) is registered for Part 2D's own router, not this one. This is the real, structural boundary
this test pass verifies — not merely the self-reported role string.

**Maintenance permissions** (`permission_center.py`): `supervised_maintenance_register_repository`
(ask_first/high), `supervised_maintenance_read_code` (allowed/low),
`supervised_maintenance_create_analysis` (allowed/low). `register_repository()` additionally hard-gates
on `requested_by in {founder, guardian_a, guardian_b, guardian_c, verifier}` independent of the
permission-center check.

**Database tables**: `approved_repositories` (single-repository-in-practice: `register_repository()`
unconditionally resolves to `self_improvement_verify.REPO_ROOT`, never a client path, and rejects a
second registration against the same root), `maintenance_analyses`, `maintenance_findings`,
`maintenance_audit_events`. All four confirmed present in `models.py` at their expected class
definitions. `maintenance_audit_events` has **no hash-chaining column** — confirmed, matches the
already-documented honest limitation.

**Protected paths/symbols** (`self_modification_governance.py`, confirmed current list via source
read): 22 whole-file protected paths including all 5 Supervised Maintenance service/router files and
both `docs/supervised_maintenance/{protected_scope,policy}.md`; 13 protected-symbol patterns including
the 5 Supervised-Maintenance-specific additions (scope validator, compliance service, policy loader,
code-access containment, audit append).

**Sandbox / command allowlist**: reused unmodified from Part 2D — `self_modification_sandbox.py` +
`selfmod_runner.py` (fixed, no-shell command dispatcher) + `selfmod.Dockerfile`. **Docker is actually
available in this environment** (`docker --version` → 29.5.2) and the `echo-selfmod-sandbox:local`
image already exists locally — meaning a genuine, non-mocked sandbox execution is possible in this
pass. Confirmed by reading `test_layer3a_selfmod_sandbox.py`: even Part 2D's own dedicated sandbox
tests only mock `subprocess.run` for the Docker check — **no test in this codebase's history has ever
run a real Docker container for this feature.** This pass adds one.

**Test-evidence storage**: `VerificationRun` (Part 2D), unmodified, reused.

**Approval binding**: `HumanApproval` (Part 2D), unmodified — 6-field fingerprint check
(hash/base-commit/target/scope/scope-policy-fingerprint/constitution-fingerprint), plus the typed
`APPROVE EXACT PATCH <hash>` acknowledgement phrase for every decision (confirmed in Part 2D's own
report as stricter than its own original architecture doc).

**Audit events**: dedicated `MaintenanceAuditEvent` table, separate from `SelfModificationAuditEvent`
per the one-table-per-subsystem convention.

**Kill switch**: `SelfModificationKillSwitch` (Part 2D), unmodified — governs everything downstream of
proposal generation. Nothing upstream (registration/read/analysis) has its own kill switch; it relies
on the independent feature flags instead (confirmed intentional per `operator_guide.md` §5).

**Local commit controller**: `self_modification_governance.deploy()` +
`self_modification_sandbox.deploy_to_local_branch()`, confirmed by Phase 7's own test and source
inspection to be completely `analysis_id`-agnostic.

**Frontend Governance Center integration**: `SupervisedMaintenanceView.tsx`, mounted at Sidebar →
Governance → Supervised Maintenance, gated by `supervised_maintenance_frontend_enabled` (currently
`False`, so the live UI should show the disabled banner and lock every control).

## 2. Genuine gaps this pass closes (not covered by the existing 51 tests)

1. **Zero HTTP-layer tests.** All 51 existing tests call service functions directly
   (`maintenance_policy.register_repository(db, ...)`), never through FastAPI's `TestClient` against
   the actual router — meaning request/response schema validation, HTTP status-code mapping, and the
   router's own error-translation (`_run()`/`_POLICY_ERROR_STATUS` etc.) have never been exercised.
2. **Zero real Docker sandbox execution** for an analysis-originated proposal (see above).
3. **Zero live browser verification** of the actual Governance Center page — only `npm run build`/
   `vitest` component tests exist; nobody has opened the page in a real browser since it was built.
4. **A few adversarial `CodeAccessService` path-encoding cases** Phase 8 didn't cover: URL-encoded
   traversal, double-encoded traversal, Unicode-lookalike path segments.
5. **An explicit regression test pinning "no Action System exposure"** — the actual security boundary
   identified above — rather than leaving it as an untested architectural claim.

## 3. Test categories and plan

| # | Category | Components | Method |
|---|---|---|---|
| A | HTTP API layer | `routers/supervised_maintenance.py` via `TestClient` | New test file, real FastAPI app, temp SQLite DB (existing `conftest.py` fixture) |
| B | Path containment (new cases) | `maintenance_code_access._validate_and_resolve()` | Extend `test_supervised_maintenance_adversarial.py` |
| C | Action System non-exposure | `action_system.py` | New regression test asserting no `maintenance_*`/`supervised_*` action is registered |
| D | Real Docker sandbox | `self_modification_sandbox.run_patch_in_sandbox()`, real container | Live script, not pytest (needs the real Docker daemon + several seconds runtime) |
| E | Live Governance Center UI | `SupervisedMaintenanceView.tsx` | Browser pane against real dev servers, disabled-state (matches current flag state) |
| F | Full regression baseline | Whole backend/frontend suite | Re-run after adding new tests |

## 4. Fixtures

Reuses the established convention from Phases 2/8: fixture files are written directly under
`backend/tests/` (the real, approved repository — since `register_repository()` structurally cannot
point anywhere else) with a `_` prefix and removed in a `finally` block. No separate synthetic
repository is created, because the system's actual design makes that architecturally impossible to
register as a *second* approved repository — this is itself a safety property worth restating, not a
test-plan limitation.

For the live Docker sandbox test (item D), a disposable temp directory under the OS temp folder is used
as the sandbox target (matching `self_modification_sandbox.py`'s own git-worktree-per-run design) —
never the live primary working tree.

## 5. Safety precautions

- No `.env` created/edited; flags stay at their safe defaults throughout except where a test explicitly
  and temporarily monkeypatches `get_settings()` in-process (existing, established pattern — never a
  real file write).
- The live Docker sandbox test uses a `sandbox_verify`-mode analysis-originated proposal with a
  trivial, safe patch (adds a comment to a test fixture file) — never a hostile patch, since the
  hostile-patch rejection path is already proven (deterministic scope check blocks it before sandbox
  ever starts, per Phase 4-5's own test) and doesn't need Docker to prove.
- No `git push`, no `git merge`, no write to `origin`.
- Live browser test only reads the page in its default (disabled) state — no repository registration
  is performed against the real dev database unless explicitly needed to demonstrate the enabled-state
  UI, in which case it is immediately deregistered/cleaned up afterward.

## 6. Cleanup procedure

- All fixture files removed in `finally` blocks (pytest tests) or explicit cleanup steps (live script).
- Any `ApprovedRepository` row created against the dev database during live testing is deleted before
  this pass ends.
- Docker sandbox temp directories/containers removed by `self_modification_sandbox.py`'s own cleanup
  path (already exercised and audited by Part 2D's tests) — confirmed removed after the live run.
- Dev servers (backend/frontend) stopped after the live UI check if they were started solely for this
  pass.

## 7. Stop conditions

Per the test mandate: stop further risky testing immediately if any of the following is found —
live repository modified without approval, secret exposed, self-approval possible, a protected
component editable, arbitrary shell available, sandbox escape, push/deploy possible, falsified
evidence accepted, stale approval accepted, kill switch bypassed. None expected given the existing
51 tests' coverage; this pass exists to independently confirm that, not because a specific defect is
suspected.
