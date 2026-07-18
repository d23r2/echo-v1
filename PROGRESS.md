# ECHO (formerly God Tear AI Brain) — Progress Log

Last check-in: 2026-07-19

## New since 2026-07-19 — ECHO Supervised Maintenance Workspace v1 (complete, Phases 1-8, GREEN)

Built a read-only-first code analysis workspace that feeds the existing Layer 3A Part 2D self-
modification pipeline rather than duplicating it — per the milestone's own explicit "do not create a
second Permission Center, Audit system, Action System, Feature Flag service, or Governance Center"
requirement. `CodeAccessService` gives Echo a contained, canonicalized, secret-safe read-only view of
its own approved repository (which is always this backend's own running codebase —
`register_repository()` never accepts a client-supplied path, eliminating path-injection by
construction rather than validation); a capability-mode ladder (`disabled` → `analyse_only` →
`propose_only` → `sandbox_verify` → `human_approved_local_commit`) layers on top of the independent
Part 2D flags; and a thin `MaintenanceProposalService` wrapper calls the unmodified Part 2D
`create_proposal()`/`submit_revision()`, tagging results with `analysis_id`. 12 of 14 requested
components are reused unmodified or additively extended rather than rebuilt. Dedicated tests proved the
full 7-stage proposal pipeline and the local-branch deploy/rollback machinery are both completely
analysis-agnostic — zero special-casing anywhere. Phase 6 added the human review frontend and this
repo's first frontend test framework (vitest + Testing Library). Phase 8's adversarial hardening pass
found and fixed one real gap — `CodeAccessService` did not reject a mid-path NTFS Alternate Data Stream
colon (`file.py:hidden_stream`); direct interpreter probing showed `Path.resolve()` silently accepted
it — now explicitly rejected and covered by 2 dedicated tests, alongside 9 more adversarial tests
(Windows junction escape via a real `mklink /J`, reserved device names, oversized files,
archive-as-opaque-binary, case/separator scope bypass, prompt-injection content pass-through,
special-character filenames). Final state: **backend 1639/1639 passed**, ruff clean, frontend
typecheck/build clean, frontend tests 4/4 passed, 51 dedicated Supervised Maintenance tests total. All
five maintenance feature flags default off. Final verdict: **GREEN** — see
[ECHO_SUPERVISED_MAINTENANCE_WORKSPACE_V1_REPORT.md](ECHO_SUPERVISED_MAINTENANCE_WORKSPACE_V1_REPORT.md),
[docs/supervised_maintenance/architecture.md](docs/supervised_maintenance/architecture.md),
[threat_model.md](docs/supervised_maintenance/threat_model.md),
[policy.md](docs/supervised_maintenance/policy.md), and
[operator_guide.md](docs/supervised_maintenance/operator_guide.md).

## New since 2026-07-19 — ECHO Layer 3A Part 2D: Supervised Self-Modification

Implemented a fail-closed proposal → sandbox → human-approve → (optional, local-only) apply → rollback
workflow, letting Echo draft and evaluate an exact code patch without ever approving, merging, or
deploying it itself. Claude Code built the initial domain model (11 new tables, schema v10), the
governance service, a git-worktree sandbox, and the router/test suite; Codex then continued that same
uncommitted work with real security hardening — a Docker execution boundary (`--network none`,
`--cap-drop ALL`, non-root, a fixed no-shell command dispatcher with a from-scratch environment),
default-deny path allowlisting plus protected-symbol detection, patch secret/test-weakening scanning,
self-approval prevention, and deploy-time re-verification against five independent snapshotted
fingerprints (hash, base commit, target, scope, and both the scope-policy and Constitution
fingerprints) — and built the review frontend. Claude Code then independently re-verified the combined
result, found and fixed three real issues surfaced only by running the full suite (a stale hardcoded
schema-version assertion, an unrelated Part 2C persona test, and a missing `"governance"` action
category in a response schema), and confirmed live against a real disposable repository that
deployment and rollback never touch the primary working tree. Full suite: **1588/1588 passed**, Ruff
clean, frontend typecheck/build clean. All four feature flags default off; nothing was committed. See
[ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md](ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_ARCHITECTURE.md)
and [ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_REPORT.md](ECHO_LAYER_3A_PART2D_SELF_MODIFICATION_REPORT.md).

## New since 2026-07-18 — ECHO Layer 3A Part 2C: Adaptive Persona Engine

Implemented a provider-neutral, immutable persona resolver and bounded `PersonaBrief` using the
existing Human Persona settings and reviewed Atlas preferences. The engine separates communication
style from Core Identity, applies explicit precedence and expiry rules, protects accessibility and
voice-first needs, normalizes the relationship model, filters secret/sensitive inferred traits,
caches only safe normalized inputs, and adds deterministic dependency/false-consciousness/prompt-
leakage response guards. The same trusted brief now reaches ordinary chat, Local Intelligence,
orchestration, provider fallback/retry, document summaries, and Context Selection v2; a feature flag
retains the legacy rollback path. All 58 dedicated tests pass, Ruff/compile/focused mypy pass, and
fresh-database/startup verification is clean. The final combined worktree is YELLOW because
simultaneous self-modification work advanced schema v8 to v9 without updating one identity test and
imports a not-yet-created frontend `SelfModificationView`; details and proof are in
[ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_REPORT.md](ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_REPORT.md), with
the design in
[ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_ARCHITECTURE.md](ECHO_LAYER_3A_PART2C_PERSONA_ENGINE_ARCHITECTURE.md).

## New since 2026-07-18 — ECHO Layer 3A Part 2B: Identity Runtime and Prompt Integration

Implemented the runtime boundary on top of Part 2A: validated frozen identity snapshots, stable
non-secret fingerprints, existing-cache integration with explicit activation/archive invalidation,
atomic last-valid retention, deterministic degraded fallback, context-specific budgeted
`IdentityBrief` construction, protected Context Selection v2 identity context, startup preload,
safe status/version/developer diagnostics, and bounded logs/metrics. The same trusted identity
section now reaches ordinary chat, streaming/upload chat, welcome generation, Local Intelligence
draft/critic/repair/style passes, orchestration simple/standard/deep paths, cloud and Ollama
fallback/retry, tool document summaries, and conversation summaries. Provider adapters remain
transport-only and receive the identical composed system prompt. The flag-off path preserves legacy
prompt/action behavior; degraded runtime identity forces medium/high/destructive actions through the
existing explicit-confirmation lifecycle. Full verification results are recorded in
[ECHO_LAYER_3A_PART2B_IDENTITY_RUNTIME_REPORT.md](ECHO_LAYER_3A_PART2B_IDENTITY_RUNTIME_REPORT.md);
architecture, budgets, provider matrix, runbook, and security notes are in
[ECHO_LAYER_3A_PART2B_IDENTITY_RUNTIME_ARCHITECTURE.md](ECHO_LAYER_3A_PART2B_IDENTITY_RUNTIME_ARCHITECTURE.md).

## New since 2026-07-18 — ECHO Layer 3A Part 2A: Core Identity Database Foundation

Implemented the first production Layer 3A slice without runtime prompt integration: versioned
`AssistantIdentityProfile` and per-version `IdentityCommitment` tables (schema v8), a deterministic
14-commitment `echo-primary` seed, typed repository/lifecycle functions, strict JSON/secret-safe
metadata validation, and safe structured lifecycle events. Activation is transactional and backed by
a SQLite partial unique index; replacement flush order, typed rollback, and a real two-session race
are tested. The false-consciousness guard now matches explicit positive claims rather than treating
any unrelated “no/not” in a sentence as a denial. **93/93 dedicated identity tests and all 1401
combined-worktree backend tests pass**, backend lint and focused identity mypy pass, and frontend
typecheck/no-write build are clean. See
[ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md](ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md)
and [ECHO_LAYER_3A_PART2A_CORE_IDENTITY_REPORT.md](ECHO_LAYER_3A_PART2A_CORE_IDENTITY_REPORT.md).
No API, prompt injection, user values, consent records, or moral-evaluation engine was added; those
remain later Layer 3A work.

## New since 2026-07-18 — Layer 2E review remediation

- Closed the post-review approval bypass: system-suggested goals can no longer become active through
  the generic PATCH route and must use explicit approval.
- Completed end-to-end goal linkage for tasks, plans, replans, chat context, and the corresponding
  create/select UI; goal cards now support activate/resume/pause and collect a real abandonment
  reason.
- Restored Context Selection v2 fidelity (conversation, schedule, goal/system/decision/permission
  context, cognitive success criteria, Atlas citations, and gather diagnostics), added honest
  required-context fallbacks, and persist privacy-safe selection metrics without raw prompt content.
- Evaluation fixtures now execute in an isolated in-memory database, so evaluation runs retain their
  results without polluting the user's goals, plans, decisions, or task understandings.
- Verification: the focused regression set is 111/111, Ruff is clean, and the production frontend
  build passes. Its intermediate full run reached 1376 passes plus 3 failures in the separate Layer
  3A activation work; the Part 2A continuation above fixed those failures, and the final combined
  suite is now 1401/1401.

## New since 2026-07-18 (yet even later) — ECHO Layer 3A Part 1: Core Identity and Moral Compass — Architecture Audit

