# ECHO Supervised Maintenance Workspace v1 — Phase 1 Repository Audit

**Status: read-only audit. No application code was modified to produce this document.**

This audit grounds the Supervised Maintenance Workspace design in what actually exists in the
repository today, per the milestone's own instruction: "Connect, expose, measure and harden existing
systems. Do not create a second Permission Center, second Audit system, second Action System, second
Feature Flag service or second Governance Center." The single most important finding of this audit is
that **Layer 3A Part 2D ("Supervised Self-Modification," committed `c313c47c`) already implements
almost the entire back two-thirds of what this milestone asks for** — a fail-closed proposal → scope
validation → constitutional check → sandbox → human approval → local-branch-only commit → rollback →
kill-switch → audit pipeline. This audit and the accompanying architecture doc treat that system as
the trusted target to *extend*, not a parallel system to duplicate.

## 1. Existing relevant systems

| System | File(s) | Relevance |
|---|---|---|
| Supervised self-modification pipeline | `backend/app/services/self_modification_governance.py`, `self_modification_sandbox.py`, `backend/app/routers/self_modification.py`, `backend/app/models.py` (11 tables) | The proposal/revision/scope-check/compliance-check/sandbox/approval/deploy/rollback/audit/kill-switch machinery this milestone's sections 6, 13–35 describe already exists here. |
| Constitution + Guardian Council | `backend/app/constitution.py`, `backend/app/council.py` | Ranked `CORE_VALUES`, 5 immutable `VALUE_INVARIANTS`, deterministic `classify_amendment_text()`, real quorum voting. Already reused (unmodified) by the self-modification pipeline's compliance check. |
| Permission Center | `backend/app/services/permission_center.py` | Single shared local-device `allowed`/`ask_first`/`disabled` policy, keyed by string. Already extended with 6 `self_modification_*` keys. |
| Action System | `backend/app/services/action_system.py` | `ActionSpec`/`ACTIONS` registry with a `pending → approve_run()/cancel_run() → running → completed/failed` resumable lifecycle. Already extended with 5 `governance`-category actions that delegate to the self-modification service. |
| Audit trail (subsystem-scoped, not consolidated) | `SelfModificationAuditEvent` (self-modification), `ActionRun`/`ToolRun` (actions/tools), `MemoryConsolidationEvent` (memory) | **No consolidated, general-purpose audit table exists anywhere in this codebase, and no hash-chaining exists anywhere** (confirmed by a fresh repo-wide grep for `hash_chain`/`previous_hash`/`chain_hash` — zero hits). This is a real, repeated, honestly-documented gap. |
| Feature flags | `backend/app/config.py` (plain `Settings` booleans), `backend/app/core/feature_flags.py` (`list_feature_flags()` registry/metadata layer) | Self-modification's 4 flags (all default off) already follow this exact pattern. |
| Sandbox / process isolation | `backend/app/services/self_modification_sandbox.py`, `backend/selfmod_runner.py`, `backend/selfmod.Dockerfile` | Git-worktree source isolation + a real Docker execution boundary (`--network none --cap-drop ALL --read-only --security-opt no-new-privileges:true --pids-limit --memory --cpus`, non-root image user, a fixed no-shell command dispatcher that reconstructs its environment from scratch). This **is** the disposable sandbox this milestone's sections 21–24 ask for; it does not need to be rebuilt. |
| "Governance Center" | *(does not exist as a named entity)* | Confirmed by a repo-wide grep for `Governance Center`/`GovernanceCenter` — zero hits. The closest existing analog is `Sidebar.tsx`'s `"Governance"` nav group (`constitution`, `amendments`, `self-modification`). This audit treats that nav group as the de facto Governance Center and recommends nesting Supervised Maintenance inside it, per the "do not create a separate competing application" instruction. |
| Git integration | `backend/app/self_improvement_verify.py` (read-only `git status`/`git diff`), `self_modification_sandbox.py` (`git worktree add/remove`, `git apply --check`, `git commit`, `git branch -D`) | No `GitPython`/Docker-Python-SDK dependency anywhere (confirmed via `backend/requirements.txt` grep) — every Git/Docker operation goes through `subprocess.run()` with explicit argv lists, never `shell=True`. This is the established, safe convention to keep following. |
| Local-only / provider routing | `backend/app/router.py`, `backend/app/providers/` | Existing local-first/cloud-fallback provider routing (`cloud_api_use` permission key, default `disabled`) is the precedent for this milestone's §38 "default to local-only models, require explicit permission before cloud disclosure" requirement. |
| Secret redaction | `backend/app/core/logging.py` (`RedactingFilter`, `_REDACTION_PATTERNS`), `self_modification_governance.py` (`_LIKELY_SECRET_PATTERNS`, `contains_likely_secret()`) | Two existing, complementary layers: log-line redaction (applied to rendered messages) and patch-content secret scanning (applied before a revision is even stored). Both are reusable/extensible rather than needing reinvention. |
| Role/capability labels | `frontend/src/state/roleContext.tsx` (`useRole()`, `ROLE_LABELS`) | Same simulated-role pattern (`founder`/`guardian_a`/`guardian_b`/`guardian_c`/`verifier`) used by Guardian Council and the self-modification approval gateway. This app has no real multi-user authentication anywhere (confirmed in the Part 2D audit and unchanged since). |
| Database repositories/migrations | `backend/app/db.py` (`init_db()`, `_ensure_column()`, `CURRENT_SCHEMA_VERSION`, currently **10**) | No Alembic; additive-only convention (`Base.metadata.create_all()` for new tables, `_ensure_column()` for new columns on existing tables, a hand-bumped version int with a dated comment block). |
| Structured events / error handling | `backend/app/core/errors.py` (`ApiError`, `ErrorCategory`, `RequestIDMiddleware`), `backend/app/core/logging.py` (`log_event()`) | Reusable typed-exception → HTTP-status translation pattern, already followed by `routers/self_modification.py`'s `_ERROR_STATUS` dict. |
| Frontend routing / API client | `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx` (`View` union, `NAV_ITEMS`), `frontend/src/api/client.ts` (`request()`/`requestMultipart()` helpers, typed interfaces per endpoint) | Established, consistent pattern for adding a new page: add to the `View` union, add a nav entry, add a component, add typed `client.ts` functions. |
| Frontend state management | Local `useState`/`useEffect` per page (no global store), `state/roleContext.tsx`, `state/testerContext.tsx`, `state/conversationsContext.tsx` | No Redux/Zustand/etc. — every existing page (including `SelfModificationView.tsx`) manages its own local state and refetches on action completion. |
| Diff viewers / confirmation interfaces | `SelfModificationView.tsx`'s `RevisionReview` component (raw `<pre>` diff render, typed exact-hash confirmation input, `window.confirm()` for destructive actions) | Directly reusable pattern for Supervised Maintenance's proposal review UI — no dedicated diff-viewer library exists or is needed. |
| Backend tests | `backend/tests/test_layer3a_selfmod_{governance,sandbox,api}.py` (73 tests), `backend/tests/conftest.py` (`db_session` isolated-SQLite fixture) | Direct template for Supervised Maintenance's own test suite; the sandbox tests already establish the "always pass `repo_root=tmp_path`, never touch the real repo" safety convention this milestone's adversarial tests (§42) require. |
| Frontend tests | *(none)* | **Gap.** `frontend/package.json` has no test runner (`vitest`, `@testing-library/*`, etc.) on `master`. A `vitest`-based test setup exists on an **unmerged** sibling branch (`add/tests-ci-pwa-capacitor`, `git branch -vv`), not on `master`. Adding frontend tests for this milestone means introducing a test framework as a real, explicit dependency addition — not just writing test files. |
| CI | `.github/workflows/ci.yml` | Exists, runs backend pytest+ruff, but is **explicitly not pushed to GitHub** (documented in its own header comment — `d23r2/echo-v1` is public, nothing gets pushed without separate explicit approval). No CI-based deployment workflow exists to worry about protecting further. |
| Git hooks | `.git/hooks/` | Only the default Git-shipped `.sample` files — no custom hooks installed. Nothing to "disable" for sandbox safety (§31) because nothing custom exists; this is a non-issue rather than a gap. |

