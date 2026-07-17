# ECHO Layer 2A — Cognitive Core v2 — Delivery Report

See [ECHO_LAYER_2A_COGNITIVE_CORE_V2_ARCHITECTURE.md](ECHO_LAYER_2A_COGNITIVE_CORE_V2_ARCHITECTURE.md)
for the full design and
[ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md](ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md)
for the manual checklist.

## Overall status: Green

1056/1056 backend tests pass (61 new), `ruff check .` clean, frontend
`tsc -b --noEmit` and `npm run build` both clean, live-verified in a real
browser against an isolated temporary backend — a real complex task was
created via the new API, correctly showed extracted deadline/local-only
constraints and generated acceptance tests in the UI, a goal correction was
saved and persisted, and the real Docker backend's data was never touched.
Secret scan: 13 findings, all pre-existing Layer 0 test fixtures (confirmed
via `git log`, last touched before this milestone), zero in any Layer 2A
file.

## Architecture audit

**Existing systems reused**: Cognitive Core v1's `TaskUnderstanding`/
`CognitiveBrief` (extended in place, not duplicated), `intent_classifier.py`
(difficulty/intent signal, unchanged), `select_relevant_concepts/skills/
causal_notes` (unchanged), Layer 0's error/logging/feature-flag
infrastructure, the existing `persona.py` integration point (unchanged call
signature, enriched return value).

