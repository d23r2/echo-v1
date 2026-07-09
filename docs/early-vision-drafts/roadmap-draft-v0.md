# God Tear AI Brain — Roadmap

Reality check first: everything described in the original vision (Echo, Atlas, Guardian Council, Multi-Model Brain, multi-device persistence) is buildable by one person on a small budget — but not all at once, and not as one "AI brain" that thinks for itself. What you're actually building at v0/v1 is a **disciplined system of files, prompts, and scheduled jobs** that make Claude behave consistently and remember things across sessions. The "single mind" feeling comes from shared state (memory + persona files), not from a new kind of AI.

Budget assumption: $0–40/mo beyond whatever Claude plan you already have. That's enough for everything through v2.

## v0 — Seed (buildable now, days not months)

Goal: Claude Code and Cowork both behave as "Echo," both read/write the same memory, and there's a written Constitution governing changes. No new infrastructure — just a git repo.

- `CLAUDE.md` — the Echo persona and operating rules, auto-loaded by Claude Code every session.
- `constitution.md` — the 5 core values, formalized, with an amendment process.
- `atlas.json` — flat-file memory store with epistemic-status tags (Verified / Inferred / Hypothesis / Narrative).
- A Cowork scheduled task ("Atlas consolidation") that runs daily or weekly: reads recent notes/conversation, extracts durable facts, appends them to `atlas.json` with proper tags, commits to git.
- Guardian Council v0 = you. No constitution change happens without your explicit approval — git commit history is the audit log. This is the cheapest possible safeguard against value drift and it's a real one.

Cost: $0. Tools: git (free), Claude Code, Cowork scheduled tasks.

## v1 — Usable memory (weeks)

Goal: Atlas becomes actually searchable, not just a growing JSON file.

- Add semantic search over `atlas.json` using **local embeddings** (e.g. `sentence-transformers` running on your own machine/sandbox) + a local vector index (FAISS or even brute-force cosine similarity for a memory store this size — it stays fast into the tens of thousands of entries). This costs nothing; no hosted vector DB needed yet.
- Migrate `atlas.json` to SQLite once it gets unwieldy as a single file (still $0, still portable, still git-friendly if you're careful about binary diffs — or keep JSON and just index it separately).
- Tighten the consolidation job: dedupe, flag contradictions between entries, let epistemic status decay or get promoted (Hypothesis → Verified) as evidence accumulates.
- Write a short eval script: sample N memory entries, sanity-check tagging quality by hand periodically. This is where "truth-seeking" becomes a practice, not a slogan.

Cost: still ~$0, maybe a few dollars if you use a hosted embedding API instead of local.

## v2 — Multi-device, real persistence (budget: fits in $40/mo)

Goal: the thing survives outside your dev machine and syncs across devices in something closer to real time.

- Minimal hosted backend: Supabase or Neon free tier (Postgres) for the Atlas store, or a $5–7/mo VPS if you want full control. Free tier is enough for a single user for a long time.
- A thin API layer in front of Atlas so any client (Claude Code, Cowork, a future mobile client) reads/writes the same remote store instead of relying on git sync.
- Guardian Council v1: formalize as a lightweight review step — constitution changes go through a PR you have to explicitly merge, with a changelog. Still just you, but now it's process, not memory.
- Start tracking cost per query/session so scaling decisions are based on real numbers, not guesses.

Cost: $0–40/mo depending on hosting choice.

## v3+ — Multi-Model Brain, wider governance (later, cost scales with ambition)

Only worth doing once v0–v2 are solid and you actually feel the limits of single-model Claude for specific tasks.

- Route specific task types to other models via something like OpenRouter (pay-per-use, no subscription) — e.g. a cheaper/faster model for routine memory tagging, Claude for anything touching the Constitution or user-facing conversation.
- If/when there's more than one person involved (co-founder, testers), the Guardian Council becomes an actual multi-party process instead of a single approver.
- Mobile/web front-end becomes worth building once the backend from v2 is proven.

## What to explicitly *not* build yet

- No autonomous self-modification of the Constitution or persona — ever, without your sign-off. This isn't just a cost-saving shortcut; it's the actual safeguard against value drift the original vision asks for.
- No custom model training/fine-tuning. Not needed for anything in this roadmap and it's expensive.
- No elaborate governance UI. A CHANGELOG and git history covers "Guardian Council" until there's more than one human involved.

## Immediate next actions

1. Put `CLAUDE.md`, `constitution.md`, and `atlas.json` (all provided alongside this roadmap) into a git repo.
2. Point Claude Code at that repo so it loads `CLAUDE.md` every session.
3. Set up the Cowork "Atlas consolidation" scheduled task once you've used the system for a few real sessions and have something worth consolidating.
