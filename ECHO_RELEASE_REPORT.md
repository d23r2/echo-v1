# ECHO Release Report

## 1. Overall status: 🟡 Yellow

Backend and web app are Green — fully tested, fully verified, ready. Android is Green —
built and installable, with one manual config step required before it can reach a
backend (documented below, not a code defect). Windows is **blocked**, not failed: the
Tauri build environment is real and works, but the build couldn't complete because a
previous test build (`app.exe`) was still running and locking its own output file. That
requires either your go-ahead to close it or you closing it yourself — see §7.

## 2. Version / build date

- Backend: commit `dc56cf75` + this session's uncommitted fixes (see §6 for exact list).
- Build date: 2026-07-16.
- Frontend `package.json` version: `1.0.0`. Tauri `tauri.conf.json` version: `0.1.0`.

## 3. Commands run

```bash
# Backend
cd backend && pytest -q                       # ×3 across this pass, all stable
cd backend && ruff check . --fix               # 33 cosmetic findings auto-fixed
cd backend && mypy app                         # optional, non-blocking

# Web
cd frontend && npm run build
cd frontend && npm run typecheck

# Android
cd frontend && npm run build
cd frontend && npx cap sync android
cd frontend/android && JAVA_HOME="<jdk21+>" ./gradlew.bat assembleDebug

# Windows
cd frontend && npm run tauri build             # blocked — see §7
```

## 4. Results

| Check | Result |
|---|---|
| Backend tests | ✅ 393/393 passing, 3 consecutive full runs, no Chroma flake |
| Backend ruff | ✅ clean (33 pre-existing cosmetic findings auto-fixed) |
| Backend mypy | 🟡 15 findings, all the same pre-existing non-blocking typing-narrowness class documented in `DEVELOPMENT.md` — not a functional bug, not fixed (optional gate) |
| Frontend build | ✅ clean, 0 TypeScript errors |
| Frontend typecheck | ✅ clean |
| Android APK build | ✅ built successfully |
| Windows Tauri build | 🟡 blocked by a locked file from a prior test build — see §7 |

## 5. Artifact paths

- **Web production build**: `frontend/dist/` (`index.html`, `assets/`, `manifest.webmanifest`, `sw.js`, `icons/`)
- **Android debug APK**: `frontend/android/app/build/outputs/apk/debug/app-debug.apk` (built 2026-07-16, ~5.8MB)
- **Windows installer**: not produced this pass — see §7. Expected location once built: `frontend/src-tauri/target/release/bundle/`

## 6. Bugs found and fixed

1. **`.env.example`'s `CORS_ORIGINS` was missing the Tauri and Capacitor origins** —
   a fresh checkout following the example file would have working web/Docker CORS but
   broken Android/Windows CORS out of the box. Added `capacitor://localhost`,
   `https://localhost`, `tauri://localhost`, `http://tauri.localhost` to match what the
   real working `.env` already had.
2. **`GET /api/features` never exposed web search/wiki/RSS availability** — the only
   way to learn whether search was configured was to send a chat message and see what
   happened. Added `web_search_enabled` / `wiki_enabled` / `rss_enabled` (config-gated,
   mirroring the exact same checks `app/web_search.py`'s own provider functions use, so
   the flag never claims a source is ready when a real call would immediately fail) plus
   `library` / `schedule` (always-true, matching the existing `voice_input`/`file_upload`
   pattern) to `FeatureAvailability`. Updated the matching TypeScript interface too.
3. **Android build failed outright** — `@capacitor/android`'s Gradle module requires
   JDK 21+; the default `JAVA_HOME` on this machine points at JDK 17. Not a code bug,
   but genuinely blocked the build until diagnosed; documented the exact fix and added
   an Android/Windows build section to `DEVELOPMENT.md` since none existed before.
4. **App display name/title was "Echo" (mixed case) instead of "ECHO"** across
   `capacitor.config.ts`, Android's `strings.xml`, and `tauri.conf.json` — inconsistent
   with the web app's branding (browser title, PWA manifest) that was already correctly
   "ECHO". Fixed the display name/title in all three; deliberately left `appId`/
   `identifier` (`com.godtear.echo`) untouched — changing that is a breaking change
   (existing installs, signing identity) with no real benefit, and wasn't asked for.
5. **33 pre-existing cosmetic ruff findings** (`datetime.UTC` alias suggestions, import
   ordering) had accumulated since the last cleanup pass — auto-fixed, tests re-verified
   clean after.
6. **One test broke from the `FeatureAvailability` change** — a test's fake settings
   object (`SimpleNamespace`) didn't have the new fields the endpoint now reads; fixed
   the fake, and added a dedicated test (`test_search_flags_reflect_settings_not_just_
   enabled_toggle`) for the new flags' correctness, including the "enabled but not
   configured" edge case.

All of the above were verified with a full backend test re-run after each change (never
batched blind) — final count: 393/393 passing.

## 7. Bugs not fixed

