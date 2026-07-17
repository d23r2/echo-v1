# ECHO Layer 1 — Memory Foundation v1 — Delivery Report

See [ECHO_LAYER_1_MEMORY_FOUNDATION.md](ECHO_LAYER_1_MEMORY_FOUNDATION.md)
for the full architecture writeup and
[ECHO_LAYER_1_MEMORY_SMOKE_TEST.md](ECHO_LAYER_1_MEMORY_SMOKE_TEST.md) for
the 39-step manual checklist.

## 1. Overall status: Green

995/995 backend tests pass (129 new), `ruff check .` clean, frontend
`tsc -b --noEmit` and `npm run build` both clean, live-verified in a real
browser against a temporary, isolated backend instance (real memories
created, a real conflict detected and resolved through the UI, maintenance
run, Settings' new Memory section confirmed) — never touching the real
running Docker backend's data. Secret scan reports 13 findings, all
pre-existing in Layer 0's own test fixtures (intentional fake secret-shaped
strings used to test the redaction logic itself, last touched in commit
`ec2ac48`, before this milestone) — zero findings in any Layer 1 file. Not
infallible: memory is never presented as certain, and several items are
documented as deliberately deferred (§21).

## 2. Architecture audit

**Existing systems reused**: `AtlasEntry` (extended into the unified memory
model), `MemoryCandidate` (extended as the capture pipeline), `memory_conflicts.py`
(extended with typed/severity conflict classification), `atlas.py`'s local
Chroma/sentence-transformers search (reused as-is for semantic retrieval),
`Project`/`ConversationSummary` (extended with lightweight profile fields),
`chat_actions.py` (extended with one new, narrowly-scoped forget action),
Layer 0's `core.logging.redact()` and `core.metrics` (reused, not
reimplemented).

**Duplicate systems avoided**: no parallel `MemoryRecord` table (extended
`AtlasEntry` instead); no parallel candidate queue; `CognitiveConcept`/
`CognitiveRelationship` left untouched (world-model concept graph, distinct
from the new memory-instance `MemoryRelationship` graph — decision documented
in the Foundation doc §11); `KnowledgeItem`/`ConversationSummary` extended
rather than replaced.

**Major design decisions**: containment-based (not Jaccard) similarity for
duplicate detection (Foundation doc §8); import always stages
`MemoryCandidate` rows, never writes `AtlasEntry` directly (Foundation doc
§20); "forget that" archives, never hard-deletes, and is the one deliberate
exception to this app's existing "destructive actions stay UI-only" rule
(Foundation doc §17).

## 3. Memory model