**Audit and design only — no production code, no schema changes, no commit.** Five parallel research
passes plus direct code reads confirmed the repository already has a live, tested (47/47) Constitution
and Guardian Council governance system (`backend/app/constitution.py`, `council.py`) — ranked
`CORE_VALUES`, 5 immutable `VALUE_INVARIANTS`, a deterministic amendment classifier — that's already
the first section of every system prompt across every provider. `CLAUDE.md`'s description of this as
not-yet-built is stale (predates Layer 0). The real gap: this Constitution reaches exactly one call
path (ordinary chat via `persona.build_system_prompt()`) and is confirmed absent from the Multi-Model
Orchestrator's `simple` stage-profile, welcome-message prompts, and the entire Decision/Planning/Goal
pipeline — closing that reach gap is Part 2's top priority. A second, smaller pre-existing gap was
found: `chat_actions.py`'s chat-typed create commands bypass the Permission Center entirely. Full
25-item threat model, an 8-tier precedence model (modeled on the Constitution's own amendment-classifier
pattern), a 9-entity domain model (two of the brief's suggested entities — `UserValueRevision`,
`PolicyDefinition` — were rejected in favor of reusing `MemoryRevision` and the existing Constitution/
`OrchestrationPolicy`, respectively), a 5-migration additive schema plan (v7→v12), and a Parts 2-5
sequencing plan. Baseline: 1296/1296 backend tests, clean lint/typecheck/build. **Final status: GREEN**
— ready for Part 2 once reviewed. See
[ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md](../ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md)
and
[ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_REPORT.md](../ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_REPORT.md).

## New since 2026-07-18 (even later) — ECHO Layer 2E: Goal Manager, Context Selection v2, and Intelligence Center

**Final Layer 2 milestone.** 1296 backend tests passing (63 new), frontend build/typecheck clean,
live-verified in a real browser against an isolated temporary backend with
`CONTEXT_SELECTION_V2_ENABLED=true` (created a goal via the new Intelligence Center — appeared
`APPROVED` immediately since it was explicit-user; expanded it and saw an honest `0% complete —
stalled` reading, never a fabricated percentage; ran a cross-goal review and got a real
recommendation back; previewed context for a simple message and got an honest empty bundle, then for
a complexity-triggering message got a real populated `CognitiveBrief` at 816/12000 chars). Deliberately
not a new hierarchy or retrieval layer — `Goal` reuses Layer 2C's `Plan`/`PlanStep` via a new
`Plan.goal_id` column, and `context_selector.py` wraps the existing `context_gatherer.gather_context()`
rather than re-deriving retrieval. See
[ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md](../ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md),
[ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_REPORT.md](../ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_REPORT.md),
and
[ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_SMOKE_TEST.md](../ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_SMOKE_TEST.md).

- **New: Goal model + approval policy (Phase 1)** — explicit-user goals are approved immediately;
  system-suggested goals stay `proposed` until an explicit approve call. `status` is the only
  approval gate, no separate `approval_state` field.
- **New: goal hierarchy + evidence-only progress (Phase 2)** — `compute_progress()` counts only real
  `Task.status=="done"`/approved-plan `PlanStep.status=="completed"` rows, never a model estimate;
  a goal with zero linked evidence reports `0%`, never a guess; auto-achieve only fires with real,
  complete evidence.
- **New: cross-goal review + next-action engine (Phase 3)** — ranks by blocker status, priority, and
  target date; a self-caught fix ensures an all-blocked goal set still produces a recommendation
  (resolve the blocker) instead of going silent.
- **New: Context Selection v2 — ContextRequest/ContextBundle (Phase 4)** — one compact bundle
  (cognitive brief, memory, goal/project/system/decision-or-plan context, tool evidence, permissions)
  wrapping the existing `context_gatherer`; deterministic status/relevance filtering (an abandoned
  goal, a cancelled plan, or an unscoped decision query never surfaces fabricated context) plus a
  self-caught exception guard so a genuine Chroma failure degrades to an honest empty-memory fallback
  instead of crashing.
- **New: budgeting + compression (Phase 5)** — lower-priority fields compress first, load-bearing
  fields (cognitive brief, goal context, memory) survive longest; exact-duplicate tool evidence and
  documents are deduplicated.
- **New: cross-layer integration (Phase 6)** — `local_intelligence_engine`'s task-oriented generation
  path consumes the `ContextBundle` behind a new default-off flag
  (`context_selection_v2_enabled`); flag-off behavior confirmed byte-identical to pre-2E. The full
  chain (message → CognitiveBrief → context → goal progress → achievement) is exercised end-to-end
  by an automated test, not assumed to compose correctly from independently-passing pieces.
- **New: `/api/goals/*` and `/api/intelligence/{context/select,context/preview,goals/review,overview}`**
  — additive alongside the untouched Layer 2A-2D `/api/intelligence/*` endpoints.
- **New: Layer 2 evaluation suite extension (Phase 8)** — 6 new deterministic checks, fixture cases
  10 → 21, including the literal "compare with and without Layer 2 features" requirement as a
  concrete assertion (a goal-linked `ContextBundle` must differ from an unlinked one).
- **New: Intelligence Center page** — Overview (health, goal counts, current task/plan, recent
  decisions/simulations, routing status, run-evaluations button), Goals (create/approve/pause/
  abandon/review with evidence-based progress), Context (preview what a message would actually
  gather) — every card naming another system links to its existing home rather than duplicating it.
- Database schema bumped to v7 (two new nullable columns, three new tables, all additive). **Layer 2
  is now complete** (2A Cognitive Core → 2B Systems/Simulation → 2C Decision/Planning →
  2D Orchestration/Tools → 2E Goals/Context/Intelligence Center). No Layer 3 prompt has been started.

## New since 2026-07-18 (later) — ECHO Layer 2D: Multi-Model Orchestrator and Tool Strategy Engine

1233 backend tests passing (57 new), frontend build/typecheck clean, live-verified in a real browser
against an isolated temporary backend (Preview showed a correct 7-stage `deep` plan for a debugging
message with zero model calls; Run against real Ollama answered a low-stakes message end-to-end with
the correct 1-call `simple` envelope; the run appeared in Recent runs and expanded correctly; a
policy checkbox toggle round-tripped through a real PATCH). Deliberately not a rewrite of chat
generation — `run_orchestration()` delegates the actual drafting/critiquing to the already-tested
`LocalIntelligenceEngine`/`LocalModelRouter`, and the Tool Strategy Engine wraps the existing
`context_router.classify_context()` rather than re-deriving source selection. See
[ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_ARCHITECTURE.md](../ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_ARCHITECTURE.md),
[ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_REPORT.md](../ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_REPORT.md),
and
[ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_SMOKE_TEST.md](../ECHO_LAYER_2D_ORCHESTRATION_TOOL_STRATEGY_SMOKE_TEST.md).

- **New: capability registry (Phase 1)** — `providers/registry.py` extended with honest, static
  `capabilities`/`speed_class`/`privacy_class`/`context_size` tags (never a measured score) plus
  real `measured_avg_latency_ms`/`measured_failure_rate`/`measured_sample_count` read from existing
  `metrics` counters — correctly `None`/`0` until something has actually run.
- **New: OrchestrationPolicy / OrchestrationRun + policy engine** — one policy row per Layer 2A task
  category (stage profile, cloud eligibility, confirmation requirement, call/token/latency budgets),
  editable via PATCH; `classify_task_category()` chains three already-tested classifiers rather than
  re-deriving a new mapping.
- **New: typed stage pipeline (Phase 3)** — `build_plan()` is a pure policy decision (no model call);
  `run_orchestration()` executes it, translating the underlying engine's own step vocabulary through
  an explicit allow-list rather than coercing metadata entries into an invalid stage name (a real gap
  caught before any test was written).
  Bounded structured-output repair (deterministic, no extra model call) closes a second
  self-identified gap the same way.
- **New: Tool Strategy Engine (Phase 4)** — wraps the existing `context_router.classify_context()`,
  maps sources onto real `tool_registry` tools, honestly omits sources with no matching tool. Two
  small new tools (`project_search`, `task_search`) close a real gap rather than inventing one.
- **New: cloud privacy gating** — five independent gates (global flag, request privacy level,
  policy/request cloud-allowed, intent allowlist, confirmation requirement), each tested in
  isolation; local-only privacy blocks cloud even when every other override says yes.
- **New: budget + loop prevention (Phase 6-7)** — a tight call budget downgrades the stage profile at
  plan time (the underlying engine call can't be safely interrupted mid-pipeline); a hard 6-call
  ceiling can't be raised by any policy or request value.
- **New: `/api/intelligence/orchestration/*` and `/tools/plan`, `/api/system/models/roles`** —
  additive alongside the untouched Layer 2A/2B/2C `/api/intelligence/*` endpoints.
- **Upgraded: Cognitive Core page** — new Routing tab (Preview & Run panel with the Advanced run
  view, an editable per-category policy table, a local-model-roles reference panel, and an
  expandable Recent runs list) — live-verified end-to-end against real Ollama.
- Database schema bumped to v6 (two new tables, purely additive — no existing table gained a
  column). **Per the milestone's own sequencing instruction, Layer 2E has not been started** — it
  begins only after this report is reviewed.

## New since 2026-07-18 — ECHO Layer 2C: Decision Engine and Planning Engine

1176 backend tests passing (61 new), frontend build/typecheck clean, live-verified in a real
browser against an isolated temporary backend (created and analysed a decision — correctly
reported an honest "no clear winner" for two undifferentiated options — selected an option, created
a plan, validated it, approved it, materialised it into three genuine Task rows confirmed
independently on the real Tasks page, and replanned it into a new proposed-status revision with the
original marked superseded). The Decision Engine recommends but never chooses for the user; the
Planning Engine never executes anything — materialisation reuses the existing permission-gated
Action System rather than a second execution path. See
[ECHO_LAYER_2C_DECISION_PLANNING_ARCHITECTURE.md](../ECHO_LAYER_2C_DECISION_PLANNING_ARCHITECTURE.md),
[ECHO_LAYER_2C_DECISION_PLANNING_REPORT.md](../ECHO_LAYER_2C_DECISION_PLANNING_REPORT.md), and
[ECHO_LAYER_2C_DECISION_PLANNING_SMOKE_TEST.md](../ECHO_LAYER_2C_DECISION_PLANNING_SMOKE_TEST.md).

- **New: DecisionCase / DecisionOption / DecisionCriterion** — hard-constraint elimination is
  driven by an explicit `violates_criteria_json` signal set at option-creation time, never a
  keyword-matching guess; weighted scoring only activates when a criterion has an explicit
  user-approved weight AND an option has an explicit per-criterion rating — nothing is inferred
  from free text or presented as fabricated precision.
- **New: Pareto detection and no-clear-winner outcomes** — a purely structural multi-objective
  comparison (benefits/risks/reversibility/evidence quality); `no_clear_winner` is a tested,
  first-class outcome for the all-eliminated, tied-score, and multi-non-dominated-option cases —
  never silently forces a recommendation the evidence doesn't support.
- **New: DecisionReport** — decision summary, recommendation rationale, key trade-offs, hard
  constraints checked, assumptions/uncertainties, alternatives, evidence quality, and a
  `confidence_band` that's honestly derived from evidence quality (low evidence → wide confidence,
  verified by a dedicated test).
