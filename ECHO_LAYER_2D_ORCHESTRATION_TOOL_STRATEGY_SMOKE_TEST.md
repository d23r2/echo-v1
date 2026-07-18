# ECHO Layer 2D — Multi-Model Orchestrator and Tool Strategy Engine Manual Smoke Test

Run alongside the automated 57-test Layer 2D suite. Uses the safe temp-port pattern (never point the
frontend at a real port-8000 backend while testing against data you care about — see prior
milestones' established pattern) and real Ollama (already running in this dev environment).

## Setup (1-2)

1. Confirm backend on `http://localhost:8000` and frontend on `http://localhost:5174` (reuse the
   existing backend if healthy).
2. Confirm `GET /api/system/version` reports `schema_version: 6`.

## Preview (3-5)

3. Open Advanced → Cognitive Core → Routing — confirm the tab renders a Preview & Run panel, a
   Policies-by-task-category table (14 rows, one per Layer 2A `TaskCategory`), a Local model roles
   panel (5 roles), and an empty Recent runs list.
4. Type a low-stakes message ("I really appreciate your patience and kindness.") and click "Preview
   plan" — confirm it shows `QUESTION` / `SIMPLE` / cloud not allowed, exactly one `final` stage, and
   a budget of 1 call — with no model call having been made (no delay, no run appears in Recent
   runs).
5. Type a complex message ("Fix the failing backend test for the login flow") and Preview again —
   confirm `DEBUGGING` / `DEEP` / 7 stages (`understand, plan, reason, critique, repair, style,
   final`), a budget of 4 calls, and the correct role tags (`reasoning`/`coding`/`critic`/`writing`).

## Run — simple path (6-8)

6. Re-type the low-stakes message and click "Run" — confirm a real answer appears (genuine Ollama
   output, not a placeholder), status `COMPLETED`, exactly 1 model call, and a `final` stage entry
   showing `fast` role, `via ollama (llama3)`, a real duration in ms, `completed`.
7. Confirm the run now appears in Recent runs with the message as its title and a `COMPLETED` badge.
8. Click the run row to expand — confirm the same detail (answer, stage list, tools/token summary)
   renders identically to the live Run result.

## Policies (9-11)

9. On the "question" policy row, toggle "cloud allowed" — confirm the checkbox reflects the new
   state after the page's own refresh (no manual reload needed).
10. Change "max calls" on the "coding" row to a smaller number and confirm it persists.
11. `GET /api/intelligence/orchestration/policies` directly — confirm the same values are reflected
    server-side (not just optimistic UI state).

## Cloud gating (12-14, via API — no dedicated cloud-confirmation UI control yet)

12. With `CLOUD_FALLBACK_ENABLED` unset (default off), `POST /api/intelligence/orchestration/preview`
    with any message — confirm `cloud_allowed: false` regardless of policy.
13. With `CLOUD_FALLBACK_ENABLED=true` and a policy's `cloud_allowed=true`/
    `require_confirmation_for_cloud=true`, preview with `cloud_confirmed: false` — confirm
    `cloud_allowed: false`; repeat with `cloud_confirmed: true` — confirm `cloud_allowed: true` and
    `"cloud_call"` present in `confirmation_points`.
14. Preview the same request with `privacy_level: "local_only"` — confirm `cloud_allowed: false`
    even with `cloud_allowed: true` and `cloud_confirmed: true` set on the request.

## Tool selection (15-17, via API)

15. `POST /api/intelligence/tools/plan` with a creative-writing message — confirm `items: []`.
16. `POST /api/intelligence/tools/plan` with a current-info question ("what's the latest news on...
    today") — confirm at least one of `web_search`/`rss_search`/`wiki_search` appears.
17. `POST /api/intelligence/tools/plan` with "what are my active projects and open tasks?" — confirm
    both `project_search` and `task_search` appear, each with a `purpose` string and no raw internal
    field names.

## Structured-output repair (18-19, via API — no dedicated UI toggle yet)

18. `POST /api/intelligence/orchestration/run` with `structured_output_required: true` against a
    message whose real Ollama answer isn't already clean JSON — confirm either a repaired JSON
    `answer` with a `repair` stage entry (`status: completed`), or — if the model's raw text has no
    extractable JSON at all — `status: failed` / `stop_reason: malformed_output`, never a silently
    malformed `answer` returned as if it succeeded.

## No hidden reasoning / clean metadata (20)

20. Inspect any `/api/intelligence/orchestration/*` response — confirm no field contains a raw system
    prompt, a stack trace, or the literal word "Traceback"; `stages_json` entries only ever contain
    the typed envelope fields (`stage`/`role`/`provider`/`model`/`duration_ms`/`status`/`detail`).

## Regression (21-23)

21. Confirm the pre-existing World Model, Skill Library, Causal Notes, Task Understandings, Cognitive
    Briefs, Systems, Simulations, Decisions, and Plans tabs still work exactly as before.
22. Confirm normal chat still works end-to-end with clean `via Ollama`-style metadata, unaffected by
    this milestone.
23. Run the full backend test suite and frontend build; confirm both pass clean (1233/1233 backend
    at the time of this milestone, 57 of them new; frontend typecheck + build clean).
