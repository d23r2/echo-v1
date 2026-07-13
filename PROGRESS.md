# ECHO (formerly God Tear AI Brain) — Progress Log

Last check-in: 2026-07-14

## New since 2026-07-14 — Post-diagnosis cleanup pass

Targeted cleanup on top of the 2026-07-13 Green baseline (not a re-diagnosis) — see
[PROJECT_HEALTH_REPORT.md](../PROJECT_HEALTH_REPORT.md)'s "2026-07-14" section for the
full breakdown. 349 backend tests passing (14 new), frontend build/typecheck clean.

- Branding: "God Tear" / "AI Brain — Seed v1.0" → **ECHO** / **Adaptive Personal AI**
  (sidebar, mobile drawer, browser title, PWA manifest, FastAPI title, Constitution's
  own `PHILOSOPHY` text).
- Sidebar: removed the duplicate "+ New conversation" button and the duplicate "Search"
  nav item (identical to the already-present inline conversation search); deleted the
  now-redundant `SearchView.tsx`.
- **Real bug fixed**: outdated Atlas memories (`AtlasEntry.outdated=True`) were still
  being retrieved by semantic search, injected into the persona prompt, and used for
  conflict detection. Now excluded from all three by default (still visible in the Atlas
  list UI) — `atlas.search()`/`memory_conflicts.find_conflicts()`/`find_all_conflicts()`
  gained an `include_outdated` escape hatch for the rare case that wants them back.
- **Real bug fixed**: Schedule `due_at` could display shifted after a reload — SQLite
  drops tzinfo on `DateTime(timezone=True)` read-back, so a naive datetime was
  serialized without a UTC offset and the frontend misparsed it as local time. Fixed via
  a Pydantic validator that reattaches UTC to naive datetimes read from the DB; verified
  live (9:00 AM in, 9:00 AM out after a real reload).
- Streaming (`POST /api/chat/stream`) no longer leaks raw exception text into SSE
  `error` events on unexpected failures — clean generic messages now, full detail still
  in server logs.
- **Real bug fixed**: the image-generation unavailable reason in the chat "+" menu was
  reading `features.vision.reason` (image-*understanding* status) instead of
  `features.image_generation_detail.reason` (image-*generation* status) — confirmed live
  that these are genuinely different values.
- Library API (`GET /api/library`) no longer includes the server-absolute `file_path` in
  its response — download/delete already went through the item's `id`, so this was a
  pure information-exposure trim, no functional change.

## New since 2026-07-13 — Full diagnosis + v1 safety hardening pass (Phases 0–15)

See [PROJECT_HEALTH_REPORT.md](../PROJECT_HEALTH_REPORT.md) for the full breakdown —
overall status 🟢 Green, 335 backend tests passing (75 new this pass), frontend build
clean. Summary:

- **Envelope integrity fields** (`envelope_status`, `envelope_degradation_reason`) now
  persist through the whole chat pipeline (both endpoints, both DB and API), and a real
  bug was fixed where `stream_chat()`'s default implementation fabricated a fake complete
  envelope even when the model returned none.
- **Cloud quota/credit/billing exhaustion now falls back to Ollama** with a specific,
  required message, backed by real error classification (`provider_errors.py`) and a
  persistent per-provider cooldown (`PROVIDER_COOLDOWN_MINUTES`) so an exhausted provider
  isn't retried every turn.
- **FREE_MODE** (Ollama → Gemini → Azure → Ollama, paid-only providers excluded from auto
  unless explicitly pinned) and a new, safe-by-default **Azure OpenAI provider**
  (disabled unless explicitly enabled+configured, never primary in FREE_MODE, optional
  daily request cap) both shipped.
- **Image generation provider architecture** (`image_router.py`): honest per-provider
  status (Gemini is the only one that actually generates; Ollama/ComfyUI correctly
  self-report as non-functional rather than failing silently), generated images now
  register into the new Library.
