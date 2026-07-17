# Development

Quick reference for running quality checks locally. Everything here is free and local —
no paid services, no CI required (a GitHub Actions workflow exists at
`.github/workflows/ci.yml` but has not been pushed — see
[ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md](ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md#19-continuous-integration)).
See [DAILY_SMOKE_TEST.md](DAILY_SMOKE_TEST.md) and
[ECHO_LAYER_0_SMOKE_TEST.md](ECHO_LAYER_0_SMOKE_TEST.md) for manual
click-through checklists to run alongside these automated checks, and
`scripts/` (`check_echo_ports.ps1`, `start_echo_dev.ps1`, `stop_echo_dev.ps1`,
`check_database.ps1`, `backup_echo_data.ps1`, `restore_echo_data.ps1`,
`check_secrets.ps1`) for local dev/ops helpers.

## Backend (Python)

From `backend/` (with `.venv` active, or prefix commands with `.venv/Scripts/python.exe -m`):

```bash
pip install -r requirements.txt   # includes pytest, ruff, mypy (dev-only)

pytest                            # run the test suite (see tests/README.md)
ruff check .                      # lint
ruff check . --fix                # lint + auto-fix what's safe to auto-fix
mypy app                          # optional type check — see note below
```

**ruff** is configured in `backend/pyproject.toml` with a deliberately small rule set:
pyflakes + pycodestyle's error subset (ruff's own defaults) plus import sorting (`I`),
common bug patterns (`B`), and syntax modernization (`UP`). No docstring or
type-annotation-coverage rules — those tend to produce hundreds of warnings on a
codebase that wasn't written with them in mind, which isn't useful signal. As of
2026-07-13 this surfaces 17 findings, all cosmetic (2 import-order, 15 Python
3.11+ `datetime.UTC` alias suggestions) and all fixable with `--fix`.

**mypy** is configured gently (`ignore_missing_imports`, `check_untyped_defs = false` —
see `[tool.mypy]` in `pyproject.toml`). It's genuinely useful here (14 findings as of
2026-07-13 — mostly a plain `str` passed where a narrower Pydantic `Literal` type is
expected, plus a few `str | None` vs `str` narrowing gaps in provider classes where a
separate `available()` call — not visible to mypy — already guarantees the value is set
before `chat()` runs) but is **not wired into CI or a required gate** — treat it as an
optional second opinion, not a blocker.

**pytest**: 785 tests as of 2026-07-16, all passing, no real external API calls anywhere
(every provider is a fake/mock — see `tests/fake_providers.py` and `tests/README.md`).
The no-billing web/wiki/RSS search system (`app/search_intent.py`, `app/web_search.py`)
is covered the same way — `tests/fake_http.py` fakes `httpx.get()` with real (but
offline) `httpx.Response` objects, so `test_search_intent.py`/`test_web_search.py`/
`test_persona_search_injection.py` never touch a real SearXNG/Wikipedia/RSS endpoint.

**ECHO Personal OS v1** (Projects/Tasks/Mission Control/Smart Context Router/chat
actions) adds `test_projects.py`, `test_tasks.py`, `test_mission_control.py`,
`test_context_router.py`, `test_chat_actions.py` — run just those with:
```bash
pytest tests/test_projects.py tests/test_tasks.py tests/test_mission_control.py tests/test_context_router.py tests/test_chat_actions.py -v
```
See [ECHO_PERSONAL_OS_V1.md](ECHO_PERSONAL_OS_V1.md) for what these features do and their
known limitations.

**ECHO Human Persona Layer v1** (relationship memory, mood, operational modes, humour,
proactivity, personality settings, rituals) adds `test_human_persona.py` — run it with:
```bash
pytest tests/test_human_persona.py -v
```
See [ECHO_HUMAN_PERSONA_LAYER_V1.md](ECHO_HUMAN_PERSONA_LAYER_V1.md) for what these features
do, safety limits, and known limitations.

