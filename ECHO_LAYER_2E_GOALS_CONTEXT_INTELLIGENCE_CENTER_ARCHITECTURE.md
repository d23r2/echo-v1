# ECHO Layer 2E — Goal Manager, Context Selection v2, and Intelligence Center — Architecture

This is the final Layer 2 milestone. It adds long-running goal tracking, a single deterministic
context-selection surface that the rest of Layer 2 can consume, and a unified Intelligence Center
page that ties Layers 2A-2E together without duplicating any of their controls.

## 0. Phase 0 audit — what already existed, what's genuinely new

Three build-vs-reuse questions were resolved before any code was written:

1. **Does Goal need its own subgoal/milestone/task hierarchy?** No. `Plan`/`Milestone`/`PlanStep`/
   `materialise_plan()` (Layer 2C) already model "objective → ordered steps → real Tasks." `Goal`
   gets a nullable `Plan.goal_id` (and a nullable `Task.goal_id` for ad hoc goal-tracked tasks not
   part of a formal plan) rather than a parallel structure.
2. **Does Context Selection v2 need a new retrieval layer?** No. `context_gatherer.gather_context()`
   already assembles a near-`ContextBundle`-shaped `GatheredContext` (memory/project/library/web
   context, source names, warnings) with its own char-budget precedent. `context_selector.py` wraps
   it and adds only what's genuinely new: goal/system/decision-or-plan context, cross-field
   deduplication, and a single compact `ContextBundle` shape.
3. **Does the evaluation suite need a new evaluator?** No. `evaluation_lab.py`'s existing
   fixture-driven `_CHECKS` dict is extended with 6 new deterministic check functions and 11 new
   fixture cases, each delegating to an already-tested Layer 2A-2D system directly. Zero model calls
   anywhere in the file, matching its existing convention.

## 1. Goal model

`Goal` (new table): `title`, `description`, `scope` (free-text, no rigid taxonomy), `origin`
(`explicit_user` | `system_suggestion`), `owner`, `status` (`proposed → approved → active → paused |
blocked → achieved | abandoned | superseded` — status *is* the approval gate, no separate
`approval_state` field), `priority`, `horizon`, `target_date`, `success_criteria_json`,
`constraints_json`, `motivation`, `project_id`/`parent_goal_id` (loose string refs, not FKs — same
convention as `Task.project_id`), `confidence`, and lifecycle timestamps
(`approved_at`/`achieved_at`/`abandoned_at`/`abandoned_reason`/`superseded_by_goal_id`).

**Approval policy**: a goal with `origin="explicit_user"` is created `approved` immediately — you
said it, it's yours. A goal with `origin="system_suggestion"` is created `proposed` and stays that
way until an explicit `approve` call. This is the only approval gate; there is no second
`approval_state` to keep in sync.

`GoalReview` (new table) stores the output of a cross-goal review pass (see §3).
`ContextSelectionMetric` (new table) stores per-selection budgeting telemetry (categories
included/excluded, chars used vs. budget, whether compression/fallback fired) for future tuning —
written but not yet surfaced in any UI.

## 2. Goal hierarchy and evidence-based progress

`parent_goal_id` gives goals a tree; `compute_progress()` recurses into children (cycle-guarded)
and reports each child's own progress alongside the parent's.

**Progress is never estimated.** `compute_progress()` counts exactly two evidence sources:
`Task.status == "done"` where `Task.goal_id` matches, and `PlanStep.status == "completed"` where the
step's `Plan.goal_id` matches *and* that plan's own status is one of
`approved/active/blocked/completed` (a `proposed` plan's steps don't count — nothing has actually
been approved to work on yet). `percent_complete = round(done/total * 100, 1)` if `total > 0`, else
`0.0` — a goal with zero linked evidence is `0%`, never a guess.

**Blocker detection**: any `blocked` task or `blocked` plan step under the goal (or a `blocked`
child goal, surfaced as `"Subgoal blocked: <title>"`) becomes a blocker string.
**Next-action engine** (`_next_action_item()`): in low-energy mode, prefers the first open task over
a plan step (smaller unit of work); otherwise prefers the first *unblocked* item, falling back to
the first item overall if everything is blocked — a blocked item can itself be surfaced as "the next
action" (resolve the blocker), rather than the engine going silent.
**Staleness**: a goal in `proposed/approved/active` with zero evidence, or whose most recent linked
task/step activity is more than 14 days old, is flagged `stale: true`.

**Evidence-only auto-achieve**: `maybe_mark_achieved()` only fires from
`approved/active/blocked`, only when `total_evidence > 0` and `percent_complete >= 100.0` — a goal
with no linked evidence can never silently become `achieved`.

## 3. Goal review and next-action engine

`generate_review()` produces a `GoalReview`: which goals are stalled, which have no next action,
which have unresolved blockers, and a single recommended next action across *all* goals — ranked by
`(has_blockers, priority_rank, target_date_or_created_at)`, so a blocked-but-still-actionable goal
(recommend resolving its blocker) is preferred over one that's simply idle, and unblocked
high-priority work is preferred over both. `_conflicting_commitment_notes()` flags pairs of
high-priority goals whose `target_date`s fall within 7 days of each other — a lightweight, honest
signal, not a scheduling solver. `low_energy=True` changes only which item gets *recommended*; it
never mutates any goal's status or priority as a side effect.

