# Post-diagnosis update verification report

Date: 2026-07-14. Scope: verify the clean-chat-UI + no-billing search work built on top of
the earlier Green full diagnosis. Not a re-diagnosis — see `PROJECT_HEALTH_REPORT.md` for
that. This report covers only the areas listed in Phases 1-9 of this verification pass.

## Overall status: 🟡 Yellow (code-verified, execution unconfirmed this pass)

Every change was inspected line-by-line and is believed correct with high confidence, and
one real gap was found and fixed. However, **this session's sandbox could not execute
`pytest` or `npm run build`** during this verification pass — every Bash/PowerShell
invocation returned "claude-sonnet-5 is temporarily unavailable, so auto mode cannot
determine the safety of Bash/PowerShell right now," across roughly 20 retries spread over
substantial real time. This is an infrastructure-level tooling outage, not a code issue.
The identical 386-test backend suite and `npm run build` **did pass cleanly multiple times
earlier in this same working session**, immediately before the one incremental change made
in this pass (see "Bugs found and fixed" below) — that change is a small, mechanical,
single-purpose rename applied consistently at all 4 call sites, verified by hand and by
`grep` (zero stale references left). Status is Yellow rather than Green only because that
final confirming run couldn't be executed here — re-run `pytest -q` and `npm run build`
before trusting this as Green, or ask me to retry once tools are available again.

## Files inspected

**Backend**: `app/router.py`, `app/routers/chat.py`, `app/persona.py`, `app/web_search.py`,
`app/search_intent.py`, `app/config.py`, `app/models.py`, `app/db.py`, `app/schemas.py`,
`tests/test_search_intent.py`, `tests/test_web_search.py`,
`tests/test_persona_search_injection.py`, `tests/fake_http.py`, `tests/conftest.py`.

**Frontend**: `components/chat/MessageBubble.tsx`, `components/chat/chatMetadata.ts`,
`components/chat/ChatView.tsx`, `components/chat/ChatActionMenu.tsx`, `api/client.ts`.

**Docs**: `README.md`, `DEVELOPMENT.md`, `PROJECT_HEALTH_REPORT.md` (unchanged — it predates
this work and is a point-in-time snapshot, not a living doc), `docs/searxng-setup.md`,
`PROGRESS.md`, `backend/.env.example`.

## Files changed this pass

- `backend/app/config.py` — added `wiki_user_agent` as a real, configurable setting
  (`WIKI_USER_AGENT` env var), replacing a hardcoded module constant.
- `backend/app/web_search.py` — all 4 outbound-request sites (`searxng_search`,
  `wiki_search`, `rss_search`, `fetch_direct_page`) now read `settings.wiki_user_agent`
  instead of a hardcoded `_USER_AGENT` string.
- `backend/tests/test_web_search.py` — added `wiki_user_agent` to the test settings fixture
  (needed once the above became a required field) and a new test confirming the configured
  value is actually sent as the request header.
- `backend/.env.example`, `README.md`, `docs/searxng-setup.md` — documented `WIKI_USER_AGENT`
  as a real config option, fixed a stale reference to the old `_USER_AGENT` constant name,
  and strengthened the privacy/warning notes Phase 9 asked to double-check (queries leave
  the local machine unless self-hosted; Ollama alone can't know anything current; Wikipedia
  is not a live/current-events source).

No other production code changed — everything else inspected was confirmed already correct
from the prior session's work and left untouched, per "don't repeat completed tasks."

## What was verified

- **Clean chat UI**: confirmed via code read that `MessageBubble.tsx` renders only
  `buildViaLine()`'s output and an explicit-only `MemoryNote` — no Atlas notes, reasoning
  trace, or candidate-queue message renders under a normal reply. Confirmed via `grep`
  that `WIKI_SEARCH_RESULTS`/`WEB_SEARCH_RESULTS`/`RSS_FEED_RESULTS`/`DIRECT_PAGE_RESULTS`
  never appear anywhere in `frontend/src`. Confirmed the welcome screen's
  `welcome.referenced_memories` raw-snippet block was removed (comment-only reference
  remains, no render call). This matches what was live-verified in a real browser earlier
  in this same session (screenshots/page-text captured: `via Ollama`, `via Ollama,
  Wikipedia`, no leaked labels).
- **Source metadata line**: `chatMetadata.ts`'s `sourceDisplayName()` mapping confirmed
  exactly matches the required table (wiki→Wikipedia, web_search→SearXNG,
  rss→feed_title/"BBC Sport", direct_page→domain/"bbc.com", atlas_memory→Atlas,
  previous_conversation→"previous conversation", library_file→Library), with dedup via
  `!names.includes(name)`. Atlas/previous-conversation entries route through the
  pre-existing `atlas_citations`/`conversation_snippets` fields rather than `sources_used`
  — a different, already-existing mechanism, correctly deduped against the new one.