- **New: Library and Schedule** — new `LibraryItem`/`ScheduleItem` models + routers +
  frontend pages, plus a redesigned ChatGPT-like sidebar (New chat / Chats / Search /
  Library / Schedule / Atlas / Constitution / Amendments / Self-Improvement). Live-verified
  in a real browser against real data, not just tested.
- **Two real bugs found and fixed** during re-verification of already-built features:
  `GET /api/schedule`'s default filter silently included completed/cancelled items; and
  previous-conversation semantic search had no relevance threshold, so genuinely
  unrelated queries could return a false match (see PROJECT_HEALTH_REPORT.md §5 for the
  distance-calibration details).
- Gap #2 below (non-streaming `MEMORY:` leak) — confirmed resolved via PR #2, merged
  before this pass began.

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
1. Polish pass: loading/error states, mobile responsiveness check, empty-state copy.
   (Partially underway — mobile hamburger drawer landed 2026-07-11, sidebar redesign +
   new Search/Library/Schedule pages landed 2026-07-13 — but not complete.)
2. See PROJECT_HEALTH_REPORT.md's "Next 5 zero-cost priorities" for the current top
   picks (ComfyUI real generation, frontend test setup, Schedule background
   notifications, real Groq/OpenRouter providers, `npm audit fix`).
3. Self-improvement verification's `git status`/`git diff --stat` checks report
   "unavailable" inside the production Docker container — the image only ships `app/`
   (see `backend/Dockerfile`), not a `.git` directory, so there's genuinely nothing for
   git to check even though the binary itself is now installed. Not a bug to fix further;
   just a real limitation of the current minimal-image deploy strategy worth knowing
   about if verification results look thin in prod.

**New since 2026-07-13 — Goals 15–18 (tooling, roadmap, memory capture, conversation
recall, chat UI overhaul — all tested, 255 backend tests passing, frontend build clean):**
- **Code quality tooling** (Goal 15): `ruff` + gentle-mode `mypy` added to
  `backend/pyproject.toml`/`requirements.txt` (~20 cosmetic ruff findings, ~10 minor mypy
  findings, neither blocking); `frontend/package.json` gained a `typecheck` script; new
  [DEVELOPMENT.md](../DEVELOPMENT.md) documents test/lint/build/commit workflow. No
  ESLint yet (documented as a gap, not silently skipped).
- **[ROADMAP.md](../ROADMAP.md)** (Goal 16): honest priority-1-through-6 status (all six
  turned out to already be done as of this session) plus a "Do Not Work On Yet" section —
  meant to keep future requests anchored to the core instead of open-ended scope growth.
- **Preference/learning-style memory capture** (Goal 17, `preference_detection.py`):
  deterministic detection of durable preference statements ("when you explain... to me",
  "I prefer...", "from now on...") that don't use the literal phrase "remember that" —
  these now queue as a `preference`-type memory candidate instead of being silently
  dropped when the model doesn't spontaneously emit a MEMORY: block.
- **Previous-conversation search** (Goal 18a, `conversation_search.py`): a
  fallback/supplement to Atlas for information that was said but never distilled into a
  saved memory — SQLite keyword search + semantic search over a new Chroma
  `conversation_messages` collection (same embedding model Atlas already uses), triggered
  only by deterministic recall phrases ("do you remember", "as I said", "before", etc.),
  never on every turn. Found and fixed a real bug during review: the Chroma
  `upsert()` metadata argument wasn't wrapped in a list, which would have silently broken
  semantic indexing for every message.
- **Chat UI overhaul** (Goal 18b): provider/image-gen failures no longer leak raw
  exception text into the chat (clean generic messages now, full detail still in server
  logs via `logger.warning`); Reasoning and Atlas Notes are now separate collapsible
  sections (`ReasoningTrace.tsx`, new `AtlasNotes.tsx`) instead of one merged one; new `+`
  action menu (`ChatActionMenu.tsx`) replaces the separate paperclip/mic/generate-image
  buttons; new `GET /api/features` endpoint reports real provider/vision/image-generation
  availability so the frontend can disable things cleanly instead of failing noisily.

