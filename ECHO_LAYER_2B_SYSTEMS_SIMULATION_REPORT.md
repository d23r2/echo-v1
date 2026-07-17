# ECHO Layer 2B — Systems Thinking and Simulation Engine — Delivery Report

See [ECHO_LAYER_2B_SYSTEMS_SIMULATION_ARCHITECTURE.md](ECHO_LAYER_2B_SYSTEMS_SIMULATION_ARCHITECTURE.md)
for the full design and
[ECHO_LAYER_2B_SYSTEMS_SIMULATION_SMOKE_TEST.md](ECHO_LAYER_2B_SYSTEMS_SIMULATION_SMOKE_TEST.md)
for the manual checklist.

## Overall status: Green

1115/1115 backend tests pass (59 new), `ruff check .` clean, frontend `tsc -b --noEmit` and
`npm run build` both clean, live-verified in a real browser against an isolated temporary backend —
a real system model was created, two concepts added as nodes, a `depends_on` relationship added
between them, dependency analysis correctly reported the critical path, causal counterfactuals
correctly matched an existing note, a simulation was run both grounded (on the system) and
ungrounded (generic exploration), and the decision handoff/scenario cards rendered honest
evidence-quality, sensitivity, and uncertainty labels throughout — the real Docker backend's data
was never touched. Secret scan: 17 findings, all pre-existing Layer 0/1 test fixtures (confirmed by
filename — `test_infrastructure_*`, `test_layer1_*`), zero in any Layer 2B file.

## Architecture audit

**Existing systems reused**: `CognitiveConcept`/`CognitiveRelationship` (the world-model graph,
unchanged), `CausalNote` (unchanged), Layer 2A's `TaskUnderstanding` (optional simulation anchor),
Layer 0's error/logging/feature-flag infrastructure, the existing `/api/intelligence/*` router and
`CognitiveCoreView.tsx` page (both extended, not duplicated).

**Duplicate systems avoided**: no second graph database — `SystemModel` is a named, scoped view
over the existing concept/relationship graph via a new `SystemModelNode` join table, per the
milestone's own explicit instruction to integrate with the existing knowledge graph.

**Major design decisions**: `relation_type` extended additively (it's a free-text column, not a DB
enum) with `consumes`/`communicates_with`/`mitigates`/`feedback_to`; critical path is a structural
edge-count estimate, not time/cost-weighted, since this app tracks neither on `CognitiveConcept`
(documented honestly rather than fabricated); every ranking/label uses an explicit tie-break chain
or graph-structural count, never an invented probability.

## Memory model

**Models added**: `SystemModel`, `SystemModelNode`, `Simulation`, `SimulationScenario` (all new
tables — no existing table gained a column). **Migration approach**: `Base.metadata.create_all()`
only, `CURRENT_SCHEMA_VERSION` 3 → 4. **Legacy compatibility**: all 1056 pre-2B tests pass
unchanged; the existing `/api/cognitive/*` graph endpoints and their frontend tabs are untouched.

## Dependency graph

`scoped_edges()` — existing `CognitiveRelationship` rows filtered to both endpoints being system
members. Tested for correct scoping (an edge to a concept outside the system is excluded) and the
empty-system case.

## Cycle detection

Three-color DFS over dependency-type edges (`depends_on`/`uses`/`requires`/`blocks`/`consumes`).
Tested against a real 3-node cycle and a DAG (confirmed empty).

## Critical path

Longest dependency chain by edge count, with a shortcut edge in the test fixture to confirm the
*real* longest path is found rather than a shorter direct edge. Tested to correctly return `None`
on a cyclic graph and on a graph with no dependency edges.

## Causal evidence

`build_counterfactuals()` matches system member concept names against existing `CausalNote`
cause/effect/title text; live-verified against the seeded "Ollama offline breaks local chat" note.

## Scenario generation

`generate_scenarios()` — grounded (bottleneck/cycle/critical-path-derived) scenarios when a system
model is attached, keyword-derived generic scenarios (always honestly low-evidence) otherwise.
Live-verified both paths in the browser.

## Baseline scenario

Always generated first, always reversible/high-evidence/low-sensitivity — tested explicitly and
confirmed present in every live-verified simulation.

## Bounded simulation

`max_scenarios` clamped to 1–8, `max_steps` clamped to 1–25 — tested with an out-of-range request
(999/999) confirming the clamp, and with a low `max_steps` confirming every scenario's step list
respects the bound.

## Sensitivity analysis

`_assess_sensitivity()` — a distinct axis from evidence_quality (how much a forecast rests on
unverified assumptions specifically). Tested for the baseline (always low), a low-evidence generic
scenario (always high), and presence across every scenario.

## Uncertainty labels

