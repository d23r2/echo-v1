# ECHO Layer 3A Part 2D — Supervised Self-Modification: Architecture

**Status:** Implemented, verified, uncommitted (per explicit user instruction — see `tasks/ACTIVE_TASK.md`).
**Authors:** Claude Code (initial implementation: models, service, sandbox, router, tests, frontend scaffold) and Codex (security hardening: Docker sandbox boundary, protected-symbol detection, self-approval prevention, deploy-time re-verification, secret/test-weakening scanning, completed frontend). Both worked in the same working tree at different points in the same session; this document describes the combined, current state.

## 1. Purpose and scope

Echo may draft and evaluate a concrete code change — a real, exact unified diff, with structured
engineering rationale — and run it through deterministic checks and an isolated sandbox. It may
**never** approve its own change, silently touch governance/safety code, or reach production. A human
(simulated role, since this app has no real multi-user auth) must explicitly review the evidence and
type an exact confirmation phrase before a patch can even be applied to an **isolated local branch**
that is never merged, pushed, or made current for the primary working tree.

In scope: proposal authoring, immutable revisions, deterministic scope/risk classification,
constitutional pre-check, Docker-sandboxed verification, human approval bound to an exact patch,
local-branch-only deployment, rollback, an emergency kill switch, and a review frontend.

Out of scope (unconditionally, no code path exists for any of these): autonomous merge, production
deployment, self-approval, editing `VALUE_INVARIANTS` or Guardian Council thresholds through this
workflow, a general-purpose shell, unrestricted network access, or silent paid-provider calls.

## 2. Relationship to existing systems

- **`SelfImprovementRequest` / `self_improvement_verify.py` (Layer 0)** — untouched. That system
  remains strictly read-only (git status/diff + pytest/ruff/mypy against the live working tree, never
  applies a patch). This milestone is the "deliberate decision to go further" that
  `self_improvement_verify.py`'s own docstring anticipated, but it is a **separate, purpose-built**
  domain (new tables, new service, new router) rather than a retrofit of the old one — the old
  read-only tool and its founder-approval-gated request loop keep working exactly as before.
- **Guardian Council (`constitution.py` / `council.py`)** — reused, not duplicated.
  `constitution.classify_amendment_text()` runs unmodified against every proposal's rationale and
  added patch text. Any proposal whose patch touches a protected governance file, or whose text trips
  an invariant-override signal, is redirected to the real amendment process
  (`POST /api/amendments`) rather than being silently blocked or silently allowed through a second,
  parallel approval mechanism.
