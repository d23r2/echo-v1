# ECHO Layer 2B — Systems Thinking and Simulation Manual Smoke Test

Run alongside the automated 59-test Layer 2B suite. Uses the safe temp-port pattern (never point
the frontend at a real port-8000 backend while testing against data you care about — see prior
milestones' established pattern).

## Setup (1-2)

1. Confirm backend on `http://localhost:8000` and frontend on `http://localhost:5174` (reuse the
   existing Docker backend if healthy).
2. Confirm `GET /api/system/version` reports `schema_version: 4`.

## System models (3-9)

3. Open Advanced → Cognitive Core → Systems — confirm the tab renders with an empty-state message.
4. Create a system model (e.g. "Backend Architecture") — confirm it appears in the list with its
   scope badge.
5. Expand it — confirm the node list is empty and the concept dropdown is populated from the
   existing World Model.
6. Add two concepts as nodes — confirm both render as removable chips.
7. In the World Model tab (or via `POST /api/cognitive/relationships`), add a `depends_on`
   relationship between those two concepts.
8. Back in Systems, click "Analyze dependencies" — confirm the analysis panel shows bottleneck/
   cycle counts and, for this two-node chain, a critical path of length 1 naming both concepts.
9. Click "Show causal counterfactuals" — confirm it renders either a matched counterfactual
   statement (if an existing `CausalNote` mentions one of the concepts) or an honest "no matching
   causal notes" message — never a fabricated one.

## Bottleneck and cycle detection (10-11)

10. Add 3+ concepts that all `depends_on` a single hub concept in the same system — confirm
    "Analyze dependencies" now reports that hub as a bottleneck with a plain-language reason.
11. Add a three-concept cycle (A→B, B→C, C→A, all `depends_on`) to a system — confirm the analysis
    reports 1 cycle and that critical path becomes unavailable (cyclic graphs have no defined
    longest path).

## Simulations (12-17)

12. Click "Run simulation on this system" from an expanded system — confirm it completes without
    error (no visible "running" state — bounded rule-based execution is synchronous).
13. Switch to the Simulations tab — confirm the new simulation appears with its scenario count.
14. Expand it — confirm a `baseline` scenario is always present, ranked, and marked high evidence/
    low sensitivity.
15. Confirm every scenario shows an evidence-quality badge and a sensitivity badge, and that any
    scenario without a system model behind it is honestly labelled low evidence / wide confidence
    with an uncertainty note explaining why.
16. Confirm the decision-handoff summary above the scenario list states either a specific
    recommended scenario with an explicit "forecast, not a guarantee" caveat, or (when all
    non-baseline scenarios are low-evidence) an honest "too uncertain to rank" message with no
    single scenario singled out.
17. Create a second simulation with no system model selected ("generic exploration") — confirm it
    still runs, still includes a baseline, and every non-baseline scenario is explicitly
    low-evidence/wide-confidence.

## No hidden reasoning / no fabricated certainty (18-19)

18. Inspect any `/api/intelligence/systems/*` or `/simulations/*` response — confirm no field
    contains a raw internal reasoning trace, and that nothing presents a percentage-style
    probability as calibrated certainty (only qualitative evidence_quality/confidence_band/
    sensitivity_label values).
19. Confirm no simulation response or UI text mentions `action_system` or claims a real action was
    taken — simulated scenarios are text-only forecasts.

## Regression (20-22)

20. Confirm the pre-existing World Model, Skill Library, Causal Notes, Task Understandings, and
    Cognitive Briefs tabs still work exactly as before.
21. Confirm normal chat still works end-to-end with clean `via Ollama`-style metadata, unaffected
    by this milestone.
22. Run the full backend test suite and frontend build; confirm both pass clean (1115/1115 backend
    at the time of this milestone, 59 of them new; frontend build clean).
