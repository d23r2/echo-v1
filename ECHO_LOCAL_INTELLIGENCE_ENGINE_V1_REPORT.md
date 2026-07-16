# ECHO Local Intelligence Engine v1 — Report

## Overall status: Green

Backend test suite passes in full (614 passed, up from 508 before this milestone — 106 new
tests), `ruff check .` is clean, and the frontend production build (`tsc -b && vite build`)
succeeds. The engine was exercised live against a real local Ollama instance (not mocked) in
the browser, including a real end-to-end chat turn through the actual UI send path, and two
real bugs found during that live verification were fixed and covered by a new regression test
and a documented manual-checklist step. See "ECHO Local Intelligence Engine v1 release
candidate" at the end of this report for the exact scope of that claim.

## Files changed

**New backend files:**
- `backend/app/services/intent_classifier.py`
- `backend/app/services/context_gatherer.py`
- `backend/app/services/local_model_router.py`
- `backend/app/services/local_intelligence_engine.py`
- `backend/app/routers/local_intelligence.py`
- `backend/tests/test_intent_classifier.py`
- `backend/tests/test_context_gatherer.py`
- `backend/tests/test_local_model_router.py`
- `backend/tests/test_local_intelligence_engine.py`
- `backend/tests/test_local_intelligence_eval_cases.py`
- `backend/tests/test_local_intelligence_chat_integration.py`
- `backend/tests/fixtures/local_intelligence_eval_cases.json`

**Modified backend files:**
- `backend/app/config.py` — new settings block
- `backend/.env.example` — documented new variables
- `backend/app/providers/base.py`, `ollama_provider.py`, `anthropic_provider.py`,
  `openai_provider.py`, `gemini_provider.py`, `grok_provider.py`, `azure_openai_provider.py` —
  `model: str | None = None` override param threaded through `chat()`/`stream_chat()`
- `backend/app/services/context_router.py` — widened `_LIBRARY_PATTERN` (summarize/read/tell
  me about)
- `backend/app/schemas.py` — `AnswerQualityMode` moved earlier, new schemas added
- `backend/app/models.py`, `backend/app/db.py` — `local_answer_quality_mode` column
- `backend/app/main.py` — registered `local_intelligence` router
- `backend/app/routers/chat.py` — engine integration + cloud-fallback wiring fix (see Bugs
  fixed)
- `backend/tests/fake_providers.py` — `model` param support

**New/modified frontend files:**
- `frontend/src/api/client.ts` — `AnswerQualityMode`, `LocalIntelligenceSettingsOut`,
  `getLocalIntelligenceSettings()`, `ChatResponse` interface fixed to match the actual
  backend schema (`sources_used`/`current_info_intent`/`search_failure_reason` were missing)
- `frontend/src/components/personality/PersonalityView.tsx` — "Local Intelligence" settings
  section
- `frontend/src/components/chat/ChatView.tsx` — routes eligible sends through the
  non-streaming engine path when enabled (see Bugs fixed)
- `frontend/src/components/chat/MessageBubble.tsx` — bare-leading-ordinal Markdown escape fix
  (see Bugs fixed)

## Backend changes

Intent Classifier, Context Gatherer, Local Model Router, and the engine orchestrator are all
new services composing existing infrastructure (`context_router.py`, `search_intent.py`,
`web_search.py`, `atlas.py`, `conversation_search.py`, `human_persona.py`, `router.py`) rather
than duplicating it — see `ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md`'s pipeline diagram for the
full flow. `app/routers/chat.py`'s `_try_local_intelligence_engine()` hooks into
`POST /api/chat` only, gated by `LOCAL_INTELLIGENCE_ENGINE_ENABLED` (default `false`) and a
provider check (`auto`/`ollama` only — an explicit provider pin to a cloud provider bypasses
the engine, same "pinned means pinned" rule as the existing cloud router).

## Frontend changes

The Personality page gained a "Local Intelligence" section: four live status chips (Engine
enabled / Ollama connected / Critic on / Cloud fallback disabled), an Ollama-offline warning,
the real installed-models list, and an Answer Quality Mode selector (Fast/Balanced/Deep) wired
through the existing PersonaSettings patch flow.

Separately — found only during live verification, not part of the original build — `ChatView.tsx`
now checks whether the engine is enabled on load and, for eligible sends (no file attachments,
provider `auto` or `ollama`), calls the non-streaming `/api/chat` endpoint instead of
`/api/chat/stream`, since the engine only ever integrates into the former. Without this, the
engine was correctly built and tested but literally unreachable from the product's actual chat
UI. This does mean engine-path replies lose the live token-by-token typing indicator (a fair,
documented trade-off for v1 — see Known limitations in the companion doc).

