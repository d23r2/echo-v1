# ECHO Layer 2D — Multi-Model Orchestrator and Tool Strategy Engine — Delivery Report

See [ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_ARCHITECTURE.md](ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_ARCHITECTURE.md)
for the full design and
[ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_SMOKE_TEST.md](ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_SMOKE_TEST.md)
for the manual checklist.

## Overall status: Green

1233/1233 backend tests pass (57 new), `ruff check .` clean, frontend `tsc -b --noEmit` and
`npm run build` both clean, live-verified in a real browser against an isolated temporary backend —
a real Preview showed a correct 7-stage `deep` plan for a debugging message with no model call made;
a real Run against genuine Ollama (`llama3`) answered a low-stakes message end-to-end, correctly
reported `QUESTION`/`SIMPLE`/`COMPLETED`, one model call, and the exact stage envelope
(`final`/`fast`/`via ollama (llama3)`/real duration/`completed`); the run appeared in Recent runs and
expanded to the identical detail; a policy checkbox toggle (`cloud_allowed` on the `question` row)
round-tripped through a real `PATCH` and was independently confirmed via a follow-up `GET` — the real
backend's data was never touched. Secret scan: 7 findings, all pre-existing Layer 0/1 test fixtures
(`test_infrastructure_logging.py`, `test_infrastructure_provider_registry.py`,
`test_layer1_candidates.py`, `test_layer1_privacy.py`), zero in any Layer 2D file.

## Architecture audit

**Existing systems reused, not reimplemented**: `local_intelligence_engine.py`'s
`LocalIntelligenceEngine.generate_response()` already implements the requested stage pipeline
(intent → context → draft → critic → repair → style → confidence → cloud gate) — `run_orchestration()`
delegates to it for `standard`/`deep` profiles rather than rebuilding drafting/critiquing.
`local_model_router.py`'s `LocalModelRouter` (role-based routing, bounded concurrency, one-retry
fallback) is reused directly for the `simple` profile. `context_router.py`'s `classify_context()` is
wrapped, not re-derived, by the new Tool Strategy Engine. `provider_errors.classify_provider_error()`
is translated (not reimplemented) for failure categorization.

**Duplicate systems avoided**: no second draft/critic/repair implementation; no duplicate
`GET /api/intelligence/tools` endpoint (the milestone's own suggested route — `/api/tools` already
covers it); two small, honest new tools (`project_search`, `task_search`) closed a real gap in the
*existing* `tool_registry.py` rather than a parallel registry being built.

**Major design decisions**: capability tags are static, honest declarations (never a measured
score); real usage stats are read separately from existing `metrics` counters and are `None`/`0`
until something has actually run; budgets are enforced primarily at *plan* time (profile downgrade)
since the underlying engine call can't be safely interrupted mid-pipeline; a `_HARD_MAX_CALLS`
backstop (6) cannot be overridden by any policy or request value; routing policy is one inspectable
table (`_DEFAULT_POLICY_BY_CATEGORY` → `OrchestrationPolicy` rows), not scattered if/else.

## Memory model

**Models added**: `OrchestrationPolicy`, `OrchestrationRun` (2 new tables — no existing table gained
a column). **Migration approach**: `Base.metadata.create_all()` only, `CURRENT_SCHEMA_VERSION` 5 → 6.
**Legacy compatibility**: all 1176 pre-2D tests pass unchanged.

## Capability registry (Phase 1)

`providers/registry.py` extended with `capabilities`/`speed_class`/`privacy_class`/`context_size`
(static, honest per-provider metadata) plus `measured_avg_latency_ms`/`measured_failure_rate`/
`measured_sample_count` read from the existing `app.core.metrics` counters via a new `_health_metrics()`
helper — correctly `None`/`0` until a real call has been recorded (tested explicitly, including the
metrics-global-state ordering fix described below). `_ROLE_CAPABILITIES` tags each local role;
`GET /api/system/models/roles` exposes the enriched list. Tested and live-verified (5 roles rendered
with capability-consistent tags in the frontend).

## Role-to-model mapping

Unchanged mechanism (`LocalModelRouter.model_for_role()`), now additionally capability-tagged for
display/routing purposes. Tested via `test_local_model_roles_carry_role_specific_capabilities` and
live-verified in the Routing tab's "Local model roles" panel.

## Policy engine

`_DEFAULT_POLICY_BY_CATEGORY` seeds one row per Layer 2A `TaskCategory` (`ensure_default_policies()`,
idempotent); `get_policy()`/`list_policies()`/`update_policy()` are plain CRUD; `classify_task_category()`
chains `classify_intent()` → `_task_type_for()` → `map_task_type_to_category()` — never a new
classifier. Tested for seeding, idempotency, unknown-category fallback to `mixed`, and partial
updates preserving untouched fields.

## Typed stage envelopes

`OrchestrationStagePlanItem` (forecast) and `OrchestrationStageResult` (actual) both use the exact
`OrchestrationStageName` literal set from the spec; the engine's own `pipeline_steps` vocabulary is
translated through an explicit allow-list (`_ENGINE_STEP_TO_STAGE`), skipping metadata-only entries
rather than coercing them into an invalid stage name — a real gap caught and fixed before any test
was written (see Bugs fixed below).

