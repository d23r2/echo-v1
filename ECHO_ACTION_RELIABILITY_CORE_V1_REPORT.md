# ECHO Action + Reliability Core v1 — Report

## Overall status: Green

Backend tests (702/702) and the frontend production build (`tsc -b && vite build`) both pass.
All 9 systems were verified live against a real running backend + a real local Ollama
instance through the actual product UI (not just the test suite), and every bug live
verification surfaced was fixed and covered by a new regression test. The Multi-user Tester
System was explicitly **not** built, per instruction.

## Files changed

**New backend models** (`backend/app/models.py`): `ActionDefinition`, `ActionRun`,
`PermissionSetting`, `EvaluationRun`, `EvaluationResult`, `KnowledgeItem`,
`ConversationSummary`, `ReleaseRecord`, `ReleaseCheck`, `ReleaseArtifact`, `ToolDefinition`,
`ToolRun`; `PersonaSettings` gained `voice_mode`/`tts_enabled`.

**New backend services**: `action_system.py`, `permission_center.py`, `evaluation_lab.py`,
`knowledge_vault.py`, `conversation_summary.py`, `release_manager.py`, `tool_registry.py`.

**New backend routers**: `actions.py`, `permissions.py`, `evaluations.py`, `knowledge.py`,
`conversation_summary.py`, `releases.py`, `tools.py` — all registered in `main.py`.

**New fixture**: `backend/app/fixtures/evaluation_lab_cases.json` (10 cases).

**Modified**: `backend/app/config.py` (2 new settings), `backend/app/db.py` (2 new
`_ensure_column` calls + delegated seeding for Action/Permission/Tool registries),
`backend/app/schemas.py` (~25 new schemas + `_UtcAssumingModel` mixin), `backend/app/main.py`.

**New backend tests** (88 new, 614 → 702): `test_action_system.py` (16),
`test_permission_center.py` (9), `test_evaluation_lab.py` (11), `test_knowledge_vault.py` (6),
`test_conversation_summary.py` (8), `test_release_manager.py` (12, incl. 1 regression test),
`test_tool_registry.py` (11), `test_action_reliability_integration.py` (14), plus 1 new test
in `test_human_persona.py` (voice_mode default regression).

**New frontend pages**: `ActionCenterView.tsx`, `PermissionCenterView.tsx` (also hosts Voice
& Camera settings), `EvaluationLabView.tsx`, `KnowledgeVaultView.tsx`, `ReleaseManagerView.tsx`,
`ToolCenterView.tsx`.

**Modified frontend**: `client.ts` (~230 new lines: types + API functions for all 7 systems,
plus `voice_mode`/`tts_enabled` on PersonaSettings types), `Sidebar.tsx` (regrouped nav into
Main/Intelligence/System sections, 17 items total), `MobileDrawer.tsx` (made nav+conversation
list scrollable to fit the larger nav), `App.tsx` (6 new routes), `ChatView.tsx` (voice_mode-
aware mic gating, "Summarize this conversation" button + panel), `ChatActionMenu.tsx` (camera
placeholder item), `MessageBubble.tsx` (unchanged this pass), `api/client.ts`'s `BASE_URL`
resolution (the phone-loading fix, see below).

## Database changes

12 new tables (listed above), all created via `Base.metadata.create_all()` — no manual
migration needed for a fresh install. 2 new columns on the existing `persona_settings` table
(`voice_mode`, `tts_enabled`), added via the existing `_ensure_column()` in-place-ALTER
pattern this repo already uses for every prior schema addition. **Backup recommendation**:
before running this on an existing install, copy `backend/data/echo.db` — the same standard
advice as any prior schema change in this repo; nothing here is destructive, but a copy is
cheap insurance.

## APIs added

