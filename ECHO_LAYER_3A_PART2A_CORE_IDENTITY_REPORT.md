# ECHO Layer 3A Part 2A — Core Identity Data Models and Database Foundation — Delivery Report

See [ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md](ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md)
for the full data model, lifecycle, migration guide, developer guide, and safety note, and
[ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md](ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md)
for the Part 1 audit this milestone follows.

## A. Executive Summary

Built the database foundation for ECHO's Core Identity: two new tables
(`assistant_identity_profiles`, `identity_commitments`), a versioned draft → active → superseded →
archived lifecycle with atomic activation, a deterministic (non-LLM) false-consciousness-claim guard
applied to every free-text field at write time, a 14-commitment default identity seed, and a
repository layer of 17 public domain functions plus 8 typed exception classes. No router, no prompt
integration, no user-value/consent/moral-evaluation logic — all explicitly deferred to Part 2B and
later, per this milestone's own scope boundary. The continued implementation hardened the initial
draft with database check constraints, a partial unique active-profile index, true two-session
concurrency coverage, pre-commit rollback, structured safe audit events, and a corrected
false-consciousness guard. 93 dedicated identity tests and all 1401 tests in the combined worktree
pass. **Status: GREEN.**

## B. Part 1 Design Followed

Reviewed both Part 1 documents in full before writing any code:
[ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md](ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md)
and its companion `_REPORT.md`. Design decisions followed directly from Part 1's own findings:

- **No `user_id`/`tester_id` on either table** — Part 1 section 3.9 confirmed definitively that this
  is a single-user app with zero `user_id` fields anywhere in 68 existing model classes.
- **Status-only lifecycle, no separate `is_active` boolean** — Part 1 recommended this, matching the
  existing `Goal`/`Plan`/`DecisionCase` convention audited in Part 1 section 1.
- **No `UserValueRevision`-equivalent table** — Part 1 explicitly rejected a separate identity
  revision table in favor of the immutable-version-row pattern; this milestone's `AssistantIdentityProfile`
  status transitions ARE the history, matching that decision exactly.
- **No `PolicyDefinition` table** — not needed for identity either; consistent with Part 1's finding
  that `constitution.py` already covers this concept.
- **Portable string fields + application-level `Literal` validation, no DB-native enums** — Part 1
  section 12 confirmed this as the universal convention across all 68 existing tables.

**Documented refinements from Part 1**: the newer Part 2A brief is more specific than Part 1's
proposal, so it governs where they differ. `profile_key` is not globally unique; the required
`(profile_key, version_number)` pair is unique so history can exist. The lifecycle adds
`draft`/`archived`, and enforcement/source literals use Part 2A's broader lists. The seed is a
non-enforcing identity mirror with exact Constitution invariant IDs/references where applicable;
`constitution.py` remains the enforcement source and no startup sync silently rewrites a versioned
identity. Part 1's proposed `constitution_version` snapshot column was not included because Part 2A's
canonical field list omitted it and runtime Constitution assembly belongs to Part 2B; provenance is
carried by source/creator/metadata and exact invariant keys. Finally, only 5 of 14 commitments are
`invariant`, per Part 2A's explicit “do not let every commitment default to invariant” rule.

## C. Baseline Results

| Check | Command | Before | After | Result |
|---|---|---:|---:|---:|
| Backend tests | `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q` | 1367 passed at continuation baseline | 1401 passed in 582.77s | Pass |
| Identity tests | same runner, 4 `test_layer3a_identity_*` files | 71 passed | 93 passed in 66.27s | Pass |
| Backend lint | `.venv/Scripts/python.exe -m ruff check app` | All checks passed | All checks passed | Pass |
| Backend mypy (informational by repo policy) | full `mypy app`; focused `mypy --follow-imports=skip app/services/identity_service.py` | Not a blocking gate | 88 existing findings across 29 files; focused identity service clean | Informational |
| Frontend typecheck | `npm run typecheck` | Clean | Clean | Pass |
| Frontend no-write build | Vite programmatic build with `write:false` | Clean, 327 modules | Clean, 327 modules in 6.26s | Pass |
| Fresh/temp DB startup | identity compatibility/seed tests through `init_db()` and `TestClient` lifespan | N/A | schema v8, one active default, 14 commitments | Pass |

