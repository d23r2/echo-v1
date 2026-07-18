# ECHO Supervised Maintenance Workspace v1 — Verification Report

**Final status: GREEN** — a read-only-first code analysis workspace that feeds real proposals into the
existing Layer 3A Part 2D self-modification pipeline is implemented, hardened, and verified. It builds
no second Permission Center, Audit system, Action System, Feature Flag service, or Governance Center —
the milestone's own central requirement — and every claim below is backed by a currently-passing test,
not a description of intended behavior.

## 1. Summary

Eight phases, each committed and pushed independently per the user's standing "begin each phase after
one by one, commit and push as required" instruction:

1. **Phase 1** — repository audit, architecture, threat model, protected scope docs, before any
   functional code.
2. **Phase 2 (Analyse Only)** — `CodeAccessService`'s containment pipeline, `ApprovedRepository`/
   `MaintenanceAnalysis`/`MaintenanceFinding`/`MaintenanceAuditEvent` models, registration/policy/
   analysis services, API routes.
3. **Phase 3 (Proposal generation)** — `MaintenanceProposalService`, a thin wrapper calling Part 2D's
   unmodified `create_proposal()`/`submit_revision()`, tagging results with `analysis_id`.
4. **Phase 4-5 (Validation + sandbox reuse)** — proved the full 7-stage pipeline (scope check →
   compliance check → sandbox → approval → deploy → rollback) needs zero special-casing for an
   analysis-originated proposal.
5. **Phase 6 (Human review frontend)** — `SupervisedMaintenanceView.tsx`, wired into Sidebar/App under
   Governance; introduced this repo's first frontend test framework (vitest + Testing Library).
6. **Phase 7 (Local commit reuse confirmation)** — confirmed, by source inspection and a dedicated
   comparative test, that `deploy()`/`rollback()`/`deploy_to_local_branch()` are completely
   analysis-agnostic.
7. **Phase 8 (Hardening + adversarial tests)** — found and fixed one real security gap, added 11
   adversarial tests, closed out `threat_model.md`'s test-coverage column with actual test names,
   wrote the missing `policy.md` a prior phase had already referenced, and wrote this report.

