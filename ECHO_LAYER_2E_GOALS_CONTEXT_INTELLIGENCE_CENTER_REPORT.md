# ECHO Layer 2E — Goal Manager, Context Selection v2, and Intelligence Center — Delivery Report

See [ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md](ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md)
for the full design and
[ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_SMOKE_TEST.md](ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_SMOKE_TEST.md)
for the manual checklist. **This is the final Layer 2 milestone.**

## Overall status: Green

1296/1296 backend tests pass (63 new), `ruff check .` clean, frontend `tsc -b --noEmit` and
`npm run build` both clean, live-verified in a real browser against an isolated temporary backend
(`CONTEXT_SELECTION_V2_ENABLED=true`) — created a real goal via the Goals tab and watched it appear
as `APPROVED` immediately (explicit-user origin); expanded it and confirmed an honest `0% complete
(0/0 task(s), 0/0 plan step(s)) — stalled` reading with the status-correct action set (Pause/Abandon/
Review, no Approve); ran a cross-goal Review and got a real recommendation back; in the Context tab, a
simple unlinked message correctly returned an empty bundle (nothing fabricated), and a complexity-
triggering message returned a real, populated `CognitiveBrief` (Goal/Domain/Task type/Known/Unknown/
Constraints/Success-criteria/Watch-out-for/Next-step) at 816/12000 chars with no forced compression;
the Overview tab's health banner, stat cards, and routing-status summary all rendered from the real
`GET /api/intelligence/overview` response. Secret scan: same pre-existing findings as every prior
milestone (Layer 0/1 test fixtures only), zero in any Layer 2E file.

## Architecture audit

**Existing systems reused, not reimplemented**: `Plan`/`Milestone`/`PlanStep`/`materialise_plan()`
(Layer 2C) serve as a goal's concrete subgoal structure via a new nullable `Plan.goal_id`, rather than
a parallel hierarchy. `context_gatherer.gather_context()`'s existing `GatheredContext` dataclass and
char-budget precedent are wrapped, not replaced, by `context_selector.py`. `evaluation_lab.py`'s
existing `_CHECKS`-dict pattern is extended with 6 new deterministic checks rather than a second
evaluator. The Intelligence Center deep-links to Systems/Simulations/Decisions/Plans/Routing/
Evaluations in their existing homes (Mission Control, Cognitive Core) instead of duplicating their
controls.

**Duplicate systems avoided**: no second progress-tracking mechanism; no second retrieval layer; no
second evaluation runner; `_decision_or_plan_context_for()` deliberately returns `None` for an
unscoped request rather than surfacing an arbitrary "most recent" decision system-wide.

**Major design decisions**: goal `status` *is* the approval gate — no separate `approval_state`
field. Progress is evidence-only (`Task.status=="done"` / approved-plan `PlanStep.status=="completed"`)
— never a model estimate, never fabricated on zero evidence. `context_selection_v2_enabled` defaults
`False`; the integration point is `local_intelligence_engine`'s task-oriented generation path, not
the main chat persona (`persona.py`), specifically to keep the battle-tested primary chat prompt
builder untouched.

## Memory model

**Models added**: `Goal`, `GoalReview`, `ContextSelectionMetric` (3 new tables). **Columns added**:
`Task.goal_id`, `Plan.goal_id` (both nullable). **Migration approach**: `_ensure_column()` for the two
new columns, `Base.metadata.create_all()` for the new tables, `CURRENT_SCHEMA_VERSION` 6 → 7.
**Legacy compatibility**: all 1233 pre-2E tests pass unchanged.

## Goal model (Phase 1)

`GoalCreate`/`GoalUpdate`/`GoalOut` cover the full lifecycle; `GoalOut`'s field names were corrected
during development to exactly match the model's `*_json` attribute names (`success_criteria_json`,
`constraints_json`) after a live `ResponseValidationError` caught the mismatch — matching the existing
`DecisionCaseOut` convention. Explicit-user goals are created `approved` immediately; system-suggested
goals stay `proposed` until an explicit approve call. Tested for both origins, and for
`approve_goal()` rejecting a non-`proposed` goal.

