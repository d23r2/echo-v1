# ECHO Layer 1 — Memory Foundation Manual Smoke Test

A 39-step manual checklist, run alongside (not instead of) the automated
129-test Layer 1 suite. Uses the safe temp-port pattern established in Layer
0/prior milestones — never point the frontend at a real port-8000 backend
while testing anything that touches persisted data unless you intend real
data to change.

## Startup (1–4)

1. Confirm the backend is reachable on `http://localhost:8000` (reuse the
   existing Docker backend if it's already healthy, per Layer 0's
   `scripts/start_echo_dev.ps1`).
2. Confirm the frontend dev server is reachable on `http://localhost:5174`.
3. Open Memory Center (Advanced → Knowledge & Memory → Memory Center).
4. Confirm existing memories (created before this milestone) still list
   correctly — a pre-existing `AtlasEntry` row should show `category:
   semantic` (or the appropriate legacy-mapped category) with no error.

## Capture (5–13)

5. Say: "Remember that I prefer technical explanations to begin with an
   example."
6. Confirm the reply confirms it was saved (explicit requests still save
   directly, no candidate review step).
7. Open Memory Center, confirm the new memory appears with
   `capture_method: explicit_user_request` and `verification_status:
   verified`.
8. Ask a technical question in the same conversation.
9. Confirm ECHO's reply style reflects the preference naturally (no raw
   memory text or internal labels leaking into the reply).
10. Say: "Do not remember the next thing I say."
11. Immediately say a fictional, memorable-sounding fact (e.g. "My favorite
    planet is Zorblax").
12. Confirm it is **not** captured — check Memory Center and the Atlas
    diagnostics page; no new entry or candidate should exist for it.
13. Say something durable but not explicit (e.g. "I always want short
    answers when I'm debugging") and confirm it queues as a pending
    candidate (Atlas → Memory Candidates), not saved directly.

## Duplicate handling (14)

14. Add a memory whose content is a near-duplicate of an existing one (e.g.
    via `POST /api/atlas` with slightly different wording). Confirm it is
    either flagged as a duplicate on retrieval/consolidation checks or
    correctly recorded as a distinct-but-related memory — never silently
    duplicated without any signal.

## Conflict handling (15–16)

15. Add a conflicting project/environment-style setting (e.g. two memories
    both about "backend port," with different values).
16. In Memory Center, confirm a conflict card appears under "Conflicts
    needing review" with a plausible `conflict_type` and severity.

## Correction and history (17–18)

17. Correct an old memory by adding a new one that supersedes it (phrasing
    like "X must be Y now; Z was temporary").
18. Confirm the old memory is marked `superseded`/`outdated` (not deleted)
    and the new one references it — check via `GET /api/memory/{old_id}`
    that it still exists with `status: superseded`.

## Archive / restore (19–21)

19. Archive a memory from Memory Center.
20. Confirm it disappears from the default (active) memory list and from
    normal chat retrieval.
21. Restore it; confirm it reappears as active.

## Deletion (22–24)

22. Permanently delete a genuinely test-only memory from Memory Center
    (confirm the native browser confirmation dialog appears first).
23. Confirm it does not reappear in `GET /api/memory` or in a semantic
    search for its content — including after a page reload.
24. Say "forget that" immediately after telling ECHO something explicit in
    chat; confirm it archives (not permanently deletes) the single most
    recent explicit memory, or reports "not found"/"ambiguous" if the
    10-minute window doesn't have exactly one match.

## Provenance (25)

25. Open a memory's detail (via the API or a future provenance view) and
    confirm the `capture_method`/`source_type` fields read as an
    understandable label, not a raw internal enum leaking into chat.

## Document memory (26–27)

26. Upload a test file/attachment in chat.
27. Confirm any memory or knowledge item derived from it (if any is
    generated) correctly cites the source — and note that full chunked
    document memory is a documented Layer 1 limitation, not yet built
    (see §16 of ECHO_LAYER_1_MEMORY_FOUNDATION.md).

## Search and filters (28–29)

28. In Memory Center, search/filter by category, status, and "needs review
    only" — confirm the list updates correctly for each filter.
29. Use `POST /api/memory/search` directly (or the context-preview
    endpoint) with a query relevant to a known memory; confirm it's
    returned with a relevance score and provenance summary, and that an
    unrelated memory is not returned.

## Export / import (30–32)

30. Click "Export JSON" in Memory Center; confirm a file downloads with
    `schema_version`, `memory_count`, and a `memories` array.
31. Preview-import that same file back (`POST /api/memory/import/preview`);
    confirm it reports the memories as duplicates (since they already
    exist), not as new.
32. Open the exported JSON and confirm it contains no `embedding`,
    `embedding_id`, or secret-shaped values.

## Vector-store fallback (33–34)

33. Temporarily stop or block the Chroma directory (or simulate via a code
    change reverted afterward) and confirm memory search still returns
    results via the lexical/metadata fallback rather than erroring.
34. Confirm normal chat still works end-to-end with the vector store
    unavailable (per rule 15).

## Regression (35–39)

35. Confirm normal chat metadata (`via Ollama`, etc.) is unchanged.
36. Confirm no raw Atlas/Memory debug text appears under normal chat
    responses.
37. Confirm Cognitive Core (world model, skills, causal notes) still works
    unchanged — Layer 1 did not touch it.
38. Run the full backend test suite; confirm all pass (995/995 at the time
    of this milestone, 129 of them new).
39. Run the frontend build; confirm it's clean.