## Simple-task fast path

`simple` profile is always exactly one `final` stage, one `LocalModelRouter.call()`. Tested and
live-verified end-to-end against real Ollama: 1 model call, correct role/provider/model/duration in
the returned envelope, a genuine generated answer.

## Complex-task staged path

`deep`/`standard` profiles delegate to `LocalIntelligenceEngine.generate_response()`; the stage plan
correctly includes `plan`/`critique`/`repair`/`style` only when the profile and policy call for them
(tested and live-verified: a debugging message produces 7 stages with `reasoning`/`coding`/`critic`/
`writing` roles; a low-stakes message produces 1). A documented, deliberate divergence exists between
the planner's forecast and the engine's own real-time critic decision — never presented as a
guarantee.

## Tool Strategy Engine

`tool_strategy.build_tool_plan()` wraps `context_router.classify_context()`, maps sources to real
`tool_registry.TOOLS` entries, deduplicates, and honestly omits sources with no matching tool. Tested
for: no tools for creative tasks, a search tool for current-info tasks, `library_search` for the
uploaded-file source, both `project_search`/`task_search` present without duplication, no-tool
sources never producing an item, duplicate sources deduplicated, an unmatched source honestly
omitted, and the typed output shape. Live-verified via the API.

## Freshness / source routing

Unchanged — reuses `context_router.py`'s existing deterministic source classification entirely; this
milestone only adds the tool-name mapping layer on top.

## Permission checks

Unchanged — `tool_registry.run_tool()` still owns all permission/confirmation gating; the Tool
Strategy Engine only plans, never executes, and never bypasses that funnel.

## Cloud privacy policy

`_resolve_cloud_allowed()` composes five independent gates (global flag, request privacy level,
policy/request cloud-allowed, intent/category allowlist, confirmation requirement) — each tested in
isolation: cloud disabled by default, `local_only` privacy blocking cloud even with explicit
overrides set, and confirmation-required blocking cloud until `cloud_confirmed: true` is set. All
three also live-verified via direct API preview calls.

## Fallback chain

`LocalModelRouter.call()`'s existing one-retry-to-default-model fallback is exercised end-to-end
through the orchestrator via a real flipped retry scenario (a role-specific model configured but not
"installed," provider fails for that model name, succeeds for the default) — tested explicitly, not
assumed.

## Budget enforcement

`_effective_profile()` downgrades `deep→standard→simple` when the requested/policy call budget can't
afford the more expensive profile (tested for all three cost tiers); a post-execution
latency-budget check independently stops a run that actually exceeded it (tested with a real forced
delay, since a zero-cost fake call can finish under a millisecond and wouldn't exercise the check
honestly).

## Loop prevention

`_HARD_MAX_CALLS = 6` cannot be raised by any policy or request value — tested with an intentionally
absurd `max_model_calls: 10_000` request, confirming the resulting run's `total_model_calls` still
respects the ceiling.

## Structured repair

`repair_structured_output()` — deterministic, bounded, no extra model call: as-is parse → strip a
markdown fence → extract the first JSON span → give up. Tested for all four outcomes directly, plus
wired end-to-end through `run_orchestration()` for both the successfully-repaired case (a `repair`
stage entry recorded, `answer` rewritten to clean JSON) and the unrepairable case (`status: failed`,
`stop_reason: malformed_output`) — this was a self-identified gap (the milestone's own required test
"malformed structured output repaired within budget" had no underlying implementation) closed before
any test claiming it was written.

## Metrics

