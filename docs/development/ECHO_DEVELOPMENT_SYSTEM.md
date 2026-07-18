# Echo Development System

## Purpose

A small set of repository files acts as the shared, durable handoff layer between the user and coding agents (Claude Code, Codex), so scope, context, and verification don't depend on re-explaining a conversation.

## The operating model

```text
The user (task Owner) defines one task
          ↓
tasks/ACTIVE_TASK.md is written or updated to describe it
          ↓
The assigned implementer reads AGENTS.md + its own agent file + tasks/ACTIVE_TASK.md + repository code
          ↓
The implementer implements, tests, and writes the implementation handoff, then stops at Ready for review
          ↓
The assigned reviewer independently verifies from the committed state and writes the reviewer report
          ↓
The user reviews the diff, tests Echo, and decides whether to merge
          ↓
Only the user sets status Completed after merging; the task then moves to tasks/completed/
```

Claude Code and Codex are repository-grounded coding agents; normally one implements while the other independently reviews. `tasks/ACTIVE_TASK.md`, `AGENTS.md`, and this directory store the source of truth — not the chat transcript that produced the task.

## Files and responsibilities

| File | Purpose |
|---|---|
| `AGENTS.md` | Permanent rules every coding agent must follow, higher precedence than any active task |
| `CLAUDE.md` | Claude Code-specific role, coordination, and handoff rules |
| `docs/development/DUAL_AGENT_WORKFLOW.md` | Branch, worktree, ownership, status, and review workflow for Claude Code + Codex |
| `docs/development/DECISIONS.md` | Durable architecture/product decisions |
| `docs/development/PROJECT_CONTEXT.md` | Compact project context for agents |
| `tasks/ACTIVE_TASK.md` | The single canonical task currently loaded for implementation |
| `tasks/TASK_TEMPLATE.md` | Template for drafting future tasks |
| `tasks/active/` | Not-yet-loaded draft/queued tasks |
| `tasks/completed/` | Archived, user-approved-`Completed` task records |
| `.github/ISSUE_TEMPLATE/` | Structured GitHub feature/bug intake |
| `.github/PULL_REQUEST_TEMPLATE.md` | Review and quality checklist |
| `scripts/new-task.ps1` | Creates a task file and loads it as active, with overwrite protection |
| `scripts/complete-task.ps1` | Archives the active task once — and only once — its status is `Completed` |

## Daily workflow

### 1. Write down the outcome first

Describe the feature, trade-offs, UI, and risks in whatever form is convenient, then convert it into the task format below. Keep it to one reviewable milestone with testable acceptance criteria and exact verification commands — avoid vague instructions such as "improve intelligence" or "fix everything."

### 2. Put the result in `tasks/ACTIVE_TASK.md`

Either edit the file directly, or use `scripts/new-task.ps1` to create a task from `tasks/TASK_TEMPLATE.md` and load it immediately. `tasks/active/` is for manually queued drafts; activate one only after confirming `ACTIVE_TASK.md` has no loaded task, then move that draft into the canonical `ACTIVE_TASK.md`. Only one task should be loaded at a time.

### 3. Assign implementer and reviewer

For most Echo tasks:

```text
Implementer: Claude Code
Reviewer: Codex
```

Reverse the roles when Codex is better suited to the implementation for a given task.

### 4. Start the implementer with a small, standard instruction

> Read `AGENTS.md`, your agent file, and `tasks/ACTIVE_TASK.md`. Confirm you're the assigned implementer. Write the implementation map, implement only the approved scope, run every verification command, complete the implementation handoff, and stop at `Ready for review`. Do not begin adjacent work, merge, push, or approve your own implementation.

### 5. Hand off to the reviewer

The implementer commits, records the handoff, and sets status `Ready for review`. The reviewer resolves the clean implementation branch tip after the implementer stops, records it as `Review base commit`, and works from that exact committed state in its own worktree (see `DUAL_AGENT_WORKFLOW.md`). It verifies each acceptance criterion and records the reviewer report, ending in `Verified` or `Changes requested`.

### 6. Review the result yourself

Before merging, verify: acceptance criteria are checked truthfully; tests/build commands actually ran with real output; no unrelated files changed; no paid provider or secret was introduced; product/UI rules were respected; limitations are clearly reported.

### 7. Merge, then archive

Merge yourself, then set the task's status to `Completed` and archive it:

```powershell
./scripts/complete-task.ps1
```

The completed task becomes a permanent record of why the code changed and how it was verified.

## Task sizing rule

A task should normally fit one coherent review. Split work when it spans more than one of: database/schema migration, backend behavior, frontend feature, native packaging, infrastructure/deployment, large test framework addition.

## Branch convention

This repository uses agent-prefixed branch names tied to the task ID:

```text
claude/<task-id>-<short-name>          # implementer branch
codex/<task-id>-<short-name>-review    # reviewer branch, created from the implementer's recorded commit
```

Example: `claude/ECHO-DEV-001-dual-agent` and `codex/ECHO-DEV-001-dual-agent-review`.

## Review severity

- **Blocker:** privacy leak, secret exposure, data loss, paid call without permission, broken local-only mode, fabricated success/source/tool-use.
- **Major:** acceptance criterion missing, regression, no test for changed behavior, broken build — returns the task to `Changes requested`.
- **Minor:** maintainability, naming, documentation, or small UX inconsistency — reviewer may fix directly in a separate commit if clearly in-scope.

Blockers and majors must be resolved before the user merges.

## For the full workflow

See `docs/development/DUAL_AGENT_WORKFLOW.md` for worktree setup, task-status semantics, and review responsibilities.
