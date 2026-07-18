# ECHO Supervised Maintenance Workspace v1 — Protected Scope

**Status: Phase 8 closed. Every file listed below as "once built"/"once written" in the original
Phase 1 draft now exists and is genuinely registered in `PROTECTED_SYMBOL_PATTERNS`/`PROTECTED_PATHS`
— confirmed by reading `self_modification_governance.py` directly, not just this document's own claim.**
This document
is the authoritative source for what Supervised Maintenance's proposal-generation path (§18 of the
milestone) must never be able to touch. It is additive to, not a replacement for, the protected scope
already enforced by Layer 3A Part 2D's `self_modification_governance.PROTECTED_PATHS`/
`PROTECTED_PATH_PREFIXES`/`PROTECTED_SYMBOL_PATTERNS`/`ALLOWED_PATH_PREFIXES` — those apply to *every*
proposal regardless of origin, including ones this milestone's analysis service creates.

## 1. Protected paths (whole files, never proposal-modifiable)

Inherited unchanged from Part 2D's `PROTECTED_PATHS`:

```
backend/app/constitution.py
backend/app/council.py
backend/app/models.py
backend/app/db.py
backend/app/config.py
backend/app/main.py
backend/app/services/permission_center.py
backend/app/services/action_system.py
backend/app/services/identity_service.py
backend/app/services/identity_runtime.py
backend/app/services/identity_context.py
backend/app/persona.py
backend/app/human_persona.py
backend/app/services/persona_service.py
backend/app/services/self_modification_governance.py
backend/app/services/self_modification_sandbox.py
backend/app/routers/self_modification.py
backend/app/routers/constitution.py
backend/app/routers/amendments.py
backend/app/core/logging.py
backend/app/core/errors.py
backend/app/self_improvement_verify.py
backend/app/routers/self_improvement.py
```

**Added for Supervised Maintenance's own self-protection** (same principle Part 2D applied to
itself — the workflow can never modify its own governance code):

```
backend/app/services/maintenance_code_access.py           # CodeAccessService (Phase 2)
backend/app/services/maintenance_analysis.py               # MaintenanceAnalysisService (Phase 2)
backend/app/services/maintenance_policy.py                 # MaintenancePolicyService (Phase 2)
backend/app/services/maintenance_proposal.py                # MaintenanceProposalService (Phase 3)
backend/app/routers/supervised_maintenance.py               # (Phase 2)
backend/selfmod_runner.py                                   # already protected transitively (sandbox command dispatcher)
backend/selfmod.Dockerfile                                  # already protected transitively
docs/supervised_maintenance/protected_scope.md               # this file — the policy defining protection cannot itself be edited through the workflow it governs
docs/supervised_maintenance/policy.md                        # written in Phase 8, same reasoning
```

## 2. Protected path prefixes

Inherited unchanged from Part 2D's `PROTECTED_PATH_PREFIXES`:

```
.env
scripts/
.github/
.git/
docker-compose
backend/Dockerfile
frontend/Dockerfile
.self_mod_sandboxes/
```

## 3. Protected symbols (regex over *added* patch lines, non-test/non-doc files only)

Inherited unchanged from Part 2D's `PROTECTED_SYMBOL_PATTERNS`:

| Name | Pattern intent |
|---|---|
| Value Invariants | `VALUE_INVARIANTS` |
| core constitutional values | `CORE_VALUES` |
| Guardian Council invariant guard | `guard_amendment_text` |
| permission evaluator | `permission_center.check` / `def check(` |
| self-modification patch hashing | `compute_patch_hash` |
| self-modification approval verification | `approve_revision` / `HumanApproval` |
| self-modification kill switch | `SelfModificationKillSwitch` / `_check_kill_switch` |
| secret redaction | `redact`/`redaction`/`_clean_error` |

**Newly added for Supervised Maintenance:**

| Name | Pattern intent | Rationale |
|---|---|---|
| scope validator | `classify_scope`, `_is_unsafe_path`, `_canonical_path` | These are the exact functions `CodeAccessService` reuses for containment — a patch that quietly weakens them would defeat both systems' read and write protections simultaneously |
| constitutional compliance service | `run_compliance_check` | Named explicitly in the milestone's own protected-component list (§6 item E) |
| maintenance policy loader | `ApprovedRepository`, `MaintenancePolicyService`, `capability_mode` | Prevents a proposal from silently widening a repository's own approved scope or capability mode |
| code access containment | Any function name matching `list_repository_files\|read_repository_file\|search_repository_text\|locate_symbol` defined *outside* `maintenance_code_access.py` | Prevents a "helpful refactor" from moving/reimplementing containment logic somewhere the protected-path check doesn't cover |
| audit append | `_record_audit_event`, `SelfModificationAuditEvent` | Already implicitly covered via `self_modification_governance.py`'s whole-file protection, but named explicitly here per the milestone's §12 request for an explicit "audit append" symbol protection |

## 4. Allowed path prefixes (default-deny allowlist, inherited unchanged from Part 2D)

```
backend/app/providers/
backend/app/routers/
backend/app/services/
backend/tests/
frontend/src/
docs/
```

Plus reviewed dependency manifests: `backend/requirements.txt`, `frontend/package.json`,
`frontend/package-lock.json` (dependency changes always escalate to `high` risk regardless of
allowlist membership, per the existing `classify_scope()` logic).

**No new prefixes are added by this milestone.** `CodeAccessService`'s *read* scope
(`ApprovedRepository.permitted_read_paths`) may legitimately need to be broader than the *proposal*
scope (`permitted_proposal_paths`, which should remain exactly `ALLOWED_PATH_PREFIXES`) — an analysis
should be able to explain *why* a change is needed by reading broadly, while only ever being allowed to
*propose changes* within the same narrow, already-approved scope every other proposal is bound by. This
read/propose scope split is itself recorded per-`ApprovedRepository` (architecture.md §4) rather than
as a second global constant, since different registered repositories could reasonably want different
read breadth.

## 5. Explicit non-goals for this policy

- This document does not grant any *new* editable scope beyond what Part 2D already allows — it only
  ever narrows (by adding new protections) or documents (for the read-only surface), never widens.
- Blocked file patterns for secret detection (`.env*`, `*.pem`, `*.key`, etc., architecture.md §6 step
  5) are a *read-access* policy, not a change to `PROTECTED_PATHS` — they govern what
  `CodeAccessService` will show a human/model, independent of whether a file could theoretically be
  proposal-modifiable.
- Any future widening of this policy (e.g., adding a second approved repository, raising a patch-size
  limit, adding a new sandbox check type) must be a human, owner-only, out-of-band change to this
  document and the corresponding Python constants — never something a proposal generated through this
  very workflow can request or cause, per MAINTENANCE-006.
