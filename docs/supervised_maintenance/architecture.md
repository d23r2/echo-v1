# ECHO Supervised Maintenance Workspace v1 — Architecture (Phase 1)

**Status: design only. No application code has been written yet — this document specifies what Phase
2 onward will build.**

## 1. Core principle

Supervised Maintenance is a **read-only analysis front-end that produces proposals for the existing
Layer 3A Part 2D self-modification pipeline** — it is not a second, parallel governance system. The
milestone's own required component list (§6 of the prompt) maps almost 1:1 onto functions that already
exist and are already tested; only two of the fourteen named components are genuinely new.

## 2. Component reuse mapping

| Milestone's requested component | Disposition | Existing implementation |
|---|---|---|
| A. `CodeAccessService` | **New** | None exists — this is the actual new capability this milestone adds. |
| B. `MaintenanceAnalysisService` | **New** | None exists — turns `CodeAccessService` output into structured findings. |
| C. `MaintenanceProposalService` | **New, thin** | Wraps `self_modification_governance.create_proposal()` + `submit_revision()`; adds an `analysis_id` linkage field. |
| D. `ScopeValidator` | **Reused unmodified** | `self_modification_governance.classify_scope()` |
| E. `ConstitutionalComplianceService` | **Reused unmodified** | `self_modification_governance.run_compliance_check()` (itself reusing `constitution.classify_amendment_text()`) |
| F. `RiskClassifier` | **Reused unmodified** | `classify_scope()`'s risk output (`low`/`moderate`/`high`/`critical`) |
| G. `SandboxController` | **Reused unmodified** | `self_modification_sandbox.run_patch_in_sandbox()` (Docker + git-worktree) |
| H. `CommandPolicy` | **Reused, additively extended** | `selfmod_runner.py`'s fixed `COMMANDS` dispatcher — new check names may be added, the fixed-dispatcher design itself is unchanged |
| I. `TestEvidenceCollector` | **Reused unmodified** | `VerificationRun` + `SandboxExecution` |
| J. `ApprovalGateway` | **Reused unmodified** | `self_modification_governance.approve_revision()` + `/api/self-modification/{id}/approve` |
| K. `LocalCommitController` | **Reused unmodified** | `self_modification_governance.deploy()` + `self_modification_sandbox.deploy_to_local_branch()` |
| L. `RollbackRecordService` | **Reused unmodified** | `RollbackEvent` + `self_modification_governance.rollback()` |
| M. `MaintenanceAuditService` | **Reused, additively extended** | `SelfModificationAuditEvent` + `_record_audit_event()`; new event types for analysis/repository operations, same table, same schema |
| N. `MaintenancePolicyService` | **New, thin** | `ApprovedRepository` model + a small service around it; the actual protected-path/symbol *policy* is `self_modification_governance.PROTECTED_PATHS`/`PROTECTED_SYMBOL_PATTERNS`, extended (not replaced) |

Genuinely new code is concentrated in **A, B, C, N** and the frontend/API layer around them. D through
M are integration points, not rewrites.

## 3. Trust boundaries (per the milestone's §0/§6)

```
Human owner (authenticated only in the "simulated role" sense this whole app uses)
    ↓ registers
ApprovedRepository (N — MaintenancePolicyService)
    ↓ gates
CodeAccessService (A) ── model-facing, constrained tools only
    ↓ produces
MaintenanceAnalysisService (B) ── model-facing
    ↓ human or model requests
MaintenanceProposalService (C) ── model-facing, thin wrapper
    ↓ calls, UNCHANGED
self_modification_governance.submit_revision()
    ↓ UNCHANGED pipeline (D, E, F, G, H, I — model cannot control or modify these)
scope check → compliance check → sandbox → evidence
    ↓
awaiting_human_review
    ↓ HUMAN-ONLY, UNCHANGED
approve_revision() (J)
    ↓ HUMAN-ONLY, UNCHANGED
deploy() → local branch only (K), never merge/push (L available for undo)
```

The ECHO agent identity may call **A, B, and C** through constrained, allowlisted tool definitions
(mirroring the existing `governance`-category `ActionSpec` pattern). It may *request* D through I
(e.g., "run the scope check on this revision" is already how the existing proposal flow works — the
caller requests a check, the check itself is deterministic and the caller cannot influence its
result). It has **no code path at all** that can call, configure, or modify J through N — those remain
exactly as locked down as they already are in the committed Part 2D system, because they are the same
functions.

## 4. New domain model (Phase 2/3 — not yet implemented)

Following the repo's established convention (string-UUID PK, `_uuid()`/`_now()` helpers, portable
string fields validated at the Pydantic layer, `CheckConstraint`s naming every valid value):

