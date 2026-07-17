# ECHO Layer 2A — Cognitive Core v2 Manual Smoke Test

Run alongside the automated 61-test Layer 2A suite. Uses the safe temp-port
pattern (never point the frontend at a real port-8000 backend while testing
against data you care about — see prior milestones' established pattern).

## Setup (1-2)

1. Confirm backend on `http://localhost:8000` and frontend on
   `http://localhost:5174` (reuse the existing Docker backend if healthy).
2. Confirm `GET /api/system/version` reports `schema_version: 3`.

## Task understanding (3-8)

3. Send a simple message ("hi") via `POST /api/intelligence/task-understanding`
   — confirm it returns `null`, not an error.
4. Send a complex message ("Fix the failing backend test, keep this
   local-only, by Friday") — confirm the response includes `task_category`,
   explicit constraints (deadline + local-only), acceptance tests, and
   success criteria.
5. Open Advanced → Cognitive Core → Task Understandings — confirm the new
   task appears with a status badge and confidence badge.
6. Expand the task — confirm goal, explicit/inferred constraints, known
   facts, success criteria, acceptance tests, and risks all render as plain
   readable text, never raw JSON.
7. Send a message with a quoted instruction inside it (e.g. a fenced code
   block containing `delete_all_users()`) — confirm the quoted content is
   not treated as part of the instruction.
8. Send a compound message ("Fix the login bug and also write the docs for
   it") — confirm it's represented as multiple intents, not one flattened
   label.

## Constraints and clarification (9-11)

9. Send a message with contradictory constraints if you can construct one
   (e.g. explicitly "local-only" and "cloud_required" in the same
   sentence) — confirm a conflict note appears in constraints.
10. Send a decision-style message with genuinely missing critical
    information — confirm the task's status becomes `needs_clarification`
    and the "Why ECHO needs clarification" panel shows in the UI.
11. Confirm a task with only optional/important missing info does NOT show
    the clarification panel (it should just proceed with a stated
    assumption).

## Correction and re-analysis (12-14)

12. In the expanded task view, click "Correct goal," change it, save —
    confirm the goal updates in place and the row refreshes.
13. Click "Re-analyse" — confirm a new task row appears with
    `parent_task_id` pointing at the original, and the original's status
    becomes `superseded` (and disappears from the default list).
14. Send the exact same message twice in the same conversation — confirm
    no duplicate task row is created (re-analysis is skipped when nothing
    materially changed).

## No hidden reasoning (15-16)

15. Inspect any `/api/intelligence/*` response — confirm no field contains
    a raw reasoning trace, internal score, or hidden chain-of-thought.
16. Send a chat message that triggers a Cognitive Brief — confirm the
    normal chat reply never mentions "CognitiveBrief," "TaskUnderstanding,"
    or any other internal label.

## Regression (17-19)

17. Confirm normal chat still works end-to-end with clean `via Ollama`-style
    metadata, unaffected by this milestone.
18. Confirm the existing `/api/cognitive/*` endpoints and their frontend
    sections (World Model, Skill Library, Causal Notes, Settings) still
    work exactly as before.
19. Run the full backend test suite and frontend build; confirm both pass
    clean (1056/1056 backend at the time of this milestone, 61 of them new;
    frontend build clean).
