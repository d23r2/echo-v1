# AGENTS.md — God Tear AI Brain / Echo

This repo builds "Echo" (God Tear AI Brain): a truth-seeking AI persona governed by a versioned constitution, with a memory system (Atlas) and a simulated governance layer (Guardian Council).

## Stack

- Backend: FastAPI + SQLAlchemy (SQLite) + ChromaDB.
- Frontend: React + TypeScript + Tailwind (Vite), with native packaging support.
- Model routing: Anthropic, OpenAI, xAI, Gemini, Azure when explicitly configured, and local Ollama fallback.

Full setup/run instructions are in `README.md`. Code is the source of truth when older documentation disagrees.

## Non-negotiable Echo rules

- Never edit `backend/app/constitution.py`'s `VALUE_INVARIANTS` without the user explicitly asking for that exact change.
- Never edit `backend/app/council.py`'s approval thresholds without the user explicitly asking for that exact change.
- Atlas SQLite is the source of truth and Chroma is its semantic mirror. Use the real Atlas service/router; do not invent a parallel memory store.
- Preserve Echo's truth-seeking, anti-sycophancy, uncertainty, no-dependency-fostering, no-power-seeking, and no-fabricated-certainty directives.
- Never introduce or silently call a paid provider. Local Ollama operation and explicit user approval for paid/cloud escalation must remain intact.
- Never expose secrets, `.env` values, local databases, user files, private memories, or hidden chain-of-thought in logs, UI, reports, or commits.
- User-facing rationale may be concise, but do not claim it is hidden/private chain-of-thought.
- Do not change unrelated behavior while implementing a focused task.

## Repository operating rules

1. Read `PROGRESS.md` and relevant current code before acting; early vision drafts are superseded where code exists.
2. New durable facts about the project or user preferences belong in Atlas through the real backend when running, not ad hoc fact files.
3. Update `PROGRESS.md` after meaningful product work, minimally and additively. Workflow-only maintenance should not rewrite product status.
4. Preserve unrelated and concurrent changes. Do not reset, discard, or overwrite them.
5. Never use destructive Git commands or forced pushes without explicit user approval.
6. Do not commit `.env`, databases, Chroma data, model weights, `.venv`, `node_modules`, build output, logs, exports, or private data.

## Dual-agent workflow (Claude Code + Codex)

Full detail: `docs/development/DUAL_AGENT_WORKFLOW.md` (branches, worktrees, task statuses, review responsibilities) and `docs/development/DECISIONS.md` (durable architecture decisions). These non-negotiables always take precedence over the active task, per "Active task bootstrap" below.

Before editing:

1. Read `tasks/ACTIVE_TASK.md` and confirm your assigned role (`Implementer` or `Reviewer`) and branch/worktree.
2. Confirm no other agent is editing the same working tree.
3. Read the files listed under that task's **Required context**.
4. Write a brief implementation map under **Agent implementation notes** before editing any other file.

During implementation:

1. Stay inside the task's **Allowed paths**; stop and flag it if the work would require going outside them.
2. Work in small, reviewable steps; add/update tests with behavior changes.
3. Do not mark an acceptance criterion complete until it is verified with a real command.

Before finishing:

1. Run every verification command in the active task, in addition to the default quality gates below.
2. Record the **Implementation handoff** (or **Reviewer report**) truthfully — only claim a command passed if it actually ran and passed.
3. The implementer stops at `Ready for review`; only the reviewer sets `Verified`/`Changes requested`, and only the user sets `Completed`, after merging. Never approve your own implementation.

## Verification

- Backend: run relevant tests first, then the task's required backend gates.
- Frontend: `npm run build` is the required typecheck/build gate unless the task says otherwise.
- Cross-stack work requires both sets of gates.
- Do not claim a command passed unless it actually ran successfully.

## Active task bootstrap

When a task is loaded, read `tasks/ACTIVE_TASK.md`. The active task may narrow scope but can never override these non-negotiable rules.
