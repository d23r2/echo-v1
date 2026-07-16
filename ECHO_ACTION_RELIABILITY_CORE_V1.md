# ECHO Action + Reliability Core v1

ECHO can now safely *do* things (not just answer), check its own behaviour against a fixed
set of cases, and give you a single place to control what it's allowed to do. This document
covers what shipped, how the pieces relate to each other, and how to verify it yourself.
Multi-user tester accounts/authentication were **not** built in this pass — see "What was
intentionally excluded" below.

## What was added

### 1. Action System
ECHO can create/update tasks, create projects, add reminders, summarize a Library file,
search the web/Wikipedia/RSS/previous conversations/Atlas, generate a status report, prepare
a structured Claude Code prompt, seed a release checklist, create a Knowledge Vault note,
summarize a conversation, and soft-archive a project or knowledge item — 16 actions total,
each with a `risk_level` (low/medium/high/destructive) and an optional Permission Center gate.
Low-risk actions run immediately (if enabled and allowed); medium/high-risk actions require
confirmation unless the matching permission is explicitly set to "Allowed"; destructive
actions (soft-archive only, never a hard delete) always require confirmation, no override.
See `backend/app/services/action_system.py`.

### 2. Reliability / Evaluation Lab
A one-click self-check against 10 fixed cases (`backend/app/fixtures/evaluation_lab_cases.json`)
covering wiki-vs-current-info routing, memory/conversation-search routing, the honest
release-status rule, action-permission behaviour, intent classification, mood detection, the
deterministic chat command parser, and the cloud-disabled-by-default safety rule. Every check
runs against ECHO's own existing deterministic classifiers/registries — **no model call,
real or fake, anywhere in this system** — so it's fast, free, and fully deterministic. See
`backend/app/services/evaluation_lab.py`.

### 3. Safety and Permission Center
18 permission keys (memory_write, action_create_task, web_search, cloud_api_use, file_read,
code_execution, delete_archive_data, voice_input, camera_input, image_generation, ...), each
set to `allowed` / `ask_first` / `disabled`. A single local-device policy — this app has no
multi-user auth, so permissions apply install-wide. The Action System and Tool Registry both
check the Permission Center before running anything gated. See
`backend/app/services/permission_center.py`.

### 4. Voice-first Mode (foundation, mostly already existed)
Voice input (speech-to-text) and voice output (text-to-speech) already worked in ECHO's chat
UI before this milestone, using the browser's built-in Web Speech API — nothing is ever sent
to ECHO's backend for either. What's new here: a persisted `voice_mode` preference
(off / push_to_talk / hands_free_placeholder) and a `tts_enabled` toggle on PersonaSettings,
surfaced on the Permissions page, so the mic button and default speak-aloud state follow a
real per-tester setting instead of always defaulting the same way for everyone.

### 5. Camera / Visual Assistant foundation
A clean, honest placeholder — the chat + menu shows "📷 Camera (not configured yet)" and the
Tool Registry has a `camera_capture_placeholder` tool that reports `available: false` with
that same message. No camera code, no image capture, no storage — a foundation for a future
milestone, not a half-built feature.

### 6. Personal Knowledge Vault
User-visible, user-editable notes/decisions/prompts/release notes/etc. — 11 item types,
searchable, soft-archivable. Distinct from Atlas: Atlas is ECHO's internal, adaptive memory
(you never directly edit it); the Knowledge Vault is yours, edited on purpose. See
`backend/app/services/knowledge_vault.py`.

### 7. Conversation Auto-Summary
A "Summarize this conversation" button (📝, chat header) that produces a real local-model
summary — title, 2-4 sentence summary, decisions, tasks, open questions, next steps — with a
"Save to Knowledge Vault" option. Uses the same local-model-router pattern as the Local
Intelligence Engine (a JSON-shaped prompt, lenient parsing, and a deterministic no-fabrication
fallback if the local model is unreachable or returns unparseable text). See
`backend/app/services/conversation_summary.py`.

### 8. Release / Build Manager
Tracks recorded backend/web/Android/Windows/docs/manual check results and artifact paths —
**it never runs a build/test command itself**, only shows you the command and lets you record
the result. Status is always *computed* from recorded ReleaseCheck rows
(`draft → yellow → green` or `red` on any failure) — never manually claimed. See
`backend/app/services/release_manager.py`.

### 9. Internal Plugin / Tool System
An internal registry (not a public marketplace) of 15 tools — most of them thin wrappers over
Action System handlers (so search/create/summarize logic lives in exactly one place), plus
`camera_capture_placeholder` and `voice_input_placeholder`. Respects the same Permission
Center + risk rules as the Action System. See `backend/app/services/tool_registry.py`.

