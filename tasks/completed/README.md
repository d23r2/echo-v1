# Completed task archive

This directory holds timestamped archives of tasks written **only** by `scripts/complete-task.ps1`, and only once a task's Status is `Completed`.

`Completed` means the user has already merged the change and explicitly authorized this status — it is not set by either agent, and it is not the same as `Verified` (reviewer-approved, still awaiting the user). See `docs/development/DUAL_AGENT_WORKFLOW.md` for the full status lifecycle.

Each archived file is named `<Task ID>-<yyyyMMdd-HHmmss>.md` and is a permanent record of why the code changed and how it was verified. Do not hand-edit files in this directory.
