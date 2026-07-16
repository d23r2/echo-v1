# ECHO Local Intelligence Engine v1

A local-first answer workflow layered on top of ECHO's existing Ollama support: intent
detection → context gathering → role-based local model routing → draft → local critic/checker
pass → optional repair → optional style pass → honest confidence scoring → an off-by-default,
gated cloud fallback. The goal is more *consistent* answers from local models, not cloud-level
performance — and never claiming cloud-level confidence from a local-only answer.

## Why this helps local models specifically

A single raw prompt to a local model (llama3, qwen, etc.) is noticeably less consistent than
the same prompt to a large cloud model — it drifts off-topic, states things with false
certainty, ignores relevant context it was given, or produces a wall of text for a one-line
question. Cloud models mostly self-correct for this; local models mostly don't. This engine
compensates structurally instead of just hoping for a better prompt:

- **Intent-aware prompting** — a coding question, a definition lookup, and "how are you doing"
  get different, narrow, single-purpose prompts instead of one generic system prompt trying to
  cover every case.
- **A dedicated critic pass** checks the draft against the actual context it was given and
  against its requested answer style, catching drift and false-certainty claims before they
  reach the user.
- **A bounded repair loop** (at most `LOCAL_CRITIC_MAX_REPAIR_LOOPS`, default 1) fixes flagged
  issues without an unbounded self-correction loop that could burn time/tokens indefinitely.
- **Honest confidence scoring** — the engine tracks and reports high/medium/low/unverified
  per answer, and `release_testing`-intent answers are hard-capped at "low" regardless of what
  the local model or even the critic claims. No claim of "Green" is ever made purely from local
  inference.

## Why this reduces cloud/API-key dependence

Every step above (intent, context, routing, critic, repair, style) is local-only — no cloud
call happens anywhere in the default path. Cloud is reachable only through the Cloud Fallback
Gate, which is **off by default** (`CLOUD_FALLBACK_ENABLED=false`) and, even when turned on, is
further restricted to a specific intent allowlist, a confidence threshold, and (by default)
requires the user to explicitly ask for it rather than calling out automatically. An install
with zero API keys configured and Ollama running gets the full pipeline.

## Pipeline

```
user message
    │
    ▼
1. Intent Classifier  (app/services/intent_classifier.py)
    — 20-category taxonomy: difficulty, source_need, reasoning_need, freshness_need,
      answer_style, can_answer_local_only, should_ask_clarifying_question.
      Deterministic regex classification, layered on the existing
      context_router.py / search_intent.py — no model call.
    │
    ▼
2. Context Gatherer  (app/services/context_gatherer.py)
    — pulls only what the intent says it needs: Atlas memory, previous-conversation
      snippets, active projects/tasks, schedule items, Library files, Wikipedia,
      RSS, or web search — reusing the existing services for each, not duplicating
      them. Compressed to a char budget (LOCAL_CONTEXT_MAX_CHARS, default 12000).
    │
    ▼
3. Local Model Router  (app/services/local_model_router.py)
    — picks a role (fast / reasoning / coding / critic / writing) for this intent,
      maps it to an OLLAMA_MODEL_* env var, falls back to the plain OLLAMA_MODEL
      default if that role's model isn't configured or isn't installed.
    │
    ▼
4. Draft pass — one focused, role-appropriate prompt, answer-style instruction,
      source-honesty rule, persona overlay (humour/relationship callback), context block.
    │
    ▼
5. Local Critic pass (conditional — see "When the critic runs" below)
    — a second local model call, JSON-only output, checks: did it answer the
      question, did it ignore context, did it state an unverified current fact,
      is it the wrong length, does it leak debug/JSON text, does it overclaim
      certainty, does it contradict its context.
    │
    ▼
6. Repair pass (only if critic says needs_repair, capped at LOCAL_CRITIC_MAX_REPAIR_LOOPS)
    — rewrites the draft to fix the specific flagged issues only.
    │
    ▼
7. Style pass (only if critic flagged too_verbose, or answer_style=short and the
      draft is still long) — a narrow "make this shorter" rewrite, nothing else.
    │
    ▼
8. Confidence scoring — high/medium/low/unverified, release_testing hard-capped
      at low regardless of what any local pass claimed.
    │
    ▼
9. Cloud Fallback Gate (off by default) — see below.
    │
    ▼
clean answer + user_visible_metadata{via: [...]}  (no critic/pipeline/JSON text ever
    reaches the reply — internal_diagnostics is a separate, non-user-facing field)
```

