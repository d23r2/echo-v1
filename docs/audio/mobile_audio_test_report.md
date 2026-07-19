# Mobile Audio Diagnosis — Test Report

## Overall Status: YELLOW

Root causes identified and the two "smallest necessary" fixes within current voice-feature scope are implemented, unit-tested, and verified live in emulation. Status is YELLOW rather than GREEN because **no physical mobile device or real mobile browser was used** — see [Environment](#environment) and [Real-Device Results](#real-device-results). The fixes address the two most likely causes of "can't speak to ECHO" / "ECHO won't speak back" on mobile, but that cannot be called fully resolved without a real-device pass.

## Environment

- **Test harness**: In-app Browser pane only (Chromium-based, desktop rendering engine), viewport forced to 375×812 (mobile preset) via `resize_window`.
- **No physical mobile devices were available or used.** No real iOS Safari, no real Android Chrome/Firefox/Samsung Internet.
- Per an earlier standing agreement with the user, this task's mandate was: diagnose and fix via code + emulation; the user verifies on real devices.
- Frontend dev server (Vite, port 5174) and the existing `echov1-backend-1` Docker backend (port 8000) were used directly — voice is 100% client-side, so no backend changes or version-matching were required for this task. (An unrelated, pre-existing version mismatch between that Docker image and current source causes background `interface-settings`/`mission-control` 404s; confirmed non-blocking for chat/voice.)

## Current Architecture

Confirmed via exhaustive grep across the repo before any code change:

- **Voice input**: browser `SpeechRecognition` / `webkitSpeechRecognition` (Web Speech API) only. No `MediaRecorder`, no `getUserMedia`, no backend speech-to-text anywhere in the codebase.
- **Voice output**: browser `speechSynthesis` / `SpeechSynthesisUtterance` only. No backend text-to-speech.
- Both live entirely in [ChatView.tsx](../../frontend/src/components/chat/ChatView.tsx); the "+" action menu ([ChatActionMenu.tsx](../../frontend/src/components/chat/ChatActionMenu.tsx)) exposes voice input, the header exposes a "Voice replies" toggle for output.

Full architecture audit: [mobile_audio_test_plan.md](mobile_audio_test_plan.md).

## Root Causes Found

1. **No unsupported/insecure-context messaging.** The mic control previously just vanished (`voiceSupported` boolean hid the menu item) when `SpeechRecognition` was unavailable or the page wasn't a secure context, with no explanation. A user on an unsupported mobile browser, or reaching ECHO over plain HTTP on a LAN IP, would see no mic option and no indication why — reads as "can't speak to ECHO."
2. **TTS autoplay/gesture-activation block, undetected.** `speak()` calls were fired asynchronously after an `await` on the chat network response — outside the original click's user-gesture window. Mobile browsers (notably iOS Safari) can silently drop `speechSynthesis.speak()` calls made outside an active gesture stack, with no error surfaced to the app. This reads as "ECHO not speaking responses back," silently.
3. **Deliberately insecure deployment context** (HTTP on a LAN IP, per `capacitor.config.ts`'s `androidScheme: 'http'` and `vite.config.ts`'s `host: true`) is itself a plausible cause of `getUserMedia`/`SpeechRecognition` unavailability on strict mobile browsers, but this is existing infrastructure the task does not have license to redesign — surfaced as an explicit, user-facing reason string instead (see Fix 1).
4. **Stale service-worker cache** (`frontend/public/sw.js`, hardcoded `"echo-shell-v1"` cache key, never bumped) — confirmed live via `caches.keys()` to actually serve a stale bundle baked with an old `.env` API port in at least one session. This is a real defect but is orthogonal to the voice architecture itself; not fixed this pass (out of the "smallest necessary" scope for the voice task), documented as a remaining limitation below.

## Voice Input Results

| Scenario | Result |
|---|---|
| Chromium desktop-engine browser, mobile viewport, `localhost` (secure context), `webkitSpeechRecognition` present | Mic control renders **enabled** with plain "🎤 Voice input" label — confirmed live (see Tests Executed). |
| Unsupported browser (no `SpeechRecognition`/`webkitSpeechRecognition`) | Mic control renders **disabled** with reason `"Voice input (not supported in this browser)"`, `title` attribute set, click is a no-op. Confirmed via unit test, not live (see Real-Device Results — this environment's engine always has `webkitSpeechRecognition`, so the "unsupported" path can't be forced live without overriding the constructor before module load, which the harness can't do post-navigation). |
| Insecure context (HTTP on a non-localhost host) | Mic control renders **disabled** with reason `"Voice input (requires a secure connection (HTTPS) on mobile)"`. `toggleListening()` also short-circuits with a chat-level error banner if triggered by keyboard/programmatically. Confirmed via unit test; not reproducible live in this harness for the same reason as above. |
| Voice mode off in Settings | Mic control renders disabled with reason `"turned off in Settings"`. Confirmed via unit test. |

## Voice Output Results

| Scenario | Result |
|---|---|
| `speechSynthesis.speak()` succeeds normally (fires `onstart`) | No banner; unaffected by this change (not separately re-verified live this pass — no regression risk since the watchdog only acts when `onstart` never fires). |
| `speechSynthesis.speak()` silently blocked (mocked to simulate a mobile autoplay/gesture block — `onstart` never fires) | **Confirmed live**: after the ~1.2s watchdog window, an amber "Your browser blocked automatic audio." banner with a "▶ Tap to play" button appears. Clicking it re-issues `speak()` synchronously from the click handler (gesture-satisfying), confirmed via a second `speak()` call being observed. |
| `onerror` fires with `event.error === "not-allowed"` | Same blocked-banner path triggers immediately (code-reviewed, not separately forced live — same code path as the watchdog case, lower incremental risk). |

## Browser Compatibility Matrix

| Browser | Voice input | Voice output | Notes |
|---|---|---|---|
| Chromium desktop engine (this harness, mobile viewport) | Supported, verified live | Supported, verified live (incl. block-and-recover) | Not a real mobile engine. |
| iOS Safari (real device) | Not run | Not run | Known constraints: `webkitSpeechRecognition` absent on iOS Safari historically; `speak()` gesture policy is strict — this is the fix's primary target and is unverified on real hardware. |
| Android Chrome (real device) | Not run | Not run | Generally the best-supported mobile combination for Web Speech API; still unverified here. |
| Android Firefox / Samsung Internet (real device) | Not run | Not run | Not attempted. |

## Tests Executed

### Automated Test Results

- `frontend/src/components/chat/ChatActionMenu.test.tsx` (new, 6 tests): mic control enabled/plain-label when available; disabled with each distinct reason string (unsupported, insecure-context, off-in-settings) instead of vanishing; click no-ops when disabled; click fires `onToggleVoice` when enabled; "Stop voice input" label while listening.
- Full frontend suite: **10/10 tests passed** (`npm run test -- --run`, 2 test files, 2.42s).
- `npm run build` (`tsc -b && vite build`): passed clean, no type errors. Pre-existing >500kB chunk-size warning only, unrelated to this change.

### Manual / Live Browser Verification (this session)

All performed in the Browser pane, 375×812 mobile viewport, against the live dev server + existing Docker backend:

1. Cleared a stale service-worker cache (`caches.delete()` + `unregister()`) in a fresh tab and confirmed a clean reload with no residual stale-port requests — ruled out a caching artifact as a confound before testing.
2. Opened a chat conversation; opened the "+" action menu; confirmed "🎤 Voice input" renders enabled with the plain label (happy path, matches the "available" branch of the fix).
3. Toggled "Voice replies" on.
4. Mocked `window.speechSynthesis.speak` to accept the call but never fire `onstart`/`onend` (simulating a mobile autoplay block).
5. Sent a chat message; after the response arrived and the watchdog window elapsed, confirmed the "Your browser blocked automatic audio." banner and "▶ Tap to play" button appeared in the DOM.
6. Clicked "▶ Tap to play"; confirmed a second `speak()` invocation was recorded, proving the retry path re-issues the utterance from a real click-gesture context.

## Real-Device Results

**Not run.** No physical mobile device was used or is available in this environment. All matrix rows above marked "Not run" require the user's own device testing per the standing agreement for this task. This is the primary reason Overall Status is YELLOW and not GREEN.

## Performance

Not separately profiled — the fixes add a single `setTimeout` watchdog (cleared on `onstart`/`onend`/`onerror`/unmount) and a derived string computation per render; no measurable performance impact expected or observed during live testing.

## Privacy and Security

- No new network calls, no new data collection. Voice input/output remain 100% client-side (browser Web Speech APIs only).
- No microphone or audio data is transmitted, logged, or persisted by these changes.
- No new third-party or paid API was introduced.

## Fixes Applied

Both are UI-messaging / robustness fixes within the existing SpeechRecognition/speechSynthesis architecture — no architecture redesign, per the task's "smallest necessary fix" mandate.

1. **Explicit unavailability reasons for voice input** ([ChatView.tsx](../../frontend/src/components/chat/ChatView.tsx), [ChatActionMenu.tsx](../../frontend/src/components/chat/ChatActionMenu.tsx)): `voiceUnavailableReason` (turned off in Settings / not supported in this browser / requires HTTPS on mobile / available) replaces the old boolean-hide behavior. The mic menu item now always renders, disabled with a `title` and inline reason text when unavailable, matching the existing pattern already used for image generation and the camera placeholder in the same menu.
2. **TTS autoplay-block detection and manual recovery** ([ChatView.tsx](../../frontend/src/components/chat/ChatView.tsx)): a watchdog started alongside each `speak()` call flags a blocked utterance if `onstart` doesn't fire within 1.2s (or if `onerror` reports `not-allowed`), surfacing an amber "Your browser blocked automatic audio." banner with a "▶ Tap to play" button that re-issues the utterance synchronously from the click handler — satisfying mobile browsers' user-gesture requirement for audio playback.

## Remaining Limitations

- **No real mobile device or mobile browser was used.** This is the single largest gap — the fixes target well-documented mobile browser behaviors (secure-context requirements, autoplay/gesture policies) but are unverified against real iOS Safari / Android Chrome.
- The "unsupported browser" and "insecure context" messaging paths were verified only via unit test (mocked props), not live in a browser that actually lacks `SpeechRecognition` or actually runs on an insecure origin — this harness's engine has neither condition and the harness cannot override a page's secure-context state.
- The insecure-context (plain HTTP on a LAN IP) deployment pattern itself was not changed — it remains a plausible root cause of voice input failing entirely on strict mobile browsers, but redesigning ECHO's HTTP/HTTPS deployment story is out of scope for this pass and was called out to the user as a design decision, not silently left broken.
- The stale service-worker cache key (`"echo-shell-v1"`, never bumped) was confirmed live to cause stale-bundle serving in at least one session, but was not fixed this pass (out of scope for the voice-specific task).
- No regression test was added for the "happy path" TTS case (`onstart` firing normally) — the watchdog's clear-on-`onstart` logic was code-reviewed but not separately exercised live beyond the blocked-path test, since the blocked-path test already proves the watchdog fires only when `onstart` doesn't.

## Final Recommendation

Ship the two fixes — they are low-risk, additive, and directly address the two most likely mobile failure modes without touching the underlying architecture. **Before closing this out as fully resolved, the user should test on at least one real iOS Safari device and one real Android Chrome device**, specifically: (a) whether the mic control now shows a clear reason instead of silently vanishing wherever it's unavailable, and (b) whether a voice reply that would previously have failed silently now either plays normally or shows the "Tap to play" recovery banner. If real-device testing surfaces a case neither fix's reason-string or watchdog-timeout values account for (e.g. a browser that fires `onstart` late but past 1.2s, causing a false-positive "blocked" banner), the watchdog timeout is the first place to tune.
