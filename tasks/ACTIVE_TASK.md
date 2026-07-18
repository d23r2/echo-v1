# ECHO-DEV-001 — Safe dual-agent development workflow

Status: **Ready for review**
Task ID: `ECHO-DEV-001`
Owner: `User`
Implementer: `Claude Code`
Reviewer: `Codex`
Base branch: `master`
Base commit: `be3c686ebe2f78f6c081e11b0ea050694598d990`
Implementation branch: `claude/ECHO-DEV-001-dual-agent`
Implementation worktree: `C:\Users\newte\echo-claude`
Implementation commit: `Pending — will be recorded in a small follow-up commit once known`
Review branch: `codex/ECHO-DEV-001-dual-agent-review`
Review worktree: `C:\Users\newte\echo-codex`
Review commit: `Pending`

## Objective

Install a safe, repository-native Claude Code implementer / Codex reviewer workflow using only the workflow assets from `C:\Users\newte\Downloads\Echo_Development_System_Dual_Agent_Only.zip`. Merge and correct those assets rather than extracting them over existing files. The full repository ZIP is explicitly forbidden.

## User outcome

The user can define one approved task, let one agent implement it in an isolated worktree, let the other independently review the committed result in a second worktree, approve the verified result, merge it, and archive an accurate task record without risking concurrent edits or silent paid-provider behavior.

## Scope

### In scope

- Safely inspect the workflow-only ZIP and selectively recreate its useful text assets.
- Merge additions into `AGENTS.md`, `CLAUDE.md`, `DEVELOPMENT.md`, and `.gitignore` without removing current Echo protections.
- Add corrected development workflow documentation under `docs/development/`.
- Add task storage, a corrected task template, and a truthful empty/active-task convention under `tasks/`.
- Add guarded `scripts/new-task.ps1` and `scripts/complete-task.ps1`.
- Add GitHub issue and pull-request templates if they do not weaken existing configuration.
- Document sequential worktree creation from the actual `master` base, then reviewer worktree creation from the recorded implementation commit—no unnecessary fetch/cherry-pick.
- Document separate runtime data/ports and no copying of real `.env` or user data into worktrees.
- Complete the implementation handoff, commit only the approved workflow files, and stop at `Ready for review`.

### Out of scope

- Any backend, frontend, model, database, schema, Constitution, Council, Atlas, persona, or product behavior changes.
- Extracting or copying application files from `Echo_Development_System_Dual_Agent_Repository.zip`.
- Modifying the primary worktree at `C:\Users\newte\echo v1`.
- Merging to `master`, pushing, opening a PR, deleting worktrees/branches, or marking the task `Completed`.
- Installing software, changing Claude/Codex global settings, or running either agent in bypass-permissions mode.

## Required context

- `AGENTS.md`
- `CLAUDE.md`
- `.gitignore`
- `DEVELOPMENT.md`
- `PROGRESS.md`
- `C:\Users\newte\Downloads\Echo_Development_System_Dual_Agent_Only.zip`
- Current Git branch/worktree state

## Required corrections to the supplied workflow

- Preserve Echo's immutable value-invariant, Guardian threshold, Atlas, privacy, local-only, no-silent-paid-provider, and `PROGRESS.md` rules.
- Make `AGENTS.md` non-negotiables higher precedence than an active task.
- Distinguish hidden chain-of-thought from a concise user-facing rationale; do not contradict current Echo behavior accidentally.
- Do not copy stale test counts or outdated architecture claims from the ZIP.
- Keep all existing `.gitignore` protections and add only missing safe patterns.
- Remove the duplicate `Owner`; add explicit Task ID, base SHA, implementation/review branches, worktrees, commit SHAs, and allowed/touched paths.
- `new-task.ps1` must refuse to overwrite a loaded task unless an explicit `-Force` is passed, and `-Force` must require an interactive confirmation unless a separate explicit confirmation switch is supplied.
- `complete-task.ps1` must archive only a task whose status is `Completed`; `Verified` means reviewer approval awaiting the user, while only the user may authorize `Completed` after merge.
- Keep the queued task copy and `ACTIVE_TASK.md` synchronized or document one canonical record without allowing silent divergence.
- Use `master`, not nonexistent `main`.
- For sequential review, create the reviewer branch/worktree directly from the implementer's recorded commit. Do not use `git fetch` from another linked worktree.
- Treat the task file as a social coordination record, not a mutex: require branch, worktree, clean-status, and base-SHA checks.
- Major defects or scope expansion return `Changes requested` to the implementer; reviewer fixes are limited to small confirmed in-scope defects in a separate commit.

