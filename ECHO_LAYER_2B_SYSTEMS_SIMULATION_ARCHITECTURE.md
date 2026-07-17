# ECHO Layer 2B — Systems Thinking and Simulation Engine — Architecture

## 1. Scope

Adds two capabilities on top of Layer 2A's Cognitive Core v2: a **systems view** over the
existing world-model graph (dependency structure, bottlenecks, cycles, critical path, causal
counterfactuals) and a **bounded, non-executing simulation engine** (scenario generation, rule-based
bounded execution, comparison/ranking, decision handoff). Both are forecasting/analysis tools —
nothing here ever performs a real action; real execution stays behind the existing, separate,
permission-gated Action System (`action_system.py`).

## 2. Phase 0 audit findings

- **Reusable as-is**: `CognitiveConcept`/`CognitiveRelationship` (the existing world-model graph),
  `CausalNote` (existing cause→effect facts), Layer 2A's `TaskUnderstanding` (a simulation can
  optionally be anchored to a `task_id`), Layer 0's typed models/error handling/feature-flag
  infrastructure, the established `/api/intelligence/*` router and `CognitiveCoreView.tsx` page.
- **Duplicate systems avoided**: the milestone's own instruction was to integrate with the existing
  knowledge graph rather than create a second, unrelated graph database. `SystemModel` is therefore
  a named, scoped *view* — a `SystemModelNode` join/attribute table tags which existing
  `CognitiveConcept` rows belong to a given system, and the edges between those nodes are the
  existing `CognitiveRelationship` rows, scoped by membership. No parallel node/edge tables.
- **Major design decision — relation_type extension**: `relation_type` on `CognitiveRelationship`
  is a plain string column (not a DB enum), so the milestone's requested systems-thinking edge
  types (`consumes`, `communicates_with`, `mitigates`, `feedback_to`) were added additively to the
  `RelationType` Literal in `schemas.py` alongside the 12 pre-existing values — no migration needed
  for this specific change, since the column itself never constrained values at the DB level.
- **Major design decision — no invented probabilities**: every ranking, bottleneck flag, and
  confidence label in this milestone is either a graph-structural count (in-degree, out-degree,
  path length) or a small explicit tie-break chain — never a fabricated composite score presented
  as calibrated certainty. This directly satisfies the milestone's own non-negotiable rule.

## 3. Data model

### `SystemModel` (new table)
A named, scoped container: `name`, `scope` (`software_architecture` | `project_plan` |
`physical_system` | `organisational_workflow` | `study_plan` | `decision_context`), `description`,
optional `project_id`, soft-archive via `archived_at` (matches this app's established convention —
nothing in this codebase hard-deletes a durable record from a normal API call).

### `SystemModelNode` (new table)
Tags one `CognitiveConcept` as a member of one `SystemModel`, carrying system-specific attributes a
bare world-model concept doesn't have: `node_role` (`component` | `actor` | `resource` |
`constraint` | `interface` | `external_factor`), `state`, `owner`, `evidence`, `confidence`.
Unique on `(system_model_id, concept_id)` — adding the same concept twice upserts rather than
duplicating. No FK constraint on `concept_id`, matching the existing `CognitiveRelationship`
cross-reference style used throughout this codebase.

### `Simulation` / `SimulationScenario` (new tables)
`Simulation` records the bounded run's parameters (`objective`, optional `system_model_id`/`task_id`,
`max_scenarios`, `max_steps`, `risk_tolerance`, ...) and `too_uncertain_to_rank`. `SimulationScenario`
is one candidate strategy (including the mandatory `baseline` no-action scenario): strategy text,
steps (JSON list of `{step, description}`), predicted outcomes/dependencies/costs/risks/failure
modes, `reversibility`, `evidence_quality`, `confidence_band`, `uncertainty_notes`,
`sensitivity_label`/`sensitivity_note` (see §6), `steps_completed`/`steps_blocked`/`stopped_reason`
(bounded-execution bookkeeping), and `rank` (null when the simulation was too uncertain to rank).

Schema version bumped 3 → 4. All four are brand-new tables created by
`Base.metadata.create_all()` — no `_ensure_column()` migrations were needed since nothing
pre-existing gained a column.

## 4. Graph algorithms (`services/systems_thinking.py`)

Deterministic, no model call — same convention as `cognitive_core.py`/`task_understanding_v2.py`.

- **`scoped_edges()`** — the existing `CognitiveRelationship` rows whose both endpoints are members
  of a given `SystemModel`'s node set.
- **`detect_bottlenecks()`** — flags nodes whose in-degree or out-degree (over
  dependency-type edges: `depends_on`/`uses`/`requires`/`blocks`/`consumes`) meets a threshold
  (default 3), with a plain-language reason. "Bottleneck" here means *structurally load-bearing*,
  not *broken*.
- **`detect_cycles()`** — classic three-color DFS over dependency-type edges; returns each cycle as
  an ordered list of concept ids.
- **`compute_critical_path()`** — longest dependency chain by edge count (a structural estimate,
  not a time/cost-weighted critical path — this app tracks neither on `CognitiveConcept`). Returns
  `None` on a cyclic graph (longest-path is undefined there) or when there are no dependency edges.
