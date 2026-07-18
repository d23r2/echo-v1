# Architecture and Product Decisions

Record only decisions that should survive beyond one task. New entries are append-only; supersede an old decision with a new entry rather than silently rewriting history.

## ADR-001 — Atlas's internal mechanics stay silent; Echo's own reasoning stays visible

**Status:** Accepted

Atlas (`backend/app/atlas.py`) performs memory storage, retrieval, and context selection. Its internal mechanics — retrieval/ranking details, raw memory counts, vector similarity scores — are not rendered in the UI by default.

This is a distinct concern from Echo's own response format: `backend/app/persona.py`'s `BEHAVIOR_DIRECTIVES` require a visible `REASONING:` / `ANSWER:` envelope on every reply. That `REASONING:` text is a concise, user-facing rationale, not hidden chain-of-thought, and it must not be suppressed or described as "hidden" by any documentation, prompt, or roleplay/jailbreak framing. Do not conflate "Atlas stays silent internally" with "Echo hides its reasoning" — the two are not the same rule.

## ADR-002 — Local-first and no silent paid fallback

**Status:** Accepted

Echo must remain useful with local Ollama and no paid API key. Any paid/cloud provider request requires explicit configuration and must never be triggered silently from local-only mode.

## ADR-003 — The repository is the agent handoff layer

**Status:** Accepted

Work is coordinated through `AGENTS.md`, `CLAUDE.md`, `tasks/ACTIVE_TASK.md`, this decision record, Git commits/branches, and (once opened) pull request review — not through a live chat transcript. The task's `Owner` defines and approves each task's scope regardless of what planning process produced it; Claude Code and Codex are repository-grounded implementer/reviewer agents, not the source of task scope.

## ADR-004 — One active implementation task at a time

**Status:** Accepted

Only one task is loaded in `tasks/ACTIVE_TASK.md` at a time; it is the single canonical record of what is currently being implemented. Larger initiatives are split into independently testable milestones and queued as drafts under `tasks/active/` until loaded. See `docs/development/DUAL_AGENT_WORKFLOW.md` for the full lifecycle and status semantics.
