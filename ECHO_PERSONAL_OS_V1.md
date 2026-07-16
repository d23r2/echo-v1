# ECHO Personal OS v1

Turns ECHO from a chatbot into a light personal operating system: Mission Control,
Projects, Tasks, a "Continue Where We Left Off" suggestion panel, and a Smart Context
Router that classifies what a chat message is actually asking about. This document
covers what shipped, how it works, what's deliberately left out, and how to verify it
yourself.

## What's in v1

### Mission Control (sidebar, above Chats)

A single dashboard (`GET /api/mission-control`) aggregating:
- **Today** — tasks due today, plus upcoming Schedule reminders.
- **Continue Where We Left Off** — up to 5 suggestions (see below).
- **Active Projects** — projects with `status=active`, most recently touched first.
- **Tasks** — overdue tasks (always shown) and upcoming tasks.
- **Recent Activity** — recent conversations and Library files.
- **System Status** — whether Ollama, Wiki, RSS, SearXNG, image generation, Library, and
  Schedule are currently available.

Each section is queried independently server-side. If one section's query fails, that
section comes back empty and a short, clean message is appended to a `warnings` array —
the rest of the dashboard still renders. No raw exception text ever reaches the response.

### Projects (sidebar)

A durable body of ongoing work: title, description, status (`active` / `paused` /
`completed` / `archived`), priority (`low` / `medium` / `high`), category, tags. Full CRUD
at `/api/projects`. **Deleting a project archives it — it is never hard-deleted.** A
project's detail view lists its linked tasks and lets you add a task directly from there.

### Tasks (sidebar)

A single actionable item, optionally linked to a project: title, description, status
(`todo` / `in_progress` / `blocked` / `done` / `cancelled`), priority, due date. Full CRUD
at `/api/tasks`, with filters for status, project, and due-date range. **Deleting a task
cancels it — it is never hard-deleted**; a completed or cancelled task stays visible when
you filter to see it, it just drops off the default "active" view. A task can be created
with no project at all — projects are optional, not required.

### Continue Where We Left Off

Part of the Mission Control response (`continue_where_left_off`, up to 5 items). Built
only from data ECHO actually has — no fabricated facts. Priority order: overdue tasks
first, then in-progress tasks, then recently-touched active projects, then the most
recent conversation, then the next upcoming Schedule item. If there's nothing yet, the
frontend shows "No active work yet. Create a project or task to begin." instead of an
empty, unexplained list.

### Smart Context Router (`backend/app/services/context_router.py`)

A deterministic, regex-only classifier (same style as `app/search_intent.py` — no model
call) that looks at a chat message and decides which context source(s) are relevant:
`normal_chat`, `atlas_memory`, `previous_conversation`, `library`, `schedule`,
`projects`, `tasks`, `wiki`, `rss`, `web_search`, `code_project_files`. For example:
"What did we decide about SearXNG?" routes to `atlas_memory` + `previous_conversation`
(never wiki/web); "What tasks are due today?" routes to `tasks` + `schedule`; "Continue
where we left off" routes broadly across `projects` + `tasks` + `previous_conversation` +
`schedule` + `library`.

**v1 scope note**: the router currently classifies and returns routing metadata
(`selected_sources`, `reason`, `confidence`, and per-source `should_search_*` flags) — it
is tested directly (`tests/test_context_router.py`) but is **not yet wired into the live
chat pipeline's actual source-fetching**. Integrating it into `POST /api/chat[/stream]`
was judged the riskier path for a v1 pass (that pipeline already has its own working
current-info/wiki/web routing via `search_intent.py`), so per this milestone's own
fallback instruction, the router ships as a tested, standalone service now, with live
chat integration as a follow-up.

### Chat commands (`backend/app/chat_actions.py`)

A small, deterministic set of exact-match commands that bypass the model entirely —
tried before normal chat, on both `POST /api/chat` and `POST /api/chat/stream`:

