# ECHO Layer 2C — Decision Engine and Planning Engine — Architecture

## 1. Scope

Adds two interoperating capabilities: a **Decision Engine** (structured multi-option analysis —
hard-constraint elimination, trade-off matrices, optional weighted scoring, Pareto detection, and
a compact, honest recommendation report) and a **Planning Engine** (approvable plans of ordered
steps with dependency/critical-path/parallel-step analysis, adaptive replanning that preserves
history, and execution handoff into real Tasks via the existing permission-gated Action System).
The Decision Engine recommends; it never makes an irreversible choice for the user — only an
explicit `select` call commits. The Planning Engine never executes anything itself — only an
explicit `materialise-tasks` call, on an already-approved plan, creates real Task rows.

## 2. Phase 0 audit findings

- **Reusable as-is**: `Project`/`Task` (the existing goal-container/actionable-item pair — plan
  steps map to Tasks only after approval, never duplicating this system), `SkillPattern` (a
  matching-skill's `steps_json` seeds a minimum-viable plan when nothing more specific is known),
  Layer 2B's `Simulation`/`SimulationScenario` (an optional option-source for a `DecisionCase` — a
  decision also works fully standalone with user-typed options), `action_system.run_action()` (the
  existing propose → permission-check → confirm-if-needed → execute funnel — reused verbatim for
  plan-step materialisation rather than building a second one), `permission_center.py` (unchanged).
- **Duplicate systems avoided**: no parallel task-execution path; `PlanDependency` edges are a new,
  small table (plan steps aren't part of the Cognitive Core world-model graph, so they can't reuse
  `CognitiveRelationship` the way Layer 2B's `SystemModel` does) but the *algorithms* (cycle
  detection, longest-path critical path, depth-based parallel grouping) are the same pattern
  established in `systems_thinking.py`/`plan_engine.py` shares no code but the same approach.
- **Major design decision — no invented probabilities**: weighted scoring only activates when a
  criterion has an explicit, user-approved `weight` AND an option has an explicit
  `criterion_ratings_json` entry for that criterion — nothing is inferred from free text. Hard-
  constraint elimination is driven by an explicit `violates_criteria_json` list set at
  option-creation time, never a keyword-matching guess against free-text drawbacks/risks.
- **Major design decision — no-clear-winner is a first-class outcome**: `analyse()` sets
  `no_clear_winner = True` (and never fabricates a `recommended_option_id`) whenever every option
  is eliminated, whenever weighted scores tie, or whenever more than one Pareto-non-dominated
  option remains with no weights set to break the tie.
- **Major design decision — replanning creates a new Plan row**: rather than mutating an existing
  plan's steps in place, `replan()` creates a new `Plan` (incrementing `revision_number`,
  `status="proposed"` — always requiring fresh approval), carries completed steps forward
  unchanged, drops failed steps, and links the old plan via `superseded_by_plan_id`. This makes "do
  not rewrite completed history" true by construction rather than by convention.

## 3. Data model

### Decision Engine (`DecisionCase` / `DecisionOption` / `DecisionCriterion`)
`DecisionCase` holds the question/objective/constraints/stakeholders/evidence/assumptions/
uncertainty/time_horizon/reversibility/consequence_level/status, an optional link to a Layer 2B
`simulation_id`/Layer 2A `task_id`/`project_id`, and the Phase 3 `DecisionReport` embedded as
`report_json` (a plain dict of the report fields — see §5). `DecisionOption` carries
benefits/drawbacks/costs/dependencies/risks/failure_modes, `reversibility`/`evidence_quality`/
`confidence`, the explicit `violates_criteria_json` and `criterion_ratings_json` inputs, and the
engine-set `eliminated`/`eliminated_reason`/`score`/`pareto_dominated` outputs.
`DecisionCriterion` carries `name`/`importance`/`hard_or_soft`/`source` and a `weight` that only
ever gets set through an explicit user PATCH call.