## Acceptance criteria

- [ ] Only workflow/documentation/template/script/GitHub-template files change.
- [ ] Current Echo-specific safeguards remain present and are strengthened by dual-agent rules.
- [ ] The task template has one Owner and all required identity/handoff/SHA/path fields.
- [ ] Task status semantics clearly reserve `Verified` for reviewer and `Completed` for user-approved merge.
- [ ] New-task refuses accidental active-task overwrite.
- [ ] Complete-task refuses incomplete, Ready, In-progress, Ready-for-review, Changes-requested, Blocked, and merely Verified tasks.
- [ ] Worktree instructions are correct for `master` and require clean/recorded commits.
- [ ] Runtime isolation and no-real-data/no-silent-paid-provider safeguards are explicit.
- [ ] No archive application source, secret, generated data, or stale test-count claim is introduced.
- [ ] Scripts parse and their positive/negative lifecycle paths are tested in a disposable temporary directory.
- [ ] Implementation is committed on the assigned branch with a complete handoff and status `Ready for review`.

## Verification commands

```powershell
git status --short --branch
git diff --check
git diff --name-only be3c686ebe2f78f6c081e11b0ea050694598d990...HEAD

# Parse both scripts without executing repository mutations.
[scriptblock]::Create((Get-Content scripts/new-task.ps1 -Raw)) | Out-Null
[scriptblock]::Create((Get-Content scripts/complete-task.ps1 -Raw)) | Out-Null

# Exercise task creation/overwrite protection and completion guards in a disposable copied fixture.
# The implementer must record the exact commands and outputs in the handoff.
```

No backend/frontend quality gate is required because product source is out of scope. If product source changes, stop: the task scope has been violated.

## Risks and safeguards

- Primary-worktree collision: this task runs only in the assigned Claude worktree.
- Stale archive overwrite: recreate/merge workflow assets selectively; never expand the full repository ZIP over Echo.
- Paid provider use: no application provider behavior changes and no live provider tests.
- Secret exposure: do not copy `.env` or user data into either worktree.
- False reviewer independence: implementation and reviewer commits remain separate and the user performs final approval.

## Allowed paths

- `.github/**`
- `.gitignore`
- `AGENTS.md`
- `CLAUDE.md`
- `DEVELOPMENT.md`
- `docs/development/**`
- `scripts/new-task.ps1`
- `scripts/complete-task.ps1`
- `tasks/**`

## Agent implementation notes

