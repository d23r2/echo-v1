# [TASK-ID] Task title

Status: **Draft**
Task ID: `TASK-ID`
Owner: `User`
Implementer: `Unassigned`
Reviewer: `Unassigned`
Base branch: `master`
Base commit: `Pending`
Implementation branch: `Not created`
Implementation worktree: `Not created`
Implementation commit: `Pending`
Review branch: `Not created`
Review worktree: `Not created`
Review commit: `Pending`

## Objective

One paragraph describing the engineering objective.

## User outcome

A concrete example of what changes for the user.

## Scope

### In scope

- Specific change 1
- Specific change 2

### Out of scope

- Adjacent feature 1
- Unrelated refactor 2

## Required context

- `AGENTS.md`
- `path/to/relevant/file`

## Acceptance criteria

- [ ] Criterion is observable and testable.
- [ ] Error/failure state is specified.
- [ ] Existing behavior remains intact where required.
- [ ] Automated tests cover the change, where practical.
- [ ] Documentation/config examples are updated when needed.

## Verification commands

```bash
# Exact commands the agent must run.
```

## Risks and safeguards

- Risk and required mitigation.

## Allowed paths

- List every file/directory this task may touch. The implementer and reviewer both check the diff against this list.

## Agent implementation notes

The assigned implementer writes the implementation map here before editing any other file.

## Implementation handoff

Pending. The implementer records: summary of behavior changed, files changed, migrations/configuration changes, tests executed and results, known limitations, and specific areas the reviewer should inspect — then sets Status to `Ready for review`.

## Reviewer report

Pending. The assigned reviewer independently checks the diff, every acceptance criterion, tests actually run, regressions, and privacy/cost/local-only rules — then sets Status to `Verified` (reviewer-approved, awaiting the user) or `Changes requested`. Only the user sets Status to `Completed`, after merging.
