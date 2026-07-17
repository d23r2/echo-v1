# ECHO Layer 0 — Infrastructure Foundation v1

This document describes ECHO's infrastructure layer: the configuration, logging,
error-handling, health-check, caching, metrics, database-safety, and deployment
scaffolding that every other layer (Memory, Intelligence, Wisdom, Human
Interaction, Mastery) sits on top of. It adds **no new user-facing intelligence
feature** — every existing behavior (chat, Atlas, Guardian Council, Cognitive
Core, Human Persona, Local Intelligence, Action/Reliability systems) is
unchanged. See [ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md](ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md)
for the delivery report and [ECHO_LAYER_0_SMOKE_TEST.md](ECHO_LAYER_0_SMOKE_TEST.md)
for the manual verification checklist.

## 1. Purpose

Before this milestone, ECHO's config lived in one `Settings` class with no
startup validation, errors leaked raw exception text and provider internals
straight into HTTP responses, there was no structured logging or redaction, no
place to ask "is ECHO healthy right now" other than a single `/api/health`
check that only proved the process was alive, no in-process metrics, no
enforced SQLite foreign-key integrity, and no documented backup/restore path.
None of that blocked shipping features — but every later layer (persistent
Memory, more autonomous Intelligence, deeper Human Interaction) needs a
foundation that's safe to build on without re-discovering the same gaps one at
a time. This milestone is that foundation.

## 2. Architecture overview

New code lives under two additive namespaces plus one router:

- `backend/app/core/` — `logging.py`, `errors.py`, `feature_flags.py`,
  `metrics.py`, `cache.py`. Cross-cutting, no dependency on any specific
  feature module.
- `backend/app/providers/registry.py` — a read-only summary layer over the
  existing `ModelRouter`/`local_model_router`, not a new provider system.
- `backend/app/routers/system.py` — the one new router, exposing
  `/health`, `/ready`, and `/api/system/*`.

Everything else (config, models, db, main) was extended in place rather than
replaced. No existing router, service, or frontend component changed its
public behavior.

## 3. Configuration system

`backend/app/config.py`'s `Settings` (pydantic-settings, reads `backend/.env`)
gained an "ECHO Layer 0" section: application identity (`app_name`, `app_env`,
`app_version`, `debug`, `log_level`, `host`, `port`), `frontend_url`, database
extras (`database_echo`, `database_backup_enabled`, `database_backup_path`),
Ollama extras (`ollama_enabled`, `ollama_timeout_seconds`), feature flags not
already covered, safety defaults (all off: `file_write_enabled`,
`code_execution_enabled`, `destructive_actions_enabled`,
`public_push_enabled`), performance settings, and observability toggles.

Two new methods:

