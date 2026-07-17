# ECHO Layer 1 — Memory Foundation v1

This document describes ECHO's long-term memory architecture: a unified memory
model, provenance/evidence, a sensitivity-gated capture pipeline, duplicate
consolidation, typed conflict detection, lifecycle/aging, hybrid retrieval,
prompt integration (MemoryBrief), deletion/forgetting, a consolidated API,
export/import, metrics, and adaptive feedback. This is not a second memory
system — it consolidates and extends the Atlas/memory-candidate/Cognitive-Core
infrastructure that already existed. See
[ECHO_LAYER_1_MEMORY_REPORT.md](ECHO_LAYER_1_MEMORY_REPORT.md) for the
delivery report and [ECHO_LAYER_1_MEMORY_SMOKE_TEST.md](ECHO_LAYER_1_MEMORY_SMOKE_TEST.md)
for the manual checklist.

## 1. Purpose

Before this milestone, Atlas stored facts with a 4-value epistemic status and
a flat confidence number, memory candidates were reviewed one at a time with
only a word-overlap "plausible conflict" flag, and the prompt injected a flat
top-K list with no scoring, no sensitivity gate, no lifecycle awareness, and
no fallback if the vector store went down. Layer 1 doesn't replace any of
that — it extends it into something that can carry Memory, Intelligence,
Wisdom, and Human Interaction layers built on top of it later, per the
milestone's own stated goal: remember the right things, in the right
structure, with the right confidence, and retrieve them safely.

## 2. Architecture: consolidation over duplication

The Phase 0 audit (delivered in chat before implementation began) found 13
existing tables already covering large parts of what this milestone asked
for: `AtlasEntry`, `MemoryCandidate`, `MemoryExtractionLog`, `KnowledgeItem`,
`ConversationSummary`, `CognitiveConcept`/`CognitiveRelationship`,
`TaskUnderstanding`, `SkillPattern`, `CausalNote`, `Project`, `Task`. The
decision, consistently applied: **extend what exists, add only what
genuinely doesn't**.

