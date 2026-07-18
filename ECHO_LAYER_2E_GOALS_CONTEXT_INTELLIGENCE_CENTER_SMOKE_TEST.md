# ECHO Layer 2E — Goal Manager, Context Selection v2, and Intelligence Center Manual Smoke Test

Run alongside the automated 62-test Layer 2E suite. Uses the safe temp-port pattern (isolated temp
DB/Chroma dir, backend on `http://localhost:8001`, frontend dev server temporarily pointed at it via
`.env`, both reverted afterward) — never point the frontend at a real port-8000 backend while testing
against data you care about.

## Setup (1-2)

1. Start an isolated backend: temp `DATABASE_URL`/`CHROMA_DIR`/`ATTACHMENTS_DIR`,
   `CONTEXT_SELECTION_V2_ENABLED=true`, port 8001. Point the frontend dev server's `.env` at it,
   restart the dev server (Vite reads `.env` once at boot — a plain page reload isn't enough).
2. Confirm `GET /api/intelligence/overview` returns `intelligence_health: "green"` on a fresh DB with
   no data.

## Overview tab (3-5)

3. Open Advanced → Knowledge & Memory → Intelligence Center — confirm it loads on the Overview tab
   with the health banner, three goal-count stat cards (all 0 on a fresh DB), current-task/active-plan
   cards reading "Nothing right now.", empty recent-decisions/simulations lists, and a routing-status
   summary line.
4. Confirm every card that names another system (Open Tasks, Open Plans, Open Decisions, Open
   Simulations, Open Routing) is a link, not an inline control.
5. Click "Run evaluations" — confirm it doesn't error and the last-evaluation summary updates.

## Goals tab (6-10)

6. Switch to Goals — add a goal via the form ("Ship the Layer 2E Intelligence Center", priority
   medium) — confirm it appears immediately with status `APPROVED` (explicit-user goals are approved
   on creation, never left `proposed`).
7. Expand the goal — confirm the progress panel reads "0% complete (0/0 task(s), 0/0 plan step(s)) —
   stalled" (zero evidence is reported honestly, never a fabricated percentage), and that the action
   buttons shown are exactly `Pause`, `Abandon`, `Review` — no `Approve` button, since the goal is
   already approved.
8. Click Review — confirm a per-goal `GoalReview` renders without erroring.
9. Click "Review all goals" at the list level — confirm a cross-goal summary renders, including a
   recommended next action referencing the goal just created (its only evidence-free task/step means
   it's the only actionable candidate).
10. Click Pause, then Abandon — confirm the status badge updates each time and the action set updates
    accordingly (Approve never reappears; Abandon disappears once the goal is terminal).

## Context tab (11-13)

11. Switch to Context — type a simple message with no goal linkage ("How's the Layer 2E Intelligence
    Center goal going?") and click Preview — confirm a valid, mostly-empty bundle renders (`0 / 12000
    chars`, no categories populated) rather than erroring or fabricating content; this is correct
    when the message doesn't trigger `is_complex_task()`'s gating and no goal/project is scoped in.
12. Type a message that reliably triggers the Cognitive Core's complexity gate ("Implement a new
    feature that lets users export their tasks as a CSV file, including error handling.") and Preview
    again — confirm a populated `Cognitive brief` renders with Goal/Domain/Task type/Known/Unknown/
    Constraints/Success-looks-like/Watch-out-for/Next-step sections, a non-zero char count under the
    12000 budget, and no `compressed`/`fallback used` badges (nothing forced degradation at this
    size).
13. Confirm `excluded_context_summary` reasoning, when present, reads as a plain diagnostic string
    (e.g. "goal_context: goal not found or no longer active") — never a raw prompt fragment or stack
    trace.

## Layer 2 completion gate (14)

14. Confirm the full chain works as one path, not five disconnected pieces: a user message → Cognitive
    Core's `TaskUnderstanding`/brief (step 12 above) → `ContextBundle` assembly → (verified via the
    automated `test_context_bundle_goal_context_reaches_the_draft_prompt` /
    `test_end_to_end_request_to_goal_progress_pipeline` tests) the same bundle reaching
    `local_intelligence_engine`'s draft prompt when `context_selection_v2_enabled=true` → a linked
    `Goal`'s progress reflecting real Task/PlanStep evidence → the Intelligence Center's Overview
    reflecting that goal's counts and health. Each link was exercised directly above or via the
    automated suite; this step is the explicit acknowledgment that they were checked as one chain, not
    assumed to compose correctly from independently-passing pieces.

## Cleanup (15)

15. Revert `frontend/.env`'s `VITE_API_BASE_URL` to `http://localhost:8000`, stop the temp backend
    process and the temp-pointed dev server, confirm `git status` shows no stray changes outside the
    intended source files.
