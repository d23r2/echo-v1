# ECHO Supervised Maintenance Workspace v1 — Operator Guide

A single practical reference for running this system, rather than ten near-duplicate files. This
milestone's own §2 explicitly forbids building a second Permission Center, Audit system, Action System,
Feature Flag service, or Governance Center — the same discipline applies to documentation: the sandbox,
approval, deployment, and rollback mechanics below are Part 2D's, unchanged, and are described here only
at the level an operator needs, not re-derived. For full detail on any of them, follow the
cross-reference to `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`.

## 1. What this system is

A read-only-first code analysis workspace: Echo can inspect its own approved repository (always this
backend's own codebase, never an arbitrary path), record structured findings, and optionally generate a
real Self-Modification proposal from an analysis. From that point on, the proposal is indistinguishable
from one created directly through Self-Modification — same scope check, same constitutional compliance
check, same sandbox, same human approval gate, same local-only deployment, same rollback. See
`architecture.md` §2 for the full component-reuse mapping and `policy.md` for the exact current scope/
capability-mode/secret-pattern configuration.

## 2. Getting started (Founder walkthrough)

1. **Enable the flags.** All of `supervised_maintenance_enabled`, `supervised_analysis_enabled`,
   `supervised_proposals_enabled` default `False` in `backend/.env`. Nothing in this system does
   anything until they're set.
2. **Register the repository.** From the Supervised Maintenance page (Sidebar → Governance →
   Supervised Maintenance), click "Register repository." This always registers the backend's own
   running codebase — there is no field to type a different path.
3. **Set a capability mode.** Starts at `disabled`. Move it to `analyse_only` to unlock read access and
   analysis creation. See `policy.md` §2 for what each subsequent mode unlocks.
4. **Run an analysis.** Give it an objective, browse/search the read-only code view, record findings
   with an honest `epistemic_status` (don't mark something `verified` on a guess).
5. **Mark the analysis complete.**
6. **Generate a proposal (requires `propose_only`+).** From that point, the proposal follows the
   existing Self-Modification lifecycle exactly — continue its review on the Self-Modification page, not
   here. This page has no approve/sandbox/deploy controls of its own by design (§0/§6 of the milestone
   spec: this is never a second approval surface).

## 3. Approval, sandbox, deployment, rollback (unchanged from Part 2D)

These are described in full in `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md` (§4 Domain
model, §5 Lifecycle, §7 Sandbox design) and `_REPORT.md` (§4 verification evidence). The only thing
Supervised Maintenance changes about any of it is tagging the resulting `CodeModificationProposal` with
an optional `analysis_id` — confirmed by direct source inspection and a dedicated test
(`test_supervised_maintenance_local_commit_reuse.py`) to have zero effect on `deploy()`, `rollback()`,
or the sandbox runner. In short, for an operator:

- **Approval** requires a human role (never the same role as the proposer), the exact
  `APPROVE EXACT PATCH <hash>` acknowledgement phrase, and is invalidated by any later change to the
  patch, base commit, target branch, scope, scope policy, or Constitution.
- **Sandbox** runs in a network-isolated Docker container with a fixed, non-shell command dispatcher —
  never arbitrary shell execution.
- **Deployment** only ever means committing to a fresh local branch/worktree. There is no code path
  anywhere in this codebase that pushes to a remote or merges to `master` automatically.
- **Rollback** removes the local deployment branch/worktree; it never touches the primary working tree.

## 4. Test evidence

Every claim above is backed by an actual, currently-passing test, not a description of intended
behavior:

| Area | Test file |
|---|---|
| Repository registration/mode policy | `test_supervised_maintenance.py` (registration, duplicate rejection, mode changes) |
| `CodeAccessService` containment (baseline) | `test_supervised_maintenance.py` (traversal, absolute/drive paths, symlink escape, out-of-scope, `.env`, secret content, null byte) |
| `CodeAccessService` containment (adversarial, Phase 8) | `test_supervised_maintenance_adversarial.py` (Alternate Data Streams, Windows junction escape, reserved device names, oversized files, archive/binary handling, case/separator bypass, prompt-injection content pass-through, special-character filenames) |
| Analysis/finding lifecycle | `test_supervised_maintenance.py` |
| Proposal generation reuses Part 2D unmodified | `test_supervised_maintenance_proposal.py` |
| Full pipeline reuse (scope → compliance → sandbox → approval → deploy → rollback) | `test_supervised_maintenance_pipeline_reuse.py` |
| Local commit / rollback are analysis-agnostic | `test_supervised_maintenance_local_commit_reuse.py` |
| Frontend (disabled state, empty state, error surfacing, repository listing) | `frontend/src/components/supervised-maintenance/SupervisedMaintenanceView.test.tsx` |

Run the backend suite with `cd backend && .\.venv\Scripts\python.exe -m pytest -q` and the frontend
suite with `cd frontend && npm run test`.

## 5. Emergency shutdown

There is no separate kill switch for this system — it reuses Part 2D's existing
`SelfModificationKillSwitch` for anything downstream of proposal generation (sandbox/approval/deploy),
and its own five feature flags (all independently settable to `False` in `backend/.env` with no restart
beyond the normal backend restart) for everything upstream (registration, read access, analysis,
proposal generation). Setting `supervised_maintenance_enabled=false` alone is sufficient to fail closed
on every endpoint this system adds — confirmed by `test_code_access_fails_closed_when_disabled_by_default`.

## 6. Known limitations (honest, not glossed over)

- No tamper-evident audit hash-chaining on `MaintenanceAuditEvent` — same limitation
  `SelfModificationAuditEvent` already has (see `threat_model.md` §D).
- Symbol lookup (`locate_symbol`/`find_symbol_references`) is a bounded plain-text scan, not an
  AST index.
- `approve_revision()` requires the typed `APPROVE EXACT PATCH <hash>` phrase for **every** decision,
  not only high/critical risk — a Codex hardening addition from the Part 2D session that is stricter
  than `ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md`'s original description of that
  requirement. Operators should expect the stricter behavior; the architecture doc has not been
  retroactively corrected.
- High/critical-risk deployment is blocked entirely (not merely gated) because this is a single-user
  app with simulated roles — there is no authenticated second-human boundary to actually enforce
  "dual approval" for high-risk changes.