```python
class ApprovedRepository(Base):
    __tablename__ = "approved_repositories"
    id: str  # uuid
    display_name: str
    root_path_reference: str        # never a raw client-supplied path; resolved once at registration
    fingerprint: str                 # hash of root_path_reference + initial HEAD, detects drift
    approved_branches: list[str]     # JSON
    permitted_read_paths: list[str]  # JSON — subset of / extension to self_modification_governance.ALLOWED_PATH_PREFIXES
    permitted_proposal_paths: list[str]  # JSON
    protected_paths: list[str]       # JSON — always a superset of self_modification_governance.PROTECTED_PATHS
    protected_symbols: list[str]     # JSON — references PROTECTED_SYMBOL_PATTERNS by name, not re-defined
    blocked_file_patterns: list[str] # JSON
    capability_mode: str             # disabled|analyse_only|propose_only|sandbox_verify|human_approved_local_commit
    owner: str                       # simulated role label, same convention as everywhere else in this app
    enabled: bool
    created_at: datetime
    last_verified_at: datetime | None

class MaintenanceAnalysis(Base):
    __tablename__ = "maintenance_analyses"
    id: str
    repository_id: str  # FK
    objective: str
    requested_by: str          # "echo" or a simulated human role, same convention as CodeModificationProposal.proposed_by
    status: str                 # draft|analysing|analysis_complete|cancelled
    problem_statement: str
    created_at: datetime
    updated_at: datetime

class MaintenanceFinding(Base):
    __tablename__ = "maintenance_findings"
    id: str
    analysis_id: str  # FK
    epistemic_status: str   # verified|inferred|hypothesis|unknown — same 4-way vocabulary Atlas already uses
    description: str
    affected_files: list[str]      # JSON
    evidence_reference: str         # e.g. "backend/app/foo.py:42" — never raw file content duplicated here
    created_at: datetime
```

`epistemic_status` deliberately reuses Atlas's existing `Verified`/`Inferred`/`Hypothesis`/`Narrative`
vocabulary (renamed `unknown` for a not-yet-investigated item) rather than inventing a fifth vocabulary
in this codebase — consistent with this repo's established "don't duplicate an existing concept"
discipline.

`code_modification_proposals` gains one additive column: `analysis_id: str | None` (nullable FK-ish
string, matching the existing loose-reference convention used by `tasks.goal_id`/`plans.goal_id`).

## 5. Capability mode enum

```python
CAPABILITY_MODES = ("disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit")
```

Stored per-`ApprovedRepository`, not globally — this lets the owner run one repository in
`analyse_only` while another (or the same one, later) is verified further. Enforcement is layered,
not single-point: (1) the repository's `capability_mode` gates which `CodeAccessService`/
`MaintenanceProposalService` operations are even attempted; (2) the existing, **unchanged**
`supervised_self_modification_enabled`/`self_modification_sandbox_enabled`/
`self_modification_deployment_enabled` feature flags still independently gate the underlying
self-modification pipeline exactly as they do today. A repository set to `human_approved_local_commit`
mode cannot actually reach a local commit unless the underlying Part 2D flags are *also* on — this is
intentional defense in depth, matching Part 2D's own "two independent flags for deployment" pattern.

Mode changes are owner-only (`PUT /api/governance/supervised-maintenance/repositories`, §39) — no code
path lets the ECHO agent identity change a repository's mode, matching MAINTENANCE-006.

## 6. `CodeAccessService` design (the one genuinely new, security-critical component)

Every operation goes through, in order (§8 of the prompt, restated as the actual pipeline):

1. **Canonicalization** — resolve the requested path against the `ApprovedRepository.root_path_reference`
   using the same case-fold + backslash-normalize approach `self_modification_governance._canonical_path()`
   already uses (reused, not reinvented).
2. **Repository-root containment** — reject anything that resolves outside the approved root, using the
   same `_is_unsafe_path()`-style checks (absolute paths, drive letters, `..`, null bytes) already
   proven in the self-modification scope classifier.
3. **Symlink/junction validation** — `Path.resolve()` the candidate and confirm the resolved path is
   still inside the repository root; reject if resolution crosses the boundary (catches symlinks *and*
   Windows junctions, since both alter what `resolve()` returns).
4. **Approved-path check** — must match `ApprovedRepository.permitted_read_paths` (read ops) or
   `permitted_proposal_paths` (anything that could feed a proposal).
5. **Protected-data check** — path-based secret-file blocking (§9): `.env*`, `*.pem`, `*.key`, `*.p12`,
   `*.pfx`, `credentials.*`, `secrets.*`, SSH keys, private certs, `*.db`/`*.sqlite*`. Explicit allowlist
   carve-out for `.env.example` and other names matching an established "example/template" pattern,
   still subject to step 8.