| Say this | ECHO does this |
|---|---|
| `Create a project called Kitchen Remodel` | Creates a project. |
| `Add a task to test Android APK tomorrow` | Creates a standalone task. |
| `add a task to Website Redesign called Pick a font` | Creates a task under the named project (reports back cleanly if that project doesn't exist — never guesses or auto-creates it). |
| `mark task Buy groceries done` | Completes the task, only if exactly one open task matches that title (ambiguous or missing matches are reported, not guessed). |
| `show my tasks today` / `what tasks are due today?` | Lists today's tasks. |
| `show active projects` / `what projects are active?` | Lists active projects. |
| `continue where we left off` | Summarizes overdue tasks + active projects. |

Anything that doesn't match one of these patterns exactly falls straight through to
normal chat — unchanged. A matched command never calls a model provider; the reply is
persisted like any other chat turn (`provider_used: "system"`), so it survives reload
and shows up in conversation history and search like normal.

No delete/archive commands are exposed through chat — that stays a UI-only action, per
the "ask confirmation before anything destructive" rule. Keeping the command set this
small sidesteps that question entirely for v1 rather than half-building confirmation
flows inside a chat turn.

### Atlas memory linking (Phase 10)

Creating a project queues a **pending** `MemoryCandidate` ("Started a project: X") for
the existing Atlas review queue — never saved directly, never shown anywhere in the chat
UI or the project-creation response itself. Individual tasks do **not** generate memory
candidates; they're too granular to be worth a review-queue entry each. You'll see these
candidates the same place every other opportunistic memory candidate shows up: the Atlas
review UI.

## Out of scope for v1

Per the original spec: no autonomous actions, no sending emails, no paid APIs required,
no complex agent marketplace, no cloud sync, no multi-user accounts, no advanced
analytics/reporting, no full mobile push-notification system, no self-modifying code, no
Ollama fine-tuning, no calendar integration beyond the existing Schedule feature. The
Smart Context Router does not yet drive live chat source-fetching (see above). Tasks
have no drag-and-drop/kanban board — filters and lists only.

## Data model

Two new tables, added via SQLAlchemy's `Base.metadata.create_all()` on startup (which
only creates missing tables — it never touches or alters existing ones, matching how
every other table in this app was added):

- **`projects`** — `id`, `title`, `description`, `status`, `priority`, `category`,
  `tags` (JSON), `last_touched_at`, `created_at`, `updated_at`, `archived_at`. Indexed on
  `status`.
- **`tasks`** — `id`, `title`, `description`, `status`, `priority`, `project_id`
  (nullable FK), `due_at`, `scheduled_item_id`, `source_type`, `source_id`, `tags`
  (JSON), `sort_order`, `created_at`, `updated_at`, `completed_at`. Indexed on `status`,
  `project_id`, `due_at`.

See [DEVELOPMENT.md](DEVELOPMENT.md#how-to-back-up-echo-data-before-upgrading) for how
to back up `backend/data/` before upgrading.

## Manual test checklist

- [ ] Open ECHO — Mission Control loads by default (above Chats in the sidebar).
- [ ] Empty state: on a fresh DB, Mission Control shows "No active work yet..." not a
      blank/broken page.
- [ ] Create a project from the Projects page; confirm it appears in the list and in
      Mission Control's Active Projects.
- [ ] Open the project, add a task from the detail view; confirm it's linked.
- [ ] Mark that task done; confirm it moves into the collapsed "done/cancelled" section.
- [ ] Archive the project (Projects list); confirm it disappears from the active list but
      is still fetchable (soft-archive, not deleted).
- [ ] Create a standalone task (no project) from the Tasks page; confirm it appears with
      no project name shown.
- [ ] Filter Tasks by Today / Overdue / In progress / Done; confirm each filter is
      correct.
- [ ] Cancel a task; confirm it's excluded from the default list but visible when you'd
      filter for it.
- [ ] In chat, type `show my tasks today` — confirm an instant reply with no model
      "thinking" delay and a `via System` (or similarly clean) metadata line, no raw
      debug text.
- [ ] In chat, type `create a project called <X>` — confirm it's created and shows up on
      the Projects page.
- [ ] In chat, type an ordinary question (e.g. "hello") — confirm it still goes through
      normal chat/model flow, unaffected by the command parser.
- [ ] Confirm existing chat, Atlas, Library, Schedule, Wiki/RSS/SearXNG, and image
      generation still all work as before (see [DAILY_SMOKE_TEST.md](DAILY_SMOKE_TEST.md)).

## Known limitations

- Smart Context Router is tested but not yet driving live chat source selection (see
  above) — it's available for a future integration pass or via direct import.
- Chat commands are exact-pattern matches, not general NLU — phrasing has to roughly
  match the patterns in the table above (e.g. "mark X done" needs the literal word
  "task" and an unambiguous title match). This is intentional for v1: a wrong guess on a
  destructive-feeling action (creating or completing something) is worse than a command
  that occasionally doesn't match and just falls through to normal chat.
- No recurring tasks, no subtasks, no kanban/drag-and-drop board.
- No push/OS-level notifications for due tasks — same limitation Schedule already had.
- `scheduled_item_id` on Task exists in the schema for a future Task↔Schedule link but
  isn't populated by anything yet.

## Future improvements

- Wire the Smart Context Router into `POST /api/chat[/stream]` so its routing decisions
  actually drive which sources get fetched for a turn, replacing/augmenting
  `search_intent.py`'s narrower current-info-only classification.
- Let a Task point at a real Schedule item (`scheduled_item_id`) so a due task can also
  produce a reminder.
- Broaden the chat command set once the exact-match set above has been used enough to
  know which phrasings are missing.
- Simple recurring tasks and lightweight subtasks, if real usage shows a need.