### When the critic runs

Governed by `_should_run_critic()`: always when `LOCAL_ANSWER_QUALITY_MODE=deep`; always for
`coding`/`code_review`/`release_testing`/`troubleshooting` intents (if
`LOCAL_CRITIC_ALWAYS_FOR_CODING=true`, default); always when `freshness_need` is
current/live (if `LOCAL_CRITIC_ALWAYS_FOR_CURRENT_INFO=true`, default); never in
`fast` mode otherwise; in `balanced` mode (the default), also for `difficulty=hard` or
`answer_style=prompt`. All of this requires `LOCAL_CRITIC_ENABLED=true` (default) as the
master switch.

## Local model roles

| Role | Config variable | Used for |
|---|---|---|
| `fast` | `OLLAMA_MODEL_FAST` | Default role — simple chat, quick lookups |
| `reasoning` | `OLLAMA_MODEL_REASONING` | High reasoning-need intents, repair passes, `deep` mode |
| `coding` | `OLLAMA_MODEL_CODING` | `coding`, `code_review`, `prompt_generation` intents |
| `critic` | `OLLAMA_MODEL_CRITIC` | The critic/quality-check pass |
| `writing` | `OLLAMA_MODEL_WRITING` | The style-shortening pass |

Any role left unset (or pointing at a model that isn't actually installed) falls back to the
plain `OLLAMA_MODEL` default — a single-model Ollama install still works end to end, role
routing is a refinement, not a requirement.

## Answer quality modes

Set per tester on the Personality page ("Local Intelligence" section), or via
`LOCAL_ANSWER_QUALITY_MODE` as the install-wide default (`balanced`):

- **Fast** — one pass, no critic (unless the intent forces one — coding/current-info/
  release-testing still get checked). Lowest latency.
- **Balanced** (default) — critic for hard/coding/current-info questions, repairs if the
  critic flags a real issue.
- **Deep** — critic runs on every eligible answer, more willing to trigger the reasoning-role
  model and a repair pass.

## Cloud fallback rules

Off by default (`CLOUD_FALLBACK_ENABLED=false`). When turned on, a fallback to the existing
cloud `ModelRouter` (`app/router.py`, `provider="auto"`) is only even considered when **all**
of these hold:

1. `CLOUD_FALLBACK_ENABLED=true`.
2. The classified intent is in `CLOUD_FALLBACK_ALLOWED_INTENTS` (default:
   `coding,code_review,complex_reasoning,long_document`).
3. Confidence came out `low` or `unverified`.

If those hold and `CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION=true` (default), ECHO appends a
short offer to the local answer instead of calling out — "Local confidence was low on this
one. Cloud fallback is available if you'd like a second opinion — just ask." — the local
answer is what's shown, cloud is never silently invoked. Only with confirmation explicitly
turned off does the engine actually call the cloud router; any quota/billing/auth failure
there is swallowed and the local answer is kept, never surfaced as an error.

`CLOUD_FALLBACK_DAILY_REQUEST_LIMIT` / `CLOUD_FALLBACK_MONTHLY_COST_LIMIT` exist as config
placeholders for future enforcement; nothing currently reads them to block a call.

## Config variables (`backend/.env`)

```
LOCAL_INTELLIGENCE_ENGINE_ENABLED=false   # master switch — off by default
LOCAL_MODEL_ROUTING_ENABLED=true
OLLAMA_MODEL_FAST=
OLLAMA_MODEL_REASONING=
OLLAMA_MODEL_CODING=
OLLAMA_MODEL_CRITIC=
OLLAMA_MODEL_WRITING=
LOCAL_MODEL_DEFAULT_ROLE=fast
LOCAL_MODEL_TIMEOUT_SECONDS=120
LOCAL_MODEL_MAX_RETRIES=1
LOCAL_CRITIC_ENABLED=true
LOCAL_CRITIC_ALWAYS_FOR_CODING=true
LOCAL_CRITIC_ALWAYS_FOR_CURRENT_INFO=true
LOCAL_CRITIC_MAX_REPAIR_LOOPS=1
CLOUD_FALLBACK_ENABLED=false
CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION=true
CLOUD_FALLBACK_ALLOWED_INTENTS=coding,code_review,complex_reasoning,long_document
CLOUD_FALLBACK_DAILY_REQUEST_LIMIT=0
CLOUD_FALLBACK_MONTHLY_COST_LIMIT=0
LOCAL_CONTEXT_MAX_CHARS=12000
LOCAL_CONTEXT_MAX_MEMORY_ITEMS=5
LOCAL_CONTEXT_MAX_FILE_CHUNKS=5
LOCAL_CONTEXT_MAX_WEB_RESULTS=5
LOCAL_CONTEXT_MAX_CONVERSATION_SNIPPETS=5
LOCAL_ANSWER_QUALITY_MODE=balanced
```

**Why `LOCAL_INTELLIGENCE_ENGINE_ENABLED` defaults to `false` rather than `true`:** this is a
deliberate deviation from a "ship it on" default. The engine adds real new multi-call surface
area (up to 4 local model calls per message) touching the primary chat path; defaulting it off
means every existing install keeps its current, already-verified behavior until someone
explicitly opts in on the Personality page or in `.env`.

## How to choose local models

Any model already pulled in Ollama (`ollama pull <name>`, then `ollama list`) can be assigned
to a role. Rough guidance: use a small/fast general model (e.g. `llama3.2`, `qwen2.5:7b`) for
`fast` and `critic` (the critic only needs to follow a JSON-output instruction, not reason
deeply); use a stronger general model (e.g. `llama3.1:8b` or larger) for `reasoning`; use a
code-tuned model (e.g. `codellama`, `qwen2.5-coder`) for `coding` if installed. Leaving
everything unset and just having `OLLAMA_MODEL` set is a completely valid starting point.

## How to test your Ollama connection

- `GET /api/models/local` — returns the actually-installed model list via Ollama's own
  `/api/tags` endpoint (used by the Personality page's "Installed models" line).
- `GET /api/local-intelligence/settings` — read-only reflection of the current `.env`
  configuration plus live `ollama_available` / `ollama_status_reason`, same convention as the
  rest of the app's feature-availability endpoints.
- The Personality page's "Local Intelligence" section shows all of the above as status chips —
  Engine enabled / Ollama connected / Critic on / Cloud fallback disabled — plus the installed
  model list and the Answer Quality Mode selector.

## Known limitations

- **Only `POST /api/chat` (non-streaming) integrates the engine.** `POST /api/chat/stream`
  is untouched regardless of the flag — a deliberate v1 scope cut, since the multi-pass
  pipeline (draft → critic → repair → style) doesn't have a natural token-by-token streaming
  shape yet. The chat UI itself now routes to the non-streaming endpoint automatically when
  the engine is enabled and the provider is `auto`/`ollama` (see "a real bug this caught"
  below) — file-attachment sends still use `send-with-files` and are unaffected.
- **Memory extraction, dependency nudges, and conversation-snippet metadata aren't carried
  over into the engine path yet** — a documented, clean scope cut versus the normal chat
  flow, not an oversight.
- **The critic is itself a local model call** — it can be wrong, miss issues, or (rarely)
  fail to produce parseable JSON, in which case the engine degrades cleanly (skips the
  repair/style steps, keeps the original confidence) rather than crashing or fabricating a
  critic verdict.
- **No guarantee of cloud-level answer quality.** The explicit goal is a more *consistent*,
  more *honestly-scored* local answer — not parity with a large cloud model.
- **`search_intent.py`'s existing "what is"/`\bnow\b` pattern quirks are inherited as-is** —
  e.g. "What is 12 * 7?" classifies with `current_info_intent=definition_lookup` and triggers
  an (irrelevant) Wikipedia lookup. This is pre-existing, widely-used shared code intentionally
  left untouched in this milestone; the local model correctly ignored the irrelevant context
  in live testing, but the wasted lookup is a real, known inefficiency.
- **`CLOUD_FALLBACK_DAILY_REQUEST_LIMIT` / `CLOUD_FALLBACK_MONTHLY_COST_LIMIT` are unenforced
  placeholders** — present in config for a future limiter, not read by any code path yet.

## A real bug this caught, and the fix

Live browser verification found that the chat UI's send button only ever called
`POST /api/chat/stream` (and `send-with-files` for attachments) — never the plain
`POST /api/chat` that the engine hooks into. As shipped, that would have made the entire
engine unreachable from the actual product, reachable only via direct API calls. Fixed by
having `ChatView.tsx` check `GET /api/local-intelligence/settings` on load and route
eligible sends (no attachments, provider `auto`/`ollama`, engine enabled) through the
non-streaming endpoint instead — see `frontend/src/components/chat/ChatView.tsx`.

A second gap in the same class: `app/routers/chat.py` built the request the same as every
other test but never set `allow_cloud_fallback=True` on `generate_response()` — meaning the
Cloud Fallback Gate could never fire from the real chat path even with
`CLOUD_FALLBACK_ENABLED=true`, no matter the config. Fixed by passing it explicitly; the
`settings.cloud_fallback_enabled` check inside the engine remains the real on/off switch.

A separate, unrelated Markdown rendering bug was also caught live: a short numeric answer
like `"84."` is CommonMark ordered-list syntax at the start of a line, so `react-markdown`
was rendering it as an empty, invisible list item. Fixed in `MessageBubble.tsx` by escaping a
bare leading `<digits>.`/`<digits>)` marker when nothing else follows on that line.

## Manual test checklist

1. With the flag off (default), send a normal chat message — confirm behavior is unchanged
   from before this milestone.
2. Set `LOCAL_INTELLIGENCE_ENGINE_ENABLED=true`, restart the backend, confirm Ollama is
   running (`ollama list`).
3. Open the Personality page — confirm the "Local Intelligence" section shows Engine
   enabled, Ollama connected, the real installed-models list.
4. Send a simple factual question with provider Auto — confirm a real answer comes back with
   a clean `via Ollama...` line and no JSON/critic/pipeline text visible.
5. Send a coding question ("write a function that reverses a linked list") — confirm the
   critic pass engages (check `internal_diagnostics` isn't leaked, only the final answer is
   shown).
6. Pin the provider to a cloud provider (e.g. Gemini) — confirm the engine is bypassed and
   the normal cloud path is used.
7. Change Answer Quality Mode to Fast — confirm simple questions skip the critic (check
   response latency drops).
8. Change Answer Quality Mode to Deep — confirm the critic runs even on a simple question.
9. Stop Ollama and send a message with the engine on — confirm a clean "can't reach the
   local model" message, not a crash or a raw stack trace.
10. Turn on `CLOUD_FALLBACK_ENABLED=true` with confirmation required (default) — ask a
    coding question likely to score low confidence — confirm the offer text appears but no
    cloud call is made (check `provider_used` stays `ollama`).
11. Turn off `CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION` — repeat — confirm a real cloud
    answer comes back (if a cloud provider is configured) with `fallback_note` set.
12. Confirm `POST /api/chat/stream` behaves identically regardless of the flag.
13. Run the full backend test suite and confirm no existing tests broke.
14. Run the frontend production build and confirm it compiles cleanly.
15. Send a message whose only content is a short number (e.g. "what's 12*7? be brief") —
    confirm the numeric answer is actually visible in the chat bubble (regression check for
    the Markdown list-marker bug above).
16-20. Repeat steps 1-2 and 4-6 with each of the other four `IntentCategory` groups covered
    by `backend/tests/fixtures/local_intelligence_eval_cases.json` to spot-check the
    classifier against real messages, not just the automated fixture.