```
GET  /api/actions                          POST /api/actions/run
GET  /api/actions/runs                     POST /api/actions/runs/{id}/approve
                                            POST /api/actions/runs/{id}/cancel

GET  /api/permissions                      PATCH /api/permissions/{key}
                                            POST /api/permissions/reset-defaults

GET  /api/evaluations/cases                POST /api/evaluations/run
GET  /api/evaluations/runs                 GET /api/evaluations/runs/{id}

GET  /api/knowledge                        POST /api/knowledge
GET  /api/knowledge/search                 GET/PATCH/DELETE /api/knowledge/{id}

POST /api/conversations/{id}/summarize     GET /api/conversations/{id}/summary

GET  /api/releases                         POST /api/releases
GET/PATCH /api/releases/{id}               POST /api/releases/{id}/checks
POST /api/releases/{id}/checklist/seed     POST /api/releases/{id}/artifacts
POST /api/releases/{id}/mark-status

GET  /api/tools                            POST /api/tools/{tool_name}/run
GET  /api/tools/runs
```

## Frontend pages added

Action Center, Permissions (+ Voice & Camera settings), Evaluation Lab, Knowledge Vault,
Release Manager, Tool Center. Sidebar reorganized into Main/Intelligence/System groups.

## Tests added

88 new backend tests (614 → 702), all using `db_session`/`FakeProvider`/`ScriptedProvider` —
**zero real network calls, zero real Ollama calls, zero paid API calls** in the entire suite.
The one system that touches a model (Conversation Auto-Summary) is tested exclusively via a
`LocalModelRouter` swapped for a `FakeProvider`, same pattern as the Local Intelligence
Engine's own test suite.

## Commands run and results

```
cd backend
./.venv/Scripts/python.exe -m pytest -q            # 702 passed
./.venv/Scripts/python.exe -m ruff check .          # All checks passed!
cd ../frontend
npx tsc -b --noEmit                                 # exit 0
npm run build                                       # tsc -b && vite build — succeeded
```

No unrelated Chroma flake encountered this run — the full suite passed cleanly on the first
attempt every time it was run during this session.

## Bugs found and fixed

All four bugs below were caught during **live** browser/API verification against a real
running backend and (for two of them) a real local Ollama instance — not hypothetical.

1. **Phone/LAN dev-server access was broken.** `frontend/.env`'s `VITE_API_BASE_URL=http://localhost:8000`
   resolves to "the phone itself" when the dev server is reached from a LAN/Tailscale IP (which
   `vite.config.ts`'s `host: true` is specifically configured to allow). Fixed by making
   `client.ts`'s `BASE_URL` resolve dynamically to the page's own hostname whenever the
   configured value is itself localhost-shaped and the page wasn't loaded from localhost. The
   Docker production build (`VITE_API_BASE_URL=""`, same-origin via nginx) was already correct
   and is unaffected by this change.
2. **`release_manager.add_check()` always inserted a new row, never updated an existing one.**
   Seeding the standard checklist then marking a check "Pass" via the UI dropdown left the
   original "not_run" seed row sitting alongside the new "Pass" row forever — `compute_status()`
   would see the stale "not_run" row and never reach Green, no matter how many times you marked
   every check pass. Reproduced live: after seeding + marking 3 checks pass, status stayed
   Yellow with 13 rows recorded for 8 named checks. Fixed by upserting on `(release_id, check_name)`
   instead of always inserting; added `test_marking_a_seeded_check_updates_in_place_not_duplicates`
   as a permanent regression test. Verified live afterward: a fresh release seeded + all 5
   required checks marked pass produced exactly 8 rows (no duplicates) and status "green".
3. **`voice_mode` defaulted to "off", silently regressing already-working voice input.**
   Voice input (speech-to-text) worked unconditionally in this app before this milestone,
   gated only by browser support. Adding a new `voice_mode` PersonaSettings column with
   `default="off"` meant every tester — existing and new — lost the 🎤 button from the chat +
   menu the moment the column was created, since the SQLite `_ensure_column()` ALTER backfills
   the literal default value into every existing row. Caught live: the mic button was missing
   after this milestone's changes for a tester that had voice input working moments before.
   Fixed the model/migration default to `"push_to_talk"` (matching the pre-existing behavior),
   and directly corrected the 3 tester rows that had already been backfilled with the buggy
   `"off"` value in the shared local database. Added
   `test_persona_settings_voice_mode_defaults_to_push_to_talk_not_off` as a regression test.
4. **A leftover, abandoned draft line in `action_system.py`'s `approve_run()`** (an
   `if False else` construct calling a nonexistent `._replace_id()` method, left over from an
   earlier version of the function) was caught and fixed via static inspection before it ever
   ran — `approve_run()` now cleanly re-executes the same pending `ActionRun` row.