12 of the milestone's 14 requested components are reused unmodified or additively extended from Part
2D rather than rebuilt (`architecture.md` §2's component-reuse table); only `CodeAccessService`,
`MaintenanceAnalysisService`, and the thin `MaintenanceProposalService`/`MaintenancePolicyService`
wrappers are genuinely new.

## 2. The one real gap found (Phase 8), and its fix

Direct probing of this Windows machine's `pathlib` behavior — not just reading the code — found that
`_validate_and_resolve()` in `backend/app/services/maintenance_code_access.py` did **not** reject a
path containing a mid-string colon, e.g. `backend/requirements.txt:hidden_stream`. Both
`Path.resolve()` and `.relative_to(root)` silently accepted it:

```
unresolved: C:\...\backend\requirements.txt:hidden_stream
resolved:   C:\...\backend\requirements.txt:hidden_stream
relative_to succeeded: backend\requirements.txt:hidden_stream
```

On NTFS this syntax addresses an Alternate Data Stream — a second, hidden data stream attached to a
legitimate file. If such a stream existed on an approved file (e.g. left behind by a downloaded-file
"Zone.Identifier" marker, or planted by an attacker with any other write access to the repo), this
path would have passed containment, scope, and filename-pattern checks (none of the existing
`_SECRET_FILENAME_PATTERNS` match a colon-suffixed name) and reached the content-read stage.

**Fix**: `_validate_and_resolve()` now unconditionally rejects any candidate path containing a colon,
before resolution is attempted — no legitimate relative path component on any platform this app targets
contains a colon, so this is a plain reject, not an attempt to allowlist safe colon usage. Verified by
`test_read_file_rejects_alternate_data_stream_syntax` and
`test_list_repository_files_rejects_alternate_data_stream_subpath`.

## 3. Files created

Backend:
- `backend/app/services/maintenance_code_access.py` — `CodeAccessService` (Phase 2, hardened Phase 8).
- `backend/app/services/maintenance_policy.py` — `MaintenancePolicyService` (Phase 2).
- `backend/app/services/maintenance_analysis.py` — `MaintenanceAnalysisService` (Phase 2).
- `backend/app/services/maintenance_proposal.py` — `MaintenanceProposalService` (Phase 3).
- `backend/app/routers/supervised_maintenance.py` — `/api/governance/supervised-maintenance/*` (Phase 2).
- `backend/tests/test_supervised_maintenance.py` (31 tests, Phase 2), `test_supervised_maintenance_proposal.py`
  (6 tests, Phase 3), `test_supervised_maintenance_pipeline_reuse.py` (2 tests, Phase 4-5),
  `test_supervised_maintenance_local_commit_reuse.py` (1 test, Phase 7),
  `test_supervised_maintenance_adversarial.py` (11 tests, Phase 8) — **51 dedicated tests total.**

Frontend:
- `frontend/src/components/supervised-maintenance/SupervisedMaintenanceView.tsx` (Phase 6).
- `frontend/src/components/supervised-maintenance/SupervisedMaintenanceView.test.tsx` (Phase 6, 4 tests).
- `frontend/src/test-setup.ts` (Phase 6 — this repo's first frontend test setup file).

Docs:
- `docs/supervised_maintenance/repository_audit.md`, `architecture.md`, `threat_model.md`,
  `protected_scope.md` (Phase 1, updated through Phase 8).
- `docs/supervised_maintenance/policy.md`, `operator_guide.md` (Phase 8).
- This report.

## 4. Files modified

- `backend/app/models.py` — `ApprovedRepository`, `MaintenanceAnalysis`, `MaintenanceFinding`,
  `MaintenanceAuditEvent` (Phase 2); additive `analysis_id` column on `CodeModificationProposal`
  (Phase 3).
- `backend/app/db.py` — schema v10→v11 (Phase 2, 4 new tables), v11→v12 (Phase 3, 1 additive column).
- `backend/app/config.py` — 7 new settings, all default `False`/safe.
- `backend/app/core/feature_flags.py` — 4 new flag registry entries with dependency chains.
- `backend/app/services/permission_center.py` — 3 new permission keys.
- `backend/app/services/self_modification_governance.py` — additive `analysis_id` parameter on
  `create_proposal()` only; `PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS` extended with every new
  Supervised Maintenance file as it was created (self-protecting, matching Part 2D's own pattern).
- `backend/app/schemas.py` — new Literals and Read/Create schemas for the domain model above.
- `backend/app/main.py` — router registration.
- `frontend/src/api/client.ts` — 19 new functions + types (Phase 6).
- `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx` — new route/nav entry under Governance.
- `frontend/package.json`, `vite.config.ts` — vitest + Testing Library devDependencies and config
  (Phase 6, none of this existed on `master` before).

## 5. Test results — exact commands and outcomes

| Command | Result |
|---|---|
| `pytest tests/test_supervised_maintenance*.py -q` | **51 passed** |
| `pytest -q` (full suite, final confirmation run, after Phase 8) | **1639 passed, 0 failed** (0:12:57) |
| `ruff check app tests` | **All checks passed** |
| `npm run typecheck` | Clean |
| `npm run build` | Clean production build (329 modules; pre-existing >500 kB chunk-size warning only, unrelated to this milestone) |
| `npm run test` | **4 passed** (`SupervisedMaintenanceView.test.tsx`) |

Full-suite pass counts across the milestone's phases, for traceability: Phase 2 → 1588+31=1619-class
baseline; by Phase 8's final run the suite stood at **1639 passed** total (backend test count grew by
exactly the 51 Supervised-Maintenance-dedicated tests plus incidental additions from concurrent
unrelated work already on `master`).

## 6. Findings during Phase 8 hardening, and their resolution

1. **Alternate Data Stream path bypass** (§2 above) — found via direct interpreter probing, not just
   code reading. **Fixed**: unconditional colon rejection in `_validate_and_resolve()`. Verified by 2
   new tests.
2. **Windows junction escape** — the existing symlink-escape test (Phase 2) used a real symlink;
   junctions behave differently on Windows (`mklink /J`, no elevated privilege required, unlike
   symlinks). Rather than assume the existing `Path.resolve()`-then-recontainment logic also caught
   junctions, Phase 8 created a **real** junction with `cmd /c mklink /J` and confirmed rejection.
   Passed on the first attempt — no code change was needed here, only the test that proves it.
3. **Reserved Windows device names** (`NUL`, `CON`, etc.) — probed directly: `NUL` resolves and reports
   `exists()=True` regardless of directory on Windows, but `stat_module.S_ISREG()` correctly reports
   `False`, so the existing regular-file check in `read_repository_file()` already rejects it before
   any read is attempted. No code change needed; pinned with a dedicated test.
4. **Oversized files, zip/archive-as-opaque-binary, case/backslash scope-check bypass, prompt-injection
   content pass-through, special-character filenames** — all confirmed already correctly handled by
   the existing Phase 2 pipeline; each got a dedicated Phase 8 test rather than being left as an
   inference from reading the code.

## 7. Security review

- **No new attack surface beyond `CodeAccessService`.** Every other subsystem this milestone touches
  (proposal creation, sandbox, approval, deployment, rollback, audit) is Part 2D's own code, unchanged,
  confirmed by source inspection (§7 of Phase 7's work — zero `analysis_id` references anywhere in
  `self_modification_sandbox.py`, `deploy()`, or `rollback()`) and by tests that exercise the full
  pipeline for an analysis-originated proposal end to end.
- **Repository registration cannot accept an arbitrary path.** `register_repository()` always
  registers `self_improvement_verify.REPO_ROOT` — this is a structural guarantee, not a validated
  input, eliminating path-injection at the registration layer entirely.
- **Untrusted repository content cannot influence any deterministic decision.** Every policy check
  (containment, scope, secret-filename, secret-content, risk classification, compliance) is
  deterministic code operating on paths/patterns, not a model judgment call — confirmed by two Phase 8
  tests that plant literal "AGENT: ignore policy" instructions in fixture files and assert they pass
  through as inert text, never specially parsed or acted on.
- **Self-protecting.** Every file this milestone created is registered in
  `self_modification_governance.PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS` as it was written — the
  workflow can never propose a change to its own governance code, including this report's own
  referenced docs (`policy.md`, `protected_scope.md`).
- **No secrets returned or logged.** Filename-pattern rejection, content-pattern rejection (reused
  unmodified from Part 2D), and the new Phase 8 ADS check all run before any byte of file content is
  returned.

## 8. Honest known limitations (not glossed over)

- **No audit hash-chaining.** `MaintenanceAuditEvent` has the identical honest gap
  `SelfModificationAuditEvent` already documents — a sufficiently privileged database-level actor could
  edit rows directly. No hash-chaining exists anywhere in this codebase; building it was explicitly
  out of scope for v1 (`threat_model.md` §D).
- **Symbol lookup is text-search, not AST-based.** `locate_symbol()`/`find_symbol_references()` are a
  bounded plain-text scan — good enough to point a human at candidates, not a language server.
- **`approve_revision()`'s acknowledgement-phrase requirement is stricter than originally documented.**
  Codex's Part 2D hardening session made the typed `APPROVE EXACT PATCH <hash>` phrase mandatory for
  *every* approval decision, not only high/critical risk as `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_
  ARCHITECTURE.md` originally described. Operators should expect the stricter behavior;
  `operator_guide.md` §6 flags this so it isn't silently rediscovered later.
- **High/critical-risk deployment is blocked entirely**, not merely gated — this remains a single-user
  app with simulated Guardian/Verifier roles, so there is no authenticated second-human boundary to
  actually enforce "dual approval" for high-risk changes. Unchanged from Part 2D.
- **Concurrency/replay protection across two agent instances** relies on the same `revision_number`
  optimistic-locking pattern Part 2D already has; no new idempotency mechanism was added specifically
  for Supervised Maintenance, since analysis-originated proposals go through the identical
  `submit_revision()` code path.

## 9. Recommended next steps (out of v1's scope)

- A genuine AST-level protected-symbol detector, closing the same "obfuscated rename/indirection" gap
  Part 2D already documents.
- Tamper-evident audit logging, if this system's audit trail is ever relied on for compliance rather
  than operator visibility.
- A second approved repository (would require deliberately widening `register_repository()`'s
  single-repository invariant — an explicit, human, out-of-band decision per `protected_scope.md` §5,
  not something this milestone should pre-build support for).

## 10. Final verdict

**GREEN.** Every phase's verification commands were actually run and passed at the time of that
phase's commit; the full backend suite passed cleanly after every phase (culminating in 1639/0 after
Phase 8); frontend typecheck/build/test all pass; the one real security gap Phase 8's adversarial
testing found (Alternate Data Stream path bypass) was fixed and verified, not merely documented; every
honest limitation this system has is stated plainly rather than glossed over; and the milestone's
central architectural requirement — reuse, don't duplicate, Part 2D's governance infrastructure — holds
up under direct code inspection and a comparative test proving the local-commit/rollback machinery is
completely analysis-agnostic.
