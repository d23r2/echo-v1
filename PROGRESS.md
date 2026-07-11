# Echo (God Tear AI Brain) — Progress Log

Last check-in: 2026-07-11

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
1. **No automated tests anywhere** (backend or frontend) — highest priority given the
   Guardian Council invariant guard is safety-critical logic worth locking down with tests.
   New `memory_extraction.py` (below) raises the stakes here: explicit-memory regex
   matching and MEMORY: JSON parsing are exactly the kind of logic that silently rots
   without tests.
2. Polish pass: loading/error states, mobile responsiveness check, empty-state copy.
3. Consider streaming chat responses (currently single request/response per turn).

**New since 2026-07-10 (inferred from file activity, not yet in a prior snapshot):**
- `backend/app/memory_extraction.py` (98 lines, added 2026-07-10 evening) — turns
  conversation into Atlas memory writes without a second model call. Explicit path
  (regex-detected "remember that..." phrasing) writes directly from user text; implicit
  path parses a MEMORY: JSON block that persona.py's chat completion emits. Confirmed
  wired into `routers/chat.py` (imported, `is_explicit_remember_request`,
  `extract_explicit_memory`, `parse_memory_json` all called there) — this is a real,
  integrated feature, not a stray file.

**Resolved since 2026-07-09:**
- Version control: git repo initialized and committed from Claude Code (not the Cowork
  sandbox — see note below), multiple commits in, working normally.
- Gemini provider: smoke-tested end-to-end (see above).
- Deployment target: `docker compose up --build` run end-to-end successfully — both
  containers healthy, nginx correctly proxies `/api` to the backend, confirmed a full
  chat round-trip through the containerized stack (including the host-run Ollama
  fallback via `host.docker.internal`).

## Blockers
- (none recorded yet)

## Environment note: git
Tried to `git init` this folder from a Cowork session's sandboxed shell — it failed
repeatedly (corrupted `.git/config`, and delete/unlink operations are blocked on this
bridged mount). This looks like a limitation of the FUSE bridge between the sandbox and
this Windows folder, not a problem with the project. **Run `git init` / first commit
locally** (Claude Code, or a plain terminal in this folder) instead — that writes directly
to disk with no bridge involved. There is a stray empty `.git/` folder here from the
failed attempt; safe to delete manually in Explorer, or just overwrite with a fresh
`git init` locally.

Retried from a Cowork sandbox shell again on 2026-07-09 (~16:00) — same failure mode
(`.git/config` intermittently unreadable, `fatal: unknown error occurred while reading
the configuration files`). Confirms this is still a sandbox/FUSE limitation, not
something that self-resolved. Still needs to be done locally.

Checked again on 2026-07-10: `.git/` still present with a stale lock file
(`_stale_lock_1783578633`, `config.lock.bak`, `index.lock.bak`) and `git log` still
fails with the same config-read error. No change — still needs a local `git init`.

Resolved 2026-07-10 via the recommended workaround: initialized and committed from
Claude Code running locally (not the Cowork sandbox), which confirmed this was purely
the sandbox/FUSE bridge limitation described above. Repo now has normal git history.

## Notes for the daily check-in task
- This file is the source of truth for "where things stand." Update the **Last check-in**
  date and the **Next up** list each time significant progress is made.
- Once a real git repo exists (see note above), prefer `git log`/`git diff` over file
  mtimes for detecting what changed since the last check-in.
