/**
 * ECHO Layer 0 — typed frontend environment/build configuration.
 *
 * `VITE_API_BASE_URL` itself is still resolved by api/client.ts's own
 * `resolveBaseUrl()` (it has LAN/Tailscale-hostname-matching logic this
 * module shouldn't duplicate) — this module is for everything else that
 * scattered `import.meta.env.VITE_*` reads would otherwise spread across
 * the codebase, plus a single place documenting what's intentionally NOT
 * here.
 *
 * Deliberately does not include "show advanced systems" or "developer
 * mode" — those are runtime, per-install settings backed by the
 * `InterfaceSettings` DB row (see api/client.ts's getInterfaceSettings()),
 * not Vite build-time env vars. A build-time flag and a runtime DB setting
 * for the same concept would just be two competing sources of truth.
 *
 * Never put a secret in a VITE_ variable — Vite inlines every VITE_-
 * prefixed variable into the built JS bundle, which ships to the browser
 * in plain text. This app has no frontend secrets today; keep it that way.
 */

export interface EchoEnv {
  appName: string;
  appEnv: "development" | "production" | "test";
  isDevelopment: boolean;
  isProduction: boolean;
}

function readAppEnv(): EchoEnv["appEnv"] {
  const raw = import.meta.env.VITE_APP_ENV;
  if (raw === "production" || raw === "test") return raw;
  return "development";
}

export const env: EchoEnv = {
  appName: import.meta.env.VITE_APP_NAME || "ECHO",
  appEnv: readAppEnv(),
  isDevelopment: readAppEnv() === "development",
  isProduction: readAppEnv() === "production",
};
