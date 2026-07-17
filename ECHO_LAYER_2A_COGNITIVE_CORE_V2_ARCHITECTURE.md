# ECHO Layer 2A — Cognitive Core v2 and Task Understanding

A shared understanding layer that converts a raw request into an explicit
goal, constraints, assumptions, success criteria, and a compact
`CognitiveBrief` for downstream systems (Layer 2B-2E). This extends the
existing Cognitive Core v1 in place rather than replacing it — see
[ECHO_LAYER_2A_COGNITIVE_CORE_V2_REPORT.md](ECHO_LAYER_2A_COGNITIVE_CORE_V2_REPORT.md)
for the delivery report and
[ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md](ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md)
for the manual checklist.

## 1. Purpose

Cognitive Core v1 already built a deterministic `TaskUnderstanding` (goal/
domain/task_type/known/unknown/constraints/success_criteria/risks) and a
compact `CognitiveBrief` for medium/hard-difficulty messages, injected into
the prompt via `persona.py`. What it didn't have: explicit-vs-inferred
constraint separation, contradiction detection, tiered missing-knowledge
classification with a real clarification policy, acceptance tests/failure
conditions, intent hierarchy (literal request vs. underlying objective vs.
requested output), quoted-content exclusion, re-analysis/staleness handling,
or a dedicated API/frontend surface for inspecting and correcting a task's
understanding. This milestone adds all of that as an extension.

## 2. Architecture: extend, don't replace

Per the milestone's own explicit rule ("Do not replace the existing
Cognitive Core v1; migrate or extend it with compatibility adapters"),
`TaskUnderstanding` and `CognitiveBrief` were extended in place — the same
consolidation pattern Layer 1 used for `AtlasEntry`. The legacy `task_type`
taxonomy (`ask_question`, `build_feature`, `fix_bug`, ...) is completely
untouched; a new `task_category` field carries the milestone's broader
taxonomy (question/explanation/research/coding/debugging/planning/decision/
document/action/reminder/learning/emotional_support/creative/mixed)
alongside it, backfilled via `task_understanding_v2.map_task_type_to_category()`.
`backend/app/services/cognitive_core.py`'s `build_task_understanding()` and
`build_cognitive_brief()` were extended, not duplicated; a new module
(`task_understanding_v2.py`) holds the additional deterministic passes
(intent hierarchy, constraints/assumptions, success criteria/acceptance
tests, missing-knowledge classification) as pure functions the orchestrator
calls into.

**One notable finding from the Phase 0 audit**: the milestone's Phase 7
references a "two-pass NEED_TOOL_RUN / NEED_USER_INPUT / DONE protocol" —
this does not exist anywhere in the codebase (confirmed by a full-repo
grep). The actual existing protocol is the `REASONING:`/`ANSWER:`/`MEMORY:`
envelope (`persona.py`) plus the Local Intelligence Engine's own
intent→context→draft→critic→repair→style pipeline. CognitiveBrief was
integrated with what actually exists; a dedicated tool-orchestration
protocol is explicitly Layer 2D's job (Multi-Model Orchestrator and Tool
Strategy Engine), not 2A's — building one here would have been exactly the
kind of parallel/duplicate system the milestone's own rules warn against.

## 3. Unified task model

New `TaskUnderstanding` columns (all additive, all default-safe):
`project_id`, `parent_task_id`, `normalized_request`, `task_category`,
`urgency`, `complexity`, `primary_goal`, `secondary_goals_json`,
`user_intent`, `expected_output`, `inferred_constraints_json`,
`preferences_json`, `forbidden_actions_json`, `uncertainties_json`,
`missing_information_json` (tiered: blocking/important/optional/
safely_inferable), `failure_conditions_json`, `acceptance_tests_json`,
`required_capabilities_json`, `candidate_skills_json`,
`candidate_tools_json`, `required_sources_json`, `risk_level`,
`consequence_level`, `reversibility`, `confirmation_requirement`, `status`
(draft/analyzing/ready/needs_clarification/stale/superseded),
`intent_hierarchy_json`, `scope`, `clarification_questions_json`,
`content_fingerprint`, `updated_at`. The legacy `constraints_json` field
now holds explicit constraints (v1's structural constraints plus newly
extracted per-request ones); `inferred_constraints_json` is always kept
separate and labelled, never merged in.

## 4. Intent hierarchy and scope

`task_understanding_v2.build_intent_hierarchy()` separates the literal
instruction text (with quoted/example/fenced-code content stripped —
`strip_quoted_content()`) from the requested output form (information /
plan / file / real_action / scheduled_action) and flags multiple distinct
intents (`detect_multiple_intents()`) rather than flattening a compound
request into one vague label. `detect_scope()` classifies the request as
current_turn / conversation / project / recurring_workflow / long_term_goal
based on explicit phrasing signals ("my goal is to", "from now on, always",
"project-wide", "as we discussed").

## 5. Constraint and assumption engine

`extract_explicit_constraints()` matches deadline/budget/platform/privacy/
local-only/file-format/approval-required patterns directly in the user's
words. `infer_soft_constraints()` only infers with real evidence (e.g.
domain match, task-type-specific structural rules already established
elsewhere in this codebase) and always labels the result "inferred" with a
stated basis — never converts a one-off preference into a universal rule.
`detect_contradictory_constraints()` flags known-opposite constraint pairs
(a small, curated table, not general NLU) rather than silently letting
downstream planning violate one.

## 6. Success criteria and acceptance tests

