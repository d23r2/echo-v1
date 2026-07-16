# ECHO Cognitive Core v1

## 1. What this is

A structured understanding layer sitting on top of Atlas. Where Atlas stores durable facts about the user, Cognitive Core stores durable facts about *the world ECHO operates in* (concepts and how they relate), and — for genuinely complex requests only — builds a compact, internal picture of what the request actually needs before ECHO answers: the goal, what's already known, what's missing, constraints, success criteria, and a recommended next step.

## 2. What this is not

- Not artificial consciousness, sentience, or a claim that ECHO has a human mind.
- Not autonomous self-modification or an autonomous agent that acts without the user.
- Not a replacement for Atlas — Atlas is still the source of truth for facts about the user; Cognitive Core is a separate, smaller structure for facts about the system/workflow world.
- Not a chain-of-thought exposed to the user. The internal `CognitiveBrief` never appears in a normal chat response.
- Not dependent on any paid API or real model call for its own logic — every classification, template, and matching step is deterministic (regex/keyword), matching the rest of this codebase's routing layer (`search_intent.py`, `intent_classifier.py`, `context_router.py`).

## 3. Why knowledge alone isn't enough

Atlas can tell ECHO *what it knows*. It can't tell ECHO *what a given request needs*: which facts are missing, what "done" looks like, which known workflow already covers this, or what usually causes what. Cognitive Core adds that layer — a small amount of structure that measurably improves how well ECHO frames complex answers, without pretending to be a mind.

## 4. World Model / Knowledge Graph

Two tables: `CognitiveConcept` (a durable, named thing — a project, tool, file, process, domain, goal, constraint, risk, etc., with a `confidence` level and a `source_type`) and `CognitiveRelationship` (a typed edge between two concepts — `uses`, `depends_on`, `causes`, `blocks`, `enables`, `part_of`, `conflicts_with`, `similar_to`, `requires`, `produces`, `verifies`, `belongs_to`).

Seeded with 20 concepts and 18 relationships describing this repo's own architecture (e.g. "Android APK" `uses` "Capacitor", "Android APK" `requires` "frontend build", "Local Intelligence Engine" `uses` "Ollama"). Search via `GET /api/cognitive/graph?query=`, which returns matching concepts plus their relationships.

## 5. Task Understanding Model

`TaskUnderstanding` — built only for requests classified as complex (`is_complex_task()` in `cognitive_core.py`). Captures goal summary, domain, task type, known facts, unknowns, constraints, assumptions, success criteria, risks, relevant concepts, a recommended next step, and an overall confidence level. 13 task-type templates (`ask_question`, `build_feature`, `fix_bug`, `run_test`, `plan_project`, `research_topic`, `summarize_file`, `make_decision`, `create_prompt`, `release_build`, `troubleshoot`, `study_learn`, `personal_support`) each grounded in real facts about this codebase — never fabricated.

## 6. Concept Map

`concept_extractor.py` adds durable concepts mentioned in chat to the world model automatically, but only from a fixed allowlist of 14 known ECHO-architecture concepts (ECHO, Atlas memory, Ollama, SearXNG, Android APK, backend tests, etc.) — it is not general-purpose entity extraction, so it structurally cannot invent a concept from arbitrary user text. A `_SENSITIVE_TOPIC_RE` guard blocks all extraction for a message that mentions health, medication, sexual, religious, political, immigration, or salary topics, even if the same message also mentions a known-safe concept. Duplicate concepts are merged by case-insensitive name match, not re-created.

## 7. Skill Library

`SkillPattern` — reusable, named workflows with ordered steps, required tools, success criteria, and common failure modes. Seeded with 7 skills matching real workflows in this repo: Build Android APK, Build Windows App, Run ECHO Release Verification, Fix Failing Backend Test, Create Claude Code Prompt, Configure No-Billing Search, Improve ECHO Feature Safely. `POST /api/cognitive/skills/{id}/suggest-plan` and the more general `suggest_plan()` match a user message against skill trigger keywords.

## 8. Causal Reasoning Notes

`CausalNote` — simple cause → effect pairs with a plain-language explanation, e.g. "Ollama offline breaks local chat" or "Failing tests block Green." Seeded with 6 notes describing real failure modes in this repo. Surfaced in a `CognitiveBrief` when the task type/domain match.

## 9. Abstraction Ladder