**ECHO Local Intelligence Engine v1** (intent classifier, context gatherer, local model
router, draft/critic/repair/style pipeline, cloud fallback gate) adds
`test_intent_classifier.py`, `test_context_gatherer.py`, `test_local_model_router.py`,
`test_local_intelligence_engine.py`, `test_local_intelligence_eval_cases.py`,
`test_local_intelligence_chat_integration.py` — run just those with:
```bash
pytest tests/test_intent_classifier.py tests/test_context_gatherer.py tests/test_local_model_router.py tests/test_local_intelligence_engine.py tests/test_local_intelligence_eval_cases.py tests/test_local_intelligence_chat_integration.py -v
```
Off by default (`LOCAL_INTELLIGENCE_ENGINE_ENABLED=false`); no real Ollama or cloud call in
any of these tests. See [ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md](ECHO_LOCAL_INTELLIGENCE_ENGINE_V1.md)
for what it does, config variables, and known limitations.

**ECHO Action + Reliability Core v1** (Action System, Permission Center, Evaluation Lab,
Knowledge Vault, Conversation Auto-Summary, Release Manager, Tool Registry) adds
`test_action_system.py`, `test_permission_center.py`, `test_evaluation_lab.py`,
`test_knowledge_vault.py`, `test_conversation_summary.py`, `test_release_manager.py`,
`test_tool_registry.py`, `test_action_reliability_integration.py` — run just those with:
```bash
pytest tests/test_action_system.py tests/test_permission_center.py tests/test_evaluation_lab.py tests/test_knowledge_vault.py tests/test_conversation_summary.py tests/test_release_manager.py tests/test_tool_registry.py tests/test_action_reliability_integration.py -v
```
No real network/Ollama/cloud call in any of these tests — the one system that touches a
model (Conversation Auto-Summary) is tested with a `FakeProvider`-backed `LocalModelRouter`,
same pattern as the Local Intelligence Engine's own tests. See
[ECHO_ACTION_RELIABILITY_CORE_V1.md](ECHO_ACTION_RELIABILITY_CORE_V1.md) for what it does,
config variables, and known limitations. Multi-user tester accounts were explicitly **not**
part of this milestone.

**ECHO Cognitive Core v1** (world model/knowledge graph, task understanding, skill library,
causal notes, missing-knowledge/success-criteria generation, prompt integration) adds
`test_cognitive_core.py`, `test_cognitive_router.py`, `test_cognitive_prompt_integration.py`
— run just those with:
```bash
pytest tests/test_cognitive_core.py tests/test_cognitive_router.py tests/test_cognitive_prompt_integration.py -v
```
All classification/matching is deterministic (regex/keyword), no model call of its own; the
two tests that touch the Local Intelligence Engine path use the same `ScriptedProvider`/
`FakeProvider` pattern as the rest of this suite. See
[ECHO_COGNITIVE_CORE_V1.md](ECHO_COGNITIVE_CORE_V1.md) for what it does, the data model, and
known limitations.

**ECHO Operational Self-Model v1** (goal/mode/confidence/risk tracking, prompt overlay,
consciousness/emotion honesty, Interface Simplification sidebar/settings) adds
`test_operational_self_model.py` — run it with:
```bash
pytest tests/test_operational_self_model.py -v
```
All mode/risk/confidence detection is deterministic (regex/keyword), no model call of its own.
See [ECHO_OPERATIONAL_SELF_MODEL_V1.md](ECHO_OPERATIONAL_SELF_MODEL_V1.md),
[ECHO_INTERFACE_SIMPLIFICATION_V1.md](ECHO_INTERFACE_SIMPLIFICATION_V1.md), and
[ECHO_HONEST_INNER_STATE_V1.md](ECHO_HONEST_INNER_STATE_V1.md) for what it does and known
limitations.

## Frontend (TypeScript)

From `frontend/`:

```bash
npm install
npm run build       # tsc -b (type check) && vite build — this is the real gate
npm run typecheck   # tsc -b --noEmit — same type check, no build output
npm run dev         # local dev server
```

There's no ESLint configured yet — `tsc -b` (via `build` or `typecheck`) is the current
quality gate on the frontend. Adding ESLint would be a reasonable future addition but
isn't set up today; don't assume `npm run lint` exists. There's also no `npm run test`
(no Vitest/Jest configured) — frontend correctness is currently verified by the type
checker plus manual/browser testing, not an automated test suite.

