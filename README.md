# God Tear AI Brain — Echo (Seed v1.0)

A symbiotic, truth-seeking AI partner governed by a versioned constitution with ranked
core values, immutable Value Invariants, and a simulated Guardian Council amendment process.

- **Echo** — the chat persona: truth-seeking, transparent reasoning, resists sycophancy
  and jailbreaks, actively discourages dependency.
- **Atlas** — persistent memory with epistemic status (Verified / Inferred / Hypothesis /
  Narrative), tags, confidence, and semantic search (ChromaDB + local embeddings). Any
  Atlas entry is retrievable in any future conversation, regardless of which one it was
  created in. Writes happen two ways: explicitly ("remember that I prefer tea" is
  detected and saved directly from your own words, no model judgment involved), or
  opportunistically (Echo's single chat-completion call also emits a `MEMORY:` section
  alongside its reasoning/answer — no second model call, so it can't double your rate
  limit — which gets parsed and saved when it decides something's worth keeping).
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

Model routing supports Anthropic (Claude), OpenAI, Gemini (Google), xAI (Grok), and a
local Ollama fallback. "auto" mode tries them in that order and uses the first available
one; you can also pin a specific provider from the model picker.

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

## Multi-device

The frontend is a fully responsive web app — the same build works on desktop and mobile
browsers. There's no native app or real multi-account sync; "multi-device" here means
"open the same URL from any device."

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for running tests, lint, type checks, and the
recommended commit workflow. See [ROADMAP.md](ROADMAP.md) for what's done, what's in
flight, and what's deliberately out of scope for now.

## Notes on the Value Invariant guard

`backend/app/constitution.py` defines a small set of immutable invariants (no fabricated
certainty, no dependency-fostering, no power-seeking, no self-deception about being an AI,
mandatory reasoning transparency). `backend/app/council.py` scans proposed amendment text
for override language near those invariants' guarded keywords and rejects the proposal
before it can be voted on. This is a heuristic first line of defense, not a substitute for
actually reading proposals — the Guardian Council vote is still the real safeguard.