For complex tasks, `_build_brief_text()` implicitly separates high-level goal framing from mid-level constraints/success-criteria from low-level next-step recommendation — this stays internal-only (never shown in normal chat) and is kept deliberately compact rather than a full multi-level reasoning trace.

## 10. Missing-Knowledge Detector

`detect_missing_knowledge(task_type, domain)` returns the `unknowns` list from the matched template — e.g. for a release-status request: "has the full test suite actually been run this session," "has the frontend build actually been run this session." This list also feeds `_initial_confidence()` in the Local Intelligence Engine, downgrading confidence by one step when unknowns are present (except `release_testing`, which is always hard-capped at `low` regardless).

## 11. Success Criteria Generator

`generate_success_criteria(task_type, domain)` returns what "done" looks like for that kind of request — e.g. for `build_feature`: "existing tests still pass," "the new behavior is covered by a test," "no unrelated regressions." Fed into the Local Intelligence Engine's critic prompt as an explicit checklist item.

## 12. Context Selection Engine

`select_relevant_concepts()`, `select_relevant_skills()`, and `select_relevant_causal_notes()` pick a small, relevant subset (5 concepts, 3 skills, 3 causal notes max) from the world model based on keyword/substring match against the user's message and the task's type/domain — never a full dump of the graph.

## 13. Integration with the prompt builder

`CognitiveBrief` is inserted into the system prompt in two places: `persona.py`'s `build_system_prompt()` (normal/streaming chat) and `local_intelligence_engine.py`'s `_build_draft_system_prompt()` (the Local Intelligence Engine's draft pass). In both, it's placed after the constitution/persona sections and before conversation context, wrapped in a preamble telling the model never to repeat the section or its labels to the user. Both integration points degrade safely (try/except, returns `None`) if anything goes wrong — chat never breaks because of Cognitive Core.

## 14. How this helps local models

Small local models benefit disproportionately from an explicit, compact statement of goal/knowns/unknowns/success-criteria — it reduces meandering and improves whether the answer actually addresses what was asked. The Local Intelligence Engine's critic now checks a draft against the generated success criteria explicitly (critic check #8), and missing-knowledge detection lowers the engine's own confidence label rather than letting a small model sound more certain than it should.

## 15. How this avoids fake consciousness

Every classification is a regex/keyword match against a fixed table, not a model call — there is no "cognitive" process happening, only structured bookkeeping. Nothing in this system claims ECHO has beliefs, feelings, or a mind; the brief is explicitly documentation-style ("Goal: ...", "Known: ..."), not first-person reasoning. The `CognitiveSettings` page lets a user disable Cognitive Core entirely at any time.

## 16. Cognitive Core page

`/cognitive-core` (nav: Intelligence → Cognitive Core) — 6 sections: World Model (browse/search/add concepts, see relationships), Skill Library (browse by category, expand steps), Causal Notes (browse, add cause→effect notes), Task Understandings (recent complex-task summaries, no chain-of-thought), Cognitive Briefs (compact brief text only, never raw JSON prompt dumps), Settings (4 toggles: core enabled, concept extraction, skill matching, developer diagnostics).

## 17. Manual test checklist

1. Open `/cognitive-core`, confirm the 20 seeded concepts load under World Model.
2. Search "Android APK" — confirm it shows the concept plus its `uses`/`requires` relationships.
3. Open Skill Library — confirm "Build Android APK" and the other 6 seeded skills are present with steps.
4. Open Causal Notes — confirm all 6 seeded notes are present.
5. Send a complex chat message ("Give me a prompt to update Android APK.") — confirm the reply is coherent and the `via` metadata line is unaffected; confirm the raw text never contains "COGNITIVE_BRIEF" or its labels.
6. Send a trivial message ("hi") — confirm no `TaskUnderstanding` row is created for it.
7. Toggle "Cognitive Core enabled" off in Settings — confirm briefs stop being generated (verified in tests; can be spot-checked by disabling and re-sending a complex message).
8. Confirm Atlas, Personality, Actions, and existing chat features are all unaffected by this milestone.

## Known limitations

- Concept/skill/causal-note matching is keyword-based, not semantic — a request phrased very differently from the seeded keywords may not surface relevant world-model context even if it exists.
- `TaskUnderstanding` confidence is heuristic, not calibrated against real outcome data.
- The world model does not yet visualize the graph (text list + relationship list only, no graph rendering).