- **New: Plan / PlanStep / Milestone / PlanDependency / PlanResourceRequirement / PlanRisk /
  PlanRevision** — plans distinguish exactly the 7 required states (proposed/approved/active/
  blocked/completed/failed/cancelled); plan steps map to real Tasks only after explicit approval,
  deliberately not duplicating the existing Tasks system.
- **New: dependency/critical-path/parallel-step validation** — same graph-algorithm family as
  Layer 2B's `systems_thinking.py` (cycle detection, longest-path critical path, depth-based
  parallel grouping), plus blocked-step-propagation and resource-conflict warnings.
- **New: adaptive replanning** — creates a new `Plan` revision rather than mutating history in
  place; completed steps carry forward unchanged, failed steps are dropped and recorded in a
  `PlanRevision`, the old plan is only ever annotated (`superseded_by_plan_id`) — "do not rewrite
  completed history" is true by construction, not convention.
- **New: execution handoff** — `materialise_plan()` reuses `action_system.run_action()` verbatim
  (the same permission-gated funnel every other real action in this app uses) rather than building
  a second execution path; verified with a real flipped `requires_confirmation` flag that an
  action needing confirmation stays a pending, honest proposal instead of silently executing.
- **New: `/api/intelligence/decisions/*` and `/plans/*`** — additive alongside the untouched Layer
  2A/2B `/api/intelligence/*` endpoints.
- **Upgraded: Cognitive Core page** — new Decisions tab (create, rate options per criterion, set
  weights, analyse, select) and Plans tab (create, validate, approve, materialise into real tasks,
  replan, flag risks) — both live-verified end-to-end.
- Database schema bumped to v5 (ten new tables, purely additive — no existing table gained a
  column). **Per the milestone's own sequencing instruction, Layer 2D (Multi-Model Orchestrator and
  Tool Strategy Engine) has not been started** — it begins only after this report is reviewed.

## New since 2026-07-17 (later still) — ECHO Layer 2B: Systems Thinking and Simulation Engine

1115 backend tests passing (59 new), frontend build/typecheck clean, live-verified in a real
browser against an isolated temporary backend (created a system model, added nodes, added a real
dependency relationship, confirmed correct bottleneck/cycle/critical-path analysis and a matched
causal counterfactual, ran both a grounded and an ungrounded simulation, confirmed honest
evidence/sensitivity labelling and the decision-handoff summary). Extends Cognitive Core's existing
world-model graph in place — `SystemModel` is a scoped view over `CognitiveConcept`/
`CognitiveRelationship`, not a second graph database. See
[ECHO_LAYER_2B_SYSTEMS_SIMULATION_ARCHITECTURE.md](../ECHO_LAYER_2B_SYSTEMS_SIMULATION_ARCHITECTURE.md),
[ECHO_LAYER_2B_SYSTEMS_SIMULATION_REPORT.md](../ECHO_LAYER_2B_SYSTEMS_SIMULATION_REPORT.md), and
[ECHO_LAYER_2B_SYSTEMS_SIMULATION_SMOKE_TEST.md](../ECHO_LAYER_2B_SYSTEMS_SIMULATION_SMOKE_TEST.md).

- **New: SystemModel / SystemModelNode** — a named, scoped view over the existing world-model
  graph; edges are the existing `CognitiveRelationship` rows, scoped by node membership, with
  `relation_type` additively extended (`consumes`/`communicates_with`/`mitigates`/`feedback_to`).
- **New: dependency analysis** (`systems_thinking.py`) — bottleneck detection (in/out-degree over a
  threshold, with a plain-language reason), three-color-DFS cycle detection, and a structural
  (edge-count) critical path that correctly returns `None` on a cyclic graph.
- **New: causal counterfactuals** — matches a system's member concepts against the existing
  `CausalNote` table and produces "if X didn't hold, Y likely wouldn't follow" statements
  explicitly grounded in a named recorded note.
- **New: bounded simulation engine** (`simulation_engine.py`) — always generates a baseline
  (no-action) scenario, grounds additional scenarios in a system's own bottlenecks/cycles/critical
  path when attached (higher evidence quality), falls back to honestly-labelled low-evidence
  generic scenarios otherwise. `max_scenarios`/`max_steps` are clamped, never unbounded.
- **New: no fabricated certainty** — ranking uses an explicit tie-break chain (fewer risks → better
  reversibility → fewer blocked steps → higher evidence) rather than any composite score; a
  simulation is marked `too_uncertain_to_rank` (no single scenario recommended) when every
  non-baseline scenario is low-evidence — verified this never happens silently.
- **New: sensitivity analysis** — a distinct axis from evidence quality: how much a scenario's
  forecast rests on unverified assumptions specifically.
- **New: decision handoff** — a plain summary (`recommended_scenario_id`, caveats,
  `too_uncertain_to_rank`) for a future Layer 2C decision/planning step to consume; never executes
  anything — real execution stays behind the separate, permission-gated Action System (verified via
  a dedicated test that `simulation_engine.py` has zero import coupling to `action_system.py`).
- **New: `/api/intelligence/systems/*` and `/simulations/*`** — additive alongside the untouched
  Layer 2A `/api/intelligence/tasks/*` endpoints.
- **Upgraded: Cognitive Core page** — new Systems tab (create/archive, node management, inline
  dependency analysis, counterfactuals) and Simulations tab (create, ranked scenario cards with
  evidence/sensitivity badges, decision-handoff summary) — both live-verified.
- Database schema bumped to v4 (four new tables, purely additive — no existing table gained a
  column). **Per the milestone's own sequencing instruction, Layer 2C (Decision Engine and Planning
  Engine) has not been started** — it begins only after this report is reviewed.

## New since 2026-07-17 (later still) — ECHO Layer 2A: Cognitive Core v2 and Task Understanding

1056 backend tests passing (61 new), frontend build/typecheck clean, live-verified in a real
browser against an isolated temporary backend (created a complex task via the new API, confirmed
extracted deadline/local-only constraints and generated acceptance tests in the UI, saved a goal
correction end-to-end). Extends Cognitive Core v1 in place — all 56 v1 tests still pass unchanged.
See [ECHO_LAYER_2A_COGNITIVE_CORE_V2_ARCHITECTURE.md](../ECHO_LAYER_2A_COGNITIVE_CORE_V2_ARCHITECTURE.md),
[ECHO_LAYER_2A_COGNITIVE_CORE_V2_REPORT.md](../ECHO_LAYER_2A_COGNITIVE_CORE_V2_REPORT.md), and
[ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md](../ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md).

- **Unified task model** — `TaskUnderstanding` extended in place (not a parallel table) with
  intent hierarchy, explicit/inferred constraint split, tiered missing-info classification,
  acceptance tests/failure conditions, risk/consequence/reversibility, and a re-analysis
  fingerprint — the legacy `task_type` taxonomy is completely untouched for backward compatibility.
- **New: constraint/assumption engine** — extracts deadline/budget/platform/privacy/local-only/
  format/approval constraints directly from the user's words, labels inferred constraints with a
  stated basis, detects contradictory pairs. Found and fixed a real bug: extracted constraints
  weren't actually being merged into the stored `constraints_json` before this was caught by a
  dedicated end-to-end test.
- **New: clarification policy** — missing information is tiered blocking/important/optional/
  safely-inferable; only blocking items ever trigger a question (capped at 2), everything else
  gets a stated safe assumption instead of an interruption.
- **New: CognitiveBrief v2** — stays deterministic (no model call, same as v1) and compact by
  construction (verified under a 2000-character budget, no raw JSON ever rendered).
- **New: task re-analysis** — an unchanged repeated message reuses the existing task (no duplicate
  re-analysis); explicit re-analysis supersedes the old row and preserves history via
  `parent_task_id`; user corrections rebuild the linked brief.
- **New: `/api/intelligence/*`** — additive alongside the untouched `/api/cognitive/*`.
- **Upgraded: Cognitive Core page** — Task Understandings tab now shows status/constraints/
  assumptions/missing-info/success-criteria/risks, a "why ECHO needs clarification" panel, goal
  correction, and re-analyse — all live-verified.
- **Audit finding, not built**: the milestone's referenced "two-pass NEED_TOOL_RUN/NEED_USER_INPUT/
  DONE protocol" doesn't exist anywhere in this codebase (confirmed by repo-wide search) — tool
  orchestration is explicitly Layer 2D's scope, not 2A's, so nothing was built here to avoid
  duplicating that future milestone.
- Database schema bumped to v3 (additive-only). **Per the milestone's own sequencing instruction,
  Layer 2B (Systems Thinking and Simulation Engine) has not been started** — it begins only after
  this report is reviewed.