`build_acceptance_tests()`/`build_failure_conditions()` are category-aware:
engineering tasks (build/fix/test/release/troubleshoot) get test/build/
manual-check criteria; research tasks get source-citation/uncertainty
criteria; action/reminder tasks get permission/reversibility criteria.
v1's existing `generate_success_criteria()` stays the "required" baseline;
these are the acceptance-test layer on top of it.

## 7. Missing knowledge and clarification policy

`classify_missing_information()` tags each unknown as blocking/important/
optional/safely_inferable — high risk/consequence escalates an otherwise-
"important" unknown to "blocking" (rule: "High-consequence ambiguity must
not be guessed"). `build_clarification_policy()` only ever asks about
blocking items (capped at 2 questions), and states a safe assumption for
everything else instead of asking. `TaskUnderstanding.status` becomes
`needs_clarification` automatically when any blocking item exists.

## 8. CognitiveBrief v2

New fields: `candidate_tools_json`, `risk_and_confirmation_summary`,
`confidence`, `next_reasoning_stage` ("clarify" or "answer"). The brief text
itself stays compact by construction — a handful of short lines, verified
by a dedicated test to stay under a 2000-character budget and to never
contain raw JSON or internal field names like `"tier"`. Deterministic
throughout (no model call anywhere in this layer), which trivially
satisfies "gracefully fall back to a deterministic brief if no model is
available" — there was never a model dependency to fall back from, matching
v1's own established, tested approach.

## 9. Re-analysis and staleness

`compute_fingerprint()` hashes the normalized request; `build_task_understanding()`
reuses the most recent `TaskUnderstanding` for a conversation when the
fingerprint matches and status is still `ready` — preventing repeated
re-analysis of an unchanged task. `reanalyse_task_understanding()` forces a
fresh build, marks the old row `superseded` (history preserved, never
overwritten), and links the new row via `parent_task_id`.
`apply_task_correction()` updates the specific user-correctable fields
(goal, expected output, explicit constraints, forbidden actions, scope) and
rebuilds the linked `CognitiveBrief` — an important correction never leaves
a stale brief attached.

## 10. Prompt integration

No change to persona.py's integration *point* — `_get_cognitive_brief()`
already fetches once per turn and inserts the brief right after the Human
Persona/Operational Self-Model overlays; that call now transparently
returns the enriched v2 brief since `cognitive_core.py`'s own functions were
extended, not replaced. Existing behavior (try/except wrapping so a
Cognitive Core failure never breaks chat, the "never repeat this section or
its labels" instruction) is unchanged.

## 11. API

`backend/app/routers/intelligence.py`, `/api/intelligence/*` — additive
alongside the pre-existing `/api/cognitive/*` (unchanged, still used by the
existing page sections). `POST /task-understanding`, `GET /PATCH
/tasks/{id}`, `POST /tasks/{id}/reanalyse`, `POST /context-preview`
(returns the task understanding, brief text, and clarification view
together — the frontend's one-call preview), `GET /task-types`.

## 12. Frontend

`CognitiveCoreView.tsx`'s "Task Understandings" tab gained: status/
confidence badges, an expandable detail view (goal, explicit/inferred
constraints, known facts, success criteria, acceptance tests, risks), a
"Why ECHO needs clarification" panel (only shown when blocking items
exist), a compact "assumed safely" list for non-blocking items, a goal
correction control, and a re-analyse button. Superseded task rows are
hidden from the default list (history stays reachable via the API, not
deleted). No raw JSON or internal field names ever render — verified live.

## 13. Privacy/safety rules

No chain-of-thought or raw internal scoring is ever exposed — the brief
text is a fixed set of short, human-readable lines; the API returns typed
fields, never a reasoning trace. High-risk/consequence tasks
(`derive_risk_profile()`, keyed off destructive-action keywords and the
`action` task category) set `confirmation_requirement=True`, mirroring
Operational Self-Model's own risky-action detection so the two systems
agree rather than disagree. Layer 1 memory rules are unaffected — this
milestone doesn't touch memory capture/retrieval/deletion at all.

## 14. Known limitations

- Deep project-scoped context *filtering* (excluding another project's
  concepts/memories from a project-scoped task) is explicitly Layer 2E's
  job (Context Selection v2) — this milestone only guarantees `project_id`
  is captured and round-trips correctly, which a later filtering layer
  needs to exist at all.
- The "two-pass NEED_TOOL_RUN/NEED_USER_INPUT/DONE protocol" referenced in
  the milestone spec does not exist in this codebase and was not built
  here — see §2's audit finding. Tool orchestration is Layer 2D's scope.
- Intent-hierarchy multi-intent splitting uses a narrow set of strong
  coordination signals (not general NLU) — a genuinely ambiguous compound
  sentence without one of those signals may still be read as one intent.
- No model call anywhere in this layer, by design — a future layer that
  wants LLM-assisted task understanding would need to add that as an
  optional enhancement path, not a requirement.

## 15. Rollback procedure

Every schema change is additive (`_ensure_layer2a_cognitive_columns()` in
`db.py`, no new tables — everything fit as extensions to
`task_understandings`/`cognitive_briefs`). `CURRENT_SCHEMA_VERSION` bumped
2 → 3. Reverting the modified files (`models.py`, `schemas.py`, `db.py`,
`main.py`, `cognitive_core.py`, plus the frontend `client.ts`/
`CognitiveCoreView.tsx`) restores pre-2A behavior exactly, since every
change was additive. New files (`task_understanding_v2.py`,
`routers/intelligence.py`, the new test files) can be deleted with no
effect on anything else. The existing 56 Cognitive Core v1 tests all pass
unchanged, confirming v1 records/behavior remain fully intact.