### Planning Engine (`Plan` / `PlanStep` / `Milestone` / `PlanDependency` / `PlanResourceRequirement` / `PlanRisk` / `PlanRevision`)
`Plan` holds objective/scope/assumptions/constraints/success_criteria/status (exactly the 7 states
the milestone requires: `proposed|approved|active|blocked|completed|failed|cancelled`) plus
`revision_number`/`superseded_by_plan_id` for the replanning chain. `PlanStep` carries
`order_index`/`status`/`parallel_group` (set by `_assign_parallel_groups()`) and
`materialised_task_id` (null until `materialise_plan()` runs). `PlanDependency` is a directed
`from_step_id → to_step_id` edge (`blocks`|`informs`). `Milestone`/`PlanResourceRequirement`/
`PlanRisk`/`PlanRevision` are small, honestly-scoped supporting tables — `PlanResourceRequirement.
amount` is a descriptive string, never a fabricated precise number, since this app has no real
budget/personnel data source.

Schema version bumped 4 → 5. All ten tables are brand-new — no `_ensure_column()` migrations
needed since nothing pre-existing gained a column.

## 4. Decision analysis methods (`services/decision_engine.py`)

- **`eliminate_hard_constraints()`** — rule-based: an option is eliminated iff a hard criterion's
  name is present in that option's own `violates_criteria_json`. Idempotent.
- **`build_tradeoff_matrix()`** — a plain structural listing (benefits/drawbacks/risks side by
  side), never a score.
- **`compute_weighted_scores()`** — returns `False` (leaving every `score` null) unless at least
  one criterion has an explicit weight; otherwise a plain weighted average of explicit per-option
  ratings for the weighted criteria only.
- **`detect_pareto_dominated()`** — a purely structural multi-objective comparison (benefit count,
  risk count, reversibility rank, evidence-quality rank) — no fabricated utility function.
- **`analyse()`** — orchestrates the above, then determines the outcome: no remaining options →
  `no_clear_winner`; exactly one remaining → that's the recommendation; weighted scores available
  → highest score wins unless tied; otherwise, exactly one non-Pareto-dominated option → that's the
  recommendation; more than one → `no_clear_winner`.
- **`select_option()`** — the one function that actually commits (`status="selected"`) — always a
  separate, explicit user action from `analyse()`'s recommendation.

## 5. DecisionReport (Phase 3, `report_json`)

Exact fields per the milestone spec: `decision_summary`, `recommended_option_label`,
`no_clear_winner`, `why_this_option`, `key_tradeoffs`, `hard_constraints_checked`,
`major_assumptions`, `major_uncertainties` (includes the stated case uncertainty plus every
elimination reason), `risks_and_mitigations`, `alternatives`, `reversibility`, `evidence_quality`,
`confidence_band` (derived from evidence_quality: high→narrow, medium→moderate, low→wide — directly
satisfies "low evidence reduces confidence"), `next_information_to_collect`,
`user_confirmation_needed` (true when `consequence_level` is high/critical or `reversibility` is
hard_to_reverse/irreversible).

## 6. Planning generation and validation (`services/plan_engine.py`)

- **`_generate_mvp_steps()`** — priority order: (1) a linked `DecisionCase`'s selected option's
  dependencies + a final implementation step, (2) a matching `SkillPattern` via the existing
  `skill_library.suggest_plan()`, (3) a single honest placeholder step. Never fabricates detail
  beyond what's actually known.
- **`validate_plan()`** — cycle detection (three-color DFS, same algorithm family as Layer 2B's
  `systems_thinking.py`), critical path (longest dependency chain by edge count), parallel-group
  detection (steps at the same longest-path depth with no direct edge between them), blocked-step
  propagation warnings (a step depending on a `blocked` step is flagged unless it's also
  blocked/cancelled), and a resource-conflict warning when multiple steps in the same parallel
  group need the same named, not-confirmed-available resource.
- **`approve_plan()`** — the only way `status` moves from `proposed` to `approved`; rejects any
  other starting status.

## 7. Adaptive replanning (Phase 6)

`replan()` requires the plan to already be approved/active/blocked, then creates a **new** `Plan`
row (`revision_number + 1`, `status="proposed"` — fresh approval always required), carrying
`completed` steps forward unchanged, resetting non-failed open steps to `pending`, and dropping
`failed` steps entirely (recorded in the new `PlanRevision.changed_step_ids_json`). The old plan's
own rows are never mutated beyond setting `superseded_by_plan_id` — "do not rewrite completed
history" is true by construction.

## 8. Execution handoff (Phase 7)

