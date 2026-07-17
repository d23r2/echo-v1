# ECHO — Adaptive Personal AI

*(formerly God Tear AI Brain — internal architecture concepts like Atlas and the
Constitution keep their names; "ECHO" is the app/assistant's user-facing name.)*

A symbiotic, truth-seeking AI partner governed by a versioned constitution with ranked
core values, immutable Value Invariants, and a simulated Guardian Council amendment process.

- **Echo** — the chat persona: truth-seeking, transparent reasoning, resists sycophancy
  and jailbreaks, actively discourages dependency.
- **Atlas** — persistent memory with epistemic status (Verified / Inferred / Hypothesis /
  Narrative), tags, confidence, and semantic search (ChromaDB + local embeddings). Any
  non-outdated Atlas entry is retrievable in any future conversation, regardless of which
  one it was created in. Writes happen two ways: explicitly ("remember that I prefer tea"
  is detected and saved directly from your own words, no model judgment involved), or
  opportunistically (Echo's single chat-completion call also emits a `MEMORY:` section
  alongside its reasoning/answer — no second model call, so it can't double your rate
  limit — which gets parsed and saved when it decides something's worth keeping). Marking
  an entry **outdated** keeps it visible in the Atlas list/history but excludes it from
  semantic search, prompt injection, and normal conflict detection — it's no longer
  treated as current.
- **Constitution** — ranked values, immutable invariants, edge-case protocols, amendment log.
- **Guardian Council** — Founder proposes an amendment; it must clear an automatic
  Value-Invariant guard, then be approved by 2-of-3 Guardians *and* the Verifier to be
  ratified. This is a **single-user app**: use the role switcher in the header to act as
  any of the five simulated roles (no real multi-account auth).

## Architecture

```
backend/   FastAPI + SQLAlchemy (SQLite) + ChromaDB (local embeddings)
frontend/  React + TypeScript + Tailwind (Vite)
```

Model routing supports Anthropic (Claude), OpenAI, Gemini (Google), xAI (Grok), Azure
OpenAI (disabled by default), and a local Ollama fallback. "auto" mode tries them in that
order and uses the first available one; you can also pin a specific provider from the
model picker.

## Provider fallback and quota/credit safety

"auto" mode doesn't just try providers in order once — it classifies *why* a provider
failed (rate limit, quota exceeded, credit exhausted, billing required, auth failed,
network error, etc. — see `backend/app/provider_errors.py`) and, for the quota/credit/
billing/rate-limit categories, puts that provider on a cooldown (`PROVIDER_COOLDOWN_MINUTES`,
default 30) so it isn't retried on every single turn while it's known to be exhausted.
If every cloud provider fails or is cooling down, Echo falls back to local Ollama
(`OLLAMA_ALWAYS_AVAILABLE_FALLBACK=true` by default) and tells you it did so. If Ollama
isn't running either, you get a clear message saying so — never a raw provider exception.

Every reply also carries an honest `envelope_status` (`complete` / `partial` / `missing` /
`malformed`) reflecting whether the model actually returned its REASONING:/ANSWER:/MEMORY:
structure — Echo never fabricates a reasoning trace it didn't get.

### Running at (near-)zero cost: FREE_MODE

Set `FREE_MODE=true` to make "auto" mode prefer Ollama first, then Gemini's free tier,
then Azure (only if you've explicitly enabled and configured it — see below), then
Ollama again as a last resort — skipping Anthropic/OpenAI/Grok entirely even if you have
keys configured for them. You can still reach a paid provider by pinning to it by name
in the model picker; FREE_MODE only changes what "auto" reaches for.

### Azure OpenAI (opt-in, safe by default)

Azure is disabled unless you set `AZURE_OPENAI_ENABLED=true` and fill in
`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT`. It's never
used as FREE_MODE's primary choice. You can also cap it with `AZURE_DAILY_REQUEST_LIMIT` —
once reached, Azure is skipped for the rest of that day (separate from whatever limits
Azure's own billing enforces).

## Web search, Wikipedia, and RSS (no billing)

Echo can ground answers in real search results, entirely free — no API key or billing
account for any of it:

- **Wikipedia/Wikimedia** — on by default (public API, no setup). Used for stable
  background/definitional/historical facts, never as proof of anything current.
- **SearXNG** — off by default; needs a self-hosted (or trusted public) SearXNG instance.
  Used for current/live questions (news, prices, "did X happen").
- **RSS/Atom feeds** — off by default; point at whichever feeds you want for
  news/sports headlines.

A message is only routed to search when its own phrasing suggests it needs current or
background info (see `backend/app/search_intent.py`) — never on every turn, and never for
personal-memory questions ("what did I tell you about my job?"), which use Atlas/
conversation history instead. If a current-info question can't be verified (search off,
unreachable, no results), Echo says so honestly rather than guessing from possibly-stale
training data.

In normal chat, sources show up only as a small natural line under the reply — `via
Ollama, Wikipedia` or `via Gemini, SearXNG` — never a formal "Source:" label and never
raw internal block names.

See [docs/searxng-setup.md](docs/searxng-setup.md) for the one-command local SearXNG
setup, health checks, and troubleshooting.

## Running locally (no Docker)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in whichever API keys you have; none are required to run
uvicorn app.main:app --reload
```
API docs at http://localhost:8000/docs

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
App at http://localhost:5173

If no API keys are set and Ollama isn't running, chat requests return a clear 503
explaining that no provider is available, instead of crashing.

## Running with Docker Compose

```bash
cp backend/.env.example backend/.env   # required — compose reads this file directly
docker compose up --build
```
Frontend at http://localhost:3000 (nginx proxies `/api` to the backend container).
Backend data (SQLite + Chroma) persists in `backend/data/`, mounted as a volume.

**Ollama fallback + Docker:** the backend container's `OLLAMA_BASE_URL=http://localhost:11434`
refers to the *container itself*, not your host machine, so it won't see an Ollama instance
running on your host. If you want the local fallback to work under Docker Compose, set
`OLLAMA_BASE_URL=http://host.docker.internal:11434` in `backend/.env` instead (works on Docker
Desktop for Windows/Mac). This only matters for Docker — running the backend directly with
`uvicorn` needs no change.

**Optional: local SearXNG for web search** — a separate compose file,
`docker-compose.searxng.yml`, adds a self-hosted SearXNG instance without touching the
setup above. See [docs/searxng-setup.md](docs/searxng-setup.md).

## Environment variables (backend/.env)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | GPT |
| `XAI_API_KEY` / `XAI_MODEL` | Grok (OpenAI-compatible endpoint) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini (Google, REST API) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local fallback, no key needed |
| `DEFAULT_PROVIDER` | `auto` or a specific provider name |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API |
| `INDEPENDENCE_NUDGE_EVERY_N_TURNS` | How often Echo is reminded to nudge toward user independence |
| `ATLAS_TOP_K` | How many Atlas memories are injected into context per chat turn |
| `OLLAMA_ALWAYS_AVAILABLE_FALLBACK` | Whether "auto" mode falls back to Ollama when cloud providers fail (default `true`) |
| `PROVIDER_COOLDOWN_MINUTES` | Minutes a provider is skipped after a quota/credit/billing/rate-limit error (default `30`, `0` disables) |
| `FREE_MODE` | Prefer Ollama/free-tier providers; never reach paid-only providers via "auto" (default `false`) |
| `AZURE_OPENAI_ENABLED` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION` | Azure OpenAI, disabled unless explicitly enabled + fully configured |
| `AZURE_DAILY_REQUEST_LIMIT` / `AZURE_DAILY_TOKEN_LIMIT` | Optional self-imposed daily caps for Azure (blank = no cap) |
| `IMAGE_PROVIDER` | `auto` / `gemini` / `ollama` / `comfyui` / `disabled` — see Image generation below |
| `COMFYUI_BASE_URL` | Local ComfyUI server URL — reachability-check only in this build, see below |
| `OPENROUTER_API_KEY` / `GROQ_API_KEY` | Reserved for a future free-tier provider integration — not yet wired to anything |
| `WEB_SEARCH_ENABLED` / `SEARXNG_BASE_URL` / `WEB_SEARCH_MAX_RESULTS` / `WEB_FETCH_TIMEOUT_SECONDS` / `WEB_SEARCH_CACHE_MINUTES` | No-billing web search via SearXNG, off by default — see [docs/searxng-setup.md](docs/searxng-setup.md) |
| `WIKI_SEARCH_ENABLED` / `WIKI_PROVIDER` / `WIKI_API_BASE_URL` / `WIKI_MAX_RESULTS` / `WIKI_FETCH_TIMEOUT_SECONDS` / `WIKI_USER_AGENT` | Wikipedia/Wikimedia background search, on by default (no key needed) — `WIKI_USER_AGENT` is client identification, not a credential; a working default is already set |
| `RSS_SEARCH_ENABLED` / `RSS_FEED_URLS` / `RSS_MAX_ITEMS_PER_FEED` / `RSS_FETCH_TIMEOUT_SECONDS` / `RSS_CACHE_MINUTES` | RSS/Atom feeds for news/sports headlines, off by default (no feeds configured) |

## Image generation

Image generation is a separate, explicit action (the "+" menu in chat) — it's never
triggered automatically by a normal chat turn, and it calls a paid model, so it's kept
deliberately separate from regular text chat. `IMAGE_PROVIDER` controls which backend is
used:

- **Gemini/Imagen** — the only provider that actually generates images in this build.
  Works whenever `GEMINI_API_KEY` is set.
- **Ollama** — **cannot generate images in this build.** Ollama's chat models are
  text-only; there's no image-capable model wired up, so this always reports itself as
  unavailable rather than silently failing or faking a result.
- **ComfyUI** (`COMFYUI_BASE_URL`) — currently a reachability check only
  (`backend/app/image_router.py`). A configured, reachable ComfyUI server is reported as
  such, but this build doesn't yet submit an actual generation job to it — real workflow
  submission is real, untested-in-CI work left for later rather than shipped half-built.

When nothing can generate an image, the UI shows a clean "unavailable" state with the
actual reason (not configured, not implemented yet, etc.) — never a raw provider error.
Generated images are saved to disk and automatically registered in the Library.

## Library and Schedule

- **Library** (sidebar) lists everything Echo has produced or you've uploaded — generated
  images, self-improvement/health reports, conversation exports, and so on — with
  search, a type filter, and download/delete per item.
- **Schedule** (sidebar) is a simple in-app reminder/to-do list: create, complete, cancel,
  delete. **Reminders only surface while Echo is open in your browser/app — there is no
  background OS notification delivery in this build**, so don't rely on it to interrupt
  you away from the app; that's a reasonable future addition, not something implemented
  today.

## Personal OS: Mission Control, Projects, Tasks

Beyond chat, ECHO tracks ongoing work: **Projects** (ongoing bodies of work — a study
track, a job search, a coding project), **Tasks** (standalone or linked to a project),
and **Mission Control** (sidebar, above Chats) — a dashboard of what's due, what's active,
and a **Continue Where We Left Off** panel suggesting what to pick back up based on
overdue tasks, recently-touched projects, and recent conversations. A small set of
deterministic chat commands ("create a project called X", "add a task to test Android APK
tomorrow", "show my tasks today", "what projects are active?", "continue where we left
off") are handled without a model call — see `backend/app/chat_actions.py`. See
[ECHO_PERSONAL_OS_V1.md](ECHO_PERSONAL_OS_V1.md) for full details, limitations, and the
manual test checklist.

## Human Persona Layer: relationship memory, mood, mode, personality

Beyond the base persona, ECHO has a Personality page (sidebar) controlling how it talks —
humour, formality, directness, response length, proactivity — plus a durable Relationship
Memory of how it works with you specifically, and a fixed Character Code (10 values, not
user-editable) that sits right after the Constitution in every prompt. Mood is detected fresh
each message and never stored permanently. Say "switch to strict coach mode" or "keep replies
short today" in chat to change the current conversation's tone/length without touching your
permanent settings. Multiple people testing the same install can each get their own persona —
type a name into the Personality page's "Acting as tester" field. See
[ECHO_HUMAN_PERSONA_LAYER_V1.md](ECHO_HUMAN_PERSONA_LAYER_V1.md) for full details, safety
limits, and the manual test checklist.

## Local Intelligence Engine: local-first workflow for Ollama-only use

Beyond plain single-call Ollama chat, ECHO can run a full local workflow — intent detection,
context gathering, role-based local model routing, a draft pass, a local critic/checker pass,
an optional repair pass, an optional style pass, and honest confidence scoring — entirely on
local models, with cloud as an explicit, off-by-default, gated fallback only. Off by default
(`LOCAL_INTELLIGENCE_ENGINE_ENABLED=false`); turn it on in `.env` or via the Personality
page's "Local Intelligence" section, which also shows live Ollama connection status and the
installed model list. See [ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md](ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md)
for the full pipeline, config variables, and manual test checklist.

## Action + Reliability Core: actions, permissions, evaluation, knowledge, releases, tools

ECHO can safely *do* things (create tasks/projects/reminders, search web/wiki/RSS/memory,
summarize files/conversations, seed a release checklist, ...) — every action carries a risk
level and goes through a single Permission Center (allowed/ask-first/disabled) before running;
destructive actions only ever soft-archive. A one-click Evaluation Lab checks 10 fixed cases
against ECHO's own deterministic routing/safety rules (no model call). A Knowledge Vault holds
your own notes/decisions/prompts, separate from Atlas. A Release Manager tracks recorded
test/build results — Green only when every required check has actually been recorded passing.
An internal Tool Registry backs both the Action System and future automation. Multi-user
tester accounts were **not** part of this pass. See
[ECHO_ACTION_RELIABILITY_CORE_V1.md](ECHO_ACTION_RELIABILITY_CORE_V1.md) for the full system
list, config variables, and manual test checklist.

## Cognitive Core: world model + task understanding

Beyond storing facts (Atlas) and doing things (Action System), ECHO keeps a small structured
world model — durable concepts and how they relate, reusable skill workflows, and simple
cause-effect notes — and, for genuinely complex requests only, builds an internal task
understanding (goal, known facts, unknowns, constraints, success criteria) that's folded into
the prompt as a compact `CognitiveBrief`. It's deterministic bookkeeping, not a claim of
consciousness, and it's never shown in a normal chat reply. Browse it under
Advanced → Knowledge & Memory → Cognitive Core. See
[ECHO_COGNITIVE_CORE_V1.md](ECHO_COGNITIVE_CORE_V1.md) for the full model, config, and manual
test checklist.

## Operational Self-Model + Interface Simplification

ECHO tracks an honest, explicitly non-conscious operational state each turn — current goal,
mode, confidence, known limits, and active risks — folded into the prompt as a compact overlay,
never shown raw in a normal chat reply. Risky-sounding requests (a public repo push, deleting
memories, calling a cloud API) get flagged and ECHO asks for confirmation before proceeding;
release-status or current-info questions without real evidence/a real source are honestly capped
at "unverified" confidence. The sidebar now shows only the 6 everyday pages (Mission Control,
Chats, Projects, Tasks, Schedule, Library) plus Settings and a collapsed-by-default Advanced
section — every internal system (Atlas, Cognitive Core, Actions, Tools, Evaluation Lab, Release
Manager, Permissions, Constitution, Amendments, Self-Improvement, Knowledge Vault) is still there,
just one click away under Advanced. See
[ECHO_OPERATIONAL_SELF_MODEL_V1.md](ECHO_OPERATIONAL_SELF_MODEL_V1.md),
[ECHO_INTERFACE_SIMPLIFICATION_V1.md](ECHO_INTERFACE_SIMPLIFICATION_V1.md), and
[ECHO_HONEST_INNER_STATE_V1.md](ECHO_HONEST_INNER_STATE_V1.md) for the full detail.

## Infrastructure foundation (Layer 0)

Configuration validation, structured logging + redaction, standard error
schema, health/readiness/diagnostics endpoints (`/health`, `/ready`,
`/api/system/*`), feature-flag and provider registries, in-process metrics,
SQLite foreign-key enforcement, schema-version tracking, backup/restore
scripts, and Docker hardening (healthchecks, non-root user). No user-facing
behavior changed. See
[ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md](ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md)
and [ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md](ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md).

## Multi-device

The frontend is a fully responsive web app — the same build works on desktop and mobile
browsers. There's no native app or real multi-account sync; "multi-device" here means
"open the same URL from any device."

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for running tests, lint, type checks, and the
recommended commit workflow. See [ROADMAP.md](ROADMAP.md) for what's done, what's in
flight, and what's deliberately out of scope for now. See
[DAILY_SMOKE_TEST.md](DAILY_SMOKE_TEST.md) for a quick manual checklist after a work
session, covering things the automated suite can't see (actual UI text, actual
click-through behavior).

## Notes on the Value Invariant guard

`backend/app/constitution.py` defines a small set of immutable invariants (no fabricated
certainty, no dependency-fostering, no power-seeking, no self-deception about being an AI,
mandatory reasoning transparency). `backend/app/council.py` scans proposed amendment text
for override language near those invariants' guarded keywords and rejects the proposal
before it can be voted on. This is a heuristic first line of defense, not a substitute for
actually reading proposals — the Guardian Council vote is still the real safeguard.
