# ECHO Layer 2C — Decision Engine and Planning Engine — Delivery Report

See [ECHO_LAYER_2C_DECISION_PLANNING_ARCHITECTURE.md](ECHO_LAYER_2C_DECISION_PLANNING_ARCHITECTURE.md)
for the full design and
[ECHO_LAYER_2C_DECISION_PLANNING_SMOKE_TEST.md](ECHO_LAYER_2C_DECISION_PLANNING_SMOKE_TEST.md)
for the manual checklist.

## Overall status: Green

1176/1176 backend tests pass (61 new), `ruff check .` clean, frontend `tsc -b --noEmit` and
`npm run build` both clean, live-verified in a real browser against an isolated temporary backend —
a real decision was created and analysed (correctly reporting an honest "no clear winner" for two
undifferentiated options), an option was selected, a real plan was created, validated, approved,
and materialised into three genuine Task rows (independently confirmed on the Tasks page), and a
replan produced a new proposed-status revision with the original marked superseded — the real
Docker backend's data was never touched. Secret scan: 17 findings, all pre-existing Layer 0/1 test
fixtures (same set as Layer 2B's report — confirmed by filename), zero in any Layer 2C file.

## Architecture audit

**Existing systems reused**: `Project`/`Task` (plan steps map to Tasks only after explicit
approval, never duplicated), `SkillPattern` via the existing `skill_library.suggest_plan()` (a
minimum-viable-plan template source), Layer 2B's `Simulation`/`SimulationScenario` (an optional,
not required, option source for a `DecisionCase`), and — most importantly —
`action_system.run_action()`, reused verbatim as the plan-materialisation execution path rather
than building a second permission-gated funnel.

**Duplicate systems avoided**: no parallel task-execution mechanism; `PlanDependency` is a small
new edge table (plan steps aren't part of the Cognitive Core world-model graph so can't reuse
`CognitiveRelationship` the way Layer 2B did) but its graph algorithms mirror the established
`systems_thinking.py` pattern rather than reinventing it differently.

**Major design decisions**: hard-constraint elimination and weighted scoring are both driven by
explicit inputs (`violates_criteria_json`, `criterion_ratings_json`, criterion `weight`) rather
than any text-matching inference — nothing here ever fabricates precision beyond what was
explicitly provided; `no_clear_winner` is a first-class, tested outcome, not an edge case papered
over; replanning creates a new `Plan` row rather than mutating history in place.

## Memory model

**Models added**: `DecisionCase`, `DecisionOption`, `DecisionCriterion`, `Plan`, `PlanStep`,
`Milestone`, `PlanDependency`, `PlanResourceRequirement`, `PlanRisk`, `PlanRevision` (10 new
tables — no existing table gained a column). **Migration approach**: `Base.metadata.create_all()`
only, `CURRENT_SCHEMA_VERSION` 4 → 5. **Legacy compatibility**: all 1115 pre-2C tests pass
unchanged.

## DecisionCase model

Question/objective/constraints/stakeholders/evidence/assumptions/uncertainty/time_horizon/
reversibility/consequence_level/status, optional links to a Layer 2B simulation and Layer 2A task,
`report_json` embedding the full Phase 3 DecisionReport. Tested via direct model construction and
the full `/api/intelligence/decisions` API surface.

## Options and criteria

`DecisionOption`/`DecisionCriterion` with the exact spec'd fields (benefits/drawbacks/costs/
dependencies/risks/failure_modes/reversibility/evidence_quality/confidence per option;
source/importance/hard_or_soft/weight per criterion). Tested for correct storage and retrieval.

## Hard constraints

`eliminate_hard_constraints()` — explicit `violates_criteria_json` signal, never keyword-matching.
Tested: violating option eliminated with a reason naming the constraint; soft criteria never
eliminate; idempotent re-runs.

## Trade-off analysis

`build_tradeoff_matrix()` — plain structural benefits/drawbacks/risks listing for remaining
options, rendered in the frontend report's "key trade-offs" section.

## No-clear-winner support

Tested for all three triggering conditions: every option eliminated, tied weighted scores, and
multiple Pareto-non-dominated options with no weights set — live-verified in the browser with two
undifferentiated options.

## DecisionReport

All 13 spec'd fields present and tested, including `confidence_band` correctly derived from
`evidence_quality` (low → wide, tested explicitly to satisfy "low evidence reduces confidence") and
`user_confirmation_needed` derived from consequence_level/reversibility.

## Plan model

