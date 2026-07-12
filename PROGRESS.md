# Echo (God Tear AI Brain) — Progress Log

Last check-in: 2026-07-13

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
1. **No automated tests anywhere** (backend or frontend) — still zero test files
   repo-wide as of 2026-07-12. Highest priority given the Guardian Council invariant
   guard is safety-critical, and the surface area needing coverage has grown
   (memory_extraction.py, plus the new attachments/conversation-deletion/voice code below).
2. Polish pass: loading/error states, mobile responsiveness check, empty-state copy.
   (Partially underway — mobile hamburger drawer landed 2026-07-11 — but not complete.)
3. Consider streaming chat responses (still single request/response per turn as of
   2026-07-12 — not started).
4. Attachments: text/code and PDF content is genuinely extracted and injected into the
   prompt. Images now get real vision too, but only via Gemini (`gemini_provider.py`'s
   `inline_data` wiring, 2026-07-12) — Anthropic/OpenAI/Grok/Ollama still can't see
   images at all, so the "understood: true" label is only fully honest when Gemini ends
   up handling the request. Audio/video still aren't read by anything. Also worth
   noting: the Gemini free-tier key hit its daily quota during this session's testing —
   auto mode falls back to Ollama (no vision) when that happens, now at least visible
   via a log line instead of silently.

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

## Blockers
- (none recorded yet)

## Notes for the daily check-in task
- This file is the source of truth for "where things stand." Update the **Last check-in**
  date and the **Next up** list each time significant progress is made.
- Once a real git repo exists (see note above), prefer `git log`/`git diff` over file
  mtimes for detecting what changed since the last check-in.
