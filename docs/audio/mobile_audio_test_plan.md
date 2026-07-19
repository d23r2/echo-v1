# ECHO Mobile Audio — Test Plan

Read-only audit findings and the fix/verification plan for the mobile voice input/output diagnosis
task. Written before any functional code change, per the task's own mandate.

## 1. Current audio architecture (confirmed by direct code inspection, not assumption)

**Voice input**: **(A) Browser `SpeechRecognition`/`webkitSpeechRecognition` API only.** No fallback
exists — confirmed zero occurrences of `MediaRecorder`, `getUserMedia`, `isTypeSupported`, or any
backend STT endpoint anywhere in the repo (`frontend/` and `backend/` both). Implementation lives
entirely in `frontend/src/components/chat/ChatView.tsx`:
- `SpeechRecognitionCtor` (module scope, line 89-90) — resolved once at module load from
  `window.SpeechRecognition || window.webkitSpeechRecognition`.
- `startListening()`/`stopListening()`/`toggleListening()` (lines 347-421) — creates a fresh
  `SpeechRecognitionCtor` instance per session, `lang="en-US"` hardcoded, `interimResults: true`,
  `continuous: true`. Transcript is written directly into the chat's `input` textbox — never sent as
  audio anywhere.
- `armSilenceTimer()` auto-stops after 1800ms of silence.
- Error mapping exists for `no-speech`/`audio-capture`/`not-allowed`/`service-not-allowed` (lines
  384-397) but falls through to a generic `Voice input error: ${event.error}` for anything else, and
  **the mic control disappears entirely with zero message** when `SpeechRecognitionCtor` is falsy
  (unsupported browser) — `ChatActionMenu.tsx` line 84's `{voiceSupported && (...)}`.

**Voice output**: **(A) Browser `speechSynthesis` only.** No backend TTS, no audio file/blob, no
streaming. Same file:
- Voice-list loading (lines 283-301) correctly handles the async `voiceschanged` event.
- `speak(text)` (lines 303-315) strips markdown, builds a `SpeechSynthesisUtterance`, calls
  `window.speechSynthesis.speak(utterance)`. **No autoplay-block detection exists at all** — `onerror`
  only sets `isSpeaking = false`, never distinguishes a blocked/`not-allowed` failure from a normal end,
  and there is no "tap to play" fallback.
- All three call sites (lines 486, 520, 593) fire `speak()` from inside an `async` function **after an
  `await`** on the backend response — i.e. outside the synchronous stack of the click/keypress that
  started the send. This is the single most likely reason TTS silently does nothing on mobile Safari,
  which requires speech synthesis to originate within an active user-activation window.

**Backend involvement**: none for actual audio. `voice_mode`/`tts_enabled` (`PersonaSettings`) only
reshape response *text* (shorter, less markdown-heavy) via `persona_service.py`'s `voice_first` flag —
confirmed no code path sends or receives audio bytes.

## 2. Supported / unsupported browsers (as currently implemented)

- **Supported (voice input)**: desktop Chrome/Edge, Android Chrome (real Chrome, not embedded WebView).
- **Unsupported/unreliable (voice input)**: iOS Safari (and therefore every iOS browser, all WebKit),
  Android Firefox, the Capacitor Android WebView (`android.webkit.WebView` doesn't implement the Web
  Speech API even though system Chrome does) — confirmed no `RECORD_AUDIO` permission is even declared
  in `frontend/android/app/src/main/AndroidManifest.xml`.
- **Voice output**: `speechSynthesis` has broad support including iOS Safari, but iOS enforces stricter
  user-activation requirements for playback than desktop — the missing autoplay handling above is
  therefore an iOS-specific likely failure even where the API itself is "supported."

## 3. Likely root causes (to verify, not assumed)

1. **No unsupported/insecure-context messaging for voice input** — the mic control just vanishes with
   no explanation, violating the "distinguish unsupported/permission-denied/insecure-context, don't
   show one generic error" requirement.