**Models added**: `MemoryEvidence`, `MemoryRelationship`, `MemoryConflict`,
`MemoryConsolidationEvent`, `MemoryRevision`, `MemoryFeedback` (6 new
tables). **Models modified**: `AtlasEntry` (+19 columns), `MemoryCandidate`
(+7 columns), `Project` (+5 columns), `ConversationSummary` (+2 columns).
**Migration approach**: fully additive `_ensure_column()` calls (Layer 0's
established non-destructive pattern), no Alembic, `CURRENT_SCHEMA_VERSION`
bumped 1 → 2. **Legacy compatibility**: `memory_type` (the pre-Layer-1
taxonomy) is completely untouched; `category` (Layer 1's taxonomy) is
independently populated via `atlas.legacy_type_to_category()` for both
backfill and new writes that don't specify it — verified no existing test
needed a behavior change to keep passing (866 pre-Layer-1 tests all still
pass unmodified, except the one prompt-integration wiring fix in §16).

## 4. Memory categories

10 categories: profile, preference, project, task, episodic, semantic,
skill, relationship, environment, temporary. Scope behavior: `project_id`/
`task_id` link a memory to a specific project/task (no FK constraint,
matching this repo's existing cross-reference style); retrieval respects
project scoping via both the semantic and lexical-fallback paths.

## 5. Epistemic state and provenance

Statuses: `epistemic_status` (Verified/Inferred/Hypothesis/Narrative,
unchanged) + new `verification_status` (verified/partially_verified/
unverified/disputed/outdated/not_applicable). Evidence: `MemoryEvidence` for
the multi-source case; `capture_method`/`source_type`/`source_reference` on
`AtlasEntry` for the common single-source case. Source labels: "You told
ECHO," "You confirmed this," "Inferred by ECHO," etc. — see Foundation doc
§5.

## 6. Capture pipeline

Explicit "remember that..." still saves directly (unchanged). Candidates
(preference-detection and opportunistic MEMORY: block) now carry
`category`/`sensitivity_level`/`recommendation`/`capture_reason`. Sensitive
information handling: `"do not remember..."` blocks capture outright before
any path runs; secret-shaped content is refused even on explicit request;
highly-sensitive content is refused unless explicit.

## 7. Consolidation

Duplicate detection via containment ratio (threshold 0.55) over
significant-word sets; actions: `reject_duplicate` (exact match),
`update_existing` (refinement, in-place edit + `MemoryRevision`),
`supersede_existing` (correction language detected, new entry +
`supersedes_memory_id` + old marked `superseded`), `keep_both` (below
threshold — not recorded as a consolidation event, per "avoid
over-compressing distinct preferences"). Every non-trivial action produces
an auditable `MemoryConsolidationEvent`.

## 8. Conflict system

9 conflict types, 4 severities (never auto-`critical`), 5 statuses. 5
resolution actions, always explicitly chosen by the caller — confidence
alone never silently resolves a high-severity conflict. Deduplicated per
memory pair (re-running detection on the same pair doesn't create a second
open conflict row).

## 9. Lifecycle

Expiration via `expires_at` + `run_maintenance()` (idempotent, archives —
never hard-deletes). Archival: `status=archived` excludes a memory from
default retrieval while remaining fully auditable/restorable. Outdated/
superseded handling: `mark_outdated()`, `supersede()`, both preserve the row.
Category-specific review intervals (environment: 14 days, project/task: 30
days, everything else: never age-flagged, reviewed on contradiction
instead). A real naive/aware `datetime` subtraction bug was caught and fixed
during test-writing (SQLite drops tzinfo on read-back, confirmed
empirically) — see Foundation doc §10.

## 10. Retrieval

Hybrid: semantic (Chroma) + lexical/metadata fallback, the latter always
active for project/task-scoped requests, not just when Chroma is down.
Ranking factors: semantic similarity, importance, confidence, verification
bonus, project-scope bonus, contradiction penalty, outdated penalty, capped
adaptive-feedback nudge. Vector-store-down fallback verified with a live
test that forces `atlas.search` to raise. Context budget: `max_results`
(default 5, capped at 50 via the API schema).

## 11. Project / document memory

Project: `objective`/`constraints_json`/`decisions_json`/`blockers_json`/
`last_reviewed_at`, auto-updated when a task under a project is marked done
via chat (tested). Document memory: **not built this pass** — a documented
known limitation (Foundation doc §16), not a silent gap.

## 12. User controls

Memory Center (`frontend/src/components/memory/MemoryCenterView.tsx`,
Advanced → Knowledge & Memory) — overview stats, filters, per-memory cards
with archive/restore/confirm/mark-outdated/delete, conflict review with
one-click resolution, maintenance trigger, JSON export. Settings gained a
compact "Memory" section with live stats and a pointer to Memory Center.
Edit/archive/delete/provenance are all exercised live (§15).

## 13. Privacy

Sensitivity policy: 5 levels, deterministic classification, never a model
call. Secrets policy: never stored, no exception for explicit requests
(verified live and via 3 dedicated tests). Retrieval restrictions:
`can_retrieve()` blocks secret always, blocks highly-sensitive for
general-purpose retrieval (only surfaced for a specifically-matching
purpose).

## 14. Import/export

JSON only (Markdown export was not built — a minor scope cut, JSON is
sufficient for the "own and move your memory" goal and machine-readable for
round-tripping). Duplicate handling: `skip_duplicates=True` by default on
commit. Conflict handling: import never creates a conflict directly — a
staged candidate that later gets accepted goes through the normal
capture-time conflict check. Dry run: `preview_import()` performs zero
writes (verified by a dedicated test).

## 15. Tests

- `cd backend && .venv/Scripts/python.exe -m pytest -q` → **995 passed**
  (129 new, in 12 new test files, matching exactly the delta from Layer 0's
  866-test baseline).
- `cd backend && .venv/Scripts/python.exe -m ruff check .` → **All checks
  passed!**
- Targeted: `pytest -k "memory or atlas or knowledge or project"` → all pass
  (subset of the above).
- `scripts/check_secrets.ps1` → 13 findings, all pre-existing Layer 0 test
  fixtures (verified via `git log` — last touched in commit `ec2ac48`, before
  this milestone), zero in any Layer 1 file.

## 16. Frontend

- `npx tsc -b --noEmit` → clean.
- `npm run build` → clean, 326 modules.
- No `lint` npm script exists in this project (pre-existing, documented
  state, unchanged by this milestone).
- Live-verified: Memory Center loads real data, filters render, conflict
  resolution mutates state correctly (open conflicts 1→0, active memories
  4→3 after `choose_newer`), "Run maintenance" reports real counts,
  Settings' new Memory section shows live stats matching Memory Center.

## 17. Database

- `create_all` + `_ensure_layer1_memory_columns()` ran cleanly against a
  fresh temp database during live verification; `GET /api/system/version`
  confirmed `schema_version: 2`.
- Existing-DB compatibility: additive-only migration, no destructive
  `ALTER`/`DROP`; verified via 5 dedicated backward-compatibility-style
  tests (legacy `memory_type` unaffected, `category` correctly backfilled).
- Backup recommendation: back up `backend/data/echo.db` before this
  migration reaches the real running database (via
  `scripts/backup_echo_data.ps1`, Layer 0) — not yet applied to the real
  Docker backend's database this session, by design (verification used an
  isolated temp DB instead).

## 18. Files changed

**New backend**: `services/memory_privacy.py`, `services/
memory_consolidation.py`, `services/memory_lifecycle.py`, `services/
memory_retrieval.py`, `services/memory_index.py`, `services/
memory_export.py`, `routers/memory.py`, 12 new test files.

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `main.py`,
`atlas.py`, `memory_conflicts.py`, `persona.py`, `chat_actions.py`,
`routers/chat.py`, `routers/memory_candidates.py`, `routers/projects.py`,
one existing test file (`test_persona_conversation_recall.py`, monkeypatch
target fix).

**New frontend**: `components/memory/MemoryCenterView.tsx`.

**Modified frontend**: `api/client.ts` (Layer 1 types + ~25 new functions),
`App.tsx`, `components/Sidebar.tsx`, `components/settings/SettingsView.tsx`.

**New docs**: this report, the Foundation doc, the smoke test doc.

## 19. Bugs fixed

- **Naive/aware datetime subtraction crash risk** in
  `memory_lifecycle.run_maintenance()` — SQLite silently drops tzinfo on
  `DateTime(timezone=True)` read-back (confirmed empirically with a direct
  DB round-trip test before writing the fix), so comparing a
  `datetime.now(UTC)`-aware value against a DB-read `created_at` would have
  raised `TypeError: can't subtract offset-naive and offset-aware datetimes`
  the first time maintenance ran against real data. Fixed by comparing
  against a naive "now" consistently; covered by a dedicated regression
  test.
- **Duplicate-detection threshold using the wrong similarity metric** —
  Jaccard overlap (reused from `memory_conflicts.py`'s own, differently-
  purposed threshold) scored the milestone's own worked examples ("port
  8001" → "must run on port 8000; 8001 was temporary") at 0.375, below even
  the loose 0.4 conflict threshold, because a legitimate correction that
  adds words dilutes Jaccard. Found via a failing test against the spec's
  own example, fixed by switching to a containment-based measure for
  consolidation specifically (Jaccard is still correct and untouched for
  `memory_conflicts.py`'s own looser purpose).
- **Stale monkeypatch target after refactor** —
  `test_persona_conversation_recall.py`'s
  `test_atlas_retrieval_still_works_alongside_conversation_search` patched
  `app.persona.atlas.search`, which broke when `persona.py` stopped
  importing `atlas` directly (now delegates to `memory_retrieval.py`). Fixed
  by retargeting the patch to `app.atlas.search` and adding the Layer 1
  fields the new retrieval pipeline expects on a non-persisted test object.
- Two minor test-authoring bugs caught before commit: a detached-SQLAlchemy-
  instance access after `db.close()` in a new API test, and a duplicate-
  detection false positive between two generically-worded test fixtures
  sharing a live DB (fixed by using more distinctive test content, not by
  weakening the detector).

## 20. Bugs not fixed

None outstanding in the new Layer 1 code. Pre-existing items from
`PROGRESS.md`'s Blockers section (missing `.gitattributes` for CRLF
normalization) remain open and are unrelated to this milestone.

## 21. Manual checks remaining

- The full 39-step `ECHO_LAYER_1_MEMORY_SMOKE_TEST.md` was spot-verified
  (capture, sensitivity gating, conflict detection/resolution, maintenance,
  Settings integration) but not run as one continuous pass against the real
  Docker backend's real data — verification deliberately used an isolated
  temp backend/database instead, per this milestone's own non-destructive
  intent and the established safe-verification pattern from prior
  milestones.
- The Layer 1 schema migration (`schema_version` 1→2) has not yet been
  applied to the real running Docker backend's database. It's additive and
  non-destructive by construction, but has only been exercised against a
  fresh temp DB and the isolated test suite so far — recommend backing up
  `backend/data/echo.db` before the next real restart picks up this schema
  change.
- Document-chunking memory (§16 of the Foundation doc) is not implemented.
- "Forget that" was tested via direct function calls and the automated
  suite, not via a live chat turn against a real model this session.

## 22. Rollback procedure

See [Foundation doc §24](ECHO_LAYER_1_MEMORY_FOUNDATION.md#24-rollback-procedure)
for the full list. Summary: every schema change is additive; reverting the
listed modified files restores pre-Layer-1 behavior exactly; new files can
be deleted with no effect elsewhere; back up the database before any
rollback that would follow a real-data migration.

## 23. Release-candidate readiness

**Green as a local release candidate.** Not pushed anywhere. Ready to be
tagged `echo-layer-1-memory-v1-rc` after your review of `git status`/`git
diff --stat`, matching this milestone's own Commit Guidance: no databases,
memory exports, Chroma data, backups, or secrets are tracked in this
change set (verified — see §15's secret-scan result and standard `git
status` review below); no push happens without your fresh, separate,
explicit confirmation, since `d23r2/echo-v1` is a public repository.
