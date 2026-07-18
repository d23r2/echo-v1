# Queued tasks

This directory holds **draft/queued tasks that are not yet loaded** — proposals drafted from `tasks/TASK_TEMPLATE.md` before they become the active task.

`tasks/ACTIVE_TASK.md` is the single canonical record of whatever task is currently loaded for implementation. To avoid two copies of the same task silently drifting apart:

- A file here represents a task that has **not** started yet.
- `scripts/new-task.ps1` loads a drafted file by **moving** it into `tasks/ACTIVE_TASK.md` — it does not leave a duplicate behind here.
- Once a task is loaded, this directory should not contain another copy of it. If you find one, that's stale — resolve which is authoritative before continuing (see the conflict protocol in `docs/development/DUAL_AGENT_WORKFLOW.md`).

This directory is otherwise empty by convention.