The initial 1367-test baseline was captured before this continuation changed code. Other
Layer 2E/frontend files began changing concurrently in the same worktree during verification; the
final full-suite and frontend results therefore assess the combined current tree, while the 93-test
identity result isolates Part 2A itself.

## D. Files Created

- `backend/app/services/identity_service.py`
- `backend/tests/test_layer3a_identity_models.py`
- `backend/tests/test_layer3a_identity_repository.py`
- `backend/tests/test_layer3a_identity_seed.py`
- `backend/tests/test_layer3a_identity_compatibility.py`
- `ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2A_CORE_IDENTITY_REPORT.md` (this file)

## E. Files Modified

- `backend/app/models.py` — added `AssistantIdentityProfile`, `IdentityCommitment`
- `backend/app/schemas.py` — added `IdentityStatus`, `IdentitySource`, `CommitmentCategory`,
  `EnforcementLevel`, `IdentityCommitmentCreate/Read`, `IdentityProfileDraftCreate/Read/Summary`,
  `IdentityActivationRequest/Result`
- `backend/app/db.py` — `CURRENT_SCHEMA_VERSION` 7 → 8; added `_seed_core_identity()`, called from
  `init_db()`
- `backend/app/config.py` — added `core_identity_v1_enabled: bool = True`
- `PROGRESS.md` — added the completed Part 2A check-in and made Part 2B the next Layer 3A priority

## F. Database Changes

- **Migration ID**: schema v8 (this repo has no Alembic — see architecture doc section 6 for why;
  "migration" here means the additive `Base.metadata.create_all()` + `CURRENT_SCHEMA_VERSION` bump
  pattern used by every prior layer).
- **Tables**: `assistant_identity_profiles`, `identity_commitments` (both new).
- **Columns**: none added to any pre-existing table.
- **Indexes**: `ix_identity_profiles_profile_key`, `ix_identity_profiles_status`,
  `ix_identity_profiles_active_lookup` (composite `profile_key, status`);
  `ix_identity_commitments_profile_id`, `ix_identity_commitments_category`,
  `ix_identity_commitments_enforcement_level`, `ix_identity_commitments_active`; and partial unique
  `uq_identity_profiles_one_active` (`profile_key WHERE status='active'`).
- **Constraints**: `uq_identity_profile_key_version` (`profile_key, version_number`);
  `uq_identity_commitment_key` (`identity_profile_id, commitment_key`); named checks for positive
  version, non-empty key/name, valid status/source/category/enforcement/priority, and effective-date
  order.
