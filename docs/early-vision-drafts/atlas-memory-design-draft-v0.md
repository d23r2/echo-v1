# Atlas Memory System — Design (v0 → v1)

Goal: a memory store that survives across Claude Code sessions and Cowork scheduled tasks, tags what it knows by how sure it is, and costs nothing to run at this scale.

## v0 schema (flat JSON, ships with this repo as `atlas.json`)

```json
{
  "entries": [
    {
      "id": "atlas-0001",
      "content": "The user is building the God Tear AI Brain project on a $0-40/mo budget.",
      "epistemic_status": "Verified",
      "created_at": "2026-07-09T00:00:00Z",
      "source": "conversation:2026-07-09",
      "tags": ["project-meta", "budget"]
    }
  ]
}
```

Field definitions:

- `epistemic_status` — one of:
  - **Verified** — confirmed by the user directly, or by external evidence Echo actually checked.
  - **Inferred** — a reasonable conclusion Echo drew from other Verified facts, not stated directly.
  - **Hypothesis** — a guess or untested idea worth tracking, not yet supported.
  - **Narrative** — the user's stated opinion, preference, or framing — true that they believe it, not a claim about the world.
- `source` — where this came from (a session date, a specific message, a document). Enables auditing later.
- `tags` — free-text categories for coarse filtering before semantic search exists.

Why JSON and not a database at v0: zero setup, human-readable, diffable in git, trivially portable between Claude Code and Cowork since both can just read/write a file in the shared repo.

## v0 write discipline

- Every session/task that adds to Atlas appends new entries — it does not rewrite history. If a fact turns out to be wrong, add a new entry marking the old one superseded (`"superseded_by": "atlas-00xx"`), don't silently delete it. This preserves the audit trail the Constitution asks for.
- Consolidation (the Cowork scheduled task) is the only process that should routinely write to Atlas in bulk. Ad hoc session writes should be for things worth remembering long-term, not every detail of a conversation.

## v1: making it searchable

Once `atlas.json` has more than ~50-100 entries, keyword/tag search stops being enough. Plan:

1. Generate an embedding for each entry's `content` using a **local** model (`sentence-transformers`, e.g. `all-MiniLM-L6-v2` — runs on CPU, free, no API cost).
2. Store embeddings alongside entries (either inline in the JSON or a parallel `.npy`/index file — keep them out of git if they get large, regenerate on demand instead).
3. At query time: embed the query, brute-force cosine similarity against all stored embeddings (fine up to tens of thousands of entries), return top-k.
4. If/when the store gets large enough that brute-force is slow (unlikely for a personal system for a long time), swap in FAISS — still local, still free.

No hosted vector DB needed until v2's multi-device backend makes a remote store worthwhile anyway.

## v1: migrating to SQLite (optional, once JSON gets unwieldy)

Same schema, just as a table (`entries(id, content, epistemic_status, created_at, source, tags, superseded_by)`), plus a separate `embeddings` table or a sidecar file. Still $0, still a single portable file, still works identically for both Claude Code and Cowork as long as they point at the same file path (or the same repo).

## v2 preview: shared remote store

When multi-device matters (see `roadmap.md`), Atlas moves to a small hosted Postgres (Supabase/Neon free tier) with a pgvector column for embeddings, accessed through a thin API. Schema is the same conceptually — this is a storage migration, not a redesign.