**Duplicate systems avoided**: no parallel `TaskUnderstanding` v2 table; no
new tool-orchestration protocol (the milestone's referenced "two-pass
NEED_TOOL_RUN protocol" doesn't exist in this codebase — confirmed by
repo-wide grep — and building one here would have duplicated what's
explicitly Layer 2D's job).

**Major design decisions**: `task_category` (new taxonomy) added alongside
the untouched legacy `task_type`, same compatibility-adapter pattern Layer 1
used for `AtlasEntry.category`; CognitiveBrief stays fully deterministic
(no model call), since v1 already established that pattern works and
trivially satisfies the "graceful fallback" requirement.

## Memory model

**Models added**: none — every field fit as an additive extension.
**Models modified**: `TaskUnderstanding` (+30 columns), `CognitiveBrief`
(+4 columns). **Migration approach**: fully additive `_ensure_column()`
calls, `CURRENT_SCHEMA_VERSION` 2 → 3. **Legacy compatibility**: v1's own
56-test suite passes unchanged; `task_type`/`constraints_json` (legacy
shape) both still populated exactly as before, with new fields layered on.

## Intent hierarchy

`build_intent_hierarchy()` — literal request (quoted/example content
stripped), requested output classification (information/plan/file/
real_action/scheduled_action), multi-intent detection via strong
coordination signals. Tested: quoted-content exclusion (3 tests), scope
detection (4 tests), multi-intent detection (2 tests + 1 hierarchy-level
test).

## Constraint extraction

`extract_explicit_constraints()` — 7 pattern types (deadline/budget/
platform/privacy/local-only/file-format/approval), all end-to-end verified
to land in `TaskUnderstanding.constraints_json` (found and fixed a real bug
here — see Bugs Fixed).

## Assumption tracking

`infer_soft_constraints()` — every inferred constraint carries `source:
"inferred"` and a stated `basis`, never silently presented as user-stated.

## Success criteria

`build_acceptance_tests()`/`build_failure_conditions()` — category-aware
for coding/research/action, tested for all three.

## Missing knowledge classification

`classify_missing_information()` — 4 tiers, high-stakes escalation to
"blocking" tested explicitly.

## Clarification policy

`build_clarification_policy()` — only blocking items trigger a question
(capped at 2), everything else gets a stated safe assumption instead.

## CognitiveBrief

Compact by construction — verified under a 2000-character budget and free
of raw JSON/internal field names in a dedicated test.

## Prompt integration

`persona.py`'s existing call site unchanged — the enriched brief flows
through automatically. Full 1056-test regression confirms no behavior
change to normal chat.

## Task re-analysis

Fingerprint-based staleness caching (identical repeated message reuses the
existing task, no duplicate re-analysis) plus explicit
`reanalyse_task_understanding()` (supersedes old row, links via
`parent_task_id`, history preserved) — both live-verified in browser.

## Frontend task view

`CognitiveCoreView.tsx`'s Task Understandings tab — status/confidence
badges, expandable detail (constraints/assumptions/missing-info/success-
criteria/acceptance-tests/risks), clarification panel, goal correction
control, re-analyse button. Live-verified: real task created via API,
displayed correctly with extracted constraints, correction saved and
reflected immediately.

## No chain-of-thought exposure

Verified by 2 dedicated tests (`test_no_raw_json_dump_in_context_preview_brief`,
`test_brief_text_includes_blocking_missing_info_but_not_raw_json`) plus
live browser inspection — no `{`, no field names like `"tier"`, ever
rendered.

## Backend full tests

`cd backend && .venv/Scripts/python.exe -m pytest -q` → **1056 passed**
(61 new). `ruff check .` → **All checks passed!**

## Frontend typecheck/build

`npx tsc -b --noEmit` → clean. `npm run build` → clean, 326 modules.

## Existing chat unaffected

Full regression suite (995 pre-2A tests, all Layer 0/1 tests, all Cognitive
Core v1 tests) passes unchanged. Live-verified: normal Mission
Control/Settings/System Status pages all rendered correctly against the
same temp backend during verification.

## Files changed

**New backend**: `services/task_understanding_v2.py`, `routers/intelligence.py`,
3 new test files (61 tests total).

**Modified backend**: `models.py`, `schemas.py`, `db.py`, `main.py`,
`services/cognitive_core.py`.

**New frontend**: none (existing page extended).

**Modified frontend**: `api/client.ts` (Layer 2A types + 6 new functions),
`components/cognitive/CognitiveCoreView.tsx` (Task Understandings tab
rewritten, `TaskDetail`/`ListSection` components added).

**New docs**: this report, the architecture doc, the smoke test doc.

## Bugs fixed

- **Explicit constraints extracted but never stored**: `extract_explicit_constraints()`
  correctly found deadline/local-only/etc. constraints, but
  `build_task_understanding()` never merged them into
  `TaskUnderstanding.constraints_json` — only the structural v1 constraints
  and contradiction notes were saved. Found by a dedicated end-to-end test
  (`test_explicit_constraint_preserved_end_to_end`) before this reached the
  UI; fixed by adding the extracted labels to the constraints list.
- Two Ruff import-order findings (auto-fixed, `routers/intelligence.py` and
  a test file).
- One TypeScript type-name collision: a new `TaskStatus` type collided with
  the pre-existing Tasks/Projects `TaskStatus` (`todo|in_progress|...`) —
  renamed to `CognitiveTaskStatus`, same pattern as Layer 0's
  `InfraSystemStatusOut` rename.
- One test-authoring miss: an initial high-stakes test message didn't
  actually trip the `is_complex_task()` gate (classified `difficulty:
  "easy"` by the intent classifier), so `build_task_understanding()`
  correctly returned `None` and the test failed on a `NoneType` attribute
  access — fixed by using a message that also matches an existing
  always-complex pattern (`"fix...failing"`).

## Bugs not fixed

None outstanding in Layer 2A code. Pre-existing items from `PROGRESS.md`'s
Blockers section remain open and are unrelated to this milestone.

## Manual checks remaining

- The full 19-step `ECHO_LAYER_2A_COGNITIVE_CORE_V2_SMOKE_TEST.md` was
  spot-verified (task creation, constraint extraction, correction,
  re-analysis, Settings/World Model pages unaffected) but not run as one
  continuous pass against the real Docker backend's data — verification
  deliberately used an isolated temp backend instead.
- The schema migration (v2 → v3) has not yet been applied to the real
  running Docker backend's database — additive and non-destructive by
  construction, exercised only against a fresh temp DB and the automated
  suite so far.
- Contradictory-constraint detection uses a small, curated opposite-pair
  table — not exercised against a genuinely contradictory real user message
  in the live browser pass (only unit-tested).

## Rollback instructions

See [Architecture doc §15](ECHO_LAYER_2A_COGNITIVE_CORE_V2_ARCHITECTURE.md#15-rollback-procedure).
Summary: every schema change is additive; reverting the 5 modified backend
files and 2 modified frontend files restores pre-2A behavior exactly; new
files can be deleted with no effect elsewhere.

## Is Layer 2A ready as a release candidate?

**Green as a local release candidate.** Not pushed anywhere. Ready to be
tagged `echo-layer-2a-cognitive-core-v2-rc` after your review of `git
status`/`git diff --stat`. Per the milestone's own instruction, **Layer 2B
(Systems Thinking and Simulation Engine) should only begin after this
report has been reviewed** — I have not started 2B and will not without a
fresh go-ahead.

## Proof table

| Proof item | Result |
|---|---|
| Legacy Cognitive Core compatibility | pass |
| Unified TaskUnderstanding model | pass |
| Intent hierarchy | pass |
| Constraint extraction | pass |
| Assumption tracking | pass |
| Success criteria | pass |
| Missing knowledge classification | pass |
| Clarification policy | pass |
| CognitiveBrief | pass |
| Prompt integration | pass |
| Task re-analysis | pass |
| Frontend task view | pass |
| No chain-of-thought exposure | pass |
| Backend full tests | pass (1056/1056) |
| Frontend typecheck/build | pass |
| Existing chat unaffected | pass |