## Config changes

See `ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md`'s "Config variables" section for the full list with
descriptions. Summary of the 26 new `backend/.env` variables:
`LOCAL_INTELLIGENCE_ENGINE_ENABLED` (default `false`), `LOCAL_MODEL_ROUTING_ENABLED`,
`OLLAMA_MODEL_FAST/REASONING/CODING/CRITIC/WRITING`, `LOCAL_MODEL_DEFAULT_ROLE`,
`LOCAL_MODEL_TIMEOUT_SECONDS`, `LOCAL_MODEL_MAX_RETRIES`, `LOCAL_CRITIC_ENABLED`,
`LOCAL_CRITIC_ALWAYS_FOR_CODING`, `LOCAL_CRITIC_ALWAYS_FOR_CURRENT_INFO`,
`LOCAL_CRITIC_MAX_REPAIR_LOOPS`, `CLOUD_FALLBACK_ENABLED` (default `false`),
`CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION` (default `true`), `CLOUD_FALLBACK_ALLOWED_INTENTS`,
`CLOUD_FALLBACK_DAILY_REQUEST_LIMIT`, `CLOUD_FALLBACK_MONTHLY_COST_LIMIT`,
`LOCAL_CONTEXT_MAX_CHARS`, `LOCAL_CONTEXT_MAX_MEMORY_ITEMS/FILE_CHUNKS/WEB_RESULTS/
CONVERSATION_SNIPPETS`, `LOCAL_ANSWER_QUALITY_MODE` (default `balanced`).

## Tests added

106 new backend tests (508 → 614):
- `test_intent_classifier.py` — 17 tests, the 20-category taxonomy classifier.
- `test_context_gatherer.py` — 11 tests, per-source-type gathering + char budget enforcement.
- `test_local_model_router.py` — 10 tests, role → model mapping, fallback to default model.
- `test_local_intelligence_engine.py` — 19 tests, full pipeline (draft/critic/repair/style/
  confidence/cloud-fallback-gate) using a scripted fake provider, no real Ollama or cloud call.
- `test_local_intelligence_eval_cases.py` — 41 parametrized tests over a 10-case fixture
  matching the milestone's own named evaluation cases.
- `test_local_intelligence_chat_integration.py` — 8 tests, including the new
  `test_cloud_fallback_gate_reachable_through_chat_endpoint` regression test added after live
  verification caught the wiring bug (see Bugs fixed).

No test in this suite makes a real network call to Ollama or any cloud provider — everything
local-model-shaped is scripted via `FakeProvider`/`ScriptedProvider`, matching this repo's
existing test convention.

## Commands run

```
cd backend
./.venv/Scripts/python.exe -m pytest -q            # 614 passed
./.venv/Scripts/python.exe -m ruff check .          # All checks passed!
cd ../frontend
npx tsc -b --noEmit                                 # exit 0
npm run build                                       # tsc -b && vite build — succeeded
```

## Bugs fixed

1. **The chat UI never actually reached the engine.** `ChatView.tsx`'s send handler only ever
   called `POST /api/chat/stream` (or `send-with-files` for attachments) — never the plain
   `POST /api/chat` the engine hooks into. As originally wired, every backend/test piece of
   this milestone was correct and fully tested, but a real user clicking Send in the actual app
   would never trigger the engine at all, flag on or not. Found during live browser
   verification (network tab showed `POST /api/chat/stream` for a message sent with the flag
   on), fixed by routing eligible sends through the non-streaming endpoint, verified live with
   a real Ollama call returning a real answer through `POST /api/chat`.
2. **The Cloud Fallback Gate could never fire from the real chat path.** `_try_local_intelligence_engine()`
   in `chat.py` never passed `allow_cloud_fallback=True` to `generate_response()` (it defaults
   to `False`), so even with `CLOUD_FALLBACK_ENABLED=true` configured, the gate's own internal
   check would never be reached from an actual chat request — only from tests calling the
   engine directly. Fixed by passing `allow_cloud_fallback=True` at the one real call site (the
   engine's own `settings.cloud_fallback_enabled` check remains the actual on/off control).
   Caught by re-reading the wiring while investigating bug #1; not something the original test
   suite exercised end-to-end through the router. Added
   `test_cloud_fallback_gate_reachable_through_chat_endpoint` as a permanent regression test.
3. **A short numeric answer could render as an invisible empty list item.** CommonMark (via
   `react-markdown` + `remark-gfm`) treats a bare `<digits>.` or `<digits>)` at the start of a
   line as an ordered-list marker; a local-model answer that's just `"84."` (a common shape for
   a "just answer briefly" arithmetic/factual question) rendered as `<ol><li></li></ol>` — the
   number itself never appeared on screen, even though the correct answer was present in the
   API response and in the `via` metadata line. Reproduced live (asked "What is 12 * 7? Just
   answer briefly." through the real engine, got a correct `content: "84."` from the API, saw
   nothing in the chat bubble). Fixed in `MessageBubble.tsx` by escaping a bare leading
   ordinal marker only when nothing else follows on that first line (so real intentional
   numbered lists like "1. First step\n2. Second step" are untouched). Verified live: the
   answer now renders as visible text.