`npm install` reports 8 known vulnerabilities in transitive dependencies (2 moderate, 6
high) as of 2026-07-13 — pre-existing, not introduced by any recent work. Run `npm audit`
for details before deciding whether `npm audit fix` is worth the risk of a breaking
transitive version bump; it hasn't been applied here since it wasn't tested.

## Native app builds (Android / Windows)

Both native builds run on top of the same web build — `npm run build` produces
`frontend/dist/`, which Capacitor/Tauri then package. **Always set the correct
`VITE_API_BASE_URL` in `frontend/.env` *before* building for a native target** — it's
baked into the JS bundle at build time, not read at runtime:
- Android emulator: `http://10.0.2.2:8000` (the emulator's alias for the host machine;
  `localhost` inside the app means the device itself, not your dev machine).
- Android physical device / Windows on another machine: your host's LAN or Tailscale IP,
  e.g. `http://100.x.x.x:8000`.
- Windows app running on the same machine as the backend: `http://localhost:8000` is fine.

**Android:**
```bash
cd frontend
npm run build
npx cap sync android
cd android
./gradlew.bat assembleDebug   # or gradlew on macOS/Linux
```
APK output: `frontend/android/app/build/outputs/apk/debug/app-debug.apk`

`@capacitor/android`'s bundled Gradle module requires **JDK 21+** to compile
(`sourceCompatibility JavaVersion.VERSION_21`) — if `JAVA_HOME` points at an older JDK
(17 is common), the build fails with `invalid source release: 21`. Point `JAVA_HOME` at
a JDK 21+ install for this one command if needed, e.g. on Windows:
```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot"
```

**Windows (Tauri):**
```bash
cd frontend
npm run tauri build
```
Requires the Rust toolchain (`rustc`/`cargo`) installed. Output installer(s) under
`frontend/src-tauri/target/release/bundle/` (`.msi`/`.exe` depending on target). If a
previously-built `app.exe` is still running, the build fails trying to overwrite it —
close it first.

Both `capacitor.config.ts`'s `appId` and `tauri.conf.json`'s `identifier` are
`com.godtear.echo` — a leftover from the pre-rename codebase, left as-is deliberately.
Changing either is a breaking change (existing installs, Play Store/signing identity)
and isn't done casually; the user-visible app name/title (`ECHO`) is what's kept current.

## How to back up ECHO data before upgrading

All persisted state lives under `backend/data/` (created by `app/config.py`'s
`DATA_DIR`, gitignored):
- `backend/data/echo.db` — SQLite, the source of truth for conversations, Atlas
  memories, Projects, Tasks, Schedule items, Library records, and everything else.
- `backend/data/chroma/` — ChromaDB's persisted vector index (a mirror of Atlas/
  conversation content for semantic search, rebuilt from SQLite if lost — but faster to
  just copy it).
- `backend/data/attachments/` — uploaded files, generated images, and other binary
  attachments referenced by SQLite rows.

Before pulling a new version or running a schema-affecting change, stop the backend and
copy the whole `backend/data/` directory somewhere safe. New tables (like ECHO Personal
OS v1's `projects`/`tasks`) are added via SQLAlchemy's `Base.metadata.create_all()` on
startup, which only creates tables that don't exist yet — it never drops or alters an
existing table, so upgrading in place is safe, but a backup costs nothing and covers you
against anything unexpected.

## Recommended pre-commit workflow

No `pre-commit` framework is installed (would be one more dependency for a
single-developer local project) — instead, before committing:

```bash
# backend changes
cd backend && pytest && ruff check .

# frontend changes
cd frontend && npm run build
```

Fix anything ruff flags (or run `ruff check . --fix` for the safe ones) and make sure
tests/build are green before committing.

## Recommended git commit workflow

- Small, focused commits over one giant one — makes `git log`/`git blame` actually useful
  later.
- Write the *why*, not just the *what*, in the commit message body when it's not obvious
  from the diff alone.
- Run the checks above before committing, not after — cheaper to fix locally than to
  discover later.
- Don't commit `backend/data/` (SQLite + Chroma persisted state), `.env` files, or
  `node_modules/` / `.venv/` — check `.gitignore` covers these before adding new
  directories that might need the same treatment.
