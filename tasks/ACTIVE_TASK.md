# ECHO Supervised Maintenance Workspace v1

Status: **In progress — Phases 1-6 complete and pushed, Phase 7 (local commit reuse confirmation) next**
Task ID: `ECHO-SUPMAINT-001`
Owner: `User`
Implementer: `Claude Code`
Reviewer: `Not yet assigned` (single-agent implementation; no concurrent Codex work on this task)
Base branch: `master`
Base commit: `c313c47c` (Layer 3A Part 2D self-modification, prior task)
Implementation branch: `master`
Implementation worktree: `C:\Users\newte\echo v1`
Implementation commits so far:
- `092b002e` — Phase 1: repository audit, architecture, threat model, protected scope docs
- `2da471ea` — Phase 2: Analyse-Only (CodeAccessService, ApprovedRepository, analyses)
- `486bb6f7` — Phase 3: proposal generation (thin wrapper over Part 2D)
- `32eb69ed` — Phase 4-5: validation + sandbox pipeline reuse confirmation
- `a87fc44a` — Phase 6: human review frontend + repository/analysis pages

## Objective

Add a read-only-first code analysis → structured findings → proposal pipeline that Echo can use to
inspect its own approved repository, record findings, and hand off an exact patch proposal — while
reusing the existing Layer 3A Part 2D self-modification proposal/sandbox/approval/deployment/rollback
system rather than building a second parallel governance stack. Non-negotiable invariants
(MAINTENANCE-001 through MAINTENANCE-010, see `docs/supervised_maintenance/architecture.md` §1):
human authority stays external, no self-approval, no live repository editing by Echo, exact approval
binding, protected core systems (including this policy itself), no authority expansion, evidence
independence, failure transparency, local-first privacy, no hidden chain-of-thought exposure.

## User outcome

The Founder can register their own repository (never an arbitrary path — always this backend's own
running codebase), browse/search it read-only, run a structured analysis, review findings, and
optionally generate a real Self-Modification proposal from that analysis — continuing its review,
sandbox verification, and approval on the existing Self-Modification page. Nothing here can approve,
merge, or deploy on its own.

## Scope

### In scope

- A `CodeAccessService` read-only containment pipeline (canonicalization, repository-root
  containment, scope allowlist, secret-filename/content rejection, binary/size limits).
- `ApprovedRepository` (always registers `REPO_ROOT`, never a client-supplied path),
  `MaintenanceAnalysis`, `MaintenanceFinding`, `MaintenanceAuditEvent` domain model.
- A capability-mode ladder (`disabled` → `analyse_only` → `propose_only` → `sandbox_verify` →
  `human_approved_local_commit`) layered on top of the existing independent Part 2D feature flags.
- A thin `MaintenanceProposalService` wrapper that calls the existing
  `self_modification_governance.create_proposal()`/`submit_revision()` unmodified, tagging the
  resulting proposal with `analysis_id`.
- A human review frontend (repository registration, capability-mode controls, analysis lifecycle,
  read-only code browsing, findings, proposal generation, audit trail).
- A new vitest + Testing Library frontend test framework (none existed on `master`).

### Out of scope

- A second Permission Center, Audit system, Action System, Feature Flag service, or Governance
  Center — explicitly forbidden by the milestone spec. Every reused primitive (scope validation, risk
  classification, sandbox, approval, deployment, rollback, audit pattern) must stay a single system.
- Automatic filesystem scanning or client-supplied repository paths.
- Any change to `VALUE_INVARIANTS`, Guardian Council thresholds, or established identity/moral-compass
  behavior.

## Required context

- `AGENTS.md`, `CLAUDE.md`, `tasks/completed/ECHO-3A-2D-20260719-051354.md` (prior Part 2D task, now
  archived — this task builds directly on its proposal/sandbox/approval/deployment pipeline).