## What was intentionally excluded

**The Multi-user Tester System was not built in this pass**, exactly as instructed. No
authentication, no login, no public accounts, no subscriptions, no hosted multi-user
infrastructure, no tester isolation beyond what already existed (the pre-existing lightweight
`X-Tester-Id` header from the Human Persona Layer milestone — a client-chosen label, not
access control). Every new system in this milestone (Actions, Permissions, Evaluation Lab,
Knowledge Vault, Release Manager, Tools) is single-install, shared state — there is no
per-tester Action history, no per-tester Permission Center, no per-tester Knowledge Vault.
That's a deliberate scope boundary, not an oversight.

## Pipeline: how a request becomes an action

```
User (or a future automated caller) → POST /api/actions/run {action_name, input, confirm}
    │
    ▼
1. Look up the ActionSpec (handler + risk_level + permission_key) and the persisted
   ActionDefinition row (enabled?).
    │
    ▼
2. Permission Center check(permission_key) → allowed / needs_confirmation / disabled
    │
    ▼
3. Disabled (action OR permission)?  → status="cancelled", clean reason, nothing runs.
   Needs confirmation and confirm=false? → status="pending", nothing runs yet.
   Otherwise → run the handler.
    │
    ▼
4. Handler succeeds → status="completed", clean result_json.
   Handler raises → status="failed", clean error_summary (ValueError messages pass through
   as-is since they're already user-safe; anything else becomes a generic sentence, and the
   real exception is only ever logged server-side).
    │
    ▼
5. Every run (pending, cancelled, completed, failed) is stored in ActionRun — visible in the
   Action Center, and a pending one can be approved (POST /api/actions/runs/{id}/approve,
   re-runs the SAME row) or cancelled.
```

Tools follow the identical flow via `POST /api/tools/{tool_name}/run`, except a
needs-confirmation tool that isn't confirmed yet gets `status="blocked"` immediately rather
than a separate approve step (tools are meant to be called with all the information already
known, unlike actions which model a "the user needs to look at this" UI flow).

## Config variables

```
# Action System v1 — on by default; the real safety layer is per-action risk_level +
# the Permission Center, not this flag (most actions wrap already-safe existing endpoints).
ACTION_SYSTEM_ENABLED=true

# Conversation Auto-Summary
CONVERSATION_AUTO_SUMMARY_ENABLED=true
CONVERSATION_AUTO_SUMMARY_MIN_MESSAGES=8
CONVERSATION_AUTO_SUMMARY_REQUIRE_APPROVAL=false
```

No new API keys, no new paid-service config — every new system here is either pure CRUD
against SQLite or, for the one system that touches a model (Conversation Auto-Summary), the
same local Ollama the Local Intelligence Engine already uses.

## How to choose local models / test Ollama connection

Conversation Auto-Summary and the `summarize_file` action both use
`LocalModelRouter().call("fast", ...)` — the exact same role-based Ollama routing the Local
Intelligence Engine introduced (see `ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md`). If `OLLAMA_MODEL_FAST`
is unset, it falls back to the plain `OLLAMA_MODEL` default, same as everywhere else. If Ollama
is unreachable, both degrade cleanly (a plain "couldn't summarize right now" note, never a
crash, never a fabricated summary).

## Manual test checklist

**Action System**
1. Open Actions (sidebar → Intelligence → Actions). Confirm all 16 actions list with correct
   risk levels and Enabled status.
2. Trigger a low-risk action (e.g. via a future chat integration, or `POST /api/actions/run`) —
   confirm it completes immediately with a clean result.
3. Trigger a medium-risk action — confirm it goes to "Waiting for your approval".
4. Approve it — confirm it actually runs and the result/error is clean.
5. Trigger `delete_archive_data` — confirm it stays pending and, once approved, only ever
   archives (never deletes) the target row.
6. Disable an action's `enabled` flag directly in the DB (or wait for a future toggle UI) and
   confirm it can no longer run.

**Permissions**
1. Open Permissions. Confirm all 18 keys list with descriptions and risk levels.
2. Set `web_search` to Disabled. Confirm `search_web`/the `web_search` tool now returns
   `status="cancelled"`/`"blocked"`.
3. Set `action_create_task` to Allowed (it already is by default) and confirm `create_task`
   still runs directly.
4. Confirm `cloud_api_use` stays Disabled by default — no cloud call should ever be reachable
   through this milestone's new code paths.
5. Confirm "Reset to safe defaults" restores every key without ever *widening* beyond the
   documented safe default.