**New since 2026-07-13 — Goals 5–14 (two batches, both fully tested + live-verified):**
- **Router fallback tests** (`tests/test_router_fallback.py`) — 14 tests via `FakeProvider`,
  no real API calls; also **3-way amendment guard classifier**
  (`constitution.classify_amendment_text`: allowed/blocked/needs_human_review, 422 for
  ambiguous cases) in `constitution.py`/`council.py`/`routers/amendments.py`.
- **Memory extraction diagnostics** (`MemoryExtractionLog`, `GET /api/atlas/diagnostics`,
  `MemoryDiagnostics.tsx`) and **memory-candidate review queue with conflict detection**
  (`memory_conflicts.py`, `MemoryCandidate` model, `routers/memory_candidates.py`,
  `MemoryCandidates.tsx`) — implicit memories now queue for accept/edit/reject instead of
  auto-saving; explicit "remember that…" requests still save directly.
- **Date/time grounding**: `persona.build_system_prompt()` now injects current UTC
  date/time into every provider's prompt uniformly (`_current_date_note`).
- **Self-improvement verification is now real** (`self_improvement_verify.py`): runs
  `git status`/`git diff --stat`/`pytest`/`ruff`/`mypy` against the working tree on
  founder-approved requests, stores per-check command/exit-code/output/status, never
  claims code was applied. Hit and fixed two real Docker-environment bugs along the way
  (repo-root path resolution assumed the local dev layout; git wasn't installed in the
  image — both now handled, see gap #3 above for the remaining structural limitation).
- **Atlas is now a "second brain"**: quick filters (facts/projects/goals/preferences/
  recent/low-confidence/conflicts), epistemic-status filter, confidence/recency sort,
  Confirm/Mark-outdated/Merge actions (`memory_conflicts.find_all_conflicts`,
  `atlas.merge_entries`, new `outdated` field on `AtlasEntry`).
- **Context-aware anti-dependency nudges** (`dependency_patterns.py`): replaced the
  robotic "every N turns" reminder with local rule-based detection (decide-for-me,
  reassurance-seeking, repeated-same-task, do-it-for-me, avoidance) — periodic nudge kept
  only as a fallback when no specific pattern fires. `independence_nudge_reason` stored
  per message for audit.
- **Honest attachment handling**: `Attachment.analysis_status`
  (text_extracted/vision_analyzed/stored/unsupported) replaces the misleading blanket
  "understood" label in the UI; auto mode now actually routes image turns to Gemini when
  available instead of letting a text-only provider guess; frontend warns before sending
  if an attached image won't be analyzed.
- **Streaming chat** (`POST /api/chat/stream`, SSE): only the ANSWER section streams live,
  REASONING/MEMORY stay server-side and are never sent to the client even when malformed.
  Ollama has real token-level streaming (`stream: true`); other providers get a safe
  single-chunk default via the same envelope parser. Non-streaming `/api/chat` is
  unchanged. Found and fixed two real parsing bugs via TDD + live testing: a
  streamed-vs-batched leading-whitespace mismatch, and a MEMORY-JSON leak when a model
  ignores the envelope early but adds one on late (see gap #2 above for the sibling bug
  still open in the non-streaming path).
- Test suite grew from 124 → 207 backend tests across this work, all passing; frontend
  `npm run build` clean throughout.

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
- The non-streaming `MEMORY:` JSON leak (former gap #2) — fixed via PR #2 in a separate
  session, merged before the 2026-07-13 diagnosis pass began; re-verified as part of that
  pass's envelope-integrity test suite.

## Blockers
- (none recorded yet)

## Notes for the daily check-in task
- This file is the source of truth for "where things stand." Update the **Last check-in**
  date and the **Next up** list each time significant progress is made.
- Once a real git repo exists (see note above), prefer `git log`/`git diff` over file
  mtimes for detecting what changed since the last check-in.