## 2. Exact files and symbols found (Supervised Self-Modification, the primary reuse target)

See `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md` for the full domain model. Symbols this
milestone's design must integrate with directly:

- `self_modification_governance.create_proposal()`, `submit_revision()`, `run_scope_check()`,
  `run_compliance_check()`, `mark_ready_for_sandbox()`, `run_sandbox()`, `request_review()`,
  `approve_revision()`, `deploy()`, `rollback()`, `cancel_proposal()`, `get_health()`.
- `self_modification_governance.classify_scope()`, `PROTECTED_PATHS`, `PROTECTED_PATH_PREFIXES`,
  `ALLOWED_PATH_PREFIXES`, `PROTECTED_SYMBOL_PATTERNS`, `DEPENDENCY_PATHS`,
  `scope_policy_fingerprint()`, `constitution_fingerprint()`, `compute_patch_hash()`.
- `self_modification_governance.is_kill_switch_active()`, `activate_kill_switch()`,
  `reset_kill_switch()`.
- `self_modification_sandbox.run_patch_in_sandbox()`, `deploy_to_local_branch()`,
  `rollback_local_branch()`, `get_sandbox_capabilities()`.
- Models: `CodeModificationProposal`, `CodeModificationRevision`, `ModificationImpactAssessment`,
  `ConstitutionalComplianceCheck`, `SandboxExecution`, `VerificationRun`, `HumanApproval`,
  `DeploymentAttempt`, `RollbackEvent`, `SelfModificationAuditEvent`, `SelfModificationKillSwitch`.

