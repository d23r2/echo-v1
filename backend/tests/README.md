# Backend tests

## Running

From `backend/`:
```bash
pytest
```

From the repo root:
```bash
pytest backend/tests
```

Both work — `conftest.py` adds `backend/` to `sys.path` itself, so `from app import ...`
resolves regardless of which directory you run from.

## Isolation

`conftest.py` redirects `DATABASE_URL`, `CHROMA_DIR`, and `ATTACHMENTS_DIR` to a fresh
temp directory *before* any `app.*` module is imported, and the `db_session` fixture
gives each test its own throwaway SQLite file. Running the suite never reads or writes
`backend/data/` (the real app's persisted state) and never leaves anything behind.

**Chroma isolation rule:** `atlas.py`'s and `conversation_search.py`'s Chroma
collections are process-wide singletons (`@lru_cache`'d `_get_collection()`), shared
across every test in the run regardless of which DB-isolation pattern a given test file
uses. The autouse `_isolate_chroma_collections` fixture wipes both collections'
*contents* before every single test — don't rely on a prior test's Atlas entries or
indexed messages still being there, and don't add a test that depends on another test
having run first to seed Chroma state. If you see an unrelated persona/router test fail
in a full run but pass in isolation or on retry, that was this exact class of bug before
2026-07-14 (see PROJECT_HEALTH_REPORT.md) — if it recurs, suspect a new place that reads
Chroma without going through the isolated fixture.

No paid services are used — Atlas-related tests that touch ChromaDB use the same local
`sentence-transformers` embedding model the app already uses; nothing calls a real model
provider (Anthropic/OpenAI/Gemini/Grok) or costs money.

## What's covered so far

- `test_app_smoke.py` — the app imports and starts.
- `test_memory_extraction.py` — parsing/validation of the model's `MEMORY:` envelope
  section, and the explicit "remember that..." save path.
- `test_council.py` — Guardian Council vote tallying and ratification/rejection logic.
- `test_constitution_guard.py` — the amendment invariant guard (obvious and "sneaky"
  attempts to weaken a Value Invariant get blocked; legitimate amendments don't).
- `test_search_intent.py` — the deterministic current-info/background classifier
  (`app/search_intent.py`), regex-only, no network.
- `test_web_search.py` — SearXNG/Wikimedia/RSS/direct-page providers and the
  `gather_sources()` router (`app/web_search.py`). `httpx.get` is faked via
  `tests/fake_http.py`'s real-but-offline `httpx.Response` objects — no real network
  calls, no API keys.
- `test_persona_search_injection.py` — `build_system_prompt()`'s wiring of search
  results into the prompt (block injection, the honest "couldn't verify" note when
  search was needed but nothing was found).

This is a foundation, not full coverage — broader feature/route tests aren't in scope yet.