- **`build_counterfactuals()`** — matches the system's member concepts' names against the existing
  `CausalNote` table's cause/effect/title text and produces a counterfactual statement per match,
  explicitly grounded in ("based on the recorded causal note ...") rather than fabricated.

## 5. Simulation engine (`services/simulation_engine.py`)

- **`generate_scenarios()`** — always emits the baseline (no-action) scenario first. When a
  `system_model_id` is given, grounds additional scenarios in the system's own bottlenecks/cycles/
  critical path (higher `evidence_quality`, narrower `confidence_band`). Falls back to
  keyword-derived generic scenarios (always `evidence_quality: "low"`, `confidence_band: "wide"`,
  and an explicit `uncertainty_notes` explaining why) when no system model is attached, or when a
  grounded system doesn't fill the requested scenario count.
- **Bounded by construction** — `max_scenarios` (clamped to 1–8) caps branch count, `max_steps`
  (clamped to 1–25) caps per-scenario depth. This app has no wall-clock/dollar cost data attached to
  `CognitiveConcept`/`CausalNote`, so there is no real "cost" to bound beyond scenario/step counts —
  documented honestly here rather than fabricating a cost model.
- **`compare_scenarios()`** — ranks by an explicit tie-break chain (fewer risks → better
  reversibility → fewer blocked steps → higher evidence quality → fewer steps), never a fabricated
  composite score. Sets `too_uncertain_to_rank = True` (and leaves every non-baseline scenario's
  `rank` null) when every non-baseline scenario is low-evidence/wide-confidence — ranking those
  against each other would imply a confidence the data doesn't support.
- **`_assess_sensitivity()`** — a separate axis from evidence quality: how much a scenario's
  forecast rests on *unverified assumptions* specifically (assumption count + evidence quality),
  distinct from how much graph-derived evidence backs it.
- **No side effects** — `simulation_engine.py` has zero import-level coupling to `action_system.py`
  (enforced by a dedicated test); every scenario step is a text description, never a real action.
- **`build_decision_handoff()`** — a plain summary object (`recommended_scenario_id`,
  `recommendation_summary`, `ranked_scenario_ids`, `too_uncertain_to_rank`, `caveats`) for a
  downstream decision/planning step (Layer 2C) to consume — never executes anything itself.

## 6. API (`routers/intelligence.py`, additive)

`/api/intelligence/systems` (CRUD) → `/{id}/nodes` (add/list/remove) → `/{id}/analysis`
(bottlenecks/cycles/critical path bundle) → `/{id}/counterfactuals`.
`/api/intelligence/simulations` (create/list/get) → `/{id}/decision-handoff`.
Literal-path routes are registered before any `/{id}` catch-all, matching this router's existing
convention. `POST /simulations` 404s if a given `system_model_id` doesn't exist rather than
silently running an ungrounded simulation under a false pretense of being grounded.

## 7. Frontend

`CognitiveCoreView.tsx` gains two tabs: **Systems** (create/archive a system model; add/remove
world-model concepts as nodes; run dependency analysis and show bottlenecks/cycles/critical path
inline; show causal counterfactuals; one-click "run a simulation on this system") and
**Simulations** (create a simulation, optionally grounded in a system model; expand to see ranked
scenario cards with evidence-quality/sensitivity badges, predicted outcomes, risks, costs,
uncertainty and sensitivity notes; the decision-handoff summary and its caveats render above the
scenario list). No chain-of-thought, internal field names, or raw JSON are ever rendered — only
plain-language summaries, matching Layer 2A's established pattern.

## 8. Test strategy

59 new backend tests across three files: `test_layer2b_systems_thinking.py` (pure
CRUD/graph-algorithm tests against the isolated `db_session` fixture — bottleneck/cycle/
critical-path/counterfactual correctness, including the cyclic-graph guard), 
`test_layer2b_simulation_engine.py` (baseline-always-present, bound enforcement, uncertainty
labels, sensitivity labels, ranking tie-breaks, `too_uncertain_to_rank`, decision handoff, and an
explicit no-`action_system`-import assertion), and `test_layer2b_intelligence_api.py` (the full
`/api/intelligence/systems` and `/simulations` surface via `TestClient`, matching Layer 2A's API
test convention).

## 9. Migration risk

Purely additive: four new tables, one additively-extended `Literal` type, `CURRENT_SCHEMA_VERSION`
3 → 4. No existing table gained or lost a column. Reverting the modified files (`models.py`,
`schemas.py`, `db.py`, `main.py`'s router registration was already in place from Layer 2A,
`routers/intelligence.py`, `client.ts`, `CognitiveCoreView.tsx`) and deleting the two new service
files and three new test files restores pre-2B behavior exactly.

## 10. Rollback procedure

1. Revert `backend/app/models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`.
2. Delete `backend/app/services/systems_thinking.py`, `backend/app/services/simulation_engine.py`.
3. Delete the three `test_layer2b_*.py` files.
4. Revert `frontend/src/api/client.ts` and `frontend/src/components/cognitive/CognitiveCoreView.tsx`.
5. The four new tables become orphaned but harmless in an existing SQLite file (SQLite doesn't
   enforce schema against `CURRENT_SCHEMA_VERSION`) — no destructive DROP is required for a clean
   local rollback, matching Layer 0/1/2A's own stated rollback pattern.
