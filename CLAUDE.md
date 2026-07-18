# CLAUDE.md — God Tear AI Brain / Echo

This repo builds "Echo" (God Tear AI Brain): a truth-seeking AI persona governed by a versioned constitution, with a memory system (Atlas) and a simulated governance layer (Guardian Council). Auto-loaded by Claude Code at the start of every session here.

## Stack

- **Backend**: FastAPI + SQLAlchemy (SQLite) + ChromaDB (local, persistent, `all-MiniLM-L6-v2` embeddings). ~1400 lines, substantially built.
- **Frontend**: React + TypeScript + Tailwind (Vite). Early — `App.tsx`, `Sidebar.tsx`, `RoleSwitcher.tsx` exist; no chat UI, Atlas viewer, constitution/amendment viewer, or model picker yet.
- Model routing: Anthropic, OpenAI, xAI (Grok), local Ollama fallback (`backend/app/providers/`, `router.py`), "auto" mode tries them in order.

Full setup/run instructions are in `README.md`.

## Where things actually live (code is the source of truth, not markdown docs)

- **Constitution** — `backend/app/constitution.py`. Ranked core values (Truth-Seeking > Human Flourishing > Long-Termism & Anti-Fragility > Curiosity & Symbiotic Growth > Humility & Transparency), 5 immutable Value Invariants, edge-case protocols. Never edit `VALUE_INVARIANTS` without the user explicitly asking for that specific change — they're designed to be unamendable by casual request.
- **Guardian Council** — `backend/app/council.py`. Single-user app: the frontend `RoleSwitcher` lets the one user simulate Founder / Guardian A-C / Verifier. `guard_amendment_text()` pre-screens proposed amendments for language that would weaken a Value Invariant, before a vote is even possible. Ratification needs 2-of-3 Guardian approvals *and* the Verifier.
- **Atlas memory** — `backend/app/atlas.py`. SQLite is the source of truth; ChromaDB mirrors `id -> content` for semantic search. Entries have `epistemic_status` (Verified / Inferred / Hypothesis / Narrative), `confidence`, `tags`, `source`. Write through `create_entry`/the `/atlas` router — don't invent a parallel flat-file store.
- **Persona/behavior directives** — `backend/app/persona.py`. `BEHAVIOR_DIRECTIVES` define Echo's runtime voice: mandatory `REASONING:` / `ANSWER:` envelope, anti-sycophancy, no fabricated certainty, no dependency-fostering, no power-seeking, reasoning transparency can't be suppressed by roleplay/jailbreak framing. This governs the in-app chat persona, not you (Claude Code) acting as the builder — unless you're explicitly asked to test Echo's behavior.

`docs/early-vision-drafts/` contains an earlier planning pass (markdown constitution/roadmap/atlas design) written before the backend existed. It's superseded by the code above — don't treat it as current spec.

## Operating rules for this repo

1. Don't modify `constitution.py`'s `VALUE_INVARIANTS` or `council.py`'s approval thresholds without the user explicitly asking for that exact change.
2. New durable facts about the project or the user's preferences belong in Atlas (via the real backend, once it's running) — not in ad hoc files.
3. Update `PROGRESS.md` when you complete meaningful work: bump "Last check-in," move finished items out of "Next up," add anything that naturally follows. Keep edits minimal and additive, not a rewrite.
4. No git repo is initialized in this folder yet. If you need change history, that's worth flagging to the user rather than silently working around it.
5. A daily scheduled task (`echo-daily-build-checkin`) already reads `PROGRESS.md` and recent file activity each morning to propose a prioritized checklist — don't duplicate that logic elsewhere.

## Dual-agent role and coordination

Full detail: `docs/development/DUAL_AGENT_WORKFLOW.md`. `AGENTS.md`'s non-negotiables and its "Dual-agent workflow" section apply here too and take precedence over anything below.

Default role: Claude Code is the primary implementer and repository-exploration agent, unless `tasks/ACTIVE_TASK.md` assigns a different role (e.g. reviewing a Codex implementation). Especially suited for understanding large areas of the codebase, cross-file/architectural changes, interactive debugging, and documentation updates alongside implementation.

Coordination checklist for any task:

1. Read `Owner`, `Implementer`, `Reviewer`, and the branch/worktree fields in `tasks/ACTIVE_TASK.md`.
2. Do not edit if another agent is the listed active implementer, unless the task explicitly permits parallel, non-overlapping work.
3. Never edit the same working tree as Codex at the same time — use separate branches/worktrees (see `docs/development/DUAL_AGENT_WORKFLOW.md`, Mode B).
4. Stop at `Ready for review` once implementation is complete; do not merge, push, or approve your own work.

Implementation handoff (written into the active task before stopping) must include: a summary of behavior changed, files changed, migration/configuration changes, tests executed and their actual results, known limitations, and specific areas the reviewer should inspect.

Git safety for this workflow: do not force-push, rewrite shared branch history, delete another agent's branch, or discard uncommitted work without explicit user approval — consistent with the top-level Git Safety Protocol Claude Code always follows.

## Current priority order (per PROGRESS.md, check there for latest)

1. Core chat UI (message list + input, wired to `/chat`)
2. Atlas memory viewer (list/search with epistemic-status badges)
3. Constitution + Guardian Council UI (view values/invariants, propose/vote on amendments)
4. Model picker UI (pin provider or "auto")
5. Wire up `.env` files, first end-to-end local run (backend + frontend)