## Bugs not fixed

- **`search_intent.py`'s pre-existing "what is"/`\bnow\b` classification quirks** are inherited
  as-is by the intent classifier and context gatherer (e.g. a plain arithmetic question gets
  classified with `current_info_intent=definition_lookup` and triggers an irrelevant Wikipedia
  lookup, as seen live in the "84." test above). This is shared, extensively-tested,
  widely-used code from a prior milestone; fixing it is out of scope here and documented as a
  known limitation, not silently patched over.
- **No frontend automated test for the `MessageBubble.tsx` fix.** This repository has no
  frontend test runner configured at all (no vitest/jest, no existing `*.test.*` files
  anywhere in `frontend/src`) — adding one from scratch for a single regression check was
  judged out of scope for this milestone. The fix was verified live in-browser instead (see
  manual checklist step 15 in the companion doc) and is narrow/self-contained enough that the
  risk of silent regression is low.
- **`CLOUD_FALLBACK_DAILY_REQUEST_LIMIT` / `CLOUD_FALLBACK_MONTHLY_COST_LIMIT` are unenforced.**
  Present in config as documented placeholders for a future limiter; no code path currently
  reads or acts on them. Cloud fallback itself is still fully gated by the confirmation
  requirement and intent allowlist, so this isn't a live safety gap, just an unbuilt feature.
- **Streaming (`POST /api/chat/stream`) does not integrate the engine.** A deliberate v1 scope
  cut (documented in the companion doc), not an oversight — the multi-pass pipeline doesn't
  have a natural token-streaming shape yet.

## Manual checks needed

The 20-step checklist in `ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md` covers the full surface;
highlights already exercised live during this session (real local Ollama, real browser, no
mocking):
- Flag-off default behavior unchanged (automated, `test_flag_off_by_default_existing_chat_path_used`).
- Personality page's Local Intelligence section renders live: Engine enabled, Ollama
  connected, Critic on, Cloud fallback disabled chips, and the real installed-model list
  (`llama3:latest`, `qwen3.6:latest`, `llama3.1:8b`, `llama3.2:latest`) — confirmed live.
- A real chat message ("What is 12 * 7? Just answer briefly.") sent through the actual UI,
  routed to `POST /api/chat`, answered correctly by real Ollama ("84."), with a clean
  `VIA OLLAMA, WIKIPEDIA, ATLAS` metadata line and zero critic/pipeline/JSON leakage into the
  visible reply — confirmed live, including the MessageBubble fix.
- Docker stack (`echov1-backend-1`/`echov1-frontend-1`/`echo-searxng`, ports 8000/3000/8080)
  confirmed untouched throughout — a separate `backend-verify` instance on port 8001 was used
  for all live verification, and `frontend/.env`/`backend/.env`/`.claude/launch.json` were
  reverted to their exact original content afterward.

Still needs a human pass (not exercised live this session, no cloud API key configured in this
environment to test against): cloud fallback's actual "no-confirmation, real cloud answer"
path end-to-end in the browser (steps 10-11 of the manual checklist) — covered by automated
tests with a mocked cloud router (`test_cloud_enabled_no_confirmation_uses_allowed_path`,
`test_cloud_fallback_gate_reachable_through_chat_endpoint`), but not with a real Anthropic/
OpenAI/Gemini call.

## ECHO Local Intelligence Engine v1 release candidate

**Green.** Backend tests (614/614) and the frontend production build both pass. The engine was
verified against a real, running local Ollama instance through the actual product chat UI (not
just the test suite), and both bugs that live verification surfaced — the UI never reaching the
engine at all, and the cloud fallback gate being unreachable from the real request path — were
fixed and are now covered by regression tests. This is a release candidate for the local-first
workflow itself; it is explicitly not a claim of cloud-level answer quality, and the cloud
fallback's real-cloud-call path (as opposed to its mocked-test coverage) still wants a human
pass with an actual API key configured.
