# Daily smoke test

A lightweight, real-use checklist for verifying the current baseline still works after a
work session — not a substitute for the automated test suite, just a fast sanity pass
covering things `pytest`/`tsc` can't see (actual UI text, actual click-through behavior).
No paid APIs or real provider keys are required for any of this — Ollama or a fake/local
setup is enough.

Mark each item ✅ / ❌ / ⏭️ (skipped) as you go. Items marked **(auto)** are covered by
running the commands in the "Automated" section below instead of clicking through the UI.

## Automated (run these first)

```bash
cd backend && pytest -q            # full backend suite (386 tests as of 2026-07-14)
cd backend && ruff check .         # lint
cd frontend && npm run build       # type check + production build
```

All three should be clean before doing anything below. If `pytest` shows unrelated
persona/router tests failing in a full run but passing individually — that was a known
Chroma test-isolation flake, **fixed 2026-07-14** (see `backend/tests/README.md`'s
"Chroma isolation rule" and `backend/tests/conftest.py`'s `_isolate_chroma_collections`
fixture). If you see it again, that's a regression worth investigating, not something to
wave off.

## Manual — core chat

- [ ] Backend starts cleanly (`uvicorn app.main:app --reload`), `/docs` loads.
- [ ] Frontend dev server starts (`npm run dev`), app loads with no console errors.
- [ ] Send a normal chat message with Ollama (or another configured provider). A reply
      appears.
- [ ] The reply shows **only** the answer text — no "Atlas notes", no "Reasoning:" block,
      no raw `MEMORY:`/`WIKI_SEARCH_RESULTS:`/`WEB_SEARCH_RESULTS:`/`RSS_FEED_RESULTS:`/
      `DIRECT_PAGE_RESULTS:` labels anywhere in the visible text.
- [ ] Under the reply, a small metadata line reads `via <Provider>` (e.g. `via Ollama`) —
      never the word "Source:", never a raw internal label.
- [ ] The welcome/empty-chat screen doesn't show a long "recalling: ..." memory dump.

## Manual — fallback behavior

- [ ] With a cloud provider configured but simulated/actually unavailable (quota
      exhausted, no key, etc.) and Ollama running, "auto" mode falls back to Ollama and
      the reply still renders cleanly.
- [ ] The metadata line shows the fallback subtly (`via Ollama, fallback`) — not a large
      warning banner.
- [ ] A normal message that **didn't** need a fallback shows no fallback note at all.
- [ ] With no provider available at all (no keys, Ollama stopped), sending a message
      gives a clear, honest error — never a raw stack trace or unhandled exception.

## Manual — search routing (see `docs/searxng-setup.md` for setup)

- [ ] A stable/background question ("Who is Marie Curie?") gets a wiki-grounded answer
      when `WIKI_SEARCH_ENABLED=true` (default) — metadata line includes `Wikipedia`.
- [ ] A live/current question ("what's the latest news today?") with no SearXNG/RSS
      configured gets an **honest** "I can't verify this" answer, not a guess — metadata
      line shows no source name (just `via <Provider>`).
- [ ] The same live question **with** SearXNG configured and running gets a real,
      grounded answer — metadata line includes `SearXNG`.
- [ ] A personal-memory question ("what did I tell you about my job?") never triggers
      web/wiki/RSS search — it uses Atlas/previous-conversation instead.
- [ ] A plain, non-time-sensitive chat message ("what's a good book to read?") doesn't
      trigger any search at all.
- [ ] Nowhere in any response does the literal string "Source:" appear.

## Manual — memory

- [ ] "Remember that I prefer tea over coffee" saves directly and shows a small
      confirmation note under the reply.
- [ ] A message with an incidental personal fact (not an explicit "remember that...")
      does **not** show any candidate/review message under the reply — it's queued
      silently, reviewable only in the Atlas UI's Memory Candidates section.
- [ ] Atlas UI shows the new entry/candidate as expected.

## Manual — previous-conversation search

- [ ] "Do you remember when we talked about X?" (from an earlier conversation) surfaces a
      relevant snippet and is honestly framed ("I found this in our previous
      conversation...", not presented as a confirmed Atlas memory).

## Manual — other features

- [ ] Library: a generated image or uploaded file appears in Library; search/filter and
      download/delete work.
- [ ] Schedule: create, complete, cancel, and delete a reminder.
- [ ] The "+" menu in chat opens and its actions (attach file, generate image, etc.) work
      or show a clean "unavailable" reason.
- [ ] With no image-generation provider configured, the image-gen UI shows a clean
      "unavailable — <reason>" state, never a raw error.

## What this checklist doesn't cover

Voice input/output, PWA install, and native packaging (Capacitor/Tauri) are covered
separately — see `PROJECT_HEALTH_REPORT.md`'s feature verification table for the full
picture; this checklist is deliberately scoped to what changes most often (chat, search,
memory).