## 3. Existing APIs

`/api/self-modification/*` (full list in `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`
§10) — proposals, revisions, checks, sandbox, approvals, deployments, rollback, audit, policy,
health, kill-switch. `/api/permissions`, `/api/actions`, `/api/constitution`, `/api/amendments`,
`/api/system/*` (health/status/diagnostics/features/metrics/version).

## 4. Existing permissions

`permission_center.DEFAULT_PERMISSIONS` already has `self_modification_propose` (`allowed`/`low`),
`self_modification_sandbox_run` (`ask_first`/`high`), `self_modification_approve`
(`ask_first`/`high`), `self_modification_deploy` (`disabled`/`destructive`),
`self_modification_rollback` (`allowed`/`high`), `self_modification_kill_switch`
(`ask_first`/`destructive`). Analogous `supervised_maintenance_*` keys will follow the identical
`{key, level, risk_level, description}` shape.

## 5. Existing audit controls

Subsystem-scoped only (§1 table). `SelfModificationAuditEvent` is the closest precedent: pre-sanitized
`safe_context_json`, `_require_audit_available()` fail-closed check before every mutating operation.
**No hash-chaining exists.** If this milestone's `MaintenanceAuditService` (§6, §34) is to have hash
chaining "when compatible with the existing audit architecture," that compatibility does not yet
exist — it would be new infrastructure, honestly documented as new rather than "reused."

## 6. Existing action-confirmation workflow

