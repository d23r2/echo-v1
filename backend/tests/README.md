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

This is a foundation, not full coverage — broader feature/route tests aren't in scope yet.
