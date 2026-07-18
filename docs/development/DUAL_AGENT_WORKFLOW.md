# Claude Code + Codex Dual-Agent Workflow

## Recommended division of work

The safe pattern here is **sequential collaboration in separate worktrees**, not simultaneous editing of the same working tree.

```text
User defines one task in tasks/ACTIVE_TASK.md
      ↓
Claude Code implements in its own worktree/branch
      ↓
Claude Code commits, records the handoff, sets status Ready for review
      ↓
Codex reviews independently in its own worktree/branch, from that recorded commit
      ↓
Codex records the reviewer report, sets status Verified (or Changes requested)
      ↓
User reviews, merges, and only the user sets status Completed
```

### Claude Code

Best used as:

- primary implementer;
- repository explorer;
- architectural / cross-file change agent;
- interactive debugger;
- documentation updater alongside implementation.

### Codex

Best used as:

- independent reviewer;
- test and regression specialist;
- focused bug fixer for small confirmed defects found in review;
- acceptance-criteria verifier;
- second implementation agent for a separate, non-overlapping task.

Roles can be reversed per task — `tasks/ACTIVE_TASK.md`'s `Implementer`/`Reviewer` fields are authoritative for that task.

## Golden rule

**Never run Claude Code and Codex against the same working tree at the same time.** Use sequential handoffs with separate Git worktrees, one per agent.

## Mode A — Simple sequential workflow (single worktree)

Use this only when one agent works at a time and the other reviews after a commit lands, without needing its own checked-out copy.

1. Load one task into `tasks/ACTIVE_TASK.md` (directly, or via `scripts/new-task.ps1`).
2. Set `Implementer` and `Reviewer`.
3. Ask the implementer: read `AGENTS.md`, its own agent file (`CLAUDE.md` for Claude Code), and `tasks/ACTIVE_TASK.md`; write the implementation map; implement only the approved scope; run every verification command; complete the implementation handoff; stop at `Ready for review`.
4. Review and commit the implementer's changes.
5. Ask the reviewer to read `AGENTS.md` and `tasks/ACTIVE_TASK.md`, verify every acceptance criterion against the committed diff, run the verification commands, fix only small confirmed in-scope defects in a separate commit, and complete the reviewer report.
6. The user reviews the result, merges, and — only after merging — sets the task status to `Completed`.

## Mode B — Separate worktrees (recommended for anything non-trivial)

Create the implementer's worktree from the actual base branch (`master`):

```powershell
git worktree add ..\<repo>-claude -b claude/<task-id>-<short-name> master
```

Claude Code implements and commits inside `..\<repo>-claude`. Record the exact implementation commit SHA in `tasks/ACTIVE_TASK.md`'s `Implementation commit` field before handing off.

Create the reviewer's worktree **directly from that recorded commit** — not from `master`, and not via `git fetch` pointed at the implementer's linked worktree:

```powershell
git worktree add ..\<repo>-codex -b codex/<task-id>-<short-name>-review <IMPLEMENTATION_COMMIT_SHA>
```

This gives the reviewer the exact implementer state with no fetch/cherry-pick step and no risk of picking up the implementer's uncommitted changes. The reviewer commits any small fixes on top of that branch and records the review commit SHA.

Do not delete either worktree or branch, and do not merge, until the user has reviewed and approved the result.

## Mode C — Parallel tasks

Parallel work is safe only when tasks are clearly separated. Each parallel task must have:

- a different task ID;
- a different branch/worktree per agent;
- non-overlapping primary files (an explicit `Allowed paths` list per task, checked before starting);
- separate acceptance criteria;
- an explicit integration order decided by the user before either agent starts.

Do not parallelize database migrations, shared schemas, central routing/persona/constitution/council files, or the same UI components without a single planned integration owner.

## Task statuses

Use only these values, in this order of the normal lifecycle:

- `Draft` — not yet approved to implement.
- `Ready` — approved, not yet started.
- `In progress — Claude Code` / `In progress — Codex` — implementer actively working.
- `Ready for review` — implementer stopped; committed; awaiting reviewer.
- `Review in progress` — reviewer actively working.
- `Changes requested` — reviewer found a major defect or scope problem; returns to the implementer.
- `Verified` — reviewer independently confirmed every acceptance criterion; **awaiting the user's merge decision. This is not the same as `Completed`.**
- `Completed` — **the user has merged the change and explicitly authorizes this status.** No agent sets this status itself.
- `Blocked` — cannot proceed; reason recorded in the task file.

## Conflict protocol

When an agent finds unexpected uncommitted changes, a mismatched base commit, or another agent's active worktree:

1. Stop editing.
2. Do not reset, discard, or overwrite anything.
3. Record the affected files/state in the active task.
4. Commit or stash only with the user's explicit approval.
5. Resume only from a clean, correctly-based branch/worktree.

## Review responsibilities

The reviewer independently checks:

- every acceptance criterion, against the actual committed diff (not the implementer's self-report alone);
- architecture/scope boundaries — flag anything outside `Allowed paths`;
- that claimed tests/checks were actually executed, with real output;
- regressions and edge cases;
- secret/privacy exposure (`.env`, databases, user data, hidden chain-of-thought presented as fabricated model internals);
- local-only and no-silent-paid-provider requirements;
- documentation/configuration accuracy.

Major defects or scope expansion return the task to `Changes requested` for the implementer. The reviewer's own fixes are limited to small, confirmed, in-scope defects, committed separately from the implementer's commit. The reviewer does not rewrite the feature to a preferred style, and never merges or approves their own or the implementer's work — that is the user's decision alone.