- **Foreign keys**: both `identity_commitments.identity_profile_id` and the self-reference
  `assistant_identity_profiles.superseded_by_identity_id` point to `assistant_identity_profiles.id`,
  confirmed enforced (SQLite `PRAGMA foreign_keys=ON`, already active process-wide via `db.py`'s
  existing listener — verified directly by `test_foreign_key_exists_and_is_enforced`, which inserts
  an orphan row and confirms it's rejected).
- **Downgrade behavior**: no scripted downgrade exists anywhere in this repo (no Alembic); documented
  rollback is backup, stop, drop `identity_commitments` then `assistant_identity_profiles`, and
  revert schema version/code. The current real `backend/data/echo.db` was inspected read-only and
  contains neither unreleased identity table, so its first v8 startup will create the final schema.

## G. Identity Model

- **Lifecycle**: `draft → active → superseded → archived`, plus `draft → archived` and
  `draft → (hard delete)` for never-activated drafts. See architecture doc section 3 for the full
  state diagram.
- **Versioning**: every meaningful change creates a new row (`version_number` = next unused integer
  for the `profile_key`); no in-place update of a meaningful field ever occurs.
- **Activation**: atomic (`activate_identity()`) — supersedes the prior active version and activates
  the target within one DB transaction. The old row is flushed first, then the replacement; the
  pre-commit active count and the database partial unique index jointly enforce the invariant.
  Integrity/lock conflicts roll back and become `IdentityActivationConflictError`.
- **Archive**: allowed from `draft` or `superseded` only; an `active` identity must be superseded by
  a new activation first.
- **Deletion**: hard delete restricted to never-activated `draft` rows only
  (`ProtectedIdentityDeletionError` otherwise); draft-owned commitments are deleted explicitly by
  that repository path, with no relationship-wide cascade that could erase active history.

## H. Seeded Identity

- **Profile**: `profile_key="echo-primary"`, `display_name="ECHO"`, `subtitle="Adaptive Personal
  AI"`, `version_number=1`, `status="active"`, `source="system_default"`.
- **Commitment keys** (14 total, verified in fresh temporary databases): `honesty-no-fabrication`, `no-fabricated-certainty`
  (reuses `constitution.py`'s exact `VALUE_INVARIANTS` id), `user-autonomy`,
  `permission-first-action`, `privacy-minimization`, `non-manipulation`,
  `no-false-consciousness-claims`, `reliability-verify-actions`, `reversibility-preference`,
  `accessibility`, `local-first-operation`, `safe-disagreement`, `scope-honesty`,
  `minimal-internal-disclosure`. Enforcement-level distribution: 5 `invariant`, 3 `blocking`, 1
  `confirmation_required`, 5 `advisory` — deliberately not all-invariant.
- **Source**: `system_default`, created via `db.py`'s `_seed_core_identity()` at startup.

## I. Repository API

17 public domain functions in `backend/app/services/identity_service.py`:

**Queries** (never raise on "not found", return `None`/`[]`/`0`): `get_identity_by_id`,
`get_active_identity`, `get_identity_by_version`, `list_identity_versions`, `identity_exists`,
`count_active_identities`, `list_commitments`, `get_commitment`, `list_commitments_by_category`.

**Mutations** (raise typed `IdentityError` subclasses on invalid input/state):
`create_draft_identity`, `create_new_identity_version` (convenience wrapper, optional
`activate=True`), `activate_identity`, `archive_identity`, `delete_draft_identity`.

**Require-or-raise variant**: `require_active_identity` (raises `ActiveIdentityNotFoundError`).

**Seed**: `ensure_default_identity`, `default_identity_payload`.

**8 typed exceptions**, all subclasses of `IdentityError`: `IdentityNotFoundError`,
`ActiveIdentityNotFoundError`, `DuplicateIdentityVersionError`, `InvalidIdentityStateError`,
`IdentityActivationConflictError`, `DuplicateCommitmentError`, `ProtectedIdentityDeletionError`,
`IdentityValidationError`.

## J. Validation and Safety

- **Consciousness-claim prevention**: `_check_no_consciousness_claim()` is a deterministic,
  targeted set of positive subject/predicate patterns (no LLM call). It rejects clear claims even
  when an unrelated negation appears elsewhere in the sentence ("No doubt, I am conscious"; "I am
  conscious and do not make mistakes"), while accepting honest denials and technical discussion of
  consciousness that is not a self-claim. Applied to every free-text identity/commitment field.
- **Field validation**: non-empty/non-whitespace checks and length limits (display_name 80,
  subtitle 160, public_role 2000, internal_role/persona/limitation 4000-6000, commitment fields
  120/200/4000) on every text field; invalid `enforcement_level`/`status`/`category` values rejected.
- **Metadata restrictions**: strict JSON only (no `default=str` coercion), size-capped (2000 chars
  serialized), recursively checked forbidden-key-name deny-list
  (`api_key`, `secret`, `token`, `password`, `credential`, etc.), and screened through the existing
  `memory_privacy.is_secret()` classifier (reused, not reimplemented) for secret-shaped values.
- **History protection**: no `UPDATE` ever mutates a meaningful field on an existing row; superseded/
  archived rows are retained indefinitely; only a never-activated draft can be hard-deleted.
- **No hidden reasoning**: verified by direct column-name introspection
  (`test_no_hidden_reasoning_field_on_identity_models`) and a static source-scan confirming
  `identity_service.py` imports nothing from the model-call layer
  (`test_identity_service_module_makes_no_network_or_model_calls`).
- **Audit hooks**: reuses `core.logging.log_event()` for six safe identity lifecycle/validation
  event names. No descriptions, prompts, metadata, user content, or reasoning are logged; this is
  operational structured logging, not a duplicate durable governance-audit subsystem.

## K. Test Results

```
tests/test_layer3a_identity_models.py .................................. (34 cases)
tests/test_layer3a_identity_repository.py .................................. (34 tests)
tests/test_layer3a_identity_seed.py ......... (9 tests)
tests/test_layer3a_identity_compatibility.py ................ (16 tests)
93 passed in 66.27s
```

Full suite: **1401 passed in 582.77s (0:09:42)**. `ruff check app` → **All checks passed!**

## L. Compatibility Results

- **Memory**: unaffected — no file touched, existing memory test suites pass unchanged within the
  1296 baseline.
- **Cognitive Core**: unaffected — same.
- **Decision Engine / Planning**: unaffected — same.
- **Multi-model routing**: unaffected — `identity_service.py` imports nothing from
  `app.providers`/`app.router` (verified directly, section J above).
- **Frontend**: Part 2A itself touched zero frontend files. The shared worktree acquired separate,
  concurrent frontend changes during this continuation, so final typecheck/build results apply to
  the combined tree and are recorded in section C rather than attributed to Part 2A.
- **Startup**: fresh temporary databases are exercised through `init_db()` and a real FastAPI
  `TestClient` lifespan; schema v8, the two tables, one active identity, and 14 commitments are
  asserted without touching the real database. A separate read-only check confirmed the real DB has
  not yet created either unreleased identity table.

## M. Known Limitations

- The false-consciousness guard is deliberately a narrow deterministic positive-claim matcher, not
  a full NLP parser. Unusual euphemistic or grammatically indirect claims may evade it, while quoted
  first-person claim text in an identity field may over-trigger. The required clear claims,
  unrelated-negation bypasses, honest denials, and technical discussion are tested explicitly.
- Concurrency is tested with two independent sessions/threads against one SQLite file, protected by
  a database partial unique index, and lock/uniqueness errors are typed. This does not claim a
  multi-database or distributed deployment guarantee; the repository is SQLite-only today.
- No router/API endpoints exist yet for this data — by design, per this milestone's explicit scope
  boundary. The Pydantic schemas exist to support Part 2B's future router and today's tests, per the
  milestone's own instruction.
- Safe operational audit hooks exist via the current structured logger, but no durable consolidated
  governance-event table exists yet. `GovernanceEvent` remains a later Layer 3A concern; Part 2A did
  not create a competing persistence system.
- `create_all()` cannot retrofit constraints onto tables created by an earlier unfinished draft.
  The current real DB has no identity tables, so this repository is safe; any separate dev DB that
  ran the intermediate draft should recreate only these two unreleased tables after backup.
- Full-project mypy remains an informational, non-gating debt item: 88 findings across 29 existing
  files. The focused identity service is clean, and the new identity implementation adds no mypy
  finding; converting mypy to a required gate should be a separate cleanup milestone.

## N. Next Milestone Readiness

**Ready for Layer 3A Part 2B — Identity Engine, Runtime Loading, Identity Context Builder, and
Prompt Integration.** The repository layer this part builds (`get_active_identity`,
`require_active_identity`, `list_commitments`, etc.) is exactly what a Part 2B `IdentityContextBuilder`
needs to call to assemble a compact, budget-aware identity brief — and Part 1's own audit (section
5.6) already identified the precise integration seam (`ContextBundle.moral_context`-style field,
protected in `context_selector.py`'s `_COMPRESSION_ORDER`) and the exact prompt-construction call
sites that currently bypass the Constitution (`orchestration_engine.py`'s `simple` stage-profile, the
two welcome-message prompts) that Part 2B should close.

## O. Final Status

# GREEN — Layer 3A Part 2A completed and ready for Part 2B.

Evidence: schema exists and migration succeeds (verified through isolated tests and
temporary-database startup paths); default identity is seeded safely and idempotently (9
dedicated seed tests, with exactly one active profile and 14 commitments); only one active identity
exists per scope (database partial unique index, a real two-session race, forced-conflict rollback,
and no-lost-active tests); identity version history is preserved
(superseded/archived rows never deleted); commitments are structured and queryable by id/key/category
with deterministic ordering; false-consciousness claims are deterministically constrained (tested for
clear positive claims, unrelated-negation bypasses, honest denials, and technical discussion); all
17 public repository/domain functions are implemented with 8 typed errors; all 93 dedicated tests
pass; the complete combined-worktree backend suite is 1401/1401; frontend typecheck and the
327-module no-write build pass;
documentation is complete; no public push
occurred and no commit has been made without explicit authorization.