Objective/scope/assumptions/constraints/success_criteria/estimated_effort/owner/status (exactly
the 7 spec'd states)/evidence/approval state (`approved_at`), plus optional links to a
DecisionCase/SystemModel/Task/Project and the replanning chain (`revision_number`/
`superseded_by_plan_id`).

## Milestones and dependencies

`Milestone` (target steps + verification criteria, defaulted to a generic criterion when none
given, marked `reached` once all target steps complete) and `PlanDependency` (directed
`blocks`/`informs` edges). Tested end-to-end including a live-browser critical-path check.

## Critical path

`_longest_path()` — same longest-dependency-chain-by-edge-count approach as Layer 2B's
`systems_thinking.py`. Tested with a shortcut-edge fixture to confirm the real longest path (not a
shorter direct edge) is found.

## Plan validation

`validate_plan()` — cycle detection (blocking), critical path, parallel-group detection (steps at
equal depth with no direct edge), blocked-step-propagation warnings, resource-conflict warnings.
Tested for a real cycle, a real blocked-step chain, an empty-plan blocking case, and correct
parallel grouping (two independent branches sharing a root).

## Adaptive replanning

`replan()` — requires an already-approved/active/blocked plan; creates a new `Plan` row
(`revision_number + 1`, `status="proposed"`); carries `completed` steps forward unchanged; drops
`failed` steps (recorded in `PlanRevision.changed_step_ids_json`); the old plan is only ever
annotated (`superseded_by_plan_id`), never mutated. Tested for completed-step preservation, correct
scoping of a `changed_constraint` trigger to only the actually-affected step, and rejection when
the source plan isn't yet approved. Live-verified in the browser.

## Revision history

`PlanRevision` — one immutable row per replan (reason/trigger/changed steps/previous+new status).
Tested for presence and correct field values after a replan.

## Approval gate

`approve_plan()` only transitions `proposed → approved`; `materialise_plan()` and `replan()` both
reject a plan that isn't in the right status. Tested explicitly ("Plan does not create tasks before
approval") and live-verified (materialise button only appears once approved).

## Task materialisation

`materialise_plan()` reuses `action_system.run_action()` per step; creates correctly-scoped,
provenance-tagged (`source_type="plan_step"`) Task rows; is idempotent (already-materialised steps
are skipped, not duplicated). Tested and live-verified — 3 real Task rows independently confirmed
on the Tasks page.

## Action permission handoff

Tested with a real flipped `ActionDefinition.requires_confirmation` flag (the actual lever this
app's `action_system.py` uses for low-risk-action confirmation): materialising a plan under that
condition creates zero tasks and leaves a `pending` `ActionRun` instead — an honest, inspectable
proposal, never a silent autonomous execution. A separate test confirms plan creation/approval
alone never creates a Task.

## Frontend decision view

New Decisions tab in `CognitiveCoreView.tsx` — create, expand to rate options per criterion and set
weights, Analyse, Select. Live-verified: full create → analyse (no-clear-winner) → select flow.

## Frontend planning view

New Plans tab — create, expand to see steps/parallel groups, Validate, Approve, Create tasks from
plan, Replan, flag a risk. Live-verified: full create → validate → approve → materialise → replan
flow, including confirming the materialised tasks on the real Tasks page.

## Backend full tests

`cd backend && .venv/Scripts/python.exe -m pytest -q` → **1176 passed** (61 new). `ruff check .` →
**All checks passed!**

## Frontend typecheck/build

`npx tsc -b --noEmit` → clean. `npm run build` → clean, 326 modules.

## Files changed

**New backend**: `services/decision_engine.py`, `services/plan_engine.py`, 3 new test files (61
tests total).

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`.

**New frontend**: none (existing page extended).

**Modified frontend**: `api/client.ts` (Layer 2C types + ~20 new functions),
`components/cognitive/CognitiveCoreView.tsx` (Decisions and Plans tabs added,
`DecisionDetail`/`PlanDetail` components added).

**New docs**: this report, the architecture doc, the smoke test doc.

## Bugs fixed

- **Test premise bug (caught before it reached the suite as a false negative)**: an initial
  "permission-gated action proposal" test assumed `PermissionSetting.level = "ask_first"` would
  gate a low-risk action like `create_task`. Reading `action_system.py`'s own
  `_needs_confirmation()` showed that for `risk_level == "low"`, confirmation is driven solely by
  `ActionDefinition.requires_confirmation`, not the permission level. Fixed by exercising the real
  lever instead of a level this app's own logic doesn't consult for low-risk actions.

## Bugs not fixed

None outstanding in Layer 2C code. Pre-existing items from `PROGRESS.md`'s Blockers section remain
open and are unrelated to this milestone.

## Manual checks remaining

- The full 25-step `ECHO_LAYER_2C_DECISION_PLANNING_SMOKE_TEST.md` was spot-verified (decision
  create/analyse/select, plan create/validate/approve/materialise/replan, Tasks-page confirmation)
  but not run as one continuous pass against the real Docker backend's data — verification
  deliberately used an isolated temp backend instead.
- The schema migration (v4 → v5) has not yet been applied to the real running Docker backend's
  database — purely additive (new tables only) by construction, exercised only against a fresh temp
  DB and the automated suite so far.
- Dependency-aware plan creation (steps with `depends_on_titles`) and weighted-scoring rating entry
  were live-verified for weighted scoring (via the UI) and unit/API-tested for dependencies, but
  the dependency-aware critical-path/parallel-group live-browser pass used the API directly rather
  than a dedicated frontend dependency editor (none exists yet — see Known limitations in the
  architecture doc).

## Rollback instructions

See [Architecture doc §14](ECHO_LAYER_2C_DECISION_PLANNING_ARCHITECTURE.md#14-rollback-procedure).
Summary: every schema change is additive (ten new tables, no modified columns); reverting the 4
modified backend files and 2 modified frontend files, and deleting the 2 new service files and 3
new test files, restores pre-2C behavior exactly.

## Is Layer 2C ready as a release candidate?

**Green as a local release candidate.** Not pushed anywhere. Ready to be tagged
`echo-layer-2c-decision-planning-rc` after your review of `git status`/`git diff --stat`. Per the
milestone's own instruction, **Layer 2D (Multi-Model Orchestrator and Tool Strategy Engine) should
only begin after this report has been reviewed** — I have not started 2D and will not without a
fresh go-ahead.

## Proof table

| Proof item | Result |
|---|---|
| DecisionCase model | pass |
| Options and criteria | pass |
| Hard constraints | pass |
| Trade-off analysis | pass |
| No-clear-winner support | pass |
| DecisionReport | pass |
| Plan model | pass |
| Milestones and dependencies | pass |
| Critical path | pass |
| Plan validation | pass |
| Adaptive replanning | pass |
| Revision history | pass |
| Approval gate | pass |
| Task materialisation | pass |
| Action permission handoff | pass |
| Frontend decision view | pass |
| Frontend planning view | pass |
| Backend full tests | pass (1176/1176) |
| Frontend typecheck/build | pass |