`materialise_plan()` requires `status` to be `approved`/`active`. For each un-materialised,
non-cancelled step, it calls `action_system.run_action(db, "create_task", {...}, confirm=False)` —
the exact same permission-gated funnel every other real action in this app uses. If the action
needs confirmation (per `ActionDefinition.requires_confirmation` for low-risk actions, or
`PermissionSetting.level` for medium+-risk actions), the resulting `ActionRun` stays `pending` — an
honest proposal, never silently executed — and the step is reported back as skipped, not
materialised. Milestones with a `due_at` get a Schedule reminder via the same `run_action()` path.
Nothing here ever bypasses or duplicates the Permission Center.

## 9. API (`routers/intelligence.py`, additive)

`/api/intelligence/decisions` (create/list/get) → `/{id}/analyse` → `/{id}/select` →
`/{id}/criteria/{criterion_id}/weight` (PATCH) → `/{id}/options/{option_id}/ratings` (PATCH).
`/api/intelligence/plans` (create/list/get/PATCH) → `/{id}/validate` → `/{id}/approve` →
`/{id}/replan` → `/{id}/materialise-tasks` → `/{id}/milestones` / `/{id}/risks` / `/{id}/resources`
(POST helpers). Standard Layer 0 error objects; a `POST /decisions` with an unknown
`simulation_id`, or a `POST /plans` with an unknown `decision_case_id`, 404s rather than silently
proceeding ungrounded.

## 10. Frontend

`CognitiveCoreView.tsx` gains two tabs: **Decisions** (create with free-text options/criteria;
expand to rate options per criterion, set criterion weights, Analyse for a recommendation, Select
to commit — the recommendation report renders decision summary, trade-offs, alternatives,
uncertainties, evidence/confidence, and an explicit "confirmation needed" flag) and **Plans**
(create with optional explicit steps or an auto-generated MVP; expand to see steps with
status/parallel-group badges, Validate for the critical-path/issue summary, Approve, Create tasks
from plan, Replan with a reason, and risk flagging). No raw JSON, internal field names, or
chain-of-thought are ever rendered.

## 11. Test strategy

61 new backend tests across three files: `test_layer2c_decision_engine.py` (hard-constraint
elimination, weighted scoring changing only when weights/ratings change, Pareto detection,
no-clear-winner outcomes including the elimination/tie/multi-non-dominated cases, low-evidence →
wide-confidence-band, report alternatives/uncertainties, simulation-seeded options),
`test_layer2c_plan_engine.py` (MVP generation from a decision/skill/placeholder, dependency and
critical-path validation including a real cycle, parallel-step detection, blocked-step
propagation, the approval gate, permission-gated materialisation via a real flipped
`requires_confirmation` flag, no-autonomous-action, replanning preserving completed steps and
history, changed-constraint scoping), and `test_layer2c_intelligence_api.py` (the full
`/api/intelligence/decisions` and `/plans` surface via `TestClient`).

## 12. Privacy / safety rules honored

No chain-of-thought or raw internal scores are ever exposed in a normal response (verified by a
dedicated test scanning the full decision/plan JSON payload for `action_system`). Every
autonomous-looking step (materialisation, replanning) requires an explicit prior user action
(approval, then a separate materialise/replan call) — nothing cascades automatically. Consequential
decisions (`consequence_level` high/critical or `reversibility` hard_to_reverse/irreversible) are
flagged with `user_confirmation_needed` in the report rather than silently treated as settled.

## 13. Known limitations

- Weighted scoring requires manually rating every option against every weighted criterion in the
  UI (one number input per option×criterion) — there's no bulk-import or model-assisted rating.
- Plan step dependency wiring (`depends_on_titles`) is only exposed via the API/tests; the current
  frontend's plan-creation form is a simple one-title-per-line textarea without a dependency editor
  (dependency-aware plans can still be built via the API, and are fully exercised by the automated
  test suite and a live-browser critical-path/parallel-group check).
- `PlanResourceRequirement`/`PlanRisk`/`Milestone` creation is only exposed via API POST helpers
  (used directly by tests) plus a minimal "Flag a risk" button in the UI — no dedicated
  resource/milestone creation forms yet.

## 14. Rollback procedure

1. Revert `backend/app/models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`.
2. Delete `backend/app/services/decision_engine.py`, `backend/app/services/plan_engine.py`.
3. Delete the three `test_layer2c_*.py` files.
4. Revert `frontend/src/api/client.ts` and `frontend/src/components/cognitive/CognitiveCoreView.tsx`.
5. The ten new tables become orphaned but harmless in an existing SQLite file — no destructive DROP
   is required for a clean local rollback, matching every prior layer's own stated pattern.
