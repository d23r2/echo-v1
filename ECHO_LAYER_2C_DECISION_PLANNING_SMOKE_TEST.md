# ECHO Layer 2C — Decision Engine and Planning Engine Manual Smoke Test

Run alongside the automated 61-test Layer 2C suite. Uses the safe temp-port pattern (never point
the frontend at a real port-8000 backend while testing against data you care about — see prior
milestones' established pattern).

## Setup (1-2)

1. Confirm backend on `http://localhost:8000` and frontend on `http://localhost:5174` (reuse the
   existing Docker backend if healthy).
2. Confirm `GET /api/system/version` reports `schema_version: 5`.

## Decisions (3-9)

3. Open Advanced → Cognitive Core → Decisions — confirm the tab renders with an empty-state
   message.
4. Create a decision with a question, objective, and two options (one option per line) — confirm
   it appears in the list with status `draft`.
5. Expand it — confirm both options render with Select buttons.
6. Click "Analyse" — confirm a report renders with a decision summary and, since neither option is
   structurally differentiated and no criteria/weights were set, an honest "no clear winner"
   message with `evidence: low` / `confidence: wide` (never a fabricated recommendation).
7. Click "Select" on one option — confirm the case status becomes `selected` and that option shows
   a "recommended" badge.
8. Create a second decision with one hard criterion, and give one option a `violates_criteria`
   entry naming that criterion via the API (`POST /api/intelligence/decisions` with
   `"violates_criteria": ["<name>"]` on that option) — Analyse it and confirm the violating option
   is shown eliminated with a reason, and the other option is recommended.
9. On a decision with 2+ criteria, set a weight on each criterion and a rating per option/criterion
   in the UI, then Analyse — confirm a numeric `score` appears on each option and the
   higher-scoring one is recommended with an explicit "scored highest" rationale.

## Plans (10-16)

10. Open the Plans tab — create a plan with 2-3 step titles (one per line) — confirm it appears
    with status `proposed`, revision 1.
11. Expand it — confirm all steps render as `pending` with a parallel-group tag.
12. Click "Validate" — confirm it reports `Valid` and a critical-path step count.
13. Click "Approve" — confirm status becomes `approved`.
14. Click "Create tasks from plan" — confirm a "Created N task(s)" confirmation appears and every
    step shows "→ task created".
15. Open the Tasks page — confirm the same N tasks now exist as real, independently-visible Task
    rows (not just a claimed count).
16. Click "Replan" with a reason — confirm a new plan row appears (revision 2, status
    `proposed`, requiring fresh approval) and that the original plan is marked superseded.

## Dependency-aware validation (17-19, via API — no dedicated UI dependency editor yet)

17. `POST /api/intelligence/plans` with steps `A`, `B` (`depends_on_titles: ["A"]`), `C`
    (`depends_on_titles: ["A"]`), `D` (`depends_on_titles: ["B","C"]`) — `POST .../validate` and
    confirm `critical_path_step_ids` has length 3 and `parallel_groups` places B and C in the same
    group.
18. Manually mark step A `blocked` (`PATCH` not exposed — direct DB/test only) and re-validate —
    confirm a warning naming the dependent step.
19. Inject a circular dependency and re-validate — confirm `valid: false` with a "Circular
    dependency" message.

## No autonomous action / permission gating (20-21)

20. Confirm `POST /api/intelligence/plans/{id}/materialise-tasks` on a `proposed` (not yet
    approved) plan returns 400 and creates no tasks.
21. Flip `create_task`'s `ActionDefinition.requires_confirmation` to true (via
    `/api/actions` or direct DB), then materialise an approved plan — confirm no task is created
    and a `pending` `ActionRun` exists instead (an honest proposal, not a silent auto-execution).

## No hidden reasoning (22)

22. Inspect any `/api/intelligence/decisions/*` or `/plans/*` response — confirm no field contains
    a raw reasoning trace, and that `action_system` never appears in a response body.

## Regression (23-25)

23. Confirm the pre-existing World Model, Skill Library, Causal Notes, Task Understandings,
    Cognitive Briefs, Systems, and Simulations tabs still work exactly as before.
24. Confirm normal chat still works end-to-end with clean `via Ollama`-style metadata, unaffected
    by this milestone.
25. Run the full backend test suite and frontend build; confirm both pass clean (1176/1176 backend
    at the time of this milestone, 61 of them new; frontend build clean).
