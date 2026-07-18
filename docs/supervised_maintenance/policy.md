# ECHO Supervised Maintenance Workspace v1 — Policy

The operative, current-state policy this system enforces — as opposed to `architecture.md` (why it's
built this way) and `threat_model.md` (what it defends against). Referenced from
`self_modification_governance.PROTECTED_PATHS`, so this file is itself protected: it cannot be edited
through the Supervised Maintenance / Self-Modification pipeline, only by a human editing the repository
directly.

## 1. Repository registration

Exactly one repository can ever be registered, and it is never a client-supplied path:
`maintenance_policy.register_repository()` always registers `self_improvement_verify.REPO_ROOT` — the
actual filesystem root this backend is running from. There is no code path anywhere in this system that
accepts an arbitrary path from a request body, an analysis, or a proposal and registers it. Registration
itself requires a human role (`founder`/`guardian_*`/`verifier`) — `requested_by="echo"` is rejected.

## 2. Capability mode ladder

Every registered repository has one `capability_mode`, defaulting to `disabled`:

| Mode | Unlocks |
|---|---|
| `disabled` | Nothing. `CodeAccessService` and analysis creation both reject with `CodeAccessPermissionError`/an equivalent. |
| `analyse_only` | Read-only code access (list/read/search/git status/git diff/git commit inspection) and analysis/finding creation. |
| `propose_only` | Everything above, plus `MaintenanceProposalService.create_proposal_from_analysis()` — generating a real Self-Modification proposal. |
| `sandbox_verify` | Everything above; the generated proposal can additionally be run through the existing Part 2D sandbox (`self_modification_sandbox_enabled` must also be on independently). |
| `human_approved_local_commit` | Everything above; the proposal can be approved and deployed to a local branch (`self_modification_deployment_enabled` must also be on independently). |

Changing capability mode requires a human role and is logged as a `MaintenanceAuditEvent`. This ladder
is layered **on top of**, not instead of, the five independent Part 2D feature flags
(`supervised_self_modification_enabled`, `self_modification_sandbox_enabled`,
`self_modification_deployment_enabled`, plus this system's own
`supervised_maintenance_enabled`/`supervised_analysis_enabled`/`supervised_proposals_enabled`/
`supervised_sandbox_enabled`/`supervised_local_commit_enabled`) — both gates must independently permit
an action before it proceeds.

## 3. Read/proposal scope

Default `permitted_read_paths` (readable via `CodeAccessService`):

```
backend/app/providers/   backend/app/routers/   backend/app/services/
backend/tests/           frontend/src/          docs/
*.md                     backend/requirements.txt   frontend/package.json
```

Default `permitted_proposal_paths` (where a generated proposal's patch may touch):

```
backend/app/providers/   backend/app/routers/   backend/app/services/
backend/tests/           frontend/src/          docs/
```

Both default lists are `self_modification_governance.ALLOWED_PATH_PREFIXES` — the exact same allowlist
Part 2D's own `classify_scope()` already used, not a separately maintained list. Notably absent:
`backend/app/models.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/constitution.py`,
`backend/app/council.py` — none of these are readable or proposable through this system by default.

## 4. Secret protection

`blocked_file_patterns` (filename-based, checked before any read is attempted):

```
.env*   *.pem   *.key   *.p12   *.pfx   credentials.*   secrets.*
id_rsa*   id_ed25519*   *.db   *.sqlite*
```

`.env.example`, `.env.sample`, and `.env.template` are explicitly excepted from the `.env*` pattern.
Independent of filename, every file's *content* is scanned against
`self_modification_governance._LIKELY_SECRET_PATTERNS` before being returned — a file with an innocuous
name but a hardcoded credential inside it is still rejected.

## 5. Read limits

- Maximum file size: `supervised_maintenance_max_read_bytes`, defaulting to 512,000 bytes. Checked via
  `stat()` before any read.
- Maximum directory listing / search-scan entries: 500 per call.
- Search query minimum length: 2 characters.
- Path containment: canonicalized (case-fold + backslash-normalize), resolved (`Path.resolve()`,
  which follows both symlinks and Windows junctions), then re-checked against the repository root —
  catching traversal, absolute paths, drive-letter paths, symlink escapes, and junction escapes in one
  pipeline. Alternate Data Stream syntax (a colon anywhere in the path) is unconditionally rejected.
  Binary files (a null byte in the first 8KB) are never returned as text.

## 6. Findings and epistemic status

`MaintenanceFinding.epistemic_status` reuses Atlas's existing vocabulary: `verified`, `inferred`,
`hypothesis`, and `unknown` (Atlas's `narrative` renamed for this context) — not a fifth, separately
invented classification system.

## 7. Audit

Every registration, mode change, analysis lifecycle transition, and proposal-generation event is
recorded to `MaintenanceAuditEvent` — a dedicated table for this subsystem, matching the established
one-table-per-subsystem convention (`SelfModificationAuditEvent`, `ActionRun`, `ToolRun` are all
similarly subsystem-scoped). No hash-chaining exists on this table, the same honestly-documented
limitation Part 2D's own audit trail carries — see `threat_model.md` §D.
