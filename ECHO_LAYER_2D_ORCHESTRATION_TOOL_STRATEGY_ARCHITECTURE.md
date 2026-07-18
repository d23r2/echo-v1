# ECHO Layer 2D — Multi-Model Orchestrator and Tool Strategy Engine — Architecture

## 1. Scope

A policy + budget + typed-envelope layer over generation and tool selection that already exist.
Given a user message, `build_plan()` deterministically decides: which `TaskCategory` this is, how
"staged" the answer should be (`simple`|`standard`|`deep`), which local model role(s) that implies,
whether cloud is even eligible, which read-only tools are relevant, and what budgets/stop conditions
apply — all without making a single model or tool call. `run_orchestration()` then executes that
plan by delegating to already-tested primitives and returns a typed `OrchestrationRun` with a
per-stage envelope (`stage`/`role`/`provider`/`model`/`duration_ms`/`status`/`detail`) — never raw
prompts, chain-of-thought, or a stack trace.

## 2. Phase 0 audit findings

- **Reusable as-is, not reimplemented**: `local_intelligence_engine.py`'s `LocalIntelligenceEngine.
  generate_response()` already implements almost exactly the requested "stage pipeline" (intent →
  context → draft → critic → repair → style → confidence → cloud-fallback-gate), so `run_orchestration()`
  delegates to it for `standard`/`deep` profiles rather than rebuilding drafting/critiquing.
  `local_model_router.py`'s `LocalModelRouter` already implements role-based Ollama routing with
  bounded concurrency and a one-retry-to-default-model fallback — reused directly for the `simple`
  profile's single deterministic call. `context_router.py`'s `classify_context()` already implements
  deterministic tool/source routing — `tool_strategy.build_tool_plan()` wraps it rather than
  re-deriving source selection. `provider_errors.classify_provider_error()` is reused (translated,
  not re-implemented) for failure categorization.
- **Duplicate systems avoided**: no second draft/critic/repair implementation; no second tool
  registry (two small, honest new tools — `project_search`/`task_search` — were added to the
  *existing* `tool_registry.py` to close a real gap rather than inventing a parallel one); no
  duplicate `GET /api/intelligence/tools` endpoint (the spec's own suggestion) since `/api/tools`
  already lists tools/runs.
- **Major design decision — capability tags are honest declarations, not measured scores**:
  `providers/registry.py`'s `_PROVIDER_META[...]["capabilities"]` is a static list per provider
  (what it's *typically* good at), never a claim derived from actual output quality. Real usage
  data (`measured_avg_latency_ms`/`measured_failure_rate`/`measured_sample_count`) is read
  separately from `app.core.metrics`'s existing counters — `None`/`0` when nothing has run yet,
  never fabricated.
- **Major design decision — budgets enforced at plan time, not mid-execution**: `LocalIntelligenceEngine.
  generate_response()` is a black-box call that can't be safely interrupted partway through. Rather
  than attempting (and failing) to abort mid-pipeline, `_effective_profile()` downgrades the stage
  profile (`deep→standard→simple`) at *plan* time whenever the requested/policy call budget is too
  tight for the more expensive profile, using a static `_PROFILE_CALL_COST` table. A `_HARD_MAX_CALLS`
  backstop (6) applies regardless of any policy or request override — the loop-prevention floor.
- **Major design decision — policy is one table, not scattered if/else**: `_DEFAULT_POLICY_BY_CATEGORY`
  is a single dict (one row per Layer 2A `TaskCategory`), persisted as `OrchestrationPolicy` rows and
  editable via PATCH — routing decisions are testable and inspectable in one place, not spread across
  branches in the execution path.

## 3. Data model

`OrchestrationPolicy` (one row per `task_category`, seeded idempotently by `ensure_default_policies()`):
`stage_profile`, `cloud_allowed`, `require_confirmation_for_cloud`, `max_model_calls`,
`token_budget`, `latency_budget_ms`, `skip_critic_for_low_risk`. `OrchestrationRun` (one row per
executed orchestration): `task_id`/`conversation_id` (nullable), `objective` (a truncated snapshot
of the user message, never the full raw prompt), `task_category`, `stage_profile_used`, `status`
(`completed|failed|stopped_budget|stopped_loop`), `answer`, `stages_json` (list of typed stage
envelopes), `tools_used_json`, `total_model_calls`, `total_tokens_estimate`, `cloud_used`,
`stop_reason`. Schema version bumped 5 → 6, both tables brand-new — no `_ensure_column()` migration
needed.

## 4. Capability registry (Phase 1, `providers/registry.py`)

Extends the existing Layer 0 `ProviderRecord`/`LocalModelRoleRecord` with `capabilities` (a vocabulary
of `planning|extraction|classification|coding|reasoning|critique|writing|summarization|vision|
embeddings|tool_calling|json_reliability`), `speed_class` (`fast|medium|slow`), `privacy_class`
(`local|cloud`), `context_size`, and the three `measured_*` fields read via a new `_health_metrics()`
helper that parses `metrics.snapshot()`'s existing `counters`/`durations` dicts — no new
instrumentation path, just a summary read of counters `router.py`/`local_model_router.py` were
already recording (extended in this milestone to also record `model_call_duration_ms` at their
existing chokepoints). `_ROLE_CAPABILITIES` maps each local role (`fast|reasoning|coding|critic|
writing`) to its typical capability list, matching how `local_intelligence_engine.py` actually uses
each role. `GET /api/system/models/roles` (new) exposes the capability-enriched role list — the bare
role→model mapping was already in `GET /api/system/models`; this is the fuller Phase 1 view.

## 5. Policy engine (Phase 2, `services/orchestration_engine.py`)

`classify_task_category()` chains three already-tested classifiers rather than re-deriving a new
IntentCategory→TaskCategory table: `intent_classifier.classify_intent()` → `cognitive_core.
_task_type_for()` (imported directly) → `task_understanding_v2.map_task_type_to_category()`.
`get_policy()`/`list_policies()`/`update_policy()` are plain CRUD over `OrchestrationPolicy`, falling
back to the `mixed` category's policy for an unrecognized category. `_resolve_cloud_allowed()`
composes the *existing* `settings.cloud_fallback_enabled`/`cloud_fallback_allowed_intent_list`
(never a second privacy policy): cloud is only ever eligible when the global flag is on, the
request's `privacy_level` isn't `local_only`, the resolved policy (or an explicit request override)
allows it, the classified intent/category is on the allowed-intents list, and — when the policy
requires it — the request carries `cloud_confirmed: true`.

## 6. Stage pipeline (Phase 3)

`build_plan()` is pure — classifies the task, resolves the effective stage profile (policy default,
downgraded if the budget is tight), builds a tool plan (Phase 4), resolves cloud eligibility, and
assembles a `_stages_for_profile()` list of typed `OrchestrationStagePlanItem`s
(`understand|retrieve|plan|tool|reason|critique|repair|style|final`, each with an optional `role` and
a plain-language `purpose`). `simple` is always exactly one `final` stage (no tool/critic overhead
for a trivial answer). `standard`/`deep` add `understand` (deterministic — no model call),
optionally `tool`, optionally `plan` (deep only), `reason`, `critique`/`repair` when warranted
(policy default, hard difficulty, or a coding/debugging/decision category), `style` (deep only), and
`final`. This is a forecast, not a guarantee — `run_orchestration()`'s actual `stages_json` can
differ slightly when the underlying engine's own internal logic (e.g. `_should_run_critic()`) makes
a different real-time call than the planner predicted; this divergence is deliberate and documented,
not a bug (the planner never claims certainty about the engine's internals).

## 7. Tool Strategy Engine (Phase 4, `services/tool_strategy.py`)

`build_tool_plan()` wraps `context_router.classify_context()` and maps its `ContextSource` values
onto real, registered `tool_registry.TOOLS` entries via a static `_SOURCE_TO_TOOL` dict — a source
with no matching real tool (`schedule`, `direct_page`, `code_project_files`, `normal_chat`,
`unavailable`) is honestly omitted rather than a fabricated tool being invented for it. Deduplicates
by `tool_name`. Two new tools were added to `tool_registry.py` to close a real gap: `project_search`
and `task_search` (plain read-only lookups, same shape as the existing search tools) — the "projects"
and "tasks" `ContextSource`s had no matching tool before this milestone.

## 8. Tool execution controls (Phase 5)

Unchanged — `tool_registry.run_tool()` (existing) still owns permission checks and confirmation
gating; this milestone only *plans* which tools are relevant, it never bypasses or duplicates that
funnel. A tool item's `requires_confirmation` in the plan mirrors the tool's own
`spec.requires_confirmation or risk_level in ("high","destructive")`.

## 9. Fallback / failure recovery and budgets (Phase 6-7)

`categorize_failure()` translates `provider_errors.classify_provider_error()`'s existing vocabulary
into this milestone's `FailureCategory` (`unavailable|timeout|malformed_output|rate_limited|
quota_exceeded|billing_required|model_missing|tool_failure|unknown_error`) via a static dict — never
a raw exception message reaching a caller. `run_orchestration()`'s `simple` path uses
`LocalModelRouter.call()` directly (its own tested retry-to-default-model fallback already handles a
missing role-specific model); the `standard`/`deep` path delegates to `LocalIntelligenceEngine.
generate_response()`, translating its `pipeline_steps` entries through an explicit allow-list
(`_ENGINE_STEP_TO_STAGE = {"draft":"reason","critic":"critique","repair":"repair","style":"style"}`)
— metadata-only entries (`intent:*`, `context_gathered`, `cognitive_brief:*`, `role:*`) are skipped
since they aren't valid `OrchestrationStageName` values, not silently coerced into one. After
execution, an honest post-hoc budget check (`latency_budget_ms`/`token_budget` against what actually
happened) can still flag `status="stopped_budget"` even though the primary enforcement is the
plan-time profile downgrade described in §2.

**Structured-output repair**: `repair_structured_output()` is a deterministic, bounded, *non-model-call*
repair — try `json.loads()` as-is; if that fails, strip a markdown code fence and retry; if that
fails, extract the first `{...}`/`[...]` span and retry; otherwise give up (one attempt only, no
model call — a second generation call would defeat "don't use more model calls just to appear
intelligent"). Only engages when `request.structured_output_required=True`; a successful repair
records a `repair` stage entry and rewrites `answer`; an unrepairable result sets
`status="failed"`/`stop_reason="malformed_output"` rather than returning malformed text.

## 10. API (`routers/intelligence.py`, `routers/system.py`, additive)

`POST /api/intelligence/orchestration/preview` (pure plan, no model call) · `POST .../run` (executes)
· `GET .../runs/{id}` · `GET .../runs` · `GET .../policies` · `PATCH .../policies/{id}` ·
`POST /api/intelligence/tools/plan` · `GET /api/system/models/roles`. Standard Layer 0 error objects;
an unknown run/policy id 404s.

## 11. Frontend

`CognitiveCoreView.tsx` gains a **Routing** tab: a Preview & Run panel (type a message, Preview shows
the plan with no model call, Run actually executes and shows the Advanced run view — per-stage
provider/model/duration/status, the answer, model-call/token counts, tools used, cloud-used flag),
an editable policy table (one row per task category — stage profile, cloud allowed, confirm-before-
cloud, max calls), a compact local-model-roles reference panel, and a Recent runs list with
expand/collapse detail (reusing the same `RunDetail` renderer as the live Run result). No raw JSON,
prompts, or chain-of-thought are ever rendered — only the typed stage envelope fields.

## 12. Test strategy

57 new backend tests across five files: `test_layer2d_capability_registry.py` (capability/speed/
privacy tags present, measured-health fields correctly None until metrics exist, role capability
tags), `test_layer2d_orchestration_policy.py` (policy CRUD, task classification, profile-downgrade
budgeting, the hard-cap backstop, cloud-eligibility composition including the local-only and
confirmation-required gates, stage-plan shape for simple vs. deep, failure categorization, and the
structured-output repair helper's four cases), `test_layer2d_orchestration_execution.py`
(`run_orchestration()` end-to-end for both execution paths using `FakeProvider`/monkeypatched
`LocalModelRouter` class references — never real Ollama or a real cloud call — covering: simple-task
single call, staged-pipeline delegation, the role-model-missing local fallback via a real flipped
retry, cloud-disabled/confirmation-required/local-only-privacy all correctly blocking cloud use, no
tool call for a creative task, a clean failed run on a provider exception (no stack trace leaked),
categorize_failure never leaking raw exception text, a tight latency budget stopping the run,
structured-output repair wired end-to-end for both the repaired and unrepairable cases, no raw system
prompt or traceback ever stored, and the hard-cap surviving an absurd requested budget),
`test_layer2d_tool_strategy.py` (creative task selects nothing, current-info selects a search tool,
library source maps to the file-retrieval tool, projects/tasks both get distinct tools, no-tool
sources never produce an item, duplicate sources are deduplicated, an unmatched source is honestly
omitted, and the typed output shape), `test_layer2d_intelligence_api.py` (the full orchestration +
tool-plan + capability-role API surface via `TestClient`, `FakeProvider`-backed).

## 13. Privacy / safety rules honored

Cloud is never reachable without the global flag on, an explicit non-local privacy level, policy
approval, an intent/category allowlist match, and (when required) explicit confirmation — verified
by three separate tests covering each independent gate. Tool selection never bypasses
`tool_registry.run_tool()`'s own permission/confirmation checks — this milestone only plans, it
never executes a tool itself. `stages_json`/`answer` never contain a raw system prompt, a stack
trace, or the word "Traceback" — verified directly. Structured-output repair never makes an extra
model call. The hard 6-call ceiling cannot be raised by any request or policy value.

## 14. Known limitations

- The stage-plan forecast (`build_plan()`) and the engine's own real-time critic decision
  (`LocalIntelligenceEngine._should_run_critic()`) can diverge for a specific message — documented
  in §6, not treated as a bug.
- Budget enforcement for `standard`/`deep` runs is primarily a plan-time profile downgrade, not a
  mid-pipeline abort — a black-box delegate call already in flight completes rather than being cut
  off partway (see §2/§9's rationale).
- The frontend Routing tab's Preview & Run panel always uses `task_type: undefined` (deterministic
  classification from the message) — there's no UI control yet to force a specific `task_type` or to
  set `structured_output_required`/`privacy_level`/`cloud_confirmed` from the Advanced run view; those
  fields are fully supported by the API and covered by tests, just not yet exposed as UI controls.

## 15. Rollback procedure

1. Revert `backend/app/models.py`, `schemas.py`, `db.py`, `routers/intelligence.py`,
   `routers/system.py`, `providers/registry.py`, `router.py`, `services/local_model_router.py`,
   `services/tool_registry.py`.
2. Delete `backend/app/services/orchestration_engine.py`, `backend/app/services/tool_strategy.py`.
3. Delete the five `test_layer2d_*.py` files.
4. Revert `frontend/src/api/client.ts` and `frontend/src/components/cognitive/CognitiveCoreView.tsx`.
5. The two new tables become orphaned but harmless in an existing SQLite file — no destructive DROP
   is required for a clean local rollback, matching every prior layer's own stated pattern.
