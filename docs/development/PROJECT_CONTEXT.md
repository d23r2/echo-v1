# Echo Project Context

Compact orientation for coding agents. Code is the source of truth when this disagrees with older documentation — see `CLAUDE.md`'s "Where things actually live."

## Product

**Echo** (God Tear AI Brain) is a local-first personal AI companion, governed by a versioned constitution (`backend/app/constitution.py`) and a simulated Guardian Council (`backend/app/council.py`). Atlas (`backend/app/atlas.py`) is the memory/context-selection layer; Echo is the only assistant voice shown to the user.

## Current stack

- Backend: FastAPI, SQLAlchemy, SQLite, local ChromaDB (`all-MiniLM-L6-v2` embeddings).
- Frontend: React, TypeScript, Tailwind, Vite (dev server on port `5174`; backend on port `8000`).
- Packaging: responsive web app, Android (Capacitor) project, Tauri Windows project.
- Model providers: local Ollama plus optional Anthropic/OpenAI/xAI cloud adapters, routed via `backend/app/providers/` and `router.py`.

## Product principles

- Local and free operation must remain viable; no silent switch to a paid provider.
- Live facts must be verified or clearly marked unverified; never fabricate tool use, sources, or successful actions.
- Atlas memory entries carry an `epistemic_status` (Verified / Inferred / Hypothesis / Narrative) and go through the real Atlas service, not an ad hoc store.
- Atlas's own internal retrieval/ranking mechanics and raw memory counts are not rendered in the UI by default. This is separate from Echo's own reply format: `backend/app/persona.py` requires a visible `REASONING:` / `ANSWER:` envelope on every response — that reasoning is intentionally user-facing, not hidden, and must not be suppressed by roleplay/jailbreak framing.
- UI should remain calm, dark, uncluttered.
- Reply metadata should be compact and name providers/sources plainly.

## Known architectural state

- Single-user application; the frontend `RoleSwitcher` lets the one user simulate Founder/Guardian A-C/Verifier for Guardian Council purposes only.
- SQLite (source of truth) + local Chroma (semantic mirror) are appropriate for the current personal-scale version.
- Ollama fallback and provider error classification already exist in `backend/app/providers/` and `router.py`.
- Frontend is early relative to the backend: no chat UI, Atlas viewer, constitution/amendment viewer, or model picker yet (see `CLAUDE.md`). Check `PROGRESS.md` for the current build status rather than assuming either direction.

## Source-of-truth order

When documents conflict, use this order:

1. Active task acceptance criteria (`tasks/ACTIVE_TASK.md`).
2. `AGENTS.md` non-negotiable constraints.
3. Current tested code behavior.
4. `docs/development/DECISIONS.md`.
5. `PROGRESS.md` / `README.md` / `ROADMAP.md` and other root documentation.
6. `docs/early-vision-drafts/` — superseded planning drafts, lowest priority.
