# ECHO Layer 0 — Manual Smoke Test

A 25-step manual checklist to run after any infrastructure-layer change,
alongside (not instead of) the automated backend/frontend suites. Uses the
existing dev setup — `scripts/start_echo_dev.ps1` handles the "reuse Docker
if it's already serving 8000, otherwise start fresh" logic automatically.

## Startup (1–4)

1. Run `scripts/check_echo_ports.ps1`. Confirm it reports who (if anyone)
   currently owns ports 8000 and 5174.
2. Run `scripts/start_echo_dev.ps1`. Confirm it either reuses a healthy
   existing backend on 8000 or starts a fresh one — never both, never a
   silent failure.
3. Confirm the frontend dev server comes up on `http://localhost:5174` and
   loads without a blank screen or console error.
4. Confirm `backend/data/echo.db` was not recreated/truncated by the above
   (existing conversation count unchanged — compare against
   `scripts/check_database.ps1`'s reported count before/after).

## Health (5–8)

5. `GET http://localhost:8000/health` → `200`, minimal body, responds
   instantly (no DB/provider call).
6. `GET http://localhost:8000/ready` → `200` with `ready: true` while the DB
   is reachable.
7. `GET http://localhost:8000/api/system/status` → overall `green` or
   `yellow` (not `red`) on a normally-running install; matches what
   Settings → System Status shows in the UI.
8. `GET http://localhost:8000/api/system/diagnostics` → no raw API key, no
   `.env` value, no stack trace anywhere in the response body.

## Chat (9–12)

9. Send a normal chat message through the UI. Confirm the reply still
   renders exactly as before this milestone (no new UI element, no
   behavior change).
10. Confirm the response includes an `X-Request-ID` response header (check
    via browser devtools Network tab).
11. Confirm the `via <provider>` metadata line under the reply is unchanged.
12. Send a second message in the same conversation; confirm history/context
    still works normally.

## Search (13–15)

13. Ask a question that should trigger Wikipedia lookup (on by default);
    confirm the reply still cites it via the metadata line as before.
14. If SearXNG is configured, ask a current-events question; confirm
    behavior unchanged from pre-Layer-0.
15. Ask a question with no search trigger at all; confirm no search-related
    text leaks into the reply.

## Memory (16–17)

16. Say something with an explicit "remember that ..." phrasing; confirm it
    still saves to Atlas as before.
17. Open the Atlas page; confirm existing entries still list correctly and
    semantic search still works.

## Features / flags (18–20)

18. Open Settings → System Status; confirm backend/database/ollama/wiki/rss/
    searxng/cognitive_core all show a real (not error) value.
19. `GET http://localhost:8000/api/system/features` → confirm it lists all
    28 documented keys with sane `enabled`/`available` values.
20. Toggle a Settings UI option (e.g. "Show Advanced systems expanded by
    default"), reload, confirm it persisted — unrelated to Layer 0 but
    proves the request pipeline (now wrapped in the new middleware) still
    round-trips writes correctly.

## Failure handling (21–23)

21. Temporarily stop Ollama (if running locally) and confirm
    `/api/system/status` degrades to `yellow` with a clear warning, not a
    crash, and chat still works via cloud fallback if configured (or gives
    a clean "Local models are unavailable" message if not).
22. Trigger a validation error (e.g. `POST /api/chat` with a malformed
    body via a raw HTTP client) and confirm the response is the standard
    error schema — no stack trace, has an `error_category`.
23. Confirm an existing 404 (e.g. deleting a nonexistent Atlas entry) still
    returns FastAPI's plain `{"detail": "..."}` shape, not the new
    standard-error-schema shape — this is intentionally unchanged.

## Version (24–25)

24. `GET http://localhost:8000/api/system/version` → confirm
    `application_version`, `schema_version`, and `api_version` are all
    present and sane.
25. Confirm the version/schema line rendered in Settings → System Status
    matches the API response from step 24 exactly.