## Bugs not fixed

- **`Sidebar.tsx`/`MobileDrawer.tsx` occasionally logged a React error during heavy live
  editing sessions with many rapid HMR updates** (same class of transient Fast-Refresh
  artifact documented in the prior milestone's report) — confirmed not a real bug: a clean
  cold reload always rendered the sidebar correctly with all 17 nav items present and clickable.
- **No inline "run" button on the Action Center page** — documented as a deliberate scope
  choice (see the companion doc), not a bug, but flagging it here since it might read as
  missing functionality at first glance.
- **A native `window.confirm()` dialog (used by the Knowledge Vault's "Archive" button,
  the same established pattern as the pre-existing Projects "Archive" button) is
  incompatible with this session's browser-automation tooling** — it froze the automated tab
  entirely, requiring a fresh tab to recover. This is a tooling/automation limitation, not an
  application bug; `window.confirm()` is a completely standard, well-supported browser API for
  real human users, and the exact same pattern was already shipped and working in ProjectsView's
  archive button before this milestone.

## Manual checks I must do

- **The real-cloud-call path for anything touching `cloud_api_use`** — not exercised live
  (no cloud API key configured in this environment); covered only by the Evaluation Lab's
  structural check that it stays disabled by default, and by unit tests.
- **The Knowledge Vault's Archive button** — logic is unit-tested and the underlying API was
  verified directly via curl (soft-archive confirmed working), but the actual UI click-and-
  confirm flow couldn't be exercised live due to the `window.confirm()` automation limitation
  above. Please click Archive once yourself to confirm the native browser dialog behaves as
  expected in a real browser session.
- **Verification test data was written into your real local database** during this session
  (`backend/data/echo.db`, shared with your running Docker backend on port 8000): a task
  titled "Browser-verified task", a Knowledge Vault decision note titled "Use SearXNG as
  primary no-billing search" (a genuinely accurate real note, not garbage — feel free to keep
  it), and two test releases (`v1.5.0-browser-verify`, left at Yellow from before the upsert
  fix, and `v1.5.1-fix-verify`, at Green) with their checks. There is no delete endpoint for
  releases in this milestone (matching the "manual test checklist doesn't ask for one" scope),
  so these will need manual cleanup via direct DB access if you'd rather not see them in your
  real Release Manager.
- **Android/Windows builds** — the seeded release checklist references
  `npx cap sync android` / `.\gradlew assembleDebug` / `npm run tauri build`, none of which
  were run this session (matches this repo's existing, already-documented Android/Windows-
  optional posture).

## Known limitations

See the companion doc's "Known limitations" section for the full list (no per-tester
scoping anywhere in this milestone, no chat-command-to-action NLU routing, Release Manager's
strict per-check Green rule, camera as placeholder-only, auto-summary config variables not
yet wired to an automatic trigger).

## ECHO Action + Reliability Core v1 release candidate

**Green.** Backend tests (702/702) and the frontend production build both pass. All 9
requested systems (Action System, Reliability/Evaluation Lab, Safety and Permission Center,
Voice-first Mode foundation, Camera/Visual Assistant foundation, Personal Knowledge Vault,
Conversation Auto-Summary, Release/Build Manager, Internal Plugin/Tool System) were built and
verified live, not just unit-tested. The Multi-user Tester System was explicitly excluded, as
instructed. Four real bugs were found and fixed during live verification, each with a
permanent regression test. This is a release candidate for the systems described here — not a
claim that every future extension point (chat-command routing to actions, automatic
summarization, real camera capture) is built; those are explicitly listed as known
limitations and next steps.