`router.py`'s and `local_model_router.py`'s existing call sites now also record
`model_call_duration_ms` (auto-mode chat, pinned-provider chat, streaming's time-to-first-chunk, and
both of `LocalModelRouter.call()`'s success paths) — no new instrumentation mechanism, just additional
recordings at chokepoints that already called `metrics.increment()`. Tested directly, including a
metrics-global-state test-isolation fix (see Bugs fixed).

## Clean via-metadata

`stages_json`/`answer` never contain a raw system prompt, a stack trace, or the literal word
"Traceback" — tested by constructing a run and asserting on the serialized output; `categorize_failure()`
never leaks raw exception text into its returned category string — tested explicitly.

## Frontend routing settings

New **Routing** tab in `CognitiveCoreView.tsx`: Preview & Run panel, an editable policy table (14
rows), a Local model roles reference panel, and a Recent runs list with expand/collapse. Live-verified
end-to-end: preview (no model call), run (real Ollama call, correct Advanced-run-view detail),
expand/collapse on the run list, and a policy checkbox toggle round-tripping through a real PATCH.

## Backend full tests

`cd backend && .venv/Scripts/python.exe -m pytest -q` → **1233 passed** (57 new). `ruff check .` →
**All checks passed!**

## Frontend typecheck/build

`npx tsc -b --noEmit` → clean. `npm run build` → clean, 326 modules.

## Files changed

**New backend**: `services/orchestration_engine.py`, `services/tool_strategy.py`, 5 new test files
(57 tests total).

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`,
`routers/system.py`, `providers/registry.py`, `router.py`, `services/local_model_router.py`,
`services/tool_registry.py`.

**New frontend**: none (existing page extended).

**Modified frontend**: `api/client.ts` (Layer 2D types + ~9 new functions),
`components/cognitive/CognitiveCoreView.tsx` (Routing tab added, `RoutingTab`/`RunDetail`
components added).

**New docs**: this report, the architecture doc, the smoke test doc.

## Bugs fixed

- **Real gap in pipeline-step translation (found and fixed before any test file was written)**: an
  early draft of `run_orchestration()`'s standard/deep branch mapped
  `local_intelligence_engine.py`'s `pipeline_steps` entries (including metadata-only ones like
  `"intent:*"`, `"context_gathered"`, `"cognitive_brief:*"`, `"role:*"`) almost directly into stage
  results — these aren't valid `OrchestrationStageName` values and would have thrown a Pydantic
  validation error the first time a real run's `stages_json` was serialized. Fixed by introducing an
  explicit allow-list translation (`_ENGINE_STEP_TO_STAGE`), skipping anything not in it.
- **Self-identified, closed-before-claimed gap**: `OrchestrationRequest.structured_output_required`
  was a schema field with no corresponding repair logic anywhere — the required test "malformed
  structured output repaired within budget" was not written until `repair_structured_output()` was
  implemented and wired into `run_orchestration()` first.
- **Test-isolation bug (self-caught, in test code only — no product-code fix needed)**: two
  capability-registry tests assumed a fresh `app.core.metrics` global state
  (`measured_avg_latency_ms is None` "when nothing has been recorded yet"), but `metrics`'s counters
  are process-global, not per-test — running the five Layer 2D test files together in a different
  order than the full suite's default alphabetical collection caused pollution from an earlier
  execution test to leak into these assertions. Fixed by calling the established `metrics.reset()`
  convention (already used by `test_infrastructure_metrics.py`/`test_layer1_metrics_feedback.py`) at
  the start of both tests, making them order-independent — confirmed by re-running all five new files
  together in a deliberately different order.
- **Test-assumption bug (self-caught, no product-code fix needed)**: an early `build_plan()` smoke
  test used messages containing the word "today" ("Thank you so much for your help today!"),
  expecting a `simple` profile, but `search_intent.py`'s pre-existing (Layer-0-era) freshness
  detector matches "today" as a current-info signal, classifying the message as `research`/`standard`
  instead. Confirmed as an out-of-scope, stable, already-tested quirk elsewhere in the codebase —
  fixed by rewriting the test message, not the detector.

## Bugs not fixed

None outstanding in Layer 2D code. Pre-existing items from `PROGRESS.md`'s Blockers section remain
open and are unrelated to this milestone.

## Manual checks remaining

- The full 23-step `ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_SMOKE_TEST.md` was spot-verified
  (Preview for both simple and deep tasks, a real Run against genuine Ollama, Recent-runs
  expand/collapse, a policy toggle round-trip) but not run as one continuous pass against the real
  backend's data — verification deliberately used an isolated temp backend instead.
- The schema migration (v5 → v6) has not yet been applied to the real running backend's database —
  purely additive (two new tables only) by construction, exercised only against a fresh temp DB and
  the automated suite so far.
- Cloud-gating (steps 12-14) and tool-selection (steps 15-17) and structured-output-repair (step 18)
  in the smoke test were verified via direct API calls rather than dedicated frontend controls — the
  Routing tab's Preview & Run panel doesn't yet expose `privacy_level`/`cloud_confirmed`/
  `structured_output_required` as UI toggles (documented in the architecture doc's Known limitations;
  fully supported and tested at the API layer).

## Rollback instructions

See [Architecture doc §15](ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_ARCHITECTURE.md#15-rollback-procedure).
Summary: every schema change is additive (two new tables, no modified columns); reverting the 9
modified backend files and 2 modified frontend files, and deleting the 2 new service files and 5 new
test files, restores pre-2D behavior exactly.

## Is Layer 2D ready as a release candidate?

**Green as a local release candidate.** Not pushed anywhere. Ready to be tagged
`echo-layer-2d-orchestration-tool-strategy-rc` after your review of `git status`/`git diff --stat`.
Per the milestone's own instruction, **Layer 2E should only begin after this report has been
reviewed** — I have not started 2E and will not without a fresh go-ahead.

## Proof table

| Proof item | Result |
|---|---|
| Capability registry | pass |
| Role-to-model mapping | pass |
| Policy engine | pass |
| Typed stage envelopes | pass |
| Simple-task fast path | pass |
| Complex-task staged path | pass |
| Tool Strategy Engine | pass |
| Freshness/source routing | pass |
| Permission checks | pass |
| Cloud privacy policy | pass |
| Fallback chain | pass |
| Budget enforcement | pass |
| Loop prevention | pass |
| Structured repair | pass |
| Metrics | pass |
| Clean via-metadata | pass |
| Frontend routing settings | pass |
| Backend full tests | pass (1233/1233) |
| Frontend typecheck/build | pass |