`action_system.run_action()`'s `pending → approve_run()/cancel_run() → running → completed/failed`
resumable state machine (not `tool_registry`'s terminal-`blocked` pattern) is the established idiom
for "needs a human in the loop." `self_modification_governance`'s proposal lifecycle already
generalizes this into a much richer multi-stage state machine matching almost exactly what this
milestone's §15 proposal state machine specifies.

## 7. Existing sandbox / process-isolation capabilities

Real, working, tested: git-worktree source isolation + Docker execution isolation (§1 table). Resource
limits (`--pids-limit 256 --memory 2g --cpus 2`), network isolation (`--network none`, verified via a
capability check, not just declared), non-root execution, a fixed no-shell command dispatcher
(`selfmod_runner.py`) accepting only a symbolic check name — this already satisfies essentially all of
this milestone's §21–23 requirements. The sandbox currently runs a **fixed set of four checks**
(`backend-pytest`, `backend-ruff`, `frontend-typecheck`, `frontend-build`); this milestone's §39
`run_backend_api_tests`/`run_security_scan`/`run_migration_validation`/`run_backend_startup_check`
names imply a few additional check types would need to be added to `selfmod_runner.py`'s fixed
`COMMANDS` dict (additive, not a redesign).

## 8. Existing rollback support

`RollbackEvent`, `self_modification_sandbox.rollback_local_branch()` (removes the deployment worktree,
force-deletes the branch — safe by construction since nothing is ever merged). This milestone's §32
"prefer `git revert`, never destructive reset as the normal method" is a *behavioral* difference worth
noting: the existing rollback discards an unmerged local branch entirely (nothing to "revert" from,
since it was never merged into anything); Supervised Maintenance's proposals, if ever taken further
than local-branch-only, would need the same discard-the-branch model, not a `git revert` model — there
is no merge step anywhere in this system for `git revert` to apply to.

## 9. Existing Governance Center integration points

None by that literal name (§1). The `Sidebar.tsx` `"Governance"` nav group (`constitution`,
`amendments`, `self-modification`) is the de facto integration point.

## 10. Existing Git utilities

`self_modification_sandbox.py`'s `_git()` helper (explicit argv, never shell, `SandboxError` on
failure), `_create_worktree()`, `_remove_worktree()`, `current_head()`. `self_improvement_verify.py`'s
`_run()` (bounded timeout, truncated captured output, missing-tool degrades to `"unavailable"` never a
crash) is the sibling convention for non-Git subprocess commands. Both are directly reusable by
`CodeAccessService.inspect_git_status/diff/commit()`.

## 11. Existing frontend components

`SelfModificationView.tsx` (§1 table) is the direct template: gate every control behind a frontend
feature flag, typed exact-hash confirmation, `window.confirm()` for destructive actions, honest
simulated-role copy, append-only audit-trail panel.

## 12. Existing tests

`backend/tests/test_layer3a_selfmod_{governance,sandbox,api}.py` (73 tests) — direct template,
including the critical safety convention (§7 above) that sandbox tests always pass an explicit
`repo_root=tmp_path` fixture and never let a test reach the real repository's git state. No frontend
tests exist anywhere in the repo on `master` (§1 gap).

## 13. Missing capabilities (genuine gaps this milestone must fill)

1. **Read-only repository/code access with path containment, secret-content scanning, and
   symlink/junction/traversal rejection** (`CodeAccessService`, §8–10) — self-modification only ever
   reads a *patch the caller supplies*; nothing today lets Echo browse/search/read arbitrary
   repository files under a governed policy.
2. **Structured pre-patch analysis / findings reports** (`MaintenanceAnalysisService`, §14) — nothing
   today produces a findings report *before* a patch exists; self-modification starts at "here is a
   patch," not "here is what I found wrong."
3. **Approved-repository registration policy** (§7) — self-modification implicitly operates on "the
   repository this backend process is running from" (`self_improvement_verify.REPO_ROOT`); there is no
   explicit, owner-controlled, single-approved-repository record.
4. **A formal capability-mode enum** (`DISABLED`/`ANALYSE_ONLY`/`PROPOSE_ONLY`/`SANDBOX_VERIFY`/
   `HUMAN_APPROVED_LOCAL_COMMIT`, §5) layered on top of feature flags — self-modification has 4
   independent boolean flags with an implied dependency order, not a single named-mode enum.
5. **Frontend test framework** (§1 gap) — needed for this milestone's §43 frontend test requirements.
6. **Additional fixed sandbox check types** (`run_security_scan`, `run_migration_validation`,
   `run_backend_startup_check`, `run_backend_api_tests` as distinct from `backend-pytest`) — additive
   entries to `selfmod_runner.py`'s `COMMANDS` dict.
7. **Prompt-injection-specific test fixtures** treating repository content as untrusted (§10, §42) —
   self-modification's tests cover secret/test-weakening/protected-path detection but do not
   specifically test "a code comment tells the model to ignore policy."

## 14. Security conflicts