- `AtlasEntry` is the unified memory record (the spec's "MemoryRecord") —
  extended in place with ~19 new columns, not replaced by a parallel table.
- `MemoryCandidate` is the capture-pipeline candidate — extended in place.
- `CognitiveConcept`/`CognitiveRelationship` remain the world-model concept
  graph; a new, smaller `MemoryRelationship` table links individual memory
  *instances* (a documented, deliberate distinction — see §11).
- Six genuinely new, small tables exist only because nothing covered them:
  `MemoryEvidence`, `MemoryRelationship`, `MemoryConflict`,
  `MemoryConsolidationEvent`, `MemoryRevision`, `MemoryFeedback`.
- `Project`/`ConversationSummary` gained a handful of new fields rather than
  new parallel tables (§16/§17).

## 3. Memory categories

The Layer 1 taxonomy (`category` field): `profile`, `preference`, `project`,
`task`, `episodic`, `semantic`, `skill`, `relationship`, `environment`,
`temporary`. The legacy `memory_type` field (`fact`, `preference`, `mood`,
`goal`, `fear`, `capability`, `project`, `relationship`, `event`) is
untouched for full backward compatibility — every existing row, filter, and
test using it keeps working unchanged. A compatibility mapping
(`atlas.legacy_type_to_category()`) backfills `category` for legacy rows and
new writes that only specify the old field.

## 4. Unified memory schema

New `AtlasEntry` fields, all additive/default-safe: `category`,
`verification_status` (verified/partially_verified/unverified/disputed/
outdated/not_applicable), `importance` (critical/high/medium/low),
`stability` (durable/semi_stable/volatile/temporary), `retention_policy`
(permanent_until_deleted/periodic_review/expire_after_period/
conversation_only/project_lifetime/manual_only), `expires_at`,
`last_verified_at`, `last_accessed_at`, `access_count`, `capture_method`
(explicit_user_request/approved_candidate/manual_entry/project_import/
document_extraction/conversation_summary/system_generated/migration),
`project_id`, `task_id`, `source_type`, `source_reference`,
`parent_memory_id`, `supersedes_memory_id`, `contradiction_group_id`,
`duplicate_group_id`, `review_state` (none/pending_review/reviewed),
`status` (active/archived/superseded/deleted, distinct from the legacy
`outdated` boolean, which keeps its original meaning). No FK constraint on
`project_id`/`task_id` — matches this repo's existing cross-reference style
and avoids SQLite FK enforcement (Layer 0) rejecting a legitimate reference
to a soft-archived project.

## 5. Epistemic states and provenance

`epistemic_status` (Verified/Inferred/Hypothesis/Narrative, unchanged) is the
per-statement claim; `verification_status` is the richer Layer 1 lifecycle
state. `capture_method` + `source_type` + `source_reference` answer "where
did this come from" without a full evidence record for the common case;
`MemoryEvidence` exists for the less common case of multiple, possibly
conflicting pieces of evidence for one memory. User-facing provenance labels
(`memory_retrieval.py`'s `_PROVENANCE_LABELS`): "You told ECHO," "You
confirmed this," "Manually added," "From project," "From an uploaded
document," "From a conversation summary," "Inferred by ECHO," "Imported from
an earlier Atlas memory."

## 6. Candidate capture pipeline (Phase 4)

`chat.py::_extract_memory()` now runs a sensitivity gate
(`memory_privacy.py`) before any capture path: `"do not remember the next
thing I say"` blocks capture outright; a secret-shaped string is refused even
on an explicit request; highly sensitive content is refused unless the
request was explicit. Every candidate created now carries `category`,
`sensitivity_level`, `recommendation` (always `ask_user` in this build — no
path auto-accepts), and `capture_reason`. Deterministic throughout — no model
call decides whether to capture; the model's own opportunistic `MEMORY:`
block is still just parsed, not trusted for the sensitivity decision.

## 7. Sensitivity and privacy engine (Phase 16)

`backend/app/services/memory_privacy.py` — five levels (public/
ordinary_personal/private/highly_sensitive/secret), regex/keyword-only, no
model call. `classify_sensitivity()`, `is_secret()`, `can_store()`,
`can_retrieve()`, `can_display()`, `can_export()`, `redact_for_log()`
(delegates to Layer 0's `core.logging.redact()` — one redaction
implementation). Secret-shaped content (API keys, Bearer tokens, PEM
headers, card/SSN-shaped numbers, generic `key=value` credential patterns)
is never stored, full stop, no exception for explicit requests.

## 8. Duplicate detection and consolidation (Phase 5)

`backend/app/services/memory_consolidation.py` — reuses
`memory_conflicts.significant_words()` but scores similarity by
**containment** (`max(|A∩B|/|A|, |A∩B|/|B|)`), not the plain Jaccard overlap
`memory_conflicts.py` uses for its own looser "plausible conflict" flag.
Containment is the correct measure for "is B a restatement/correction/
refinement of A" — Jaccard gets diluted whenever a correction legitimately
adds new words ("port 8001" → "must run on port 8000; 8001 was temporary"
shares few words relative to the union, but nearly all of the shorter
memory's words appear in the longer one). `classify_action()` returns
`reject_duplicate` (exact match), `supersede_existing` (correction-language
detected), `update_existing` (a strict superset refinement), or `keep_both`
(below threshold). Every non-trivial action is recorded as a
`MemoryConsolidationEvent` with a reason and a `reversible` flag; history is
preserved via `MemoryRevision` and `supersedes_memory_id`/`status=superseded`
rather than a destructive overwrite.

## 9. Conflict detection and resolution (Phase 6)

`memory_conflicts.py` (extended, not duplicated) — `find_conflicts()`/
`find_all_conflicts()` (existing, unchanged, still used at candidate-creation
time) plus new `classify_conflict_type()` (environment_drift/
project_version_conflict/user_preference_change/scope_conflict/
temporal_update/confidence_conflict/direct_contradiction),
`classify_severity()` (low/medium/high — never auto-assigns `critical`,
reserved for human judgment), `recommend_resolution()` (a suggestion only),
`detect_and_record_conflicts()` (creates a `MemoryConflict` row, deduplicated
per pair), and `resolve_conflict()` (applies an explicitly-chosen resolution
— `choose_newer`/`choose_verified` supersede the losing entry,
`retain_both_with_scope`/`user_decision` change nothing). Confidence alone
never silently resolves a high-severity conflict; resolution is always an
explicit caller action.

## 10. Lifecycle and aging (Phase 7)

`backend/app/services/memory_lifecycle.py` — `activate`/`mark_needs_review`/
`mark_verified`/`mark_outdated`/`archive`/`restore`/`supersede`, plus
`run_maintenance()` (idempotent, never deletes): expires memories past
`expires_at`, flags category-specific stale memories for review using
per-category intervals (environment: 14 days, project/task: 30 days,
everything else: never auto-flagged by age alone — reviewed on contradiction
instead, per the milestone's own guidance). A real bug was caught and fixed
here during testing: SQLite drops tzinfo on `DateTime(timezone=True)`
read-back (confirmed empirically), so `datetime.now(UTC) - entry.created_at`
would have raised a naive/aware subtraction `TypeError` in production;
fixed by comparing against a naive "now" consistently.

## 11. Memory relationships and the graph decision (Phase 2)

**Documented decision**: `MemoryRelationship` is a separate, smaller graph
layer from `CognitiveConcept`/`CognitiveRelationship`, not a reuse of it.
`CognitiveConcept` models named *world concepts* (one node for "Ollama," one
for "the ECHO repo") that many different memories can independently relate
to; `MemoryRelationship` links individual *memory statements* to each other
(this specific "port 8001" memory supersedes that specific "port 8000"
memory). Conflating the two would mean every memory-to-memory edge also
polluting the world-model graph with instance-level noise. 19 relationship
types (`related_to`, `supersedes`, `contradicts`, `duplicates`, etc.), no FK
constraint (matches `CognitiveRelationship`'s own precedent), a unique
constraint on `(source, target, type)` to prevent duplicate edges,
`status=deactivated` (not deleted) when either endpoint is removed.

## 12. Hybrid retrieval (Phase 8)

`backend/app/services/memory_retrieval.py::retrieve()` — semantic search
(Atlas/Chroma) plus a lexical/metadata fallback that **always** runs for
project/task-scoped requests (not just when Chroma is down), matching the
rule that hybrid retrieval must function on metadata/keyword/project-scope/
recency alone. Scoring combines semantic similarity, importance, confidence,
verification bonus, project-scope bonus, a contradiction penalty (open
conflict — still returned, never silently hidden), an outdated penalty, and
a small, capped adaptive-feedback nudge (§18). Sensitivity gating
(`memory_privacy.can_retrieve()`) runs before scoring, not after. A
Chroma-unreachable exception degrades to the lexical path automatically —
verified with a live test that monkeypatches `atlas.search` to raise.

## 13. Local embeddings and index (Phase 9)

Already satisfied by the pre-existing `atlas.py` (local
`sentence-transformers/all-MiniLM-L6-v2` via ChromaDB, no cloud embedding
call anywhere). Layer 1 adds *visibility*, not a new index:
`backend/app/services/memory_index.py`'s `status()`, `find_orphans()`
(SQL rows missing from the index vs. index vectors missing a SQL row),
`repair_index()` (fixes both directions), `rebuild_index()` (full re-embed,
SQL untouched — SQL is always the source of truth).

## 14. Prompt integration: MemoryBrief (Phase 10)

`persona.py::_atlas_context_for()` now delegates to
`memory_retrieval.build_memory_brief()`, which calls `retrieve()` and
formats a compact block: content, epistemic status, confidence, and — only
when relevant — a short "(due for re-verification)" or "(has an unresolved
conflicting memory)" note. Never includes a raw memory ID, an internal
score, or hidden reasoning. The function still returns the same
`list[AtlasCitation]` shape every existing caller (the `atlas_citations`
response field, the Human Persona overlay, conflict detection) already
depended on, so nothing downstream needed to change — verified via the full
regression suite (995/995) plus a live-corrected unit test
(`test_persona_conversation_recall.py`, which needed its monkeypatch target
updated from `app.persona.atlas.search` to `app.atlas.search` since
`persona.py` no longer imports `atlas` directly).

## 15. Conversation summaries and project memory (Phase 11/12, lightweight)

`ConversationSummary` gained `summary_type` (rolling/final/topic/
project_update/decision_log, defaulting to `final` — the only kind this app
generates today, documented honestly rather than building four unused
generator paths) and `candidate_memory_ids_json`. `Project` gained
`objective`, `constraints_json`, `decisions_json`, `blockers_json`,
`last_reviewed_at` — a lightweight profile, not a separate
`ProjectMemoryProfile` table, since `Project` was already the first-class
identity. An auto-update hook: completing a task via the existing
`"mark task X done"` chat command now appends a short "Completed: <task>"
note to its project's `decisions_json` and bumps `last_touched_at` — a real,
tested example of the milestone's "milestone completed → project memory
updates automatically" rule.

## 16. Document memory — known limitation

Full chunked-document memory (`DocumentRecord`/`DocumentChunk`, page/section
references, checksummed dedup) was **not built this pass**. `Attachment`
already tracks per-file `analysis_status`, and `MemoryCandidate`/
`AtlasEntry.source_type` can already cite `document_extraction` as a
provenance type — but there's no chunking or embedding pipeline for
uploaded documents yet. Documented here rather than silently skipped; a
reasonable Layer 2 candidate.

## 17. Privacy, deletion, and forgetting (Phase 16/17)

`atlas.delete_entry()` was already a real, hard delete (SQL row + Chroma
vector) — Layer 1 added relationship cleanup (`MemoryRelationship` rows
touching the deleted id are set `status=deactivated`, never left dangling).
A new chat-level `"forget that"` handler
(`chat_actions.try_handle_forget_action()`) archives — never hard-deletes —
the single most recently captured memory, and only when there's exactly one
candidate in a 10-minute window; zero or multiple matches point the user at
Memory Center instead of guessing. This is the one deliberate exception to
this app's existing "destructive actions stay UI-only" rule (documented in
`chat_actions.py`'s own module docstring), justified because archiving is
fully reversible.

## 18. Metrics and adaptive feedback (Phase 20/21, lightweight)

`GET /api/memory/metrics` — live-computed provenance/verification coverage,
stale-memory percentage, unresolved-conflict percentage, plus Layer 0's
`core.metrics` retrieval counters. `MemoryFeedback` + `record_feedback()` +
a capped ranking nudge in `_score()` (max ±0.06 total, from at most 3 samples
per direction) — a single negative rating can never erase a strong base
score (verified by a dedicated test), and nothing here ever changes a
memory's actual content or confidence.

## 19. Consolidated API (Phase 18)

`backend/app/routers/memory.py`, `/api/memory/*` — additive alongside
`/api/atlas/*` and `/api/memory-candidates/*`, neither of which changed.
Records (list/get/patch/delete/archive/restore/confirm/mark-outdated),
search, context-preview, conflicts (list/resolve), maintenance, index
(status/rebuild/repair), export/import (preview/commit), stats, metrics,
per-memory feedback. Literal-path routes (`/search`, `/conflicts`,
`/metrics`, ...) are registered before the `/{memory_id}` catch-all, since
Starlette matches in registration order.

## 20. Export, import, and portability (Phase 19)

`backend/app/services/memory_export.py` — export excludes embeddings,
internal prompts, secrets, and highly-sensitive content by default
(`memory_privacy.can_export()`). **Import never writes directly to active
memory** — every accepted record is staged as a `MemoryCandidate` for the
same human-review queue explicit/opportunistic capture already uses, so
"never overwrite active memories silently" holds by construction, not by
convention. `preview_import()` is a true dry run (no DB writes); duplicate
detection reuses `memory_consolidation.find_duplicates()`; secrets are
rejected at both preview and commit time; schema-version mismatches are
rejected outright.

## 21. User controls: Memory Center (Phase 14)

`frontend/src/components/memory/MemoryCenterView.tsx` (Advanced → Knowledge
& Memory → Memory Center) — overview stats, category/status/needs-review
filters, per-memory cards (content, category, status, confidence, epistemic
status, provenance, access count) with archive/restore/confirm/
mark-outdated/delete actions (delete requires a native confirm dialog), a
conflicts-needing-review section with one-click resolution buttons, a
"Run maintenance" button, and a JSON export download. Deliberately reuses
the existing `AtlasView.tsx`/`MemoryCandidates.tsx` pages rather than
duplicating their list/edit/candidate-review UI — Memory Center is the new,
richer Layer 1 surface, not a replacement.

## 22. Settings

`SettingsView.tsx` gained a compact "Memory" section: live active/pending/
conflict counts and a pointer to Memory Center. Granular per-category
privacy toggles (auto-accept low-risk preferences, ask-before-storing-
profile-facts, sensitive-capture policy dropdown) from the spec's suggested
Settings list were **not added as persisted UI toggles** this pass — the
underlying safety behavior (secret rejection, highly-sensitive gating) is
already enforced in code regardless of any toggle, and adding a UI control
that could let a user weaken it was judged lower-value than the core
capture/retrieval/lifecycle work. Documented as a known limitation, not a
silent omission.

## 23. Tests

129 new backend tests across 12 files (`test_layer1_privacy.py`,
`test_layer1_candidates.py`, `test_layer1_consolidation.py`,
`test_layer1_conflicts.py`, `test_layer1_lifecycle.py`,
`test_layer1_retrieval.py`, `test_layer1_index.py`, `test_layer1_deletion.py`,
`test_layer1_api.py`, `test_layer1_export_import.py`,
`test_layer1_project_memory.py`, `test_layer1_metrics_feedback.py`), plus one
existing test file fixed for the new prompt-integration wiring
(`test_persona_conversation_recall.py`). All use the isolated `db_session`
fixture or the shared-but-redirected app DB, same as the rest of this suite
— never the real user database or real vector store (conftest.py's
`DATABASE_URL`/`CHROMA_DIR` redirection, unchanged).

## 24. Rollback procedure

Every schema change is additive (`_ensure_layer1_memory_columns()` in
`db.py`, six new tables) — no destructive migration. `CURRENT_SCHEMA_VERSION`
bumped to 2. Reverting the modified files (`atlas.py`, `chat_actions.py`,
`db.py`, `main.py`, `memory_conflicts.py`, `models.py`, `persona.py`,
`routers/chat.py`, `routers/memory_candidates.py`, `routers/projects.py`,
`schemas.py`, plus the frontend `client.ts`/`App.tsx`/`Sidebar.tsx`/
`SettingsView.tsx`) to their pre-Layer-1 state restores the pre-Layer-1
system exactly, since every change was additive (new fields, new functions,
new routes) rather than a replacement of existing logic. New files
(`services/memory_*.py`, `routers/memory.py`, the new test files, the new
frontend page) can simply be deleted with no effect on anything else. Back
up `backend/data/echo.db` before any schema-affecting rollback, per this
repo's standing recommendation (`scripts/backup_echo_data.ps1`, Layer 0).

## 25. Future Layer 2 integration

This foundation is built to support later layers as named in the milestone:
`MemoryRetrievalRequest`/`Result` and `build_memory_brief()` give a
Cognitive/Systems-Thinking/Simulation/Decision engine a stable, typed
interface to query memory without touching Atlas/Chroma directly;
`MemoryRelationship` gives a future reasoning engine a graph to traverse;
`MemoryConflict`/`MemoryConsolidationEvent` give a future Reflection Engine
an audit trail of what ECHO already knows it's uncertain about; the
category/importance/stability taxonomy gives an Adaptive Learning or
Teaching Engine a way to distinguish "durable fact about the user" from
"transient environment detail" without re-deriving that distinction itself.