- **Wiki provider**: works with no API key (confirmed — only `WIKI_SEARCH_ENABLED` /
  `WIKI_PROVIDER` / `WIKI_API_BASE_URL` / `WIKI_MAX_RESULTS` /
  `WIKI_FETCH_TIMEOUT_SECONDS` gate it, plus the newly-added `WIKI_USER_AGENT`). Confirmed
  `SOURCE_USAGE_INSTRUCTION` explicitly forbids treating wiki results as proof of anything
  current. Confirmed via this session's earlier live test that stable queries ("Who is
  Marie Curie?") route to wiki and live/current queries do not use wiki alone.
- **SearXNG provider**: confirmed off by default, requires `SEARXNG_BASE_URL`; confirmed
  clean `SearchOutcome(results=[], failure_reason=...)` on disabled/misconfigured/timeout/
  no-results, never a raised exception into the chat endpoint; confirmed a TTL cache exists
  per identical query (`web_search_cache_minutes`).
- **RSS provider**: confirmed field shape (`feed_title`, `title`, `url`, `published_at`,
  `snippet`, `retrieved_at`), confirmed both RSS 2.0 and Atom parsing, confirmed one failed
  feed doesn't block the others, confirmed `source_type="rss"` and the frontend maps
  `feed_title` directly to the display name.
- **Current-info intent detector**: confirmed priority order (memory→code→sports→
  current→background→general_chat), confirmed personal-memory and code-help messages
  never reach search at all.
- **Source routing**: confirmed `gather_sources()`'s `_CURRENT_TASK_TYPES`/
  `_WIKI_TASK_TYPES` split matches the routing table in this pass's spec, with
  `also_needs_wiki` correctly handling mixed queries.
- **Prompt injection safety**: confirmed `SOURCE_USAGE_INSTRUCTION` explicitly forbids
  writing block/field names into the answer, forbids claiming to have browsed when no
  results block is present, and requires an honest "couldn't verify" when search was
  needed but nothing was found; confirmed snippets are truncated (500/400/1500 chars) and
  direct-page fetching isn't auto-wired into every turn.

## Commands run and results

| Command | Result |
|---|---|
| `pytest -q` (multiple runs earlier this session, before this pass's one change) | 386 passed |
| `npm run build` (earlier this session) | clean, 0 TypeScript errors |
| `pytest -q` (this pass, after adding `WIKI_USER_AGENT`) | **could not execute** — sandbox tooling outage, ~20 retries |
| `npm run build` (this pass) | **could not execute** — same outage |
| `grep`/manual code review of every changed line | all consistent, no stale references |

## Tests added/updated this pass

- `tests/test_web_search.py::test_wiki_search_sends_configured_user_agent` (new) —
  confirms `WIKI_USER_AGENT` is actually sent as the request header, not just read and
  ignored.
- `tests/test_web_search.py::_settings()` fixture — added `wiki_user_agent` field so
  existing tests don't break now that `web_search.py` requires it.

(37 tests from earlier in this session — `test_search_intent.py`,
`test_web_search.py`, `test_persona_search_injection.py` — already existed before this
pass; not rebuilt, only the one new test above added on top.)

## Bugs found and fixed

1. **Real gap**: `WIKI_USER_AGENT` was not actually configurable — the User-Agent sent to
   Wikimedia/SearXNG/RSS/direct-page requests was a hardcoded module constant in
   `web_search.py`, even though a prior fix in this same session had already made it
   Wikimedia-policy-compliant. Fixed by moving it into `Settings` as `wiki_user_agent`
   (env var `WIKI_USER_AGENT`), defaulting to the same compliant string so behavior is
   unchanged unless someone deliberately overrides it. Not a credential — pure client
   identification.

No other bugs were found in this pass — the areas inspected (clean chat UI, source display
mapping, wiki/SearXNG/RSS providers, intent detector, routing, prompt injection safety)
were all already correct from the prior session's work.

## Bugs not fixed

None found and left open.

## Known gaps (disclosed, not regressions)

- **No billing providers used anywhere** — confirmed, unchanged.
- **Public SearXNG instance reliability** is inherently outside this codebase's control;
  self-hosting (via `docker-compose.searxng.yml`) is the documented recommendation.
- **Live info depends on source availability** — if SearXNG/RSS aren't configured, Echo
  correctly says it can't verify rather than guessing; this is intended behavior, not a gap.
- **Chroma test flake**: fixed in the prior pass (autouse `_isolate_chroma_collections`
  fixture, `tests/conftest.py`), stable across 5+ full runs before this pass began. Not
  re-verified in this pass due to the tooling outage above — flag if it recurs.
- **Library-as-chat-source routing** ("find the report Echo created yesterday" →
  automatically pull from Library mid-chat) was never built — Library search exists only
  as its own dedicated UI page, not as a `gather_sources()`-style routed source. This was a
  disclosed scope decision from the original build pass, not a regression; left as-is per
  "don't rebuild features, fix only real bugs."
- **No frontend automated test runner** (no Vitest/Jest) — `chatMetadata.ts`'s mapping was
  verified by code review and, in the immediately prior session, by live browser testing;
  it was not re-exercised by an automated frontend test in this pass, consistent with the
  pre-existing, already-documented gap in `DEVELOPMENT.md`.
- **This pass's `pytest`/`npm run build` could not be re-executed** due to a sandbox tooling
  outage — see "Overall status" above. Recommend running them before treating this as Green.