None identified between this milestone's requirements and the existing self-modification system's
design — they are compatible by construction (this milestone's own component list in §6 maps almost
1:1 onto self-modification's existing functions; see the architecture doc §2 for the explicit mapping
table). The one point requiring a deliberate decision: this milestone's §26 says "HIGH RISK: do not
permit local commit in version 1 unless existing Guardian Council policy already supports elevated
approval" — self-modification's existing `deploy()` **already** blocks `high`/`critical`-risk
deployment unconditionally ("Echo has no authenticated second-human approval boundary"). This is
already the more conservative of the two stances; Supervised Maintenance should inherit it unchanged
rather than re-deciding it.

## 15. Possible duplication risks

Building a second `CodeModificationProposal`-shaped table, a second scope validator, a second
constitutional-compliance checker, a second sandbox controller, a second approval gateway, a second
local-commit controller, or a second kill switch would all directly violate this milestone's own §2
instruction and would fragment governance state across two parallel systems that a human reviewer
would then have to reconcile. The architecture doc (§2) makes the explicit recommendation: Supervised
Maintenance is a **read-only analysis front-end that produces `self_modification_governance`
proposals**, not a parallel pipeline.

## 16. Protected files

See `docs/supervised_maintenance/protected_scope.md` for the full, authoritative list — it is the
Part 2D `PROTECTED_PATHS` set **plus** the Supervised Maintenance system's own new files (self-
protecting, same pattern Part 2D used for itself) **plus** `docs/supervised_maintenance/policy.md`
once it exists (the maintenance policy configuration itself must not be editable through the
workflow it governs).

## 17. Protected symbols

See `protected_scope.md`. The existing `PROTECTED_SYMBOL_PATTERNS` set is extended with symbols this
milestone names explicitly: `ScopeValidator`/`classify_scope`, `ConstitutionalComplianceService`/
`run_compliance_check`, approval-gateway functions, `MaintenancePolicyService`, and the new
`CodeAccessService`'s own path-containment checks (so a "helpful" patch can never weaken the
containment logic that gates read access).

## 18. Proposed additions

- `ApprovedRepository` model + `MaintenancePolicyService` (repository registration, §7).
- `MaintenanceAnalysis`/`MaintenanceFinding` models + `MaintenanceAnalysisService` (§14, structured
  findings, verified/inferred/hypothesis/unknown per §14).
- `CodeAccessService` (§8) — typed read-only operations with the full containment/secret-scan
  pipeline (§8–10).
- `MaintenanceProposalService` — a thin service that turns an accepted analysis into a
  `self_modification_governance.create_proposal()` + `submit_revision()` call, tagging the resulting
  proposal with its originating `analysis_id` (see architecture doc for the exact additive field).
- A capability-mode enum/service layered on the existing feature-flag pattern.
- New `supervised_maintenance_*` permission keys, `governance`-category `ActionSpec` entries (for the
  read-only/analysis operations only — proposal creation already routes through the existing
  self-modification action entries), and `/api/governance/supervised-maintenance/*` routes.
- `frontend/src/components/governance/SupervisedMaintenanceView.tsx` (or nested under the existing
  Governance nav group) reusing `SelfModificationView.tsx`'s established patterns.
- A frontend test framework (`vitest` + `@testing-library/react`), since none exists on `master`.

## 19. Proposed modifications (additive only)

- `self_modification_governance.py`: add an optional `analysis_id` field to `CodeModificationProposal`
  (additive column, schema v10→v11) so a proposal can be traced back to the analysis that produced it;
  extend `PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS` to cover the new Supervised Maintenance files.
- `self_modification_sandbox.py` / `selfmod_runner.py`: add new fixed check names to the `COMMANDS`
  dict (additive) if this milestone's broader test/security-scan/migration-validation check types are
  needed beyond the current four.
- `permission_center.DEFAULT_PERMISSIONS`: add `supervised_maintenance_*` keys.
- `action_system.ACTIONS`: add `governance`-category entries for read-only analysis operations only.
- `Sidebar.tsx`/`App.tsx`: add a nav entry and route, same pattern as Part 2D's own addition.
- `backend/db.py`: schema v10→v11, additive tables/columns only.