- **Windows Tauri build didn't complete** — blocked by a running `app.exe` (PID 23100,
  a previous test build) locking its own output file. I don't kill arbitrary processes
  found by name-pattern search without your explicit go-ahead, and you haven't
  responded to that question yet. **To finish this**: close the running ECHO desktop
  window yourself (or tell me to stop it for you), then re-run `npm run tauri build`
  from `frontend/`. Everything else about the Windows build path is verified and ready —
  config is valid, branding is current, the Rust toolchain compiles the app successfully
  (it got past `Compiling app v0.1.0` before hitting the file-lock error).
- **Android APK's baked-in backend URL is `http://localhost:8000`**, which is correct
  for the web dev server but **will not reach anything from inside the Android app** —
  `localhost` there means the device itself. This isn't a code bug: `VITE_API_BASE_URL`
  is a build-time value that has to match your actual target (emulator vs. physical
  device vs. Tailscale). See §8's manual step and the new `DEVELOPMENT.md` section for
  exact values. I didn't rebuild with a guessed IP since I don't know which target
  you're testing against right now.

## 8. Known limitations

- **Ollama must be running locally** for the local-model fallback to work — it's an
  external service the app doesn't manage. `backend/.env`'s `OLLAMA_BASE_URL` must be
  `http://localhost:11434` for native runs, or `http://host.docker.internal:11434` for
  Docker Compose — these are different values for different launch methods (see
  README's "Ollama fallback + Docker" note).
- **SearXNG must be configured for real web search** — off by default, no billing, see
  `docs/searxng-setup.md`. Wiki works out of the box (public Wikimedia API, no key).
  RSS needs `RSS_FEED_URLS` set.
- **Image generation needs a configured provider** (Gemini/`GEMINI_API_KEY` is the only
  one that actually generates in this build) — shows a clean "unavailable" state
  otherwise, confirmed this pass.
- **No background OS notifications for Schedule reminders** — in-app only, reminders
  only surface while ECHO is open.
- **Android/Windows backend URL must be set correctly for your environment before
  building** — see §7 and the new `DEVELOPMENT.md` "Native app builds" section for exact
  values per target (emulator, physical device, same-machine desktop).
- **`appId`/`identifier` still say `com.godtear.echo`** — pre-rename leftover,
  deliberately not changed (breaking for existing installs/signing).

## 9. Manual test checklist

### Web
- [x] Open app — verified: loads, ECHO branding, clean welcome screen.
- [x] New chat, normal message — verified via API + rendered UI (Nikola Tesla example).
- [x] Reply shows only clean metadata — verified: `VIA OLLAMA, WIKIPEDIA, ATLAS`, no raw labels.
- [x] Search conversation — verified: title-filtered list, clean "TITLE" match label.
- [x] Open Library — verified: clean empty state, filter dropdown, no absolute paths.
- [x] Create Schedule item — verified: create → shows in Upcoming → Complete → moves to completed count.
- [x] Stable wiki query ("Who was Nikola Tesla?") — verified: `via Ollama, Wikipedia, Atlas`.
- [ ] Current-info query with SearXNG enabled — **you should verify**: point `.env` at a running SearXNG (see `docs/searxng-setup.md`) and ask something like "what's the latest news about X" — confirm `via Ollama, SearXNG` appears with real results.
- [ ] Memory query ("what did I tell you about...") — **you should verify** end-to-end with your own Atlas history.
- [x] Image generation unavailable state — verified: clean tooltip, no permanent cost banner, correctly enabled when Gemini is available.
- [x] Open + menu — verified: Attach file / Voice input / Generate image / "More tools coming later", all present.
- [ ] Attach a real file — **you should verify** (not exercised this pass).

### Android
- [ ] Install `frontend/android/app/build/outputs/apk/debug/app-debug.apk` on a device/emulator.
- [ ] **First, set `VITE_API_BASE_URL` correctly and rebuild** — see §7/§8, this APK as-built will not connect.
- [ ] Launch, confirm "ECHO" branding (label + title bar).
- [ ] Confirm backend connection works (send a normal message).
- [ ] Check sidebar/hamburger menu opens and all sections are reachable.
- [ ] Check + menu options.
- [ ] Confirm unavailable features (e.g. no SearXNG) show clean, not raw errors.

### Windows
- [ ] Close the currently-running ECHO desktop app (or authorize me to).
- [ ] Run `npm run tauri build` from `frontend/`.
- [ ] Launch the built app, confirm "ECHO" title bar.
- [ ] Confirm backend connection (same-machine `http://localhost:8000` should just work).
- [ ] Check sidebar, Library, Schedule, and the metadata line.

## 10. Next safe improvements

- Wire a real `10.0.2.2`/Tailscale-IP build variant (e.g. an `npm run build:android` script
  that temporarily swaps `VITE_API_BASE_URL`) so Android builds don't silently ship a
  `localhost` URL that can never work.
- Once the Windows build unblocks, do a real launch + chat smoke test and fold the
  result back into this report.
- `npm audit` on the 8 known transitive-dependency vulnerabilities (2 moderate, 6 high) —
  untouched this pass, pre-existing, documented in `DEVELOPMENT.md`.