- `validate_startup() -> list[str]` — checks port range, `log_level`/`app_env`
  enum membership, positive timeout, positive concurrency cap, non-negative
  cache TTL. Called once at startup; problems are logged as warnings, never
  raised (a misconfigured non-critical value shouldn't crash the app).
- `public_dict() -> dict` — the settings object with every field whose name
  ends in `_api_key`/`_secret`/`_token`/`_password` removed. Used anywhere
  config needs to reach a response body (`/api/system/diagnostics`).

All new fields have safe defaults; a fresh checkout with an empty `.env` still
starts cleanly.

## 4. Feature flag registry

`backend/app/core/feature_flags.py`'s `list_feature_flags()` reports on/off +
availability for 28 subsystem keys (chat, ollama, cloud_fallback, atlas,
cognitive_core, local_intelligence, human_persona, operational_self_model,
skill_engine, action_system, permission_center, evaluation_lab,
knowledge_vault, projects, tasks, schedule, library, wiki, rss, searxng,
direct_page_fetch, voice, camera, image_generation, android_support,
windows_support, developer_mode, advanced_navigation). This is deliberately
separate from the pre-existing `GET /api/features` (chat/image provider
availability with cooldown detail), which the chat UI's `+` menu already
depends on unchanged — the new registry answers a broader "what parts of ECHO
are on" question, the old one answers a narrower "can I send this message
right now" question.

## 5. Provider / model registry

`backend/app/providers/registry.py` wraps `ModelRouter.statuses()` and
`usage.get_active_cooldown()` with static capability metadata (cost tier,
requires-key, supports-vision, supports-streaming) per cloud provider, and
separately mirrors `local_model_router.py`'s own fast/reasoning/coding/critic/
writing role-to-model mapping, read-only. No provider-selection logic was
duplicated or changed.

## 6. Logging and redaction

`backend/app/core/logging.py`: `configure_logging(level, structured)` sets up
either a human-readable dev formatter or a structured (JSON-ish) formatter for
`app_env=production`, idempotent via a module flag. A `RedactingFilter`
rewrites any log record matching `sk-...`/`Bearer ...`/
`authorization=...`/generic `api_key=`/`secret=`/`password=`/`token=` patterns
before it's emitted — attached to the root logger, so it protects every
existing `logger.info`/`logger.warning` call in the codebase too, not just new
ones. `log_event()` only accepts a fixed set of safe structured fields
(`request_id`, `conversation_id`, `action_run_id`, `tool_run_id`,
`provider_id`, `elapsed_ms`, `error_category`) — there is no `message`/
`prompt`/`content` parameter, so it's structurally impossible to log raw user
or model text through it. `Timer` is a small context manager for elapsed-ms
measurement. `request_id_var` is a `ContextVar` populated by the request-ID
middleware (see §7) so any log line inside a request can include it.

## 7. Error handling and standard error schema

`backend/app/core/errors.py`:

- `ErrorCategory` — 18 machine-readable categories (validation, auth,
  permission, feature-disabled, provider-unavailable/rate-limited/
  quota-exceeded/billing-required, Ollama-offline, model-not-found,
  search-unavailable, current-info-unverified, database, file-not-found/
  access-denied, action-confirmation-required, destructive-action-blocked,
  internal).
- `ApiError` — raise this for any new error that should carry a category;
  `build_error_body()` produces the response JSON.
- `RequestIDMiddleware` — assigns or echoes an `X-Request-ID` header on every
  request/response, times the request, logs one structured completion event,
  and increments HTTP metrics.
- `register_exception_handlers(app)` — registers handlers for `ApiError`,
  `RequestValidationError`, and generic `Exception` **only**. FastAPI's
  default `HTTPException` handler is deliberately left untouched, so every
  existing `raise HTTPException(...)` in ~30 routers keeps its exact
  `{"detail": ...}` shape — verified by a dedicated test
  (`test_real_app_existing_http_exception_shape_unchanged`). An unhandled
  exception is logged with full detail server-side and returns a generic
  sanitized message to the client — no stack trace, no exception class name,
  no internal value ever reaches the response body.

## 8. Health, readiness, and diagnostics

`backend/app/routers/system.py`, additive alongside the pre-existing
`/api/health`:

- `GET /health` — bare process-alive check, no DB/provider calls. Cheap
  enough for a container healthcheck to poll every 30s.
- `GET /ready` — DB reachable + required tables present
  (`conversations`, `messages`, `atlas_entries`).
- `GET /api/system/status` — green/yellow/red summary (yellow = a non-critical
  subsystem like Ollama or search is down; red = database unreachable).
- `GET /api/system/diagnostics` — sanitized config (`Settings.public_dict()`),
  feature flags, provider registry, a DB write-check, schema version. No
  secret, env var raw value, or stack trace ever appears here.
- `GET /api/system/features`, `/api/system/providers`, `/api/system/models`,
  `POST /api/system/providers/{id}/check`, `/api/system/metrics`,
  `/api/system/version`.

## 9. Database safety: schema version, backup, restore, integrity

`backend/app/models.py` gained `SchemaVersion` (singleton row,
`CURRENT_SCHEMA_VERSION = 1` in `db.py`). `init_db()` now ends with
`_ensure_schema_version()`, idempotent and never downgrading an existing
higher version. **Alembic was deliberately not introduced** — the existing
non-destructive `_ensure_column`/`create_all` pattern already works and is
exercised by every prior migration in this app's history; adding a migration
framework now would be exactly the kind of "rebuild a working system" this
milestone's own rules warn against. Instead:

- `scripts/backup_echo_data.ps1` — copies `backend/data/echo.db` and
  `backend/data/chroma/` to a timestamped folder under
  `backend/data/backups/`.
- `scripts/restore_echo_data.ps1` — takes a safety copy of current data before
  overwriting, requires typed confirmation unless `-Force`.
- `scripts/check_database.ps1` — `PRAGMA integrity_check`,
  `PRAGMA foreign_key_check`, required-table presence, schema version,
  conversation/message counts. Live-run against the real dev database: clean.

## 10. SQLite foreign-key enforcement and test isolation

A generic `@event.listens_for(Engine, "connect")` listener in `db.py` turns on
`PRAGMA foreign_keys=ON` for every SQLite connection in the process —
including each isolated per-test engine in `tests/conftest.py`, not just the
main app engine. Verified safe by running the full backend suite twice (once
scoped only to the main engine, once generalized): 859/859 passed both times,
and 866/866 pass now with the Layer 0 tests added. This closes a real gap —
before this, an orphaned foreign key (e.g. a `Message` referencing a deleted
`Conversation`) would silently succeed instead of being rejected.

## 11. Caching and concurrency

`backend/app/core/cache.py` — a small generic in-process TTL cache
(`get`/`set`/`invalidate`/`invalidate_prefix`/`clear`/`stats`/`cached()`
decorator), gated by `Settings.cache_enabled`/`cache_ttl_seconds`. Used for
things that had no cache before (provider health checks, installed-model
list, feature availability) — `web_search.py`'s own already-working TTL cache
was deliberately left as-is, not migrated, since it already works and
migrating it would add risk for no benefit.

`backend/app/services/local_model_router.py` gained a
`threading.Semaphore` sized from `Settings.max_concurrent_model_requests`
(default 2), wrapping both `self.provider.chat(...)` call sites in
`LocalModelRouter.call()`. A request that can't acquire the semaphore within
30 seconds gets a clean "Local models are busy right now" result instead of
queuing indefinitely — this prevents an Ollama instance on modest hardware
from being overwhelmed by concurrent chat requests.

## 12. Startup and lifespan

`backend/app/main.py`'s `lifespan()` now, in order: configures logging
(`structured=True` only in `app_env=production`), runs
`settings.validate_startup()` and logs any problems as warnings, calls the
existing `init_db()` (now also ensuring the schema-version row), logs a
startup line, and — on shutdown — logs a shutdown line. `RequestIDMiddleware`
and `register_exception_handlers(app)` are registered immediately after the
existing `CORSMiddleware`, so they wrap every route including all pre-existing
ones.

## 13. Development ports and process management

Backend stays on `http://localhost:8000`, frontend dev server on
`http://localhost:5174` — unchanged. New scripts:

- `scripts/check_echo_ports.ps1` — reports what owns ports 8000/5174, hits
  `/api/health`, lists `docker ps`. Purely diagnostic.
- `scripts/start_echo_dev.ps1` — if port 8000 already serves a healthy ECHO
  backend (e.g. the user's Docker stack), reuses it and starts only the
  frontend; if the port is free, starts both; if the port is occupied by
  something unhealthy/unidentifiable, refuses and reports rather than
  guessing.
- `scripts/stop_echo_dev.ps1` — only stops a process whose command line
  contains `uvicorn` or `vite`; explicitly skips anything matching
  `docker|wslrelay|com.docker` so it can never accidentally take down the
  user's Docker stack.

These scripts implement this milestone's own non-negotiable rules 10–12
(reuse Docker's backend if present, never silently kill a process on 8000).

## 14. Docker and containerization

`backend/Dockerfile` and `frontend/Dockerfile` both gained a `HEALTHCHECK`
(backend: `curl -f http://localhost:8000/api/health`; frontend: `wget --spider
http://localhost/`). The backend image now runs as a non-root `echo` user
(`useradd --uid 1000`). The frontend build now uses `npm ci` instead of
`npm install` for deterministic, lockfile-exact installs. `docker-compose.yml`
gained `restart: unless-stopped` and matching `healthcheck:` blocks on both
services, and `frontend` now waits for `backend: condition: service_healthy`
instead of just `depends_on: [backend]`. New `.dockerignore` files for both
images exclude `.venv`/`node_modules`/`.env`/`data/`/`.git`/tests so images
stay small and never bake in local secrets. All of this was validated via
`docker compose config --quiet` (syntax/schema check only) — the live Docker
stack itself was **not** rebuilt or restarted, since that's a shared running
system and out of scope for this pass without explicit permission.

## 15. Frontend reliability

`frontend/src/components/ErrorBoundary.tsx` — a class-component error
boundary wrapping the whole app tree in `main.tsx`, directly motivated by a
real white-screen crash witnessed earlier in this project's history (a stale
HMR bundle produced an unrecoverable blank page). On a render error it shows
a calm "Reload ECHO" recovery screen instead of a blank page; the actual
error detail goes to `console.error` via the new `frontend/src/lib/logger.ts`
(never rendered). `frontend/src/config/env.ts` centralizes the handful of
build-time `VITE_*` reads (`appName`, `appEnv`) — explicitly documented as
NOT including "show advanced nav" or "developer mode," since those are
runtime, per-install `InterfaceSettings` DB values, not build-time flags; two
competing sources of truth for the same concept was judged worse than one
more explicit doc comment.

## 16. Metrics

`backend/app/core/metrics.py` — thread-lock-guarded in-process counters and
bounded duration samples (max 500 per key), `increment()`/
`record_duration()`/`snapshot()`/`reset()`. Wired into `RequestIDMiddleware`
(every HTTP request/error/duration) and `router.py`'s `_track_success`/
`_track_failure` (every model call, auto and pinned paths alike, one
chokepoint). No external metrics backend (Prometheus, etc.) — this is
in-process only, exposed via `GET /api/system/metrics`, reset on process
restart. Sufficient for local single-user diagnostics; a real
metrics-export pipeline is out of scope until ECHO has more than one
deployment target.

## 17. Security and secret handling

- `Settings.public_dict()` excludes any field ending in a secret-like suffix
  by pattern, not a hand-maintained allowlist — a newly added `*_api_key`
  field is automatically excluded without remembering to update a list.
- `RedactingFilter` scrubs secret-shaped strings from every log line.
- `.gitignore` gained a Layer 0 section covering `.env`/`*.env.local`/
  `*.pem`/`*.key`/build artifacts/`*.zip`/IDE folders — verified via
  `git check-ignore -v` that `backend/.env`, `frontend/.env`, and the stray
  `Echo_Code_Review.zip` are all covered.
- `scripts/check_secrets.ps1` scans only `git ls-files` (tracked files),
  looking for API-key-shaped strings, Bearer tokens, PEM headers, and generic
  `key/secret/password/token = "..."` assignments, skipping doc files that
  legitimately mention these terms. Live-run: 389 tracked files scanned, 0
  findings.
- **A real secret was inadvertently displayed during this milestone's own
  work**: `docker compose config` (without `--quiet`) prints every resolved
  environment variable, including the real `GEMINI_API_KEY` from
  `backend/.env`. That value is not reproduced anywhere in this repo, this
  document, or any commit; all Compose validation after that point used
  `docker compose config --quiet` (exit-code-only). If you need to inspect
  resolved Compose config yourself, be aware plain `docker compose config`
  does this and treat the output as sensitive.

## 18. Versioning

`Settings.app_version = "0.9.0"` — pre-1.0, reflecting that this is still an
actively-developed personal project, not a versioning scheme change. Exposed
via `GET /api/system/version` alongside the DB schema version and API
version. No semantic-versioning enforcement or changelog automation was
added; that's future scope once there's an actual release process.

## 19. Continuous integration

`.github/workflows/ci.yml` (new, **not pushed** — see §20 of the delivery
report) — a `backend` job (Python 3.11, `pip install -r requirements.txt`,
`ruff check .`, `pytest -q`, no real provider keys anywhere, using the same
fake providers and isolated temp DB/Chroma the local test suite already
uses) and a `frontend` job (Node 20, `npm ci`, `npx tsc -b --noEmit`,
`npm run build`), plus a `config-validation` job (`docker compose config
--quiet`, `scripts/check_secrets.ps1`). No `lint` npm script exists in this
project — documented in the workflow file as intentionally absent rather than
invented. Triggers on push/PR to `master`/`main`.

## 20. Quality gates

"Green" for this milestone means: full backend suite passes, `ruff check .`
clean, frontend `tsc -b --noEmit` and `npm run build` both clean, secret scan
finds nothing, `docker compose config --quiet` succeeds, and no existing
feature's behavior changed (verified by the existing, still-passing test
suite plus the fact that no non-Layer-0 router/service file's public
behavior was touched). See the delivery report for the actual numbers.

## 21. Troubleshooting

- **Backend won't start**: check `scripts/check_database.ps1` for integrity
  issues first; `validate_startup()` warnings are logged, not raised, so a
  bad `.env` value won't crash the app but will show up in the startup log.
- **Port 8000 already in use**: run `scripts/check_echo_ports.ps1` to see who
  owns it. If it's Docker serving a healthy backend, that's expected — reuse
  it (`scripts/start_echo_dev.ps1` does this automatically). Never
  `taskkill` a process on 8000 without confirming what it is first.
- **`/ready` reports false**: means the DB is unreachable or a required table
  is missing — check `backend/data/echo.db` exists and run the integrity
  script.
- **A response contains no useful error detail**: intentional for unhandled
  exceptions (see §7) — check the server log (now redacted-safe) for the full
  trace, correlated by the `X-Request-ID` header echoed on the response.

## 22. Manual smoke checklist

See [ECHO_LAYER_0_SMOKE_TEST.md](ECHO_LAYER_0_SMOKE_TEST.md) — 25 steps
covering startup, health, chat, search, memory, feature flags, failure
handling, and versioning.

## 23. Known limitations

- Docker image rebuild/restart against the user's live stack was not
  performed this session (deliberately deferred — a shared running system,
  out of scope without explicit permission). Compose/Dockerfile changes are
  validated statically only.
- Metrics are in-process and reset on restart — no persistence, no
  cross-restart history, no external export.
- No Alembic — schema changes still rely on the existing additive
  `create_all`/`_ensure_column` pattern plus the new `SchemaVersion` marker,
  which is sufficient for this app's current single-file-SQLite scale but
  would need revisiting if the schema grows much more complex.
- CI workflow exists locally but has never actually run on GitHub — it
  hasn't been pushed (see §13 of the delivery report). Its correctness is
  reasoned about, not proven by a real Actions run.
- The stray `node.exe` process (PID 36512) spawned during live testing of
  `start_echo_dev.ps1` was left running rather than force-killed, per this
  milestone's own safety rules — harmless (it never bound a port) but worth
  a manual look if you want it gone.

## 24. Rollback procedure

Every change in this milestone is additive or config-gated:

- New files (routers, services, scripts, docs) can be deleted with no effect
  on existing behavior — nothing outside `system.py` imports them.
- Modified files (`config.py`, `db.py`, `main.py`, `models.py`, `router.py`,
  `local_model_router.py`) had only new fields/functions/middleware appended
  — reverting to the pre-Layer-0 commit for just those files restores prior
  behavior exactly, since no existing field, function signature, or route was
  changed or removed.
- The `SchemaVersion` table is additive; dropping it (or ignoring it) doesn't
  affect any other table.
- If `RequestIDMiddleware`/exception handlers ever cause an unexpected
  response-shape change somewhere, they can be removed from `main.py`'s two
  `app.add_middleware`/`register_exception_handlers` call sites with no other
  code change needed, restoring FastAPI's fully default error behavior.
- Before any rollback that touches the database, run
  `scripts/backup_echo_data.ps1` first — this was true before this milestone
  too, now it's just scripted instead of manual.