## Goal hierarchy and progress (Phase 2)

`parent_goal_id` gives a tree; `compute_progress()` recurses cycle-guarded into children. Evidence is
exactly `Task.goal_id` matches with `status=="done"`, plus `PlanStep`s under goal-linked plans whose
own status is `approved/active/blocked/completed` (a `proposed` plan's steps don't count). Tested:
zero-evidence goals report `0%` never a guess; a proposed plan's steps are excluded while an approved
plan's count; `maybe_mark_achieved()` only fires with real, complete evidence and never from a
plan/step alone without `total_evidence > 0`.

## Goal review and next-action engine (Phase 3)

`generate_review()` ranks candidates by `(has_blockers, priority_rank, target_date_or_created_at)` —
a self-caught fix during development: the initial filter excluded any goal with blockers from
recommendation entirely, meaning an all-blocked goal set produced no recommendation at all. Fixed to
include blocked-but-actionable goals (recommend resolving the blocker), verified via a direct smoke
test before any test file claimed it worked. `low_energy=True` changes only which item is
recommended — tested explicitly that it never mutates goal status/priority as a side effect.
`_conflicting_commitment_notes()` flags high-priority goals with `target_date`s within 7 days of each
other.

## Context Selection v2 — ContextRequest/ContextBundle (Phase 4)

`select_context()` composes memory/project/goal/system/decision-or-plan context plus skills/
permissions into one `ContextBundle`. Two gaps were self-identified and closed during code review,
before any test claimed them (see Bugs fixed below): an unscoped decision-query fallthrough, and a
missing exception guard around `context_gatherer.gather_context()`'s memory step. `ContextPreviewOut`
was renamed to `ContextSelectionPreviewOut` after `ruff check` caught a name collision with an
existing Layer 2A schema.

## Context budgeting and compression (Phase 5)

`_apply_budget()` walks `_COMPRESSION_ORDER` (provenance/tool-evidence/documents/system/decision-or-
plan/project/memory/goal/cognitive-brief, lowest-priority-first) only when the bundle exceeds budget,
setting `compressed: true`. Tested for: staying under budget with no compression, forced compression
respecting field priority, and exact-duplicate tool-evidence/document deduplication.

## Cross-layer integration — prompt builder consumes ContextBundle (Phase 6)

Confirmed as one coherent chain, not independently-passing pieces, via
`test_end_to_end_request_to_goal_progress_pipeline`: a user message → `LocalIntelligenceEngine`
(with `context_selection_v2_enabled=true`, a real linked `Goal`, and a real linked `Task`) →
a generated answer → marking the task done → `compute_progress()` correctly reporting `100.0%` →
`maybe_mark_achieved()` correctly flipping the goal to `achieved`. A second test,
`test_context_bundle_goal_context_reaches_the_draft_prompt`, confirms the goal's title literally
appears in the system prompt string sent to the model when the flag is on. Flag-off behavior was
directly diffed against pre-2E `pipeline_steps` output and found byte-identical.

## Backend API — goals + intelligence endpoints (Phase 7)

`/api/goals/*` (create/list/get/patch/approve/pause/abandon/progress/review) and
`/api/intelligence/{context/select, context/preview, goals/review, evaluations/run, overview}`. All
service-layer `ValueError`s become `400`. `GET /overview`'s `intelligence_health` reuses `system.py`'s
existing `_database_healthy()`/`_ollama_health()` checks rather than re-deriving health logic.

## Layer 2 evaluation suite (Phase 8)

6 new deterministic checks (zero model calls), 11 new fixture cases (10 → 21 total), spanning all 8
required categories plus the explicit context-comparison requirement
(`_check_layer2_context_comparison`: the same message's bundle must differ — `goal_context` present
vs. `None` — with vs. without a real `Goal` linkage). Two fixture cases (`explanation`,
`project_continuation`) are documented as accepting a `warning` outcome rather than a forced pass —
no reliable trigger message was found for those specific categories without fabricating the result or
drifting into a more-honest adjacent category; recorded in the fixture's own `notes` field.