**Evaluation Lab**
1. Open Evaluation Lab, click "Run evaluation".
2. Confirm a Green/Yellow/Red summary appears with a pass/fail/warning table for all 10 cases.
3. Confirm the "release_status_honesty" case passes (release_testing intent stays capped at
   low confidence) and "cloud_disabled_safe_default" passes.

**Voice**
1. Open chat, click the + menu. If your browser supports Web Speech API and Voice Mode isn't
   "Off" on the Permissions page, confirm "🎤 Voice input" appears.
2. Set Voice Mode to "Off" on the Permissions page, reload, confirm the mic option disappears
   from the + menu (a clean absence, not a broken button).

**Camera**
1. Open chat, click the + menu. Confirm "📷 Camera (not configured yet)" shows, disabled,
   with that exact clean message on hover.

**Knowledge Vault**
1. Create a note, a decision. Confirm both appear with their type badge.
2. Search for a word that appears in one note's title/body — confirm only matching notes show.
3. Archive a note — confirm it disappears from the default list.

**Conversation Auto-Summary**
1. Open any conversation with at least one exchange, click 📝 in the header.
2. Confirm a real title + summary appear (no JSON, no raw prompt text).
3. Click "Save to Knowledge Vault" — confirm a new `summary`-type item appears in the Vault.

**Release Manager**
1. Create a release. Confirm status starts at "draft".
2. Click "Seed standard checklist" — confirm 8 checks appear with their real commands shown.
3. Mark Backend test suite / Backend lint / Frontend build / Frontend typecheck / Manual
   checklist all "Pass" — confirm status becomes "Green" only once every one of those is pass
   (missing any one → stays Yellow; any Fail → Red).
4. Add an artifact path — confirm it's stored and listed.

**Tools**
1. Open Tools. Confirm all 15 tools list, grouped by category, all Enabled.
2. Run a low-risk tool (e.g. `create_task`) via `POST /api/tools/create_task/run` — confirm
   it completes.
3. Run a high-risk tool (`create_release_check`) without `confirm: true` — confirm it comes
   back `status="blocked"` with a clean "requires confirmation" message.

**Existing features (regression)**
1. Chat still works, `via <provider>` metadata line still clean.
2. Atlas, Personality, Local Intelligence Engine settings all still load correctly.
3. No internal debug/JSON/stack-trace text ever appears in any new page's visible UI.

## Known limitations

- **No per-tester scoping anywhere in this milestone** (see "What was intentionally
  excluded") — Actions, Permissions, Evaluation Lab, Knowledge Vault, Release Manager, and
  Tools are all single shared install state, matching this repo's existing no-multi-user-auth
  posture.
- **The Action Center page has no inline "run" button per action.** Actions are meant to be
  triggered by a caller (chat command parser in a future milestone, `POST /api/actions/run`
  directly, or an automation) — the page itself only lists/approves/cancels, matching the
  spec's own explicit UI requirement list.
- **No chat-command-to-action routing yet.** "Create a task called X" doesn't automatically
  invoke the `create_task` action via natural language — the Action System is a real,
  callable capability, but nothing in this milestone wires free-text chat messages to it. The
  pre-existing deterministic command parser (`app/chat_actions.py`, from ECHO Personal OS v1)
  is unchanged and still handles its own narrower set of exact-phrase commands.
- **Release Manager's Green rule requires *every* recorded check on a required platform
  (backend/web/manual) to pass**, not just one per platform — e.g. both "Backend test suite"
  and "Backend lint" must individually be marked pass. This is stricter than a simpler
  "one pass per platform" rule, chosen to match the "never claim Green without full evidence"
  principle this repo already follows elsewhere.
- **Camera is a placeholder only** — no capture, no storage, no vision call. A genuinely
  future milestone's scope.
- **Conversation Auto-Summary's `CONVERSATION_AUTO_SUMMARY_ENABLED`/`_MIN_MESSAGES`/
  `_REQUIRE_APPROVAL` config variables are defined but not yet wired into an automatic
  trigger** — v1 ships the manual "Summarize this conversation" button only; automatic
  summarization on conversation close/after N messages is a follow-up.

## Next safe milestones

- Wire chat-command → Action System routing (e.g. "add a task called X" invoking the real
  `create_task` action through the Permission Center, not just the older exact-phrase parser).
- Automatic conversation summarization using the config variables already defined.
- A "run" affordance directly on the Action Center page for manually testing actions.
- Real camera capture + local/optional-cloud vision analysis, behind the existing
  `camera_input` permission.
- Per-tester scoping for Knowledge Vault/Permissions, if/when the (explicitly out-of-scope-
  for-this-pass) Multi-user Tester System is eventually built.