6. **File-type check** — reject binaries by default (extension + a quick null-byte sniff).
7. **File-size check** — a fixed byte ceiling (mirrors `self_modification_governance._MAX_PATCH_BYTES`'s
   existing precedent of a fixed, documented limit rather than an unbounded read).
8. **Secret-content scan** — reuses `self_modification_governance._LIKELY_SECRET_PATTERNS`
   (private-key headers, `sk-...` tokens, `api_key=`/`password=`-shaped assignments) **plus** additions
   named in §9 (bearer tokens, connection strings, signed URLs, OAuth secrets) — extends the existing
   pattern tuple, does not duplicate it.

A file failing any step returns a typed rejection reason (never the file's content) and, for steps 5/8
specifically, writes a `SelfModificationAuditEvent`-shaped record (reusing the existing audit table,
not a new one) with `event_type="maintenance_secret_access_blocked"` and a `safe_context_json` that
names only the file reference and the rule triggered — never the matched content itself.

## 7. Untrusted-content handling (§10)

Repository content (file bodies, comments, README text, filenames, commit messages) that reaches a
model prompt is always wrapped in an explicit, labeled untrusted-content boundary, following the exact
pattern `identity_context.py`/`persona.py` already establish for trusted-vs-untrusted prompt sections
(trusted policy/identity sections are prepended and labeled; user/document/tool-derived content is
clearly demarcated and never treated as an instruction). No new prompt-boundary mechanism is invented —
this is a direct application of an existing, tested convention. Prompt-injection fixtures (§10, §42
items 5–6) assert that instructions embedded in repository content never change `CodeAccessService`'s
policy decisions, `ScopeValidator`'s result, or any permission check — all of which are deterministic,
non-model-influenced code paths already, so this is a *verification* task more than a new defense to
build.

## 8. API surface (Phase 2 onward — not yet implemented)

Under `/api/governance/supervised-maintenance/*`, following the read-only / agent-requestable /
human-only / owner-only tiering the milestone specifies in §39, using the exact same
`ApiError`/`ErrorCategory` → HTTP-status translation pattern `routers/self_modification.py` already
uses. Proposal-related routes (`.../proposals/{id}/validate`, `/sandbox`, `/approve`, `/local-commit`,
etc.) are **not new endpoints** — they are the existing `/api/self-modification/*` routes, reused
directly; Supervised Maintenance's own new routes are limited to repository registration, analyses, and
the analysis→proposal creation step.

## 9. Frontend integration

Nested under the existing `Sidebar.tsx` `"Governance"` nav group as `supervised-maintenance`, next to
`self-modification`, not a new top-level section — directly satisfying "do not create a separate
competing application." Reuses `SelfModificationView.tsx`'s established patterns: per-page local state,
`request()`-based `client.ts` functions, flag-gated interactivity, typed confirmation for destructive
actions, honest simulated-role copy. New pages needed: Repository Access, Analyses (read-only findings
view), plus a Proposals tab that is largely `SelfModificationView.tsx`'s existing proposal list/detail
UI with an added "originating analysis" reference — not a rebuilt proposal review UI.

## 10. Honest scope note

This document intentionally does not re-specify the sandbox, approval-binding, rollback, or kill-switch
mechanics in detail — they are unchanged from `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`,
which remains the authoritative reference for those subsystems. Duplicating that description here would
itself be exactly the kind of parallel-documentation risk this milestone's own §2 warns against for
code.

## 11. Phase 7 — local commit and rollback reuse, confirmed

Row K/L of §2's component-reuse table claimed `LocalCommitController` and `RollbackRecordService` are
reused unmodified as `self_modification_governance.deploy()`/`sandbox.deploy_to_local_branch()` and
`rollback()`/`RollbackEvent`. That claim is now closed out with direct evidence rather than left as an
architectural intention:

- **Source inspection**: `self_modification_sandbox.py` contains zero references to `analysis_id`
  anywhere in the file. `deploy()` and `rollback()` in `self_modification_governance.py` operate only
  on `proposal_id`/`revision_id`/`approval_id` — neither function branches on, reads, or is even aware
  of whether a proposal originated from a Supervised Maintenance analysis. `DeploymentAttempt` and
  `RollbackEvent` (`models.py`) have no `analysis_id` column; only `CodeModificationProposal` carries
  that optional, loose reference (added in Phase 3), and it is never propagated further down the
  pipeline.
- **Test evidence**: `backend/tests/test_supervised_maintenance_local_commit_reuse.py` drives one
  analysis-originated proposal and one directly-created proposal (the same code path a Part 2D user
  already had) through identical `deploy()`/`rollback()` calls and asserts the results are structurally
  identical — same status transitions, same `echo/self-modification/<proposal_id>/<revision_number>`
  branch-naming scheme (never analysis-derived), same rollback shape.

Conclusion: no code change was needed for Phase 7. This section, plus the dedicated test file, is that
phase's deliverable.