## Frontend: Intelligence Center

New `IntelligenceCenterView.tsx` (Overview/Goals/Context tabs), reached via Advanced → Knowledge &
Memory → Intelligence Center. `Sidebar.tsx`'s `ADVANCED_NAV_GROUPS` gained one entry; `MobileDrawer.tsx`
needed no changes (already generically iterates that export). Live-verified end-to-end: goal
creation/expand/progress/pause/abandon/review, cross-goal review, and both an empty and a populated
context preview.

## Backend full tests

`cd backend && .venv/Scripts/python.exe -m pytest -q` → **1296 passed** (63 new). `ruff check .` →
**All checks passed!**

## Frontend typecheck/build

`npx tsc -b --noEmit` → clean. `npm run build` → clean, 327 modules.

## Files changed

**New backend**: `services/goal_engine.py`, `services/context_selector.py`, `routers/goals.py`, 5 new
test files (63 tests total).

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `config.py`, `main.py`,
`routers/intelligence.py`, `services/local_intelligence_engine.py`, `services/evaluation_lab.py`,
`fixtures/evaluation_lab_cases.json`, `tests/test_evaluation_lab.py` (3 pre-existing assertions
updated for the fixture count growing from 10 to 21, a direct and expected consequence of Phase 8).

**New frontend**: `components/intelligence/IntelligenceCenterView.tsx`.

**Modified frontend**: `api/client.ts` (Layer 2E types + 14 new functions), `components/Sidebar.tsx`
(`View` type + nav entry), `App.tsx` (import + render wiring).

**New docs**: this report, the architecture doc, the smoke test doc.

## Bugs fixed

- **Unscoped decision-query fallthrough (self-caught during code review, before any test was
  written)**: `_decision_or_plan_context_for()`'s initial logic fell through to querying *all*
  `DecisionCase` rows and returning the globally most-recent one when neither `project_id` nor
  `goal_id` was provided (`DecisionCase` has no `goal_id` column). Fixed so a decision is only ever
  looked up when `project_id` is explicitly set — an unscoped call now honestly returns `None` rather
  than surfacing an arbitrary unrelated decision as if it were relevant.
- **Missing exception guard around the memory-gathering step (self-caught during code review)**:
  `context_gatherer._gather_memory()` calls `atlas.search()` directly (not `memory_retrieval.py`'s
  newer fallback-aware path) with no try/except of its own — a genuine Chroma failure would have
  propagated up and crashed `select_context()`, contradicting the milestone's own "never raises"
  requirement. Fixed by wrapping the `gather_context()` call, falling back to an empty
  `GatheredContext()` with `fallback_used=True` and an honest `excluded_context_summary` entry —
  verified via a monkeypatch-to-raise test.
- **All-blocked goal sets produced no recommendation (self-caught before any test claimed it
  worked)**: `generate_review()`'s initial candidate filter excluded any goal with blockers,
  meaning a goal set where every actionable goal happened to be blocked produced zero
  recommendations. Fixed the filter and sort key so a blocked-but-actionable goal is still eligible
  (recommend resolving the blocker) — verified directly before the corresponding test was written.
- **Schema field-name mismatches (`GoalOut`/`GoalReviewOut`), caught via a live `TestClient` smoke
  test**: the Pydantic schemas initially used field names without the model's `_json` suffix
  (`success_criteria` vs. `success_criteria_json`, etc.), producing a `ResponseValidationError`.
  Fixed by exactly matching the SQLAlchemy model's attribute names, per the established
  `DecisionCaseOut` convention.
- **`ContextPreviewOut` name collision, caught by `ruff check`**: the new Context Selection v2
  preview schema collided with an existing, unrelated Layer 2A schema of the same name. Renamed to
  `ContextSelectionPreviewOut`.