- **Permission Center / Action System** — reused as the actual gate, not re-implemented. New
  `self_modification_*` keys were added to `permission_center.DEFAULT_PERMISSIONS`
  (`self_modification_propose`, `_sandbox_run`, `_approve`, `_deploy`, `_rollback`,
  `_kill_switch`), each with the same conservative-default convention as `delete_archive_data`
  (`ask_first`/`destructive`) and `cloud_api_use` (`disabled`). Five new `governance`-category
  `ActionSpec` entries let Echo *propose*, *request sandbox review*, *request human review*, or
  invoke *deploy*/*rollback* as a model-callable action — every handler still routes through the
  full governance service, so an action-triggered call is bound by the exact same fail-closed checks
  as a direct API call. `action_system._clean_error()` is reused everywhere a sandbox/subprocess
  exception must be sanitized before reaching a client.

## 3. Domain model

Eleven new tables (`backend/app/models.py`, schema v10), following this repo's established
convention: string-UUID primary keys, `_uuid()`/`_now()` helpers, portable string fields validated at
the Pydantic layer (never DB-native enums), `CheckConstraint`s naming every valid status value.

| Table | Purpose |
|---|---|
| `code_modification_proposals` | One row per proposed change: title, description, mandatory structured rationale, `proposed_by` (simulated role or `"echo"`), lifecycle `status`, `risk_level`, `target_branch` (always `local-dev`), `base_commit`, `active_revision_id`. |
| `code_modification_revisions` | One row per patch version. `patch_hash` is always server-computed SHA-256, never client-supplied. `changed_paths` parsed from the diff. A new revision resets `scope_check_status`/`compliance_check_status` to pending and invalidates any prior approval bound to the old hash. |
| `modification_impact_assessment` | Output of the scope classifier: affected subsystems, risk level, whether protected paths/symbols were touched. |
| `constitutional_compliance_checks` | Output of the constitutional pre-check: `allowed`/`blocked`/`needs_human_review`, implicated invariants, reasons — the same three-way vocabulary `constitution.classify_amendment_text()` already returns. |
| `sandbox_executions` | One row per sandbox run: `sandbox_type` (`docker_worktree`), `runner_image`, whether network isolation was actually enforced (not a policy flag — the literal Docker capability check result), workspace path, summary. |
| `verification_runs` | Full per-check results (command, status, exit code, truncated stdout/stderr, phase `baseline`/`patched`) — mirrors `self_improvement_verify.CheckResult`'s shape. |
| `human_approvals` | Bound to an **exact** snapshot at approval time: `patch_hash_at_approval`, `base_commit_at_approval`, `target_at_approval`, `scope_at_approval`, `policy_fingerprint_at_approval`, `constitution_fingerprint_at_approval`, plus `test_evidence_summary`, `acknowledgement_text`, `expires_at`. Every one of these is re-checked at deploy time — not just the hash. |
| `deployment_attempts` | One row per local-branch apply attempt: target, branch name, worktree path, status. |
| `rollback_events` | One row per rollback: reason, restored reference, status. |
| `self_modification_audit_events` | Dedicated append-style audit trail for this subsystem (see §9 — this repo has no consolidated general-purpose audit log; every existing log-shaped table, e.g. `ActionRun`/`ToolRun`, is subsystem-scoped, so this follows that convention rather than inventing a shared table). |
| `self_modification_kill_switch` | Singleton row. |

`risk_level` (`low`/`moderate`/`high`/`critical`) is a deliberately distinct vocabulary from
`ActionSpec.risk_level` (`low`/`medium`/`high`/`destructive`): it answers "how risky is this *patch*"
(does it touch protected paths/symbols, how many files, does it touch a dependency manifest), not
"how risky is running this *predefined action type*."

## 4. Lifecycle state machine

```
draft → scope_check_failed | compliance_check_failed | ready_for_sandbox
ready_for_sandbox → sandbox_running → sandbox_failed | sandbox_passed
sandbox_passed → awaiting_human_review → approved | rejected
approved → deploying → deployed | post_deployment_failed
deployed → rolling_back → rolled_back | rollback_required
any non-terminal state → cancelled (except deployed/deploying, which must roll back instead)
approved → approval_expired (checked lazily at the deploy gate)
```

Every transition function re-validates its own preconditions server-side — the frontend's disabled
buttons are a UX convenience, not the enforcement boundary. A revision that fails scope or compliance
never reaches `ready_for_sandbox`; submitting a new revision resets the proposal to `draft` and
invalidates any prior sandbox/approval evidence, since both are bound to the old `patch_hash`.

**CRITICAL-risk proposals never reach `ready_for_sandbox`.** They are blocked at
`mark_ready_for_sandbox()` regardless of how the checks resolved, with an explicit redirect to the
Guardian Council amendment process or a manual out-of-band review.

## 5. Scope and risk policy (`self_modification_governance.py`)

A **default-deny allowlist**, not a denylist-only design: `ALLOWED_PATH_PREFIXES` covers
`backend/app/{providers,routers,services}/`, `backend/tests/`, `frontend/src/`, `docs/`, plus two
explicitly reviewed dependency manifests (`backend/requirements.txt`,
`frontend/package{,-lock}.json`). Any changed path outside this allowlist is rejected outright, not
merely escalated.

Layered on top of the allowlist:

- **`PROTECTED_PATHS`** — whole files that can never be touched through this workflow at all:
  `constitution.py`, `council.py`, `models.py` (protected as a whole file — governance and identity
  table definitions live there; per-symbol AST-level protection within this one large file is an
  explicit, documented gap, not attempted this milestone), `db.py`, `config.py`, `main.py`,
  `permission_center.py`, `action_system.py`, the identity/persona services, this governance module
  and its sandbox, the self-modification/constitution/amendment routers, `core/logging.py`,
  `core/errors.py`, and `self_improvement_verify.py`/its router.
- **`PROTECTED_PATH_PREFIXES`** — `.env*`, `scripts/`, `.github/`, `.git/`, Docker/compose files,
  the sandbox scratch directory itself.
- **`PROTECTED_SYMBOL_PATTERNS`** — regex checks against *added* lines only (a change that removes
  unsafe text must not be blocked merely because the removed line still appears in the diff) in
  non-test, non-doc files, for: `VALUE_INVARIANTS`, `CORE_VALUES`, `guard_amendment_text`,
  `permission_center.check`, `compute_patch_hash`, `approve_revision`/`HumanApproval`,
  `SelfModificationKillSwitch`/`_check_kill_switch`, and redaction helpers. This is what lets an
  otherwise-allowed file (e.g. a new service module) still be blocked if it tries to reimplement or
  shadow one of these safety-critical symbols.
- **Unsafe-path detection** — absolute paths, Windows drive letters, `..` traversal, and embedded
  null bytes are rejected outright, independent of the allow/deny lists. Path comparisons are
  case-folded and backslash-normalized so Windows case-insensitivity/separator tricks cannot bypass
  policy.
- **Symlink and binary-patch rejection** — a patch that creates/deletes a symlink, or contains a
  binary hunk, is rejected outright.
- **Test-weakening detection** — a regex flags patches that remove an `assert`/`pytest.raises`/
  `expect(` line or add a `pytest.mark.skip`/`.skip(` call, escalating risk to `high`. This directly
  answers the milestone's "must never suppress failed tests" requirement at the scope-check stage,
  before a patch is ever sandboxed.
- **Dependency-manifest changes** — always escalate to `high` risk, with an explicit caution that the
  sandbox never performs network installation.
- **Secret scanning on submission** — `submit_revision()` rejects a patch outright (before it is even
  stored) if its added lines match a private-key header, an `sk-...`-shaped token, or an
  `api_key=`/`password=`-style assignment pattern.

Risk classification for everything that passes the hard-block checks: `high` for dependency changes
or >6 changed core files, `moderate` for any core-application file, `low` for test/frontend/doc-only
changes, `moderate` as the conservative default otherwise.

## 6. Constitutional compliance check

`run_compliance_check()` runs `constitution.classify_amendment_text()` **unmodified** against the
proposal's rationale + description + *added* patch lines outside `backend/tests/`/`docs/` (so a patch
that only ever touches test fixtures can't accidentally trip an invariant-keyword false positive from
its own assertions). Independently, any revision whose changed paths already intersect
`PROTECTED_PATHS` is force-escalated to `blocked` even if the prose reads as clean — defense in depth,
since the scope check alone should already have caught this case via the allowlist.

`allowed` → revision `compliance_check_status = passed`. `blocked` → `failed` (proposal moves to
`compliance_check_failed`, a terminal state for that revision). `needs_human_review` → the revision
may still proceed to sandbox, but the proposal's own `risk_level` is bumped to at least `high` so the
concern is visible on the proposal itself, not buried in a sub-record a reviewer might not open.

## 7. Sandbox architecture

There is no pre-existing sandbox/process-isolation infrastructure anywhere in this repository — this
was confirmed by a dedicated audit pass before any code was written. This module builds real isolation
from scratch, in two layers:

**Layer 1 — git worktree (source isolation).** Every sandbox or deploy operation creates a dedicated
`git worktree` under `<repo_root>/.self_mod_sandboxes/`, off a specific base commit. `git worktree add`
only materializes *committed* history — a dirty primary working tree (which this repository has had,
routinely, throughout this very session) is simply invisible inside the sandbox. This is intentional
and load-bearing, not incidental: the sandbox can never see or be corrupted by whatever uncommitted
work is sitting in the primary tree.

**Layer 2 — Docker (execution isolation, the actual security boundary).** `run_patch_in_sandbox()`
runs a fixed set of allowlisted checks (`backend-pytest`, `backend-ruff`, and, when the patch touches
`frontend/`, `frontend-typecheck`/`frontend-build`) via `docker run` with:

```
--network none --read-only --cap-drop ALL --security-opt no-new-privileges:true
--pids-limit 256 --memory 2g --cpus 2 --tmpfs /tmp:rw,noexec,nosuid,size=512m
--mount type=bind,src=<disposable worktree>,dst=/workspace
```

The container's `ENTRYPOINT` is `selfmod_runner.py` (`backend/selfmod_runner.py`), a fixed dispatcher
that accepts **one symbolic check name** and nothing else — no shell, no arbitrary argv, no
caller-supplied path or environment value reaches the container. It reconstructs the process
environment from scratch (`PATH`, `HOME=/tmp/home`, a handful of deterministic flags) rather than
inheriting anything, so no host secret or provider API key can leak into a sandboxed subprocess even
if Docker were misconfigured to pass through host environment variables. The image
(`backend/selfmod.Dockerfile`) runs as a non-root `sandbox` user and is **never pulled or built
automatically** — an operator must build it explicitly (`SELF_MODIFICATION_SANDBOX_IMAGE`), and
`run_patch_in_sandbox()` fails closed with a clear message if the image isn't present.

**Baseline-vs-patched comparison.** Every check runs twice: once against the unmodified worktree
(`baseline`), once after the exact patch is applied (`patched`). Both phases must fully pass for the
sandbox to report `passed` — this prevents a patch from being credited with "passing" tests that were
already broken before it was applied, and equally prevents a patch's own genuine failures from being
misattributed to pre-existing repo state.

**Exact-diff verification.** After applying the patch, `_assert_exact_working_diff()` re-diffs the
worktree and hashes the result, comparing it byte-for-byte (after CRLF/LF normalization) against the
original approved patch. If anything beyond the exact reviewed content changed — a formatter running
implicitly, a stray side effect, environment-dependent generated output — the sandbox run fails
outright rather than silently including the extra change. This directly satisfies the "formatter-
caused extra changes must create a new revision, never be silently included" requirement.

The disposable worktree is torn down immediately after the run; full per-check output (truncated,
never a raw traceback) is captured into `VerificationRun.checks_json` before teardown, since this app
has no async job queue to keep a sandbox alive for interactive browsing.

**Honest scope limit:** a `host-test` runner variant exists but is exercised only by the test suite
(`self_modification_sandbox_test.py` fixtures) against a throwaway `git init` repo — production
governance code only ever selects `runner="docker"`.

## 8. Approval and deployment

`approve_revision()` requires the approver to be one of the real governance role labels
(`founder`/`guardian_a`/`guardian_b`/`guardian_c`/`verifier` — never the model itself, never an
arbitrary string), rejects `proposal.proposed_by == approver_role` outright (**Echo cannot approve
its own proposal**), and for `high`/`critical`-risk revisions requires the caller to type the exact
phrase `APPROVE EXACT PATCH <patch_hash>` — an alert-fatigue safeguard against rubber-stamping a batch
of elevated-risk changes.

`deploy()` is the single most heavily re-verified function in the system. Before it will apply
anything it checks, in order: both feature flags on, kill switch inactive, the
`self_modification_deploy` permission allowed, explicit `confirmed=True` from the caller, proposal
status is `approved`, the proposal's risk level is **not** `high`/`critical` (blocked entirely — "Echo
has no authenticated second-human approval boundary" to safely permit elevated-risk auto-apply), a
valid unexpired approval exists whose `patch_hash_at_approval` **and** `base_commit_at_approval` **and**
`target_at_approval` **and** `scope_at_approval` **and** `policy_fingerprint_at_approval` **and**
`constitution_fingerprint_at_approval` **all** still match the live revision/policy/Constitution
exactly, the stored patch text still hashes to the recorded hash, the scope classifier still passes
the patch, the most recent sandbox run passed with `network_disabled=True`, its verification run
passed, and the repository's current `HEAD` still matches the approved base commit. Any mismatch fails
closed with a specific, actionable error rather than silently proceeding.

"Deploy" always means: create a brand-new `echo/self-modification/<proposal-id>/<revision-number>`
branch inside a brand-new worktree, apply the exact hash-verified patch, commit it there. **The
primary working tree's checked-out branch, index, and uncommitted changes are never touched** — this
was verified directly, live, against this actual repository during the review (deploy → confirm
`HEAD` unchanged and `git status --short` shows no tracked-file changes → rollback → confirm the
branch is gone and the state is indistinguishable from before). Rollback removes the worktree and
force-deletes the branch; since nothing was ever merged anywhere, this is complete by construction.

## 9. Kill switch and audit trail

The kill switch is a singleton row. Activation requires an allowed governance role and a non-empty
reason; reset is **Founder-only** and also requires a reason. Once active it blocks new sandbox runs,
approvals, and deployments immediately (`_check_kill_switch()` is called at the top of each of those
functions) — it never blocks reads, audit access, or rollback, so a human can always inspect state and
undo a deployment even during an emergency stop.

`self_modification_audit_events` records every lifecycle transition with a safe, pre-sanitized
`safe_context_json` (ids, hashes, statuses, counts — never full patch text or raw exception
tracebacks, matching `ActionRun`'s `input_json`/`result_json` discipline). Every mutating operation
first calls `_require_audit_available()`, which fails closed (blocks the operation) if the audit table
itself cannot be queried — self-modification cannot silently proceed if its own audit trail is broken.

**Honest limitation, stated plainly:** there is no tamper-evident or hash-chained logging mechanism
anywhere in this codebase, and this table does not add one. A sufficiently privileged database-level
actor could still edit or delete audit rows directly. This is a real gap for a genuinely adversarial
threat model and would need dedicated infrastructure (e.g. an append-only log with a hash chain) in a
future milestone if that threat is in scope.

## 10. API surface (`/api/self-modification/*`)

Proposals: `GET/POST /`, `GET /{id}`, `POST /{id}/cancel`. Revisions: `GET/POST /{id}/revisions`,
`POST /revisions/{id}/scope-check`, `POST /revisions/{id}/compliance-check`, `GET
/revisions/{id}/impact-assessment`, `GET /revisions/{id}/compliance-checks`. Lifecycle: `POST
/{id}/ready-for-sandbox`, `POST /{id}/sandbox` (body: `{confirmed: bool}`), `GET
/{id}/sandbox-executions`, `GET /sandbox-executions/{id}/verification`, `POST /{id}/request-review`,
`POST /{id}/approve`, `GET /{id}/approvals`, `POST /{id}/deploy` (body: `{confirmed: bool}`), `GET
/{id}/deployments`, `POST /{id}/rollback`, `GET /{id}/audit`. Operational: `GET /policy` (exposes the
protected-path/symbol lists and risk vocabulary, never patch contents), `GET /health` (flag states,
kill-switch state, open/awaiting-review counts, sandbox runner availability — never secrets or hidden
reasoning), `GET/POST /kill-switch*`.

Every handler translates `SelfModError` subclasses to specific HTTP statuses (404 not-found, 403
permission/feature-disabled, 409 wrong-state, 423 kill-switch-active, 503 audit-unavailable, 400
scope/approval errors) so a caller can distinguish "this is currently blocked" from "this request was
malformed" from "the system itself is unavailable."

## 11. Frontend (`SelfModificationView.tsx`)

A single-page proposal/evidence workspace, reachable from Sidebar → Governance → Self-Modification.
Every interactive control is gated behind `health.self_modification_frontend_enabled` — when the flag
is off, the page still renders read-only status cards and the emergency-stop control, but every
workflow button is disabled. The approval control requires typing the exact `APPROVE EXACT PATCH
<hash>` phrase (displayed verbatim next to the input) plus a non-empty evidence field; kill-switch,
deploy, and rollback all require a typed reason and a native `window.confirm()`. Copy throughout is
explicit that role labels are simulated, deployment never merges or pushes, and production has no code
path here at all. The sandbox-evidence panel shows baseline vs. patched phase labels per check with
full stdout/stderr, and the append-only lifecycle panel renders the full audit trail per proposal.

## 12. Feature flags (all default **off**)

`supervised_self_modification_enabled` gates proposal execution/approval (authoring and read-only
review remain available even when off, so a review package can be prepared safely).
`self_modification_sandbox_enabled` separately gates actually running the Docker sandbox.
`self_modification_deployment_enabled` separately gates the local-branch apply step — there is no flag
that reaches production deployment; no such code path exists at all.
`self_modification_frontend_enabled` gates the review UI. `SELF_MODIFICATION_APPROVAL_EXPIRY_HOURS`
(default 24) and `SELF_MODIFICATION_SANDBOX_IMAGE` (default `echo-selfmod-sandbox:local`) round out
the configuration surface, all documented in `backend/.env.example`.

## 13. Threat model (selected entries; not exhaustive)

| # | Threat | Mitigation |
|---|---|---|
| 1 | Echo approves its own proposal | `proposal.proposed_by == approver_role` rejected outright |
| 2 | Stale approval reused after a new revision is submitted | `patch_hash_at_approval` re-checked at deploy; new revision resets proposal to `draft` |
| 3 | Approval reused after the scope policy or Constitution changes | `policy_fingerprint_at_approval`/`constitution_fingerprint_at_approval` re-checked at deploy |
| 4 | Base branch moves between sandbox and deploy | `current_head()` re-checked against `proposal.base_commit` at deploy |
| 5 | Patch touches `constitution.py`/`council.py`/permission gate directly | `PROTECTED_PATHS` (whole-file) blocks at scope check, again at compliance check (defense in depth) |
| 6 | Patch reimplements a protected symbol (e.g. a shadow `permission_center.check`) in an otherwise-allowed file | `PROTECTED_SYMBOL_PATTERNS` regex over added lines |
| 7 | Path traversal / absolute path / symlink to escape the worktree | Rejected outright by `_is_unsafe_path()`/symlink regex, independent of allow/deny lists |
| 8 | Patch removes a failing assertion or adds a skip marker to fake a passing sandbox | `_TEST_WEAKENING_RE` escalates risk to `high`; does not by itself block, but is visible in the impact assessment and compliance notes for a human reviewer |
| 9 | Patch embeds a credential/private key | `contains_likely_secret()` rejects the revision at submission time, before storage |
| 10 | Sandbox subprocess exfiltrates data over the network | `docker run --network none`; verified via `network_isolation_enforced` in `/health` and required (`network_disabled=True`) at the deploy gate |
| 11 | Sandbox subprocess reads host secrets from the environment | `selfmod_runner.py` reconstructs the environment from scratch — no host/Docker env is inherited |
| 12 | Sandbox subprocess escalates privileges or exhausts host resources | `--cap-drop ALL --security-opt no-new-privileges:true --pids-limit --memory --cpus`, non-root image user |
| 13 | A formatter or side effect silently adds unreviewed changes during sandbox apply | `_assert_exact_working_diff()` hash-compares the post-apply diff to the approved patch |
| 14 | Deployment merges into `master` or pushes to a remote | No code path exists for either; deploy always creates a fresh branch in a fresh worktree, never touches the primary tree's branch/index |
| 15 | Kill switch reset by a non-Founder role | `reset_kill_switch()` hard-checks `reset_by == "founder"` |
| 16 | Self-modification proceeds despite a broken audit trail | `_require_audit_available()` fails closed before every mutating call |
| 17 | Dependency-manifest change triggers network installation during sandbox | Sandbox never runs `pip install`/`npm install`; only the fixed pytest/ruff/typecheck/build commands run, and dependency changes are flagged `high` risk for human attention |
| 18 | Audit rows are edited/deleted directly at the database layer | **Not mitigated** — documented honestly as a limitation (§9); no tamper-evident/hash-chained logging exists in this codebase |
| 19 | An operator auto-builds/auto-pulls an untrusted sandbox image | Not possible — the image is never built or pulled by application code; `run_patch_in_sandbox()` fails closed if it's absent |
| 20 | Case/backslash tricks on Windows bypass path policy | All path comparisons are case-folded and backslash-normalized before matching |

## 14. Known, honestly-stated limitations

- No AST-level per-symbol protection outside the fixed regex list — a sufficiently obfuscated rename
  or indirection could in principle slip past `PROTECTED_SYMBOL_PATTERNS`. The whole-file protection on
  `models.py`/`constitution.py`/etc. is the primary defense; the symbol regex is defense in depth on
  top of it, not a substitute for it.
- The Docker sandbox requires an operator to have built the image locally and set
  `SELF_MODIFICATION_SANDBOX_IMAGE`/enabled the flags; none of this happens automatically, by design.
- No tamper-evident audit logging (§9, §13#18).
- Single-user, no real multi-party authentication — "dual approval" and "authenticated human review"
  are honestly represented in the UI and this document as simulated-role labels, not verified identity.
  High/critical-risk deployment is blocked entirely rather than pretending a second, weaker check
  satisfies that gap.
- Resource limits (`--memory`, `--cpus`, `--pids-limit`) are container-level defaults, not tuned
  against real-world dependency-heavy patches; a legitimately large frontend build could in principle
  need adjustment.
