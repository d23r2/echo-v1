# Roadmap — zero-cost priorities

This file exists to keep future work anchored to the core product, not to keep
expanding scope. Status below is honest as of 2026-07-13 — check it before assuming
something is still open.

## Priority 1: Trustworthiness — **done**

- Backend tests: `backend/tests/` — 207 tests, `pytest` from `backend/`.
- Invariant guard tests: `test_constitution_guard.py` — blocked / allowed /
  needs_human_review classification (`constitution.classify_amendment_text`).
- Vote logic tests: `test_council.py` — Guardian Council tallying, ratification/rejection.
- Memory parser tests: `test_memory_extraction.py`, `test_envelope_stream.py` —
  `REASONING:`/`ANSWER:`/`MEMORY:` envelope parsing, both batch and streaming.
- Provider fallback tests: `test_router_fallback.py`, `test_router_streaming.py` — auto
  mode fallback, pinned-provider behavior, usage tracking, all via `FakeProvider` (no
  real API calls).

Nothing left to do here to hit the bar this priority set — future test work should be
incremental coverage of new features, not a separate initiative.

## Priority 2: Atlas usefulness — **done**

- Memory diagnostics: `GET /api/atlas/diagnostics`, `MemoryDiagnostics.tsx` — why a turn
  did/didn't save a memory.
- Memory candidates: `MemoryCandidate` model, `routers/memory_candidates.py`,
  `MemoryCandidates.tsx` — implicit memories queue for accept/edit/reject instead of
  auto-saving.
- Conflict detection: `memory_conflicts.py` — local word/tag-overlap heuristic, no model
  calls.
- Better Atlas UI: `AtlasView.tsx` — quick filters (facts/projects/goals/preferences/
  recent/low-confidence/conflicts), epistemic-status filter, confidence/recency sort,
  Confirm/Mark-outdated/Merge actions.

## Priority 3: Real self-improvement verification — **done**

- `self_improvement_verify.py` runs `git status`, `git diff --stat`, `pytest`, `ruff`,
  `mypy` against the working tree on founder-approved requests.
- Per-check command/exit-code/stdout+stderr/status/timestamp stored on
  `SelfImprovementRequest.verification_checks`; overall pass/fail shown in
  `SelfImprovementView.tsx`.
- Never claims code was applied — read-only checks only.
- Known limitation, not a bug: in the production Docker image, git checks report
  "unavailable" (no `.git` shipped in the minimal container) — see PROGRESS.md.

## Priority 4: Chat experience — **done**

- Streaming endpoint: `POST /api/chat/stream` (SSE) — `envelope_stream.py` streams only
  the ANSWER section live, REASONING/MEMORY stay server-side always.
- Frontend streaming UI: `ChatView.tsx` — live token rendering, Stop button, graceful
  error/cancellation handling.
- Envelope parsing preserved: same `REASONING:`/`ANSWER:`/`MEMORY:` contract as the
  non-streaming path, verified to produce identical saved output either way.

## Priority 5: Anti-dependency behavior — **done**

- Context-aware nudges: `dependency_patterns.py` — local rule-based detection replacing
  the old "every N turns" heuristic.
- Repeated reassurance detection: `_REASSURANCE` pattern, requires 2+ occurrences in the
  recent window before firing.
- Teach-method-rather-than-answer behavior: `do_it_for_me` pattern injects an
  instruction to teach the method, not just hand over the result.

## Priority 6: Honest multimodal handling — **done**

- Gemini vision routing: auto mode routes image-attached turns to Gemini when available
  instead of letting a text-only provider guess (`routers/chat.py`).
- Clear unsupported labels: `Attachment.analysis_status`
  (text_extracted/vision_analyzed/stored/unsupported) — audio/video and unrouted images
  are honestly labeled "stored, not analyzed," never implied as understood.

---

## What's actually in flight right now (beyond the six priorities above)

The six priorities above are the "core." Everything past this line is scope the user
has explicitly asked for on top of that core — worth tracking honestly, not worth
treating as free to keep expanding indefinitely:

- Preference/learning-style memory capture without requiring the exact phrase "remember
  that" (deterministic local detection).
- Previous-conversation search/retrieval as a fallback when Atlas has no relevant
  memory.
- Chat UI polish: clean provider-error handling, reasoning/Atlas-notes visibility, a `+`
  action menu, a feature-availability endpoint.

If more requests like these keep arriving, that's a signal to pause and re-triage
against this roadmap rather than just keep building — that's the whole point of this
file existing.

## Do Not Work On Yet

These are explicitly out of scope until asked for again, deliberately:

- **More deployment targets.** PWA, Android (Capacitor), and Windows (Tauri) already
  exist and work — no reason to add iOS, a separate Electron build, etc. without a
  concrete need.
- **More animations.** The presence orb and typography pass are done; further visual
  polish is low-value relative to correctness work.
- **More Guardian Council complexity.** The single-user 5-role simulation with a 2-of-3 +
  Verifier threshold is intentionally simple — don't add weighted votes, delegation,
  multi-tier councils, etc. without a real multi-user need driving it.
- **Paid services.** Every feature so far is free/local (SQLite, ChromaDB,
  sentence-transformers, Ollama) except the already-existing, explicitly opt-in
  Gemini/Imagen calls. Don't introduce a new paid dependency casually.
- **Real multi-user governance.** The role switcher simulates 5 roles for one person.
  Building actual multi-account auth/permissions is a different, much bigger project —
  don't start it incrementally by accident.
- **Automatic self-modifying code.** Self-improvement verification (Priority 3) is
  deliberately read-only and founder-approval-gated. Do not wire it up to actually apply
  patches or restart the app automatically — that crosses from "verification tool" into
  "autonomous agent," a different risk category entirely.