- `docs/supervised_maintenance/repository_audit.md`, `architecture.md`, `threat_model.md`,
  `protected_scope.md` (this task's own Phase 1 deliverables).
- `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md` and `_REPORT.md`.

## Acceptance criteria

- [x] Phase 1: repository audit, architecture, threat model, protected scope docs complete before any
      functional code edit.
- [x] Phase 2: `CodeAccessService` containment pipeline, `ApprovedRepository`/`MaintenanceAnalysis`/
      `MaintenanceFinding`/`MaintenanceAuditEvent` models, registration/policy/analysis services, API
      routes, 31 adversarial/functional tests passing.
- [x] Phase 3: `MaintenanceProposalService.create_proposal_from_analysis()` proven to route through
      the unmodified Part 2D `create_proposal()`/`submit_revision()` — including proof that a patch
      touching a protected file still fails scope/compliance checks regardless of analysis origin.
- [x] Phase 4-5: full 7-stage pipeline (scope check → compliance check → sandbox → approval → deploy
      → rollback) proven to work unmodified for an analysis-originated proposal; critical-risk patches
      still blocked before sandbox regardless of origin.
- [x] Phase 6: human review frontend gated behind `supervised_maintenance_frontend_enabled`, wired
      into Sidebar/App under Governance; frontend test framework introduced with passing tests for the
      disabled state, empty-repository state, error surfacing, and repository listing.
- [x] Phase 7: confirmed `LocalCommitController`/`deploy()` and `RollbackRecordService`/`rollback()`
      need no changes for analysis-originated proposals — source inspection shows zero `analysis_id`
      references anywhere in `self_modification_sandbox.py`/`deploy()`/`rollback()`, and
      `test_supervised_maintenance_local_commit_reuse.py` proves an analysis-originated and a
      directly-created proposal deploy/roll back identically. See architecture.md §11.
- [ ] Phase 8: hardening pass — adversarial tests for the genuinely-new `CodeAccessService` attack
      surface (path traversal/symlink/junction/secret-file/prompt-injection per
      `docs/supervised_maintenance/threat_model.md`), remaining operator/security docs, final
      Green/Yellow/Red report.

## Verification commands

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\frontend
npm run typecheck
npm run build
npm run test
```

## Risks and safeguards

- Every new governance file is added to `self_modification_governance.PROTECTED_PATHS`/
  `PROTECTED_SYMBOL_PATTERNS` as it's created, so this workflow can never modify its own governance
  code (including this task file's referenced docs).
- `register_repository()` never accepts a client-supplied filesystem path — it always registers
  `self_improvement_verify.REPO_ROOT`, eliminating path-injection as an attack surface by
  construction rather than by validation.
- `CodeAccessService` reuses Part 2D's existing secret-content regex and canonical-path helpers
  unmodified rather than re-implementing them.

## Allowed paths

- `backend/app/models.py`, `schemas.py`, `db.py`, `config.py`, `main.py`
- `backend/app/core/feature_flags.py`
- `backend/app/services/self_modification_governance.py` (additive: `PROTECTED_PATHS`,
  `PROTECTED_SYMBOL_PATTERNS`, optional `analysis_id` parameter only)
- `backend/app/services/maintenance_code_access.py`, `maintenance_policy.py`,
  `maintenance_analysis.py`, `maintenance_proposal.py`
- `backend/app/routers/supervised_maintenance.py`
- `backend/tests/test_supervised_maintenance*.py`
- `frontend/src/api/client.ts`, `App.tsx`, `components/Sidebar.tsx`
- `frontend/src/components/supervised-maintenance/`
- `frontend/package.json`, `vite.config.ts`, `src/test-setup.ts`
- `docs/supervised_maintenance/`
- `PROGRESS.md`, `tasks/ACTIVE_TASK.md`

## Agent implementation notes

Confirmed before product edits: no concurrent Codex editing on this working tree for this task;
each phase's docs/tests/build verification passes before that phase is committed and pushed, per the
user's standing "begin each phase after one by one, commit and push as required" instruction.

## Implementation handoff (through Phase 6)

Behavior changed: added a fully-flagged-off (`supervised_maintenance_enabled` and friends all default
`False`) read-only code analysis and proposal-generation workspace at
`/api/governance/supervised-maintenance/*`, plus a review frontend gated behind
`supervised_maintenance_frontend_enabled`. Nothing about existing chat/action/permission/self-
modification behavior changes while these flags are off.

Migrations: schema v10→v11 (Phase 2: `ApprovedRepository`, `MaintenanceAnalysis`,
`MaintenanceFinding`, `MaintenanceAuditEvent`), v11→v12 (Phase 3: additive `analysis_id` column on
`code_modification_proposals`). Both additive only, no destructive change.

Tests executed and results: full backend suite `1627 passed, 0 failed` (0:13:50) after Phase 6;
frontend `npm run typecheck`/`npm run build` clean; `npm run test` 4/4 passed (new vitest framework).

Known limitations carried into Phase 7-8: no tamper-evident audit hash-chaining on
`MaintenanceAuditEvent` (same limitation as Part 2D's `SelfModificationAuditEvent`, not newly
introduced); `CodeAccessService`'s adversarial test coverage (traversal/symlink/junction/prompt-
injection) exists for Phase 2's basic cases but the full 40-item adversarial catalog from the
milestone's own §42 is deferred to Phase 8; `approve_revision()` requires the typed
`APPROVE EXACT PATCH <hash>` phrase for all decisions (a Codex Part 2D hardening addition slightly
beyond what `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md` originally documented — worth a
small doc correction during Phase 8's final report).

Areas the next reviewer should inspect first: `maintenance_code_access.py`'s `_in_scope()` trailing-
slash matching logic (fixed once already during Phase 2 — worth an extra adversarial case in Phase 8);
whether `MaintenanceProposalService` ever needs its own capability-mode check duplicated against
`ApprovedRepository.capability_mode` versus trusting the router layer; and whether Phase 7 surfaces any
gap in `deploy()`'s re-verification chain specific to analysis-originated proposals (expected: no, but
not yet formally re-confirmed as its own phase).