## 4. Context Selection v2 — ContextRequest / ContextBundle

`ContextRequest`: `user_message`, `task_id`, `purpose`, `project_id`, `goal_id`, `conversation_id`,
`required_context_types`, `privacy_level` (reuses Layer 2D's `PrivacyLevel`), `freshness_requirement`
(`any`/`recent`/`current`), `max_tokens`/`max_chars`.

`ContextBundle`: one compact object — `cognitive_brief`, `memory_brief`, `goal_context`,
`project_context`, `relevant_skills`, `relevant_documents`, `system_or_simulation_context`,
`decision_or_plan_context`, `tool_evidence`, `active_permissions`, `uncertainty_summary`,
`provenance_summary`, `excluded_context_summary` (internal/diagnostic — why something was left out,
never hidden reasoning about the *answer*), plus `total_chars`/`budget_chars`/`compressed`/
`fallback_used`.

`select_context()` composes: `context_gatherer.gather_context()` for
memory/project/library/web/wiki/rss context; `get_cognitive_brief_for_message()` (Layer 2A) for the
brief; `skill_library.suggest_plan()` (Layer 2A) for relevant skills; new scoped lookups for
goal/system/decision-or-plan context (below); `list_permissions()` for active permissions. It never
raises — see the fallback behavior in §"Bugs fixed" below.

**Deterministic status/relevance filtering** — nothing here is a similarity score, all of it is a
plain status check:
- `_goal_context_for()`: returns `None` (and records an `excluded_context_summary` entry) unless the
  goal exists and its status is one of `proposed/approved/active/paused/blocked` — an abandoned or
  superseded goal, or a `goal_id` that doesn't exist, never surfaces fabricated context.
- `_decision_or_plan_context_for()`: a decision is only ever looked up when `project_id` is
  explicitly set (`DecisionCase` has no `goal_id` column, so there is no goal-scoped path for it) —
  an unscoped call intentionally returns `None` rather than an arbitrary "most recent decision
  system-wide." A plan is looked up by `goal_id` first, then `project_id`, and only among
  `approved/active/blocked` statuses — a `cancelled` or `proposed` plan is excluded.
- `_system_context_for()`: the latest non-archived `SystemModel` for the given `project_id`.

## 5. Context budgeting and compression

`_apply_budget()` sums the char counts of `_COMPRESSION_ORDER` — provenance_summary, tool_evidence,
relevant_documents, system_or_simulation_context, decision_or_plan_context, project_context,
memory_brief, goal_context, cognitive_brief, listed lowest-priority-first — and, only if the total
exceeds `budget_chars`, walks that list popping list items or clearing string fields until under
budget, setting `compressed: true`. `cognitive_brief`/`goal_context`/`memory_brief` are the last
fields touched — this is the "budget forces degradation, load-bearing fields survive longest"
pattern already established in Layer 2D's own budget enforcement. `budget_chars` defaults to
`max_chars`, then `max_tokens * 4`, then `settings.local_context_max_chars`.

Deduplication: `tool_evidence` (wiki+rss+web) and `relevant_documents` both use
`list(dict.fromkeys(...))` — exact-duplicate strings that legitimately arrive from two different
sources (e.g. a wiki snippet and an RSS item covering the same headline) collapse to one entry,
order-preserving.

## 6. Cross-layer integration — prompt builder consumes ContextBundle

`local_intelligence_engine.generate_response()`'s Step 2 branches on a new, **default-off** flag
(`settings.context_selection_v2_enabled`). When off, behavior is byte-identical to pre-2E
(confirmed via a direct `pipeline_steps` comparison test). When on: `context_selector.select_context()`
runs, and a new adapter, `_context_bundle_to_gathered()`, converts the resulting `ContextBundle`
back into the engine's existing `GatheredContext` shape — folding `goal_context`/
`system_or_simulation_context`/`decision_or_plan_context` into `project_context` lines, so the
already-tested, unmodified `_build_draft_system_prompt()`/`_context_block()` functions require zero
changes. This was the deliberate integration point chosen in the Phase 0 audit specifically so the
battle-tested main chat prompt builder (`persona.py build_system_prompt()`) stays untouched — Layer
2E only reaches the *task-oriented* generation path, not the primary chat persona.

## 7. Backend API

`routers/goals.py` (`/api/goals`): `POST ""`, `GET ""` (status/project_id/parent_goal_id filters),
`GET "/{id}"`, `PATCH "/{id}"`, `POST "/{id}/approve"`, `POST "/{id}/pause"`, `POST "/{id}/abandon"`
(requires a non-empty reason), `GET "/{id}/progress"` (also triggers `maybe_mark_achieved()` as a
side effect — checking progress is exactly the moment a completed goal should flip), `POST
"/{id}/review"`. All service-layer `ValueError`s (invalid status transitions) become `400`.

`routers/intelligence.py` additions: `POST /context/select`, `POST /context/preview` (a UI-safe
summary — categories included/excluded, `provenance_summary`, estimated chars, never raw content),
`POST /goals/review` (cross-goal review), `POST /evaluations/run` (an existing endpoint's route
alias, reused rather than duplicated), and `GET /overview` — the single endpoint the Intelligence
Center's Overview tab consumes, aggregating goal counts, current task, active plan, recent
decisions/simulations, blockers, routing status, last evaluation result, and a computed
`intelligence_health` (`green`/`yellow`/`red`, reusing `system.py`'s existing
`_database_healthy()`/`_ollama_health()` checks rather than re-deriving health logic).

## 8. Layer 2 evaluation suite

Six new deterministic check functions, each calling an already-tested system directly — zero model
calls: `_check_task_understanding_category` (Layer 2A), `_check_context_relevance` (this milestone's
own `select_context()`), `_check_plan_validity`/`_check_decision_transparency` (Layer 2C),
`_check_tool_efficiency` (Layer 2D's `tool_strategy.build_tool_plan()`), and
`_check_layer2_context_comparison` — the literal "compare with and without Layer 2 features"
requirement, implemented as a concrete assertion: the same message's `ContextBundle` must differ
(`goal_context` present vs. `None`) with vs. without a real `Goal` linkage. 11 new fixture cases
extend `evaluation_lab_cases.json` from 10 to 21, spanning explanation/coding/debugging/planning/
decision/research/project-continuation/tool-use categories plus the context-comparison case. Two
cases (`explanation` and `project_continuation`) are documented as accepting a `warning` outcome —
`cognitive_core.is_complex_task()`'s existing gating didn't reliably classify every candidate message
as complex enough to produce a `TaskUnderstanding`, and no reliable trigger message was found without
either fabricating a pass or drifting into a different, more-honest category (a debugging-framed
"why is my code slow" message, for instance, correctly classifies as `debugging`, not
`explanation`). This is recorded honestly in the fixture's `notes` field rather than forced to pass.

## 9. Frontend — Intelligence Center

A new additive page (`IntelligenceCenterView.tsx`, reached via Advanced → Knowledge & Memory →
Intelligence Center) with three tabs:

- **Overview**: intelligence health banner + reasons, goal-count stat cards, current task / active
  plan info cards, recent decisions/simulations, blockers, routing status summary, and a "Run
  evaluations" button — every card that names another system (Tasks, Plans, Decisions, Simulations,
  Routing) links out to its existing home in Mission Control / Cognitive Core rather than duplicating
  its controls, per the milestone's explicit "hub, not a rebuild" instruction.
- **Goals**: create-goal form, list with expand-to-detail (progress bar, evidence counts, blockers,
  next action, and status-appropriate action buttons — Approve only shows for `proposed`, Pause only
  for `approved`/`active`, Abandon hidden once terminal), and a "Review all goals" button surfacing
  the cross-goal `GoalReview` summary.
- **Context**: a free-text message box that calls `POST /context/select` and renders the full
  `ContextBundle` — which categories populated, chars used vs. budget, compression/fallback flags,
  and the `excluded_context_summary` diagnostic — explicitly never raw hidden prompts.

`Sidebar.tsx`'s `ADVANCED_NAV_GROUPS` gained one entry; `MobileDrawer.tsx` needed no changes since it
already generically iterates that same exported list.

## 10. Known limitations

- The Context tab's preview form only collects a free-text message — it doesn't expose
  `goal_id`/`project_id`/`freshness_requirement` as UI inputs (all fully supported and tested at the
  API layer). A goal-scoped preview can be exercised today via the Goals tab's per-goal progress view
  plus a manual API call, not yet a single combined UI control.
- `ContextSelectionMetric` rows are written on every `select_context()` call but have no dedicated
  viewer yet — the data exists for future budget-tuning work, not surfaced today.
- `intelligence_health` is a simple three-gate rollup (DB health, Ollama reachability, latest
  evaluation result, unresolved blocker count) — it is not a predictive or trend-aware signal.

## 11. Rollback procedure

Every schema change is additive: two new columns (`Task.goal_id`, `Plan.goal_id`, both nullable) and
three new tables (`Goal`, `GoalReview`, `ContextSelectionMetric`). `context_selection_v2_enabled`
defaults to `False`, so no existing behavior changes until it's explicitly turned on. To roll back:
revert the modified backend files (`models.py`, `db.py`, `schemas.py`, `config.py`,
`services/local_intelligence_engine.py`, `routers/intelligence.py`, `services/evaluation_lab.py`,
`fixtures/evaluation_lab_cases.json`, `main.py`), delete the new service/router files
(`services/goal_engine.py`, `services/context_selector.py`, `routers/goals.py`), delete the 5 new
test files, and revert the frontend files (`api/client.ts`, `components/Sidebar.tsx`, `App.tsx`,
delete `components/intelligence/IntelligenceCenterView.tsx`). No data migration is required either
direction since every new table/column is additive and nothing existing was renamed or repurposed.