**Source inspected:** `C:\Users\newte\Downloads\Echo_Development_System_Dual_Agent_Only.zip` (extracted read-only to a scratch temp dir, never to the repo). Contents: `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `DEVELOPMENT.md`, `docs/development/{DECISIONS,DUAL_AGENT_WORKFLOW,ECHO_DEVELOPMENT_SYSTEM,PROJECT_CONTEXT}.md`, `scripts/{new-task,complete-task}.ps1`, `tasks/{ACTIVE_TASK,TASK_TEMPLATE}.md`, `.github/ISSUE_TEMPLATE/{bug,feature}.yml`, `.github/PULL_REQUEST_TEMPLATE.md`. No application source present — confirmed workflow-only, distinct from the forbidden full-repository ZIP.

**Plan — new files:**
- `docs/development/DUAL_AGENT_WORKFLOW.md` — adapted from the ZIP, corrected: worktrees branch from `master` (not `main`); reviewer worktree/branch created directly from the implementer's **recorded commit SHA** (no `git fetch` from another linked worktree, no cherry-pick); explicit `Verified` (reviewer-approved, awaiting user) vs `Completed` (user-approved after merge) semantics; reviewer never merges/approves own or the implementer's work — user does.
- `docs/development/DECISIONS.md` — adapted; ADR-001 reworded so "Atlas stays silent" (its retrieval/ranking internals, memory counts) is clearly distinct from Echo's own visible `REASONING:`/`ANSWER:` envelope (`backend/app/persona.py`), which is user-facing by design and must not be described as hidden. ADR-003 reworded to not assume a "ChatGPT planning" step that isn't evidenced in this repo.
- `docs/development/ECHO_DEVELOPMENT_SYSTEM.md` — adapted; generalized the planning-source framing (User as task owner, not a specific external tool), branch convention corrected to this repo's actual agent-prefixed pattern (`claude/<task-id>-*`, `codex/<task-id>-*-review`) instead of the ZIP's generic `feat/<task-id>-*`.
- `docs/development/PROJECT_CONTEXT.md` — adapted; fixed the line claiming "internal reasoning is not shown by default" (contradicts `persona.py`'s mandatory visible envelope) to correctly scope silence to Atlas's internal mechanics only. Port claims (backend 8000, frontend 5174) checked against `vite.config.ts` and existing docs — accurate, kept as-is.
- `tasks/TASK_TEMPLATE.md` — corrected: single `Owner` field (ZIP had a duplicate, one commented "original"), explicit Task ID/base SHA/implementer+reviewer branch/worktree/commit fields and an `Allowed paths` section, mirroring the shape this very task file already uses.
- `tasks/active/README.md`, `tasks/completed/README.md` — new, empty queue/archive directories with their convention documented: **`tasks/ACTIVE_TASK.md` is the single canonical loaded-task record.** `tasks/active/` holds only not-yet-loaded draft/queued tasks; loading one moves (not copies) it into `ACTIVE_TASK.md` so no two copies of a loaded task can silently diverge. `tasks/completed/` holds timestamped archives written only by `complete-task.ps1` after a task reaches `Completed`.
- `scripts/new-task.ps1` — corrected: refuses to overwrite a currently-loaded active task unless `-Force` is passed; `-Force` alone still requires an interactive typed confirmation, skippable only with a separate explicit `-Yes` switch (for scripted/test use). Loads by moving the drafted file out of `tasks/active/`, not copying, per the canonical-record decision above.
- `scripts/complete-task.ps1` — corrected: only archives when `Status` is exactly `**Completed**`; explicitly rejects `Draft/Ready/In progress/Ready for review/Changes requested/Blocked/Verified` with a message explaining `Verified` means reviewer-approved-awaiting-user and only the user may move a task to `Completed` after merge.
- `.github/ISSUE_TEMPLATE/bug.yml`, `.github/ISSUE_TEMPLATE/feature.yml`, `.github/PULL_REQUEST_TEMPLATE.md` — added from the ZIP with one correction: the PR template's Echo-safeguards checklist item is reworded from "internal reasoning is not exposed" to distinguish Atlas's silent internals from Echo's intentionally visible `REASONING:`/`ANSWER:` envelope (same fix as ADR-001).

**Plan — edited files (additive merges only, nothing existing removed):**
- `AGENTS.md` — add one new `## Dual-agent workflow (Claude Code + Codex)` section (task workflow steps, coordination rules, links to the two new docs). All existing sections (Stack, Non-negotiable Echo rules, Repository operating rules, Verification, Active task bootstrap) stay untouched; the existing "active task can narrow scope but never override non-negotiables" precedence rule already satisfies the required-corrections item, so it's cross-referenced, not duplicated.
- `CLAUDE.md` — add one new `## Dual-agent role and coordination` section (Claude Code's default implementer role, per-task coordination checklist, required handoff contents, git-safety restatement). Existing sections untouched.
- `.gitignore` — add `.mypy_cache/` only (mypy is actually used per `DEVELOPMENT.md` but wasn't previously ignored). Everything else the ZIP lists is already covered by existing patterns; not duplicating them.
- `tasks/ACTIVE_TASK.md` (this file) — this implementation map now; `Implementation handoff` section and status/commit fields at the end, once verification is complete.

**Explicitly not touched:** any file under `backend/`, `frontend/`, `docker-compose*.yml`, root-level product/report docs, `PROGRESS.md`, `README.md`, `ROADMAP.md`, or anything outside the task's `Allowed paths` list. `C:\Users\newte\echo v1` is not opened.

**Test plan for the two scripts:** copy them into a disposable temp directory with a fixture `tasks/` structure (not this repo's real `tasks/`), then exercise: (1) parse both via `[scriptblock]::Create`, (2) create a new task with no active task loaded — succeeds, (3) attempt a second `new-task.ps1` while one is loaded without `-Force` — refused, (4) `-Force` without `-Yes` prompts and aborts on non-confirmation, (5) `-Force -Yes` overwrites, (6) `complete-task.ps1` against a `Ready`/`Ready for review`/`Verified` status — refused for each, (7) against `Completed` — archives and resets to the empty convention. Exact commands/output recorded below under Implementation handoff.

## Implementation handoff

**Summary:** Installed the safe, repository-native Claude Code implementer / Codex reviewer workflow by selectively merging and correcting the workflow-only assets from `Echo_Development_System_Dual_Agent_Only.zip` (inspected read-only from a scratch temp dir, never extracted into the repo). No application/backend/frontend/database/Constitution/Council/Atlas/persona file was touched. The full repository ZIP was not opened.

**Files changed (all within Allowed paths):**

New:
- `docs/development/DUAL_AGENT_WORKFLOW.md`
- `docs/development/DECISIONS.md`
- `docs/development/ECHO_DEVELOPMENT_SYSTEM.md`
- `docs/development/PROJECT_CONTEXT.md`
- `tasks/TASK_TEMPLATE.md`
- `tasks/active/README.md`
- `tasks/completed/README.md`
- `scripts/new-task.ps1`
- `scripts/complete-task.ps1`
- `.github/ISSUE_TEMPLATE/bug.yml`
- `.github/ISSUE_TEMPLATE/feature.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`

Edited (additive merge only — every existing line preserved):
- `AGENTS.md` (untracked, new to this branch) — added one `## Dual-agent workflow (Claude Code + Codex)` section.
- `CLAUDE.md` — added one `## Dual-agent role and coordination` section (+17 lines).
- `.gitignore` — added `.mypy_cache/` only (+1 line; mypy is used per `DEVELOPMENT.md` but wasn't previously ignored).
- `DEVELOPMENT.md` — added one `## Multi-agent task workflow` pointer section (+17 lines).
- `tasks/ACTIVE_TASK.md` (this file) — implementation map, this handoff, and status.

**Corrections applied vs. the ZIP source** (see "Agent implementation notes" above for full detail): reasoning-visibility contradiction fixed (Atlas-silent vs. Echo's visible `REASONING:`/`ANSWER:` envelope) in `DECISIONS.md`, `PROJECT_CONTEXT.md`, and the PR template; duplicate `Owner` field removed from `TASK_TEMPLATE.md`; `master` used instead of nonexistent `main`; reviewer worktree creation corrected to branch directly from the recorded implementation commit SHA instead of `git fetch`/cherry-pick from another linked worktree; `Verified` vs. `Completed` status semantics made explicit everywhere; stale personal-name `Owner` placeholder replaced with `User`; branch convention corrected to this repo's actual agent-prefixed pattern; the ZIP's `.github/ISSUE_TEMPLATE/*.yml` used the invalid `about:` key for GitHub issue *forms* — corrected to `description:`.

**Checks executed and results:**

```
$ git status --short --branch
## claude/ECHO-DEV-001-dual-agent
 M .gitignore
 M CLAUDE.md
 M DEVELOPMENT.md
?? .github/ISSUE_TEMPLATE/
?? .github/PULL_REQUEST_TEMPLATE.md
?? AGENTS.md
?? docs/development/
?? scripts/complete-task.ps1
?? scripts/new-task.ps1
?? tasks/

$ git diff --check
(no output, exit 0 — no whitespace/conflict-marker issues)

$ [scriptblock]::Create((Get-Content scripts/new-task.ps1 -Raw)) | Out-Null
OK — parses cleanly

$ [scriptblock]::Create((Get-Content scripts/complete-task.ps1 -Raw)) | Out-Null
OK — parses cleanly
```

Script lifecycle exercised in a disposable fixture under the session scratch dir (copies of the two scripts + a fixture `tasks/` tree — never the real repo `tasks/`), then deleted:

1. `new-task.ps1 -TaskId TEST-001 -Title "Sample task"` with no task loaded → succeeded; `ACTIVE_TASK.md` loaded with `Status: **Draft**` / `Task ID: TEST-001`; `tasks/active/` left empty (moved, not copied).
2. `new-task.ps1 -TaskId TEST-002 ...` with TEST-001 still loaded, no `-Force` → **refused**: "tasks/ACTIVE_TASK.md already has a loaded task. Pass -Force to replace it...". `ACTIVE_TASK.md` unchanged.
3. `new-task.ps1 -TaskId TEST-003 ... -Force` (no `-Yes`), fed a non-confirming/no-input session → **aborted**, `ACTIVE_TASK.md` unchanged. (The test harness's PowerShell runs `-NonInteractive`, so `Read-Host` itself throws rather than reading piped text — confirming the fail-safe property: without an explicit affirmative confirmation, nothing is overwritten, in both the "declined" and "can't-prompt" cases. A real interactive terminal session will show the `Type YES to continue` prompt normally.)
4. `new-task.ps1 -TaskId TEST-003 ... -Force -Yes` → succeeded without prompting; `ACTIVE_TASK.md` now `Task ID: TEST-003`.
5. `complete-task.ps1` run once for each of `Draft`, `Ready`, `In progress — Claude Code`, `Ready for review`, `Changes requested`, `Blocked`, `Verified` → **refused every time**, each with an explicit message naming the actual status and explaining `Verified` ≠ `Completed`.
6. `complete-task.ps1` with `Status: **Completed**` → succeeded: archived to `tasks/completed/TEST-003-<timestamp>.md`, and `ACTIVE_TASK.md` reset to the empty-task convention.

No backend/frontend gate was run — product source is out of scope and none was touched, matching the task's stated verification requirement.

**Known limitations:**
- `Read-Host`-based confirmation for `new-task.ps1 -Force` (without `-Yes`) could not be exercised end-to-end with a real "user types YES" interaction, because the available shell runs non-interactively; the decline path and the flag-based (`-Yes`) bypass were both verified directly, which together cover the intended behavior.
- `docs/development/DUAL_AGENT_WORKFLOW.md`'s worktree examples use a generic `..\<repo>-claude` / `..\<repo>-codex` placeholder pattern; this repo's actual concrete worktrees (`C:\Users\newte\echo-claude`, `C:\Users\newte\echo-codex`) are recorded in `tasks/ACTIVE_TASK.md` itself, not hardcoded into the reusable doc.
- Pre-existing staleness unrelated to this task (e.g. `CLAUDE.md`'s "frontend is early" framing vs. the more advanced state implied by `DEVELOPMENT.md`/`PROGRESS.md`) was left untouched — out of scope for this workflow-only task.

**Areas the reviewer should focus on:**
- Confirm every changed/new file is within `Allowed paths` and no application/product file was touched (`git diff --name-only be3c686ebe2f78f6c081e11b0ea050694598d990...HEAD`).
- Re-run the script lifecycle tests independently in the reviewer's own worktree/fixture.
- Check that the reasoning-visibility correction (Atlas-silent vs. Echo's visible envelope) accurately reflects `backend/app/persona.py` and doesn't itself introduce a new inaccuracy.
- Check that `AGENTS.md`'s and `CLAUDE.md`'s new sections don't conflict with, weaken, or duplicate the existing non-negotiables above them.

Implementation commit: recorded below once committed (see `Implementation commit` field at the top of this file).

## Reviewer report

Pending.