- **SQLite naive/aware datetime `TypeError`**: `compute_progress()`'s staleness check and
  `_conflicting_commitment_notes()`'s date-diff both hit a naive-vs-aware subtraction error because
  SQLite doesn't preserve `tzinfo` on round-tripped `DateTime(timezone=True)` values, even though
  `_now()` returns tz-aware UTC — the same known class of bug previously fixed for `Schedule.due_at`.
  Fixed with a local `_as_aware()` helper in `goal_engine.py`.
- **Flawed test assumption about semantic-memory relevance (self-caught after a live pytest run)**:
  a Layer 2E test asserted that an unrelated Atlas memory would never surface for a completely
  unrelated query — but `atlas.search()` has no similarity threshold anywhere in the codebase; with
  only one entry in the vector store, top-k search always returns it regardless of true relevance.
  This is honest, pre-existing Layer 1 behavior, not a Layer 2E regression. Fixed by replacing the
  test with two that verify what Context Selection v2 actually guarantees: a real stored memory does
  surface verbatim when relevant, and the `freshness_requirement="current"` fallback path fires
  correctly (via a monkeypatch, since these tests make no network calls).
- **Stale hardcoded fixture-count assertions (caught by the full regression run, expected
  consequence of Phase 8)**: `tests/test_evaluation_lab.py` had three assertions hardcoding the
  pre-2E fixture count of 10. Updated to 21, matching Phase 8's own required fixture expansion.

## Bugs not fixed

None outstanding in Layer 2E code. Pre-existing items from `PROGRESS.md`'s Blockers section remain
open and are unrelated to this milestone.

## Manual checks remaining

- The full smoke-test doc's steps were spot-verified (goal creation/expand/progress/pause/abandon/
  review, cross-goal review, an empty and a populated context preview, the Overview tab) but the
  Context tab's UI doesn't yet expose `goal_id`/`project_id` inputs, so a goal-scoped context preview
  was verified via the automated suite and the Goals tab's own per-goal progress view rather than a
  single combined UI control (documented in the architecture doc's Known limitations).
- The schema migration (v6 → v7) has not yet been applied to the real running backend's database —
  purely additive (two new columns, three new tables) by construction, exercised only against a fresh
  temp DB and the automated suite so far.
- `ContextSelectionMetric` rows are written on every real selection but have no dedicated viewer —
  data exists for future budget-tuning work, not surfaced today.

## Rollback instructions

See [Architecture doc §11](ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md#11-rollback-procedure).
Summary: every schema change is additive (two new nullable columns, three new tables); reverting the
10 modified backend files and 3 modified frontend files, and deleting the 3 new service/router files
and 5 new test files, restores pre-2E behavior exactly. `context_selection_v2_enabled` already
defaults to `False`, so no behavior change is live until explicitly turned on.

## Is Layer 2E — and Layer 2 overall — ready as a release candidate?

**Green as a local release candidate.** Not pushed anywhere. This closes out Layer 2
(2A Cognitive Core → 2B Systems/Simulation → 2C Decision/Planning → 2D Orchestration/Tools → 2E
Goals/Context/Intelligence Center) as one coherent, evidence-based intelligence stack — the
completion-gate chain (user request → CognitiveBrief → context → goal progress, with
decision/plan/orchestration context folded in when scoped) is exercised end-to-end by the automated
suite and spot-verified live. Ready to be tagged `echo-layer-2e-goals-context-intelligence-center-rc`
after your review of `git status`/`git diff --stat`. No Layer 3 prompt has been started, and none will
be without a fresh, explicit go-ahead.

## Proof table

| Proof item | Result |
|---|---|
| Goal model | pass |
| Goal approval policy | pass |
| Hierarchy and progress | pass |
| Evidence-based completion | pass |
| Blocker detection | pass |
| Next-action engine | pass |
| ContextRequest/Bundle | pass |
| Cross-layer deduplication | pass |
| Privacy/freshness filtering | pass |
| Budget and compression | pass |
| Prompt integration | pass |
| Unified Intelligence Center | pass |
| Goal UI | pass |
| Context preview | pass |
| Layer 2 evaluation suite | pass |
| End-to-end intelligence flow | pass |
| Backend full tests | pass (1296/1296) |
| Frontend typecheck/build | pass |