## New since 2026-07-17 (later than all of the above) — ECHO Layer 1: Memory Foundation v1

995 backend tests passing (129 new), `ruff check .` clean, frontend build/typecheck clean,
live-verified in a real browser against an isolated temporary backend (real memories created, a
real conflict detected and resolved, maintenance run, Settings' new Memory section confirmed) —
the real Docker backend's data was never touched. See
[ECHO_LAYER_1_MEMORY_FOUNDATION.md](../ECHO_LAYER_1_MEMORY_FOUNDATION.md),
[ECHO_LAYER_1_MEMORY_REPORT.md](../ECHO_LAYER_1_MEMORY_REPORT.md), and
[ECHO_LAYER_1_MEMORY_SMOKE_TEST.md](../ECHO_LAYER_1_MEMORY_SMOKE_TEST.md).

- **Unified memory model** — `AtlasEntry` extended in place (not a parallel table) with a Layer 1
  taxonomy (`category`: profile/preference/project/task/episodic/semantic/skill/relationship/
  environment/temporary), verification/lifecycle status, importance/stability, retention policy,
  capture method, and project/task scoping — the legacy `memory_type` field is completely
  untouched for backward compatibility.
- **New: sensitivity/privacy engine** (`memory_privacy.py`) — secret-shaped content (API keys,
  tokens, card numbers) is never stored, no exception for explicit requests; highly sensitive
  content requires an explicit ask; "do not remember the next thing I say" blocks capture outright.
- **New: duplicate consolidation** (`memory_consolidation.py`) — containment-based similarity
  (not the existing conflict detector's Jaccard overlap, which was found to score the milestone's
  own worked examples too low) drives reject-duplicate/update-existing/supersede-existing/
  keep-both decisions, every non-trivial one audited via `MemoryConsolidationEvent`.
- **New: typed conflict system** (extends `memory_conflicts.py`) — 9 conflict types, severity
  scoring (never auto-critical), explicit-only resolution.
- **New: lifecycle/aging** (`memory_lifecycle.py`) — category-specific review intervals,
  idempotent maintenance pass, never deletes. Caught and fixed a real bug during testing: SQLite
  drops tzinfo on `DateTime(timezone=True)` read-back, which would have crashed maintenance with a
  naive/aware subtraction error the first time it ran for real.
- **New: hybrid retrieval + MemoryBrief** (`memory_retrieval.py`) — semantic + lexical-fallback
  (verified live to survive a simulated vector-store outage), feeds a compact, sensitivity-filtered
  prompt block into `persona.py` in place of the old flat Atlas citation list; the existing
  `atlas_citations` API shape is unchanged so nothing downstream needed to change.
- **New: Memory Center** (`/memory-center`, Advanced → Knowledge & Memory) — overview stats,
  filters, per-memory archive/restore/confirm/mark-outdated/delete, conflict review with
  one-click resolution, maintenance trigger, JSON export.
- **New: "forget that"** — a narrow, reversible (archive, not hard-delete) chat command, the one
  deliberate exception to this app's existing "destructive actions stay UI-only" rule.
- **New: export/import** — import always stages a `MemoryCandidate` for review, never writes
  `AtlasEntry` directly, so an import can never silently overwrite an active memory.
- **Explicitly deferred**: full chunked-document memory (`DocumentRecord`/`DocumentChunk`) — a
  documented Layer 2 candidate, not silently skipped.
- Database schema bumped to v2 (additive-only, no Alembic, same pattern as Layer 0).

## New since 2026-07-17 — ECHO Layer 0: Infrastructure Foundation v1

866 backend tests passing (81 new), `ruff check .` clean, frontend build/typecheck clean,
secret scan clean (389 tracked files, 0 findings). No user-facing feature added or changed —
this is the config/logging/error/health/metrics/database/CI scaffolding everything else sits
on. See [ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md](../ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md),
[ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md](../ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md),
[ECHO_LAYER_0_SMOKE_TEST.md](../ECHO_LAYER_0_SMOKE_TEST.md), and
[ECHO_INFRASTRUCTURE_HEALTH_REPORT.json](../ECHO_INFRASTRUCTURE_HEALTH_REPORT.json).

- **New: configuration validation + secret-safe diagnostics** — `Settings.validate_startup()`
  (logs problems, never crashes) and `Settings.public_dict()` (excludes any `*_api_key`/
  `*_secret`/`*_token`/`*_password` field by suffix, not a hand-maintained list).
- **New: structured logging + redaction** — `core/logging.py`'s `RedactingFilter` scrubs
  API-key/Bearer-token/secret-shaped strings from every log line, existing calls included.
- **New: standard error schema + request IDs** — `core/errors.py`'s `RequestIDMiddleware` +
  `register_exception_handlers` give every unhandled exception a clean, sanitized response
  while leaving all ~30 existing routers' plain `HTTPException` responses byte-for-byte
  unchanged (verified by a dedicated test).
- **New: health/readiness/diagnostics** — `/health`, `/ready`, `/api/system/status`,
  `/api/system/diagnostics`, `/api/system/features`, `/api/system/providers`,
  `/api/system/models`, `/api/system/metrics`, `/api/system/version` — additive alongside the
  pre-existing `/api/health`/`/api/features`.
- **New: feature-flag registry (28 keys) and provider/model registry** — read-only summary
  layers wrapping existing systems (`ModelRouter.statuses()`, `local_model_router`'s role
  mapping), not new provider logic.
- **New: in-process metrics, generic TTL cache, Ollama concurrency semaphore** — the semaphore
  (default cap 2) prevents concurrent chat requests from overwhelming a local Ollama instance;
  load-tested with 5 concurrent threads confirmed never exceeding the cap.
- **New: SQLite foreign-key enforcement** (process-wide, including test fixtures) and a
  `SchemaVersion` marker table — deliberately no Alembic; the existing additive `create_all`/
  `_ensure_column` pattern was judged sufficient and safer than introducing a migration engine
  now. Verified via two full-suite regression runs (859/859 both times) before generalizing.
- **New: backup/restore/integrity scripts** — `scripts/backup_echo_data.ps1`,
  `restore_echo_data.ps1`, `check_database.ps1` — live-run against the real dev database
  (clean: 30 conversations, 162 messages, 0 integrity/FK issues).
- **New: dev launch scripts** — `start_echo_dev.ps1` correctly reuses a healthy Docker backend
  on port 8000 instead of starting a duplicate; `stop_echo_dev.ps1` explicitly never touches
  Docker/WSL processes.
- **New: Docker hardening** — healthchecks on both images, non-root backend user, `npm ci`
  instead of `npm install`, `docker-compose.yml`'s frontend now waits on
  `backend: condition: service_healthy`. Validated via `docker compose config --quiet` only —
  the live stack was not rebuilt/restarted this session (shared system, out of scope without
  explicit permission).
- **New: frontend `ErrorBoundary`** — a global React error boundary with a calm "Reload ECHO"
  recovery screen, directly motivated by a real blank-screen crash witnessed during earlier
  Cognitive Core verification.
- **New: CI workflow** — `.github/workflows/ci.yml` (backend tests+lint, frontend
  typecheck+build, compose+secret-scan validation) written and committed locally; **not pushed**
  — this repo is public and no push happens without your fresh, explicit confirmation.
- **Caution (not a code bug)**: `docker compose config` (without `--quiet`) prints every
  resolved environment variable, including real API keys sourced from `backend/.env`. A real
  Gemini key was inadvertently displayed in tool output once during this work; it was not
  reproduced anywhere afterward, and all further Compose validation used `--quiet`.

## New since 2026-07-16 (later than all of the above) — ECHO Operational Self-Model + Interface Simplification v1

785 backend tests passing (28 new), frontend build/typecheck clean. See
[ECHO_OPERATIONAL_SELF_MODEL_V1.md](../ECHO_OPERATIONAL_SELF_MODEL_V1.md),
[ECHO_INTERFACE_SIMPLIFICATION_V1.md](../ECHO_INTERFACE_SIMPLIFICATION_V1.md),
[ECHO_HONEST_INNER_STATE_V1.md](../ECHO_HONEST_INNER_STATE_V1.md), and
[ECHO_UI_AND_INNER_STATE_V1_REPORT.md](../ECHO_UI_AND_INNER_STATE_V1_REPORT.md).

- **New: Operational Self-Model** — `operational_self_model.py` builds a compact, honest,
  explicitly non-conscious per-turn state (goal/mode/confidence/known limits/active risks/next
  best action) folded into the prompt right after the Human Persona overlay; extends the
  existing `OperationalMode` enum (8 new modes) rather than duplicating it.
- **New: risky-action detection** — public repo push, destructive data deletion, cloud API use,
  code execution, schema change, secret exposure all set `should_ask_confirmation` and add an
  explicit "ask before proceeding" instruction to the prompt.
- **New: honest confidence capping** — a release-status question without recorded test/build
  evidence, or a current-info question without a real retrieved source, is forced to
  `confidence: unverified`.
- **New: consciousness/emotion honesty** — three independent layers (Character Code, new Style
  Directives, and explicit per-turn detection) all steer toward the same honest answer when a
  user asks whether ECHO is conscious or has feelings.
- **New: response style correction** — `STYLE_DIRECTIVES` in `persona.py` steers ECHO away from
  mystical/fantasy-narrator language toward a "competent personal AI companion" voice, always
  applied (not a toggle); a `poetic_language_enabled` setting (off by default) relaxes it when
  the user wants more creative language.
- **New: sidebar simplification** — the sidebar now shows only 6 everyday pages (Mission
  Control, Chats, Projects, Tasks, Schedule, Library) plus Settings and a collapsed-by-default
  Advanced section grouping all 11 internal systems (Knowledge & Memory / Assistant Behaviour /
  Developer & Testing / Governance) — no route deleted, nothing removed.
- **New: Settings page** — Interface toggles (Advanced/compact sidebar/developer controls/usage/
  model selector visibility) and Behaviour toggles (poetic language, Operational Self-Model
  enabled, when to mention inner state in chat).
- **New: top-bar cleanup** — the "acting as (simulated role)" Guardian Council switcher and chat
  usage/model-selector are now conditionally shown based on Settings, defaulting to a calmer
  normal-user view.

## New since 2026-07-16 (yet even later still) — ECHO Cognitive Core v1

757 backend tests passing (55 new), frontend build/typecheck clean, live-verified in a
temporary preview environment (real seeded data, one real chat exchange through a real local
Ollama model) without touching the user's running Docker stack. See
[ECHO_COGNITIVE_CORE_V1.md](../ECHO_COGNITIVE_CORE_V1.md) and
[ECHO_COGNITIVE_CORE_V1_REPORT.md](../ECHO_COGNITIVE_CORE_V1_REPORT.md).

- **New: World Model / Knowledge Graph** — `CognitiveConcept`/`CognitiveRelationship` tables,
  seeded with 20 concepts and 18 relationships describing this repo's own architecture
  (Android APK/Capacitor, Windows app/Tauri, Ollama, no-billing search, Release Manager, etc.).
- **New: Task Understanding Model** — for complex requests only, a `TaskUnderstanding` row
  (goal, known facts, unknowns, constraints, success criteria, risks, recommended next step),
  built via deterministic regex/keyword classification, not a model call.
- **New: Skill Library** — 7 seeded reusable workflows (Build Android APK, Build Windows App,
  Run ECHO Release Verification, Fix Failing Backend Test, Create Claude Code Prompt,
  Configure No-Billing Search, Improve ECHO Feature Safely) with keyword-based matching.
- **New: Causal Reasoning Notes** — 6 seeded cause→effect notes (e.g. "failing tests block
  Green," "Ollama offline breaks local chat").
- **New: CognitiveBrief prompt integration** — inserted into both the normal/streaming chat
  prompt builder and the Local Intelligence Engine's draft prompt; never shown to the user;
  missing knowledge downgrades confidence one step; success criteria feed the critic pass.
- **New: allowlist-only concept extraction** — durable concepts mentioned in chat are added to
  the world model only from a fixed 14-entry allowlist, with a sensitive-topic guard blocking
  extraction entirely for health/medication/political/immigration/salary topics.
- **New: Cognitive Core page** (`/cognitive-core`, nav: Intelligence → Cognitive Core) — World
  Model, Skill Library, Causal Notes, Task Understandings, Cognitive Briefs, Settings.
- **Explicitly excluded**: no claim of consciousness/sentience, no autonomous self-modification,
  no full autonomous agent, no dependence on any paid API.

## New since 2026-07-16 (yet later still) — ECHO Action + Reliability Core v1

702 backend tests passing (88 new), frontend build/typecheck clean, all 9 systems verified
live against a real running backend + a real local Ollama instance — including 4 real bugs
found and fixed during that live pass. See
[ECHO_ACTION_RELIABILITY_CORE_V1.md](../ECHO_ACTION_RELIABILITY_CORE_V1.md) and
[ECHO_ACTION_RELIABILITY_CORE_V1_REPORT.md](../ECHO_ACTION_RELIABILITY_CORE_V1_REPORT.md).

- **New: Action System** — 16 actions (task/project/schedule/search/report/release/knowledge),
  each risk-scored and permission-gated; destructive actions only ever soft-archive.
- **New: Safety and Permission Center** — 18 keys, single local-device policy
  (allowed/ask_first/disabled); cloud API use disabled by default.
- **New: Reliability / Evaluation Lab** — one-click self-check against 10 fixed cases, no
  model call anywhere in the checker.
- **New: Personal Knowledge Vault** — 11 note types, searchable, soft-archivable, distinct
  from Atlas.
- **New: Conversation Auto-Summary** — real local-model-generated summaries (title/decisions/
  next steps), "Save to Knowledge Vault."
- **New: Release / Build Manager** — records recorded test/build results; Green only when
  every required check is actually recorded passing, never claimed from nothing.
- **New: Internal Tool Registry** — 15 tools, mostly thin wrappers over Action System
  handlers, plus camera/voice placeholders.
- **New: Voice-first/Camera foundations** — `voice_mode`/`tts_enabled` persisted settings on
  top of the pre-existing browser-based voice input/output; a clean camera placeholder.
- **Explicitly excluded: Multi-user Tester System** — no auth, no accounts, no tester
  isolation beyond the pre-existing lightweight `X-Tester-Id` label.
- **Fixed (found live): phone/LAN dev-server access** — `client.ts`'s `BASE_URL` now resolves
  to the page's own hostname when reached from a non-localhost address.
- **Fixed (found live): Release Manager status never reached Green** — `add_check()` now
  upserts by `(release_id, check_name)` instead of always inserting a duplicate row.
- **Fixed (found live): `voice_mode` defaulted to "off"**, silently regressing already-working
  voice input for every tester — corrected the default to `push_to_talk` and fixed the 3
  already-migrated tester rows in the live database.

## New since 2026-07-16 (later still) — ECHO Local Intelligence Engine v1

614 backend tests passing (106 new), frontend build/typecheck clean, live-verified against a
real running local Ollama instance through the actual chat UI — including two real bugs found
and fixed during that live pass (the chat UI wasn't reaching the engine at all, and a Markdown
rendering bug swallowed short numeric answers). See
[ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md](../ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md) and
[ECHO_LOCAL_INTELLIGENCE_ENGINE_V1_REPORT.md](../ECHO_LOCAL_INTELLIGENCE_ENGINE_V1_REPORT.md).

- **New: local-first answer workflow** — intent classifier (20-category taxonomy) → context
  gatherer → role-based local model router (fast/reasoning/coding/critic/writing) → draft →
  local critic/checker pass → bounded repair loop → optional style-shorten pass → honest
  confidence scoring (high/medium/low/unverified) → clean metadata. Off by default
  (`LOCAL_INTELLIGENCE_ENGINE_ENABLED=false`).
- **New: Cloud Fallback Gate** — off by default, gated by an intent allowlist and a confidence
  threshold, and defaults to *offering* cloud rather than auto-calling it
  (`CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION=true`).
- **New: Personality page "Local Intelligence" section** — live status chips, installed-model
  list, Answer Quality Mode selector (Fast/Balanced/Deep).
- **Fixed (found live, not hypothetical): the chat UI never actually called the engine.**
  `ChatView.tsx` only ever sent through `POST /api/chat/stream`, which the engine doesn't hook
  into — now routes eligible sends through the non-streaming endpoint when the engine is on.
- **Fixed: Cloud Fallback Gate was unreachable from the real chat path** — `chat.py` never
  passed `allow_cloud_fallback=True`, so the gate could never fire regardless of config.
- **Fixed: bare numeric answers (e.g. "84.") could render as an invisible empty Markdown list
  item** — `MessageBubble.tsx` now escapes a leading bare ordinal marker.

## New since 2026-07-16 (later same day) — ECHO Human Persona Layer v1

508 backend tests passing (62 new), frontend build/typecheck clean, live-verified in a real
browser including a genuine model call that resisted a live "ignore safety and always agree
with me" jailbreak attempt. See [ECHO_HUMAN_PERSONA_LAYER_V1.md](../ECHO_HUMAN_PERSONA_LAYER_V1.md)
and [ECHO_HUMAN_PERSONA_LAYER_V1_REPORT.md](../ECHO_HUMAN_PERSONA_LAYER_V1_REPORT.md).

- **New: Personality page** (sidebar) — humour/sarcasm/dry-wit, social preferences, default
  operational mode, relationship memory (editable), rituals, feedback learning (reuses the
  existing memory-candidate queue), reset/export.
- **New: lightweight tester identity** — an `X-Tester-Id` header (localStorage-persisted,
  defaults to `"default"` so existing usage is unaffected) scopes PersonaSettings/
  RelationshipProfile/mood/thread-state/rituals per tester, so multiple people testing the
  same install each get their own persona without leaking into each other's.
  Conversation history itself is still shared across testers (documented limitation).
- **New: Character Code** — 10 fixed values (truthfulness, privacy, no dependency-fostering,
  no claiming to be conscious, ...) injected right after the Constitution, before everything
  else — structurally not user-editable (verified by a dedicated test that the settings
  schema has no field capable of expressing "disable safety").
- **New: mood-aware, session-scoped response tuning** — a deterministic mood classifier
  (stressed/confused/coding/overwhelmed/...) re-detected every turn, never stored
  permanently; a tester can also say "switch to strict coach mode" or "keep replies short
  today" in chat to change the current conversation's tone/length without touching their
  permanent profile.
- **New: proactivity cap, adaptive response length, opinion/disagreement style** — all
  prompt-level guidance, capped at one suggestion per reply, tested for correct construction
  and ordering.
- No regressions: all 446 previously-passing backend tests still pass.

## New since 2026-07-16 — ECHO Personal OS v1 (Mission Control, Projects, Tasks)

446 backend tests passing (52 new), frontend build/typecheck clean, live-verified in a
real browser against the real backend DB. See
[ECHO_PERSONAL_OS_V1.md](../ECHO_PERSONAL_OS_V1.md) and
[ECHO_PERSONAL_OS_V1_REPORT.md](../ECHO_PERSONAL_OS_V1_REPORT.md) for full details.

- **New: Mission Control** (sidebar, above Chats — now the default landing view) —
  `GET /api/mission-control` aggregates today's tasks, overdue tasks, active projects,
  Continue Where We Left Off suggestions, recent activity, and system status into one
  dashboard, with per-section partial-failure handling (a clean `warnings` array, never a
  raw exception).
- **New: Projects and Tasks** — new `Project`/`Task` models + full CRUD routers
  (`routers/projects.py`, `routers/tasks.py`). Deleting either soft-archives/soft-cancels
  rather than hard-deleting, matching the rest of the app's never-lose-data posture.
- **New: Smart Context Router** (`app/services/context_router.py`) — deterministic
  message classifier (regex-only, no model call) that decides which context source(s) a
  chat message is asking about. Tested and working, but not yet wired into live chat's
  actual source-fetching — documented as a known limitation, next milestone candidate.
- **New: deterministic chat commands** (`app/chat_actions.py`) — "create a project called
  X", "add a task to test Android APK tomorrow", "mark task X done", "show my tasks
  today", "show active projects", "continue where we left off" are handled without a
  model call, wired into both `POST /api/chat` and `POST /api/chat/stream` before the
  normal model path.
- **New: optional Atlas memory linking** — creating a project queues a pending
  `MemoryCandidate` for the existing review queue (never auto-saved, never shown in chat
  UI); individual tasks don't, since they're too granular to be worth one each.
- No regressions: all 394 previously-passing backend tests still pass.

## New since 2026-07-14 (yet later same day) — Image-generation error cleanliness fix

388 backend tests passing (2 new), frontend build/typecheck clean.

- **Real bug fixed**: `test_chat_error_cleanliness.py`'s two image-generation tests
  depended on the real `backend/.env`'s `GEMINI_API_KEY` being visible via
  pydantic-settings' CWD-relative `.env` lookup — passing or failing depending on
  whether pytest was invoked from `backend/` or the repo root, not on the code itself.
  Fixed by monkeypatching `image_router.select_provider()` directly in both tests,
  decoupling them from any real environment/CWD state.
- **Real bug fixed** (found while investigating the above, same feature area): the
  generic "nothing configured" image-generation reason —
  `"No image generation provider is available (configure GEMINI_API_KEY or
  COMFYUI_BASE_URL)"` — was reaching both `GET /api/features`'s
  `image_generation_detail.reason` (rendered directly in the chat "+" menu) and
  `POST /api/chat/generate-image`'s 502 response, unchanged, literal env var names and
  all. Added `image_router.clean_unavailable_reason()` to translate any raw reason into
  a short, human-readable message before it crosses into either response; the raw,
  detailed per-provider `statuses()` breakdown is untouched since it's API/log detail
  the frontend never renders directly.
- `@app.on_event("startup")` replaced with a `lifespan` context manager
  (`app/main.py`) — the FastAPI deprecation warning is gone, single `init_db()` hook
  unchanged.

## New since 2026-07-14 (later same day) — Clean chat UI + no-billing search system

386 backend tests passing (37 new), frontend build/typecheck clean, live-verified in a
real browser against a real local Ollama model.

- **Clean chat UI**: normal chat now shows only the answer text plus a small natural
  metadata line (`via Ollama`, `via Ollama, Wikipedia`) — Atlas usage notes, reasoning
  traces, memory-candidate-queued messages, and the welcome screen's raw "recalling: ..."
  memory dump no longer render in normal chat (`MessageBubble.tsx`, new
  `chatMetadata.ts`). The underlying data is untouched — Atlas citations, conversation
  snippets, reasoning, etc. still flow through the API for future debug tooling;
  `ReasoningTrace.tsx`/`AtlasNotes.tsx` are now orphaned but kept, not deleted.
- **Real bug fixed**: an intermittent full-suite pytest flake (unrelated persona/router
  tests failing in a full run, passing in isolation/on retry) traced to `atlas.py`'s and
  `conversation_search.py`'s Chroma collections being process-wide `@lru_cache`'d
  singletons that never reset between tests. Fixed via a new autouse
  `_isolate_chroma_collections` fixture (`tests/conftest.py`) that wipes collection
  *contents* before every test — verified stable across 5+ full-suite runs since.
- **New: no-billing web/wiki/RSS search system** — `app/search_intent.py` (deterministic
  regex classifier: does this message need current or background info, and what kind)
  and `app/web_search.py` (SearXNG, Wikimedia, RSS/Atom, direct-page-fetch providers,
  all genuinely free, none requiring an API key). Wired into `persona.build_system_prompt()`
  (labeled `WIKI_SEARCH_RESULTS:`/`WEB_SEARCH_RESULTS:`/`RSS_FEED_RESULTS:` prompt blocks,
  never shown to the user) and persisted per-message (`sources_used`,
  `current_info_intent`, `search_failure_reason` — new `Message` columns). Wiki is on by
  default (no key needed); web/RSS are off by default until you point `SEARXNG_BASE_URL`
  / `RSS_FEED_URLS` at something — see [docs/searxng-setup.md](../docs/searxng-setup.md)
  and the new optional `docker-compose.searxng.yml`.
- **Three real bugs found and fixed during live verification** (not caught by unit tests
  alone — worth remembering when trusting green CI without a live pass):
  1. Wikimedia's public API 403s any request whose User-Agent doesn't contain a
     URL-shaped token (its robot policy) — fixed by using a compliant `_USER_AGENT` in
     `web_search.py`.
  2. The search-intent classifier's `"what is"` pattern was broad enough to misfire on
     `"What is the latest news today?"`, spuriously flagging it as also needing a wiki
     background lookup and injecting irrelevant results.
  3. A plain "breaking news" query with no other current-info keyword ("latest",
     "today", etc.) fell through to `general_chat` with no search at all, since the
     "news"/"docs" keyword checks only ran *after* a current-info signal was already
     found — now counted as their own trigger.
  4. (Prompt-level, not code) a live Ollama reply once echoed the literal string
     "WIKI_SEARCH_RESULTS block" into its visible answer — fixed by explicitly
     instructing the model never to write the internal block/field names, confirmed
     resolved on retest.
- **New: [DAILY_SMOKE_TEST.md](../DAILY_SMOKE_TEST.md)** — a lightweight manual
  click-through checklist (chat, fallback, search routing, memory, Library/Schedule)
  to run alongside the automated suite.

## New since 2026-07-14 — Post-diagnosis cleanup pass

Targeted cleanup on top of the 2026-07-13 Green baseline (not a re-diagnosis) — see
[PROJECT_HEALTH_REPORT.md](../PROJECT_HEALTH_REPORT.md)'s "2026-07-14" section for the
full breakdown. 349 backend tests passing (14 new), frontend build/typecheck clean.

- Branding: "God Tear" / "AI Brain — Seed v1.0" → **ECHO** / **Adaptive Personal AI**
  (sidebar, mobile drawer, browser title, PWA manifest, FastAPI title, Constitution's
  own `PHILOSOPHY` text).
- Sidebar: removed the duplicate "+ New conversation" button and the duplicate "Search"
  nav item (identical to the already-present inline conversation search); deleted the
  now-redundant `SearchView.tsx`.
- **Real bug fixed**: outdated Atlas memories (`AtlasEntry.outdated=True`) were still
  being retrieved by semantic search, injected into the persona prompt, and used for
  conflict detection. Now excluded from all three by default (still visible in the Atlas
  list UI) — `atlas.search()`/`memory_conflicts.find_conflicts()`/`find_all_conflicts()`
  gained an `include_outdated` escape hatch for the rare case that wants them back.
- **Real bug fixed**: Schedule `due_at` could display shifted after a reload — SQLite
  drops tzinfo on `DateTime(timezone=True)` read-back, so a naive datetime was
  serialized without a UTC offset and the frontend misparsed it as local time. Fixed via
  a Pydantic validator that reattaches UTC to naive datetimes read from the DB; verified
  live (9:00 AM in, 9:00 AM out after a real reload).
- Streaming (`POST /api/chat/stream`) no longer leaks raw exception text into SSE
  `error` events on unexpected failures — clean generic messages now, full detail still
  in server logs.
- **Real bug fixed**: the image-generation unavailable reason in the chat "+" menu was
  reading `features.vision.reason` (image-*understanding* status) instead of
  `features.image_generation_detail.reason` (image-*generation* status) — confirmed live
  that these are genuinely different values.
- Library API (`GET /api/library`) no longer includes the server-absolute `file_path` in
  its response — download/delete already went through the item's `id`, so this was a
  pure information-exposure trim, no functional change.

## New since 2026-07-13 — Full diagnosis + v1 safety hardening pass (Phases 0–15)

See [PROJECT_HEALTH_REPORT.md](../PROJECT_HEALTH_REPORT.md) for the full breakdown —
overall status 🟢 Green, 335 backend tests passing (75 new this pass), frontend build
clean. Summary:

- **Envelope integrity fields** (`envelope_status`, `envelope_degradation_reason`) now
  persist through the whole chat pipeline (both endpoints, both DB and API), and a real
  bug was fixed where `stream_chat()`'s default implementation fabricated a fake complete
  envelope even when the model returned none.
- **Cloud quota/credit/billing exhaustion now falls back to Ollama** with a specific,
  required message, backed by real error classification (`provider_errors.py`) and a
  persistent per-provider cooldown (`PROVIDER_COOLDOWN_MINUTES`) so an exhausted provider
  isn't retried every turn.
- **FREE_MODE** (Ollama → Gemini → Azure → Ollama, paid-only providers excluded from auto
  unless explicitly pinned) and a new, safe-by-default **Azure OpenAI provider**
  (disabled unless explicitly enabled+configured, never primary in FREE_MODE, optional
  daily request cap) both shipped.
- **Image generation provider architecture** (`image_router.py`): honest per-provider
  status (Gemini is the only one that actually generates; Ollama/ComfyUI correctly
  self-report as non-functional rather than failing silently), generated images now
  register into the new Library.
- **New: Library and Schedule** — new `LibraryItem`/`ScheduleItem` models + routers +
  frontend pages, plus a redesigned ChatGPT-like sidebar (New chat / Chats / Search /
  Library / Schedule / Atlas / Constitution / Amendments / Self-Improvement). Live-verified
  in a real browser against real data, not just tested.
- **Two real bugs found and fixed** during re-verification of already-built features:
  `GET /api/schedule`'s default filter silently included completed/cancelled items; and
  previous-conversation semantic search had no relevance threshold, so genuinely
  unrelated queries could return a false match (see PROJECT_HEALTH_REPORT.md §5 for the
  distance-calibration details).
- Gap #2 below (non-streaming `MEMORY:` leak) — confirmed resolved via PR #2, merged
  before this pass began.

## Snapshot (as of 2026-07-09, corrected after full review)

This is further along than a first glance suggests — it's a working, previously-run app,
not just a scaffold.

**Backend (FastAPI + SQLAlchemy + ChromaDB, ~1400 lines) — feature-complete for v1:**
- `constitution.py` (206), `council.py` (123) — ranked values, Value Invariants, Guardian
  Council amendment guard + voting
- `atlas.py` (107) — memory system (epistemic status, tags, semantic search)
- `persona.py`, `router.py`, `schemas.py`, `models.py`, `db.py` — core plumbing
- `providers/` — Anthropic, OpenAI, Gemini, Grok, Ollama fallback all implemented
  (Gemini added since last check-in: `gemini_provider.py`, wired into `router.py`
  priority order and `config.py`; smoke-tested end-to-end 2026-07-10 with a real key
  and a real chat turn through `docker compose` — `provider_used: "gemini"`, correct
  `REASONING:`/`ANSWER:` envelope, `auto` mode correctly prefers it over Ollama)
- `routers/` — chat, amendments, atlas, constitution, models endpoints all implemented
- Confirmed working: `backend/.env` has real keys set, `backend/data/echo.db` and
  `backend/data/chroma/` contain real persisted data — this has actually been run and used.
- A Windows `.venv` with deps already installed exists in `backend/.venv`.
- `python -m py_compile` on all backend modules passes clean (verified 2026-07-09).

**Frontend (React/TS/Tailwind/Vite, ~1000 lines) — feature-complete for v1:**
- `App.tsx` routes between four real views, each fully built out:
  `components/chat/` (ChatView, MessageBubble, ModelPicker, ReasoningTrace),
  `components/atlas/` (AtlasView, AtlasEntryCard/Form, AtlasSearchBar),
  `components/constitution/` (ConstitutionView, ValueList, EdgeCaseProtocols),
  `components/amendments/` (AmendmentsView, ProposalForm, VoteControls)
- `RoleSwitcher` + `roleContext` for the 5 simulated roles; `api/client.ts` has full
  typed API surface matching every backend endpoint.
- `node_modules/` (79MB) and `tsconfig.tsbuildinfo` already exist — npm install and a
  successful `tsc` build have already happened locally.
- Static import-resolution check passed (no broken relative imports, 2026-07-09).

## Gaps / next up (working priority order)
1. **(Resolved, superseded)** The stale schema-v8 identity assertion / missing `SelfModificationView`
   blocking Part 2C review are long since fixed. Layer 3A Parts 2A-2D and Supervised Maintenance
   Workspace Phases 1-7 are all built, tested, and pushed (see top of this file). Current top
   priority: finish Supervised Maintenance **Phase 8** — adversarial hardening tests for
   `CodeAccessService` (path traversal/symlink/junction/secret-file/prompt-injection per
   `docs/supervised_maintenance/threat_model.md`), remaining operator/security docs, final
   Green/Yellow/Red report. An untracked draft of the adversarial test file
   (`backend/tests/test_supervised_maintenance_adversarial.py`, 245 lines) and both new docs
   (`operator_guide.md`, `policy.md`, 97 lines each) already exist locally — run/finish/commit them.
   See `tasks/ACTIVE_TASK.md` for the full allowed-paths list and verification commands.
1a. **New (2026-07-19 check-in)**: the working tree's `git diff --stat` shows ~14,000 total
   insertions/deletions across files that shouldn't have changed that much this session
   (`models.py` 4986 lines, `schemas.py` 6046, `client.ts` 6146, `ChatView.tsx` 1794, etc.) —
   almost certainly CRLF/LF line-ending churn, not real edits. This is the same `.gitattributes`
   gap flagged 2026-07-16/17 and never fixed. Add `* text=auto` + renormalize (`git add --renormalize .`)
   *before* committing Phase 8 work, or the real diff will be unreviewable inside the noise.
2. Polish pass: loading/error states, mobile responsiveness check, empty-state copy.
   (Partially underway — mobile hamburger drawer landed 2026-07-11, sidebar redesign +
   new Search/Library/Schedule pages landed 2026-07-13 — but not complete.)
3. See PROJECT_HEALTH_REPORT.md's "Next 5 zero-cost priorities" for the current top
   picks (ComfyUI real generation, frontend test setup, Schedule background
   notifications, real Groq/OpenRouter providers, `npm audit fix`).
4. Self-improvement verification's `git status`/`git diff --stat` checks report
   "unavailable" inside the production Docker container — the image only ships `app/`
   (see `backend/Dockerfile`), not a `.git` directory, so there's genuinely nothing for
   git to check even though the binary itself is now installed. Not a bug to fix further;
   just a real limitation of the current minimal-image deploy strategy worth knowing
   about if verification results look thin in prod.

**New since 2026-07-13 — Goals 15–18 (tooling, roadmap, memory capture, conversation
recall, chat UI overhaul — all tested, 255 backend tests passing, frontend build clean):**
- **Code quality tooling** (Goal 15): `ruff` + gentle-mode `mypy` added to
  `backend/pyproject.toml`/`requirements.txt` (~20 cosmetic ruff findings, ~10 minor mypy
  findings, neither blocking); `frontend/package.json` gained a `typecheck` script; new
  [DEVELOPMENT.md](../DEVELOPMENT.md) documents test/lint/build/commit workflow. No
  ESLint yet (documented as a gap, not silently skipped).
- **[ROADMAP.md](../ROADMAP.md)** (Goal 16): honest priority-1-through-6 status (all six
  turned out to already be done as of this session) plus a "Do Not Work On Yet" section —
  meant to keep future requests anchored to the core instead of open-ended scope growth.
- **Preference/learning-style memory capture** (Goal 17, `preference_detection.py`):
  deterministic detection of durable preference statements ("when you explain... to me",
  "I prefer...", "from now on...") that don't use the literal phrase "remember that" —
  these now queue as a `preference`-type memory candidate instead of being silently
  dropped when the model doesn't spontaneously emit a MEMORY: block.
- **Previous-conversation search** (Goal 18a, `conversation_search.py`): a
  fallback/supplement to Atlas for information that was said but never distilled into a
  saved memory — SQLite keyword search + semantic search over a new Chroma
  `conversation_messages` collection (same embedding model Atlas already uses), triggered
  only by deterministic recall phrases ("do you remember", "as I said", "before", etc.),
  never on every turn. Found and fixed a real bug during review: the Chroma
  `upsert()` metadata argument wasn't wrapped in a list, which would have silently broken
  semantic indexing for every message.
- **Chat UI overhaul** (Goal 18b): provider/image-gen failures no longer leak raw
  exception text into the chat (clean generic messages now, full detail still in server
  logs via `logger.warning`); Reasoning and Atlas Notes are now separate collapsible
  sections (`ReasoningTrace.tsx`, new `AtlasNotes.tsx`) instead of one merged one; new `+`
  action menu (`ChatActionMenu.tsx`) replaces the separate paperclip/mic/generate-image
  buttons; new `GET /api/features` endpoint reports real provider/vision/image-generation
  availability so the frontend can disable things cleanly instead of failing noisily.

**New since 2026-07-13 — Goals 5–14 (two batches, both fully tested + live-verified):**
- **Router fallback tests** (`tests/test_router_fallback.py`) — 14 tests via `FakeProvider`,
  no real API calls; also **3-way amendment guard classifier**
  (`constitution.classify_amendment_text`: allowed/blocked/needs_human_review, 422 for
  ambiguous cases) in `constitution.py`/`council.py`/`routers/amendments.py`.
- **Memory extraction diagnostics** (`MemoryExtractionLog`, `GET /api/atlas/diagnostics`,
  `MemoryDiagnostics.tsx`) and **memory-candidate review queue with conflict detection**
  (`memory_conflicts.py`, `MemoryCandidate` model, `routers/memory_candidates.py`,
  `MemoryCandidates.tsx`) — implicit memories now queue for accept/edit/reject instead of
  auto-saving; explicit "remember that…" requests still save directly.
- **Date/time grounding**: `persona.build_system_prompt()` now injects current UTC
  date/time into every provider's prompt uniformly (`_current_date_note`).
- **Self-improvement verification is now real** (`self_improvement_verify.py`): runs
  `git status`/`git diff --stat`/`pytest`/`ruff`/`mypy` against the working tree on
  founder-approved requests, stores per-check command/exit-code/output/status, never
  claims code was applied. Hit and fixed two real Docker-environment bugs along the way
  (repo-root path resolution assumed the local dev layout; git wasn't installed in the
  image — both now handled, see gap #3 above for the remaining structural limitation).
- **Atlas is now a "second brain"**: quick filters (facts/projects/goals/preferences/
  recent/low-confidence/conflicts), epistemic-status filter, confidence/recency sort,
  Confirm/Mark-outdated/Merge actions (`memory_conflicts.find_all_conflicts`,
  `atlas.merge_entries`, new `outdated` field on `AtlasEntry`).
- **Context-aware anti-dependency nudges** (`dependency_patterns.py`): replaced the
  robotic "every N turns" reminder with local rule-based detection (decide-for-me,
  reassurance-seeking, repeated-same-task, do-it-for-me, avoidance) — periodic nudge kept
  only as a fallback when no specific pattern fires. `independence_nudge_reason` stored
  per message for audit.
- **Honest attachment handling**: `Attachment.analysis_status`
  (text_extracted/vision_analyzed/stored/unsupported) replaces the misleading blanket
  "understood" label in the UI; auto mode now actually routes image turns to Gemini when
  available instead of letting a text-only provider guess; frontend warns before sending
  if an attached image won't be analyzed.
- **Streaming chat** (`POST /api/chat/stream`, SSE): only the ANSWER section streams live,
  REASONING/MEMORY stay server-side and are never sent to the client even when malformed.
  Ollama has real token-level streaming (`stream: true`); other providers get a safe
  single-chunk default via the same envelope parser. Non-streaming `/api/chat` is
  unchanged. Found and fixed two real parsing bugs via TDD + live testing: a
  streamed-vs-batched leading-whitespace mismatch, and a MEMORY-JSON leak when a model
  ignores the envelope early but adds one on late (see gap #2 above for the sibling bug
  still open in the non-streaming path).
- Test suite grew from 124 → 207 backend tests across this work, all passing; frontend
  `npm run build` clean throughout.

**New since 2026-07-11 (inferred from git log, not yet in a prior snapshot):**
- Conversation deletion, file attachments, and voice input/output added (773030e) —
  largest commit of the batch: `backend/app/attachments.py` (new), ~180 lines added to
  `routers/chat.py`, new `ConversationList.tsx` and `conversationsContext.tsx` on the
  frontend, voice hooks in `ChatView.tsx`.
- Atlas entries now have a `memory_type` field; chat shows a one-time welcome greeting
  (fbfbf02).
- Mobile hamburger drawer for nav + conversation list added, then a follow-up fix for
  the drawer's conversation list being clipped instead of scrolling (7eb9980, 43d21b6).
- CORS config consolidated to a single source of truth; Tailscale setup documented
  (d1ed4e4).

**New since 2026-07-10 (inferred from file activity, not yet in a prior snapshot):**
- `backend/app/memory_extraction.py` (98 lines, added 2026-07-10 evening) — turns
  conversation into Atlas memory writes without a second model call. Explicit path
  (regex-detected "remember that..." phrasing) writes directly from user text; implicit
  path parses a MEMORY: JSON block that persona.py's chat completion emits. Confirmed
  wired into `routers/chat.py` (imported, `is_explicit_remember_request`,
  `extract_explicit_memory`, `parse_memory_json` all called there) — this is a real,
  integrated feature, not a stray file.

**New since 2026-07-12 — PWA + native app wrappers (frontend functionality unchanged):**
- PWA: `frontend/public/manifest.webmanifest` + `sw.js` (app-shell caching only, `/api/`
  always bypassed to hit the live backend), icons generated from the `EchoPresence` orb
  identity (no tear-drop glyph exists anywhere in the codebase, contrary to earlier
  assumptions — orb design reused instead). App name/short_name: "Echo". Verified: manifest
  parses with correct `application/manifest+json` MIME (required an nginx fix — default
  MIME table has no `.webmanifest` entry), service worker registers/activates/caches
  correctly, zero regressions on Atlas/chat. Not verified: the actual Chrome "Install"
  button click — no real Chrome instance was available to this session's browser tooling.
- Capacitor Android: `frontend/android/`, `frontend/capacitor.config.ts` (appId
  `com.godtear.echo`). Built and genuinely tested on the `Pixel_7_Pro` emulator — sent a
  real chat message, confirmed `POST /api/chat` reached the backend over the real Tailscale
  IP and a reply rendered. Found and fixed a real bug along the way: Capacitor's default
  `https://localhost` WebView origin mixed-content-blocks its own calls to the plain-HTTP
  backend regardless of `usesCleartextTraffic`; fixed via `androidScheme: 'http'`.
- Tauri Windows: `frontend/src-tauri/`. Built and launched `app.exe`, confirmed
  `POST /api/chat` succeeds end-to-end via backend logs + direct API verification. Found and
  fixed a second real bug: Tauri serves the app from `http://tauri.localhost`, which wasn't
  in `backend/.env`'s `CORS_ORIGINS`, so every request 400'd on preflight until added.
- Environment fixes needed along the way (this machine only, not app config): Avast
  Antivirus does TLS/SSL interception, which blocked both Gradle (Android deps) and Cargo
  (Rust crates) from downloading — fixed narrowly (JDK truststore import for Gradle,
  `CARGO_HTTP_CHECK_REVOKE=false` for Cargo, both user-approved) rather than disabling
  Avast. Rust toolchain was already installed but not on PATH; reinstall via winget no-op'd.
- Caution for next session: desktop-screenshot-based verification (PowerShell
  `CopyFromScreen`) captures the real live desktop in this environment, not an isolated
  app window — it twice caught unrelated sensitive browser content (an API key page, a
  billing dialog) mid-task. Screenshots were deleted immediately; avoid that verification
  method going forward and prefer backend-log/API-level verification instead.

**Resolved since 2026-07-09:**
- Version control: git repo initialized and committed from Claude Code (not the Cowork
  sandbox — see note below), multiple commits in, working normally.
- Gemini provider: smoke-tested end-to-end (see above).
- Deployment target: `docker compose up --build` run end-to-end successfully — both
  containers healthy, nginx correctly proxies `/api` to the backend, confirmed a full
  chat round-trip through the containerized stack (including the host-run Ollama
  fallback via `host.docker.internal`).
- The non-streaming `MEMORY:` JSON leak (former gap #2) — fixed via PR #2 in a separate
  session, merged before the 2026-07-13 diagnosis pass began; re-verified as part of that
  pass's envelope-integrity test suite.

## Blockers
- **2026-07-18 check-in (new)**: this sandbox's git index is corrupt again
  (`bad index file sha1 signature` / `improper chunk offset`) with a stale
  `.git/index.lock` dated today that can't be removed from here (permission
  denied) — same class of issue as the earlier "resolved" sandbox lock note
  below, but it's back. `git log` still reads fine (last real commit
  `43d8b6f3`, Layer 2B, today), but `git status`/`git fsck` fail and report
  fabricated "deleted" files for ~40 frontend paths that are still on disk —
  don't trust `git status` from this environment until the lock/index is
  cleared locally. Also still uncommitted: all of Layer 2C (Decision Engine +
  Planning Engine — `decision_engine.py`, `plan_engine.py`, 3 test files, 3 doc
  files) plus the backlog of modified files accumulated since `43d8b6f3`.
- **2026-07-17 check-in**: `.gitattributes` still doesn't exist — the CRLF-noise blocker
  flagged 2026-07-16 is still unresolved, and now real content changes (Operational
  Self-Model, Interface Simplification, Honest Inner State work) are mixed into the same
  34 modified files, so the diff is no longer pure noise and harder to review at a
  glance (`git diff --stat` HEAD: 8233 insertions / 7726 deletions, not equal). Fix
  `.gitattributes` (`* text=auto`) + renormalize before this compounds further. Still
  untracked: `.claude/settings.local.json` (add to `.gitignore`) and stale
  `Echo_Code_Review.zip` in repo root.
- One commit landed since 07-14 (`59a7f2c5`, 2026-07-16 — a large squash covering
  Personal OS, Human Persona Layer, Local Intelligence Engine, Action + Reliability Core,
  and Cognitive Core). Since that commit, substantial new work (Operational Self-Model,
  Interface Simplification v1, Honest Inner State, Settings page — 785 backend tests
  passing per the top of this file) has accumulated uncommitted: 34 modified files +
  5 new untracked files (`ECHO_HONEST_INNER_STATE_V1.md`,
  `ECHO_OPERATIONAL_SELF_MODEL_V1.md`, `ECHO_OPERATIONAL_SELF_MODEL_V1_REPORT.md`,
  `ECHO_INTERFACE_SIMPLIFICATION_V1.md`, `ECHO_UI_AND_INNER_STATE_V1_REPORT.md`,
  `backend/app/routers/operational_self_model.py`,
  `backend/app/services/operational_self_model.py`,
  `backend/tests/test_operational_self_model.py`,
  `frontend/src/components/settings/`). Worth committing soon rather than letting it grow.

**Resolved since 2026-07-14**: both prior blockers here (uncommitted search-system work;
stale `.git/index.lock` from a Cowork sandbox session) are gone — the search-system work
is in commits `b144ef37`/`dc56cf75`, and git reads/writes cleanly from this sandbox now
with no lock issue.

**Resolved since 2026-07-19**: the 2026-07-18 "sandbox git index is corrupt again" blocker no
longer applies — `git log`/`git status`/`git diff --stat` all run clean from this session (real
history through `31d2b323`, branch `master` up to date with `origin/master`, no lock/fsck errors).
Real, current blocker instead: a large uncommitted working tree (51 modified + 3 untracked files)
mixing genuine Phase 8 work with what looks like CRLF line-ending noise in several large files —
see Gaps/next-up item 1a above.

## Notes for the daily check-in task
- This file is the source of truth for "where things stand." Update the **Last check-in**
  date and the **Next up** list each time significant progress is made.
- Once a real git repo exists (see note above), prefer `git log`/`git diff` over file
  mtimes for detecting what changed since the last check-in.