Every scenario carries `evidence_quality`/`confidence_band`/`uncertainty_notes` — tested that every
generic (ungrounded) scenario is honestly low-evidence/wide-confidence with a non-null explanation.

## No side effects

Dedicated test asserts `simulation_engine.py` has zero import-statement coupling to
`action_system.py`; every scenario step is a text description, never a real action call.

## Decision handoff

`build_decision_handoff()` — recommends the top-ranked non-baseline scenario with an explicit
"forecast, not a guarantee" caveat, or an honest "too uncertain to rank" message with no
recommendation when every non-baseline scenario is low-evidence. Live-verified both branches.

## Frontend system view

`CognitiveCoreView.tsx`'s new Systems tab — create/archive, add/remove concept nodes, inline
dependency analysis (bottleneck/cycle/critical-path summary), causal counterfactuals, one-click
simulation launch. Live-verified: real system created, nodes added, analysis and counterfactuals
rendered correctly against a real seeded relationship and causal note.

## Frontend simulation view

New Simulations tab — create (optionally grounded), expandable ranked scenario cards with
evidence-quality/sensitivity badges, predicted outcomes/risks/costs, uncertainty/sensitivity notes,
and the decision-handoff summary with caveats. Live-verified: both a grounded and an ungrounded
simulation rendered correctly, including the honest low-evidence labelling of the generic scenario.

## Backend full tests

`cd backend && .venv/Scripts/python.exe -m pytest -q` → **1115 passed** (59 new). `ruff check .` →
**All checks passed!**

## Frontend typecheck/build

`npx tsc -b --noEmit` → clean. `npm run build` → clean, 326 modules.

## Files changed

**New backend**: `services/systems_thinking.py`, `services/simulation_engine.py`, 3 new test files
(59 tests total).

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`.

**New frontend**: none (existing page extended).

**Modified frontend**: `api/client.ts` (Layer 2B types + ~20 new functions),
`components/cognitive/CognitiveCoreView.tsx` (Systems and Simulations tabs added,
`SystemDetail`/`SimulationDetail`/`ScenarioCard` components added).

**New docs**: this report, the architecture doc, the smoke test doc.

## Bugs fixed

- None found in Layer 2B code during this pass — the one test-authoring correction was an
  overly-strict "no `action_system` string anywhere" assertion that tripped on this module's own
  explanatory docstring; narrowed to checking actual `import`/`from` statement lines instead.

## Bugs not fixed

None outstanding in Layer 2B code. Pre-existing items from `PROGRESS.md`'s Blockers section remain
open and are unrelated to this milestone.

## Manual checks remaining

- The full 22-step `ECHO_LAYER_2B_SYSTEMS_SIMULATION_SMOKE_TEST.md` was spot-verified (system
  creation, node add/remove, dependency analysis, counterfactuals, grounded and ungrounded
  simulation, decision handoff) but not run as one continuous pass against the real Docker
  backend's data — verification deliberately used an isolated temp backend instead.
- The schema migration (v3 → v4) has not yet been applied to the real running Docker backend's
  database — purely additive (new tables only) by construction, exercised only against a fresh temp
  DB and the automated suite so far.
- Bottleneck detection's default `min_degree=3` threshold was exercised with exactly 4 dependents in
  both the automated test and the live pass; a real-world system with genuinely borderline degree
  counts (e.g. exactly 3) was unit-tested but not separately live-verified.

## Rollback instructions

See [Architecture doc §10](ECHO_LAYER_2B_SYSTEMS_SIMULATION_ARCHITECTURE.md#10-rollback-procedure).
Summary: every schema change is additive (four new tables, no modified columns); reverting the 4
modified backend files and 2 modified frontend files, and deleting the 2 new service files and 3
new test files, restores pre-2B behavior exactly.

## Is Layer 2B ready as a release candidate?

**Green as a local release candidate.** Not pushed anywhere. Ready to be tagged
`echo-layer-2b-systems-simulation-rc` after your review of `git status`/`git diff --stat`. Per the
milestone's own instruction, **Layer 2C (Decision Engine and Planning Engine) should only begin
after this report has been reviewed** — I have not started 2C and will not without a fresh
go-ahead.

## Proof table

| Proof item | Result |
|---|---|
| SystemModel | pass |
| Dependency graph | pass |
| Cycle detection | pass |
| Critical path | pass |
| Causal evidence | pass |
| Scenario generation | pass |
| Baseline scenario | pass |
| Bounded simulation | pass |
| Sensitivity analysis | pass |
| Uncertainty labels | pass |
| No side effects | pass |
| Decision handoff | pass |
| Frontend system view | pass |
| Frontend simulation view | pass |
| Backend full tests | pass (1115/1115) |
| Frontend typecheck/build | pass |