## 20. Files that should remain unchanged

`constitution.py`, `council.py`, `models.py`'s existing table definitions (only additive new tables/
columns), `permission_center.py`'s `check()`/`set_permission_level()` logic, `action_system.py`'s
`run_action()`/`approve_run()`/`_needs_confirmation()` logic, `self_modification_governance.py`'s core
lifecycle functions and safety checks (only additive extension), `self_modification_sandbox.py`'s
isolation mechanics, `core/logging.py`, `core/errors.py`, `db.py`'s migration *mechanism* (only its
data, additively).

## 21. Migration requirements

One additive schema bump (v10→v11): new tables for `ApprovedRepository`/`MaintenanceAnalysis`/
`MaintenanceFinding` (+ any policy-config table, if not kept as Python constants like Part 2D's
protected-path lists), one additive `analysis_id` column on `code_modification_proposals`. No
destructive change to any existing table. Migration verification follows the exact pattern
`self_modification_governance_test.py`/`db.py`'s `_ensure_column()` idempotency already establishes.

## 22. Threat-model summary

See `docs/supervised_maintenance/threat_model.md` (full catalog). Headline point: most of the threats
this milestone's §41 asks about (self-approval, patch substitution, stale approval, protected-path/
symbol bypass, sandbox escape, secret leakage in the sandbox, kill-switch bypass, audit tampering) are
**already mitigated by the existing self-modification pipeline** and only need to be *verified to also
cover analysis-originated proposals*, not re-mitigated from scratch. The genuinely new threat surface
this milestone introduces is entirely in `CodeAccessService` (path traversal/symlink/junction escape,
secret-file access, prompt injection via repository content) — this is where the bulk of new adversarial
test coverage (§42) is actually needed.

## 23. Implementation sequence

Matches this milestone's own §45 phase list, adjusted for reuse: Phase 1 (this document + architecture
+ threat model + protected scope — **complete**), Phase 2 (`ApprovedRepository` + `CodeAccessService`
+ containment/secret-scan pipeline + `MaintenanceAnalysisService`, Analyse-Only mode), Phase 3
(`MaintenanceProposalService` wrapping the existing `self_modification_governance` proposal creation,
tagged with `analysis_id`), Phase 4 (confirm existing `classify_scope()`/`run_compliance_check()`
already satisfy this milestone's validation requirements for analysis-originated proposals — likely
no new validator code needed, just integration tests proving it), Phase 5 (confirm the existing sandbox
already satisfies isolation requirements; add new fixed check types only if genuinely needed), Phase 6
(frontend integration under the existing Governance nav group, plus introducing a frontend test
framework), Phase 7 (local commit — already exists via `deploy()`; confirm it needs no changes for
analysis-originated proposals), Phase 8 (hardening: the new adversarial tests genuinely needed are
almost entirely `CodeAccessService`-focused, per §22).

## 24. Stop conditions

Per this milestone's own §46, restated against the current codebase: **none currently apply.** ECHO
cannot approve its own proposal (`proposal.proposed_by == approver_role` rejected), cannot directly
modify the live repository (sandbox is a disposable worktree; deploy targets a fresh branch/worktree
only), no arbitrary shell execution exists anywhere in the self-modification/sandbox code path, path
containment for the *existing* patch-based workflow is enforced (`_is_unsafe_path`, protected-path/
symbol checks), secrets cannot enter model context via a submitted patch
(`contains_likely_secret()`), protected systems cannot be modified through the workflow
(`PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS`), the kill switch cannot be changed by the workflow
itself (it's in `PROTECTED_SYMBOL_PATTERNS`), backend permission enforcement exists server-side (not
frontend-only), and Constitution/Guardian Council authority is unweakened (reused unmodified). The one
requirement not yet satisfied — because it doesn't exist yet — is path containment for **read-only
repository browsing**, since that capability doesn't exist prior to this milestone; that is exactly
what Phase 2's `CodeAccessService` must deliver and adversarially test before Analyse-Only mode is
ever enabled.