2. **No autoplay-block handling for TTS** — `speak()` calls fire outside the originating gesture with
   no `onstart`-watchdog, no `not-allowed` handling, no manual fallback control. This is the most
   likely explanation for "ECHO is not speaking responses back."
3. **Insecure-context deployment**: `frontend/src/api/client.ts`'s `resolveBaseUrl()`,
   `capacitor.config.ts`'s `androidScheme: 'http'`, and `vite.config.ts`'s `host: true` are all built
   around serving/reaching ECHO over plain `http://<LAN-ip>` rather than HTTPS — most mobile browsers
   treat that as a non-secure context and refuse microphone access regardless of `SpeechRecognition`
   support. **This is infrastructure/deployment configuration, not something this pass changes** (per
   the task's own "do not change production configuration" rule) — the fix here is limited to
   *detecting* this condition and telling the user clearly, not changing how ECHO is served.
4. **Stale service-worker cache**: `frontend/public/sw.js` caches the app shell under a static,
   never-bumped key (`"echo-shell-v1"`) — any fix could appear not to have taken effect on an
   already-visited phone until a hard reload/cache-clear. Documented as an operational note, not
   changed this pass (out of scope — a cache-versioning overhaul is a larger change than "smallest
   necessary fix" justifies for this diagnosis).

## 4. Test matrix

| # | Case | Method | Expected |
|---|---|---|---|
| T-1 | `SpeechRecognitionCtor` undefined | Chromium emulation, mock `window.SpeechRecognition`/`webkitSpeechRecognition` removed | Mic control shown disabled with "not supported in this browser" reason, not silently hidden |
| T-2 | `window.isSecureContext === false` | Emulation, override `isSecureContext` | Mic control shown disabled with "requires a secure connection" reason |
| T-3 | Permission denied | Emulation, mock `recognition.onerror({error: "not-allowed"})` | Existing message unchanged ("Microphone access was denied.") |
| T-4 | TTS blocked (no `onstart` fires) | Emulation, mock `speechSynthesis.speak()` to never fire `onstart`/`onend` | Fallback "Tap to hear reply" control appears after the watchdog window; text reply remains visible regardless |
| T-5 | TTS `onerror` with `not-allowed` | Emulation, mock utterance `onerror({error: "not-allowed"})` | Same fallback control appears |
| T-6 | TTS succeeds normally | Emulation, mock `onstart` firing promptly | No fallback control shown; speaking indicator behaves as before |
| T-7 | Regression | Existing voice-adjacent behavior (silence-timer, error mapping, markdown stripping) | Unchanged |

## 5. Fixtures / mocking approach

Frontend unit tests (Vitest + Testing Library, already introduced in this repo's Supervised Maintenance
Phase 6) with `window.SpeechRecognition`/`webkitSpeechRecognition`/`window.speechSynthesis` mocked per
the existing convention (`vi.stubGlobal` or direct property assignment on `window`), matching how
`SupervisedMaintenanceView.test.tsx` already mocks `../../api/client`.

## 6. Privacy precautions

No real audio is recorded or used in any test — every test drives mocked browser APIs. No change to
what data ECHO's backend receives (still nothing — voice stays 100% client-side, confirmed and
preserved by this pass's fixes).

## 7. Real-device coverage (explicit limitation)

This environment has no physical Android/iPhone device. Per user direction, this pass diagnoses and
fixes via code inspection plus Chromium mobile-viewport emulation (Browser pane), and marks the
required real-device matrix rows as "not run — needs your device" rather than claiming device-level
verification that didn't happen.

## 8. Stop conditions

Per the task's own list: do not auto-enable the microphone, do not weaken CSP/Permissions-Policy
(none exist to weaken), do not add a paid speech API, do not add a billing dependency, do not bypass
HTTPS by hacking around the secure-context check.
