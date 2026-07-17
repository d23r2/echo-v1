/**
 * ECHO Layer 0 — lightweight frontend logging wrapper.
 *
 * In production builds, debug/info are suppressed (console noise a real
 * user would never want to see); warn/error always show, since those
 * matter for diagnosing a real problem. Never logs full user message
 * content or secrets — callers pass a short label plus safe metadata only
 * (matches the same discipline as backend/app/core/logging.py's
 * log_event()). Sends nothing externally — this is console-only.
 */

import { env } from "../config/env";

function safeArgs(args: unknown[]): unknown[] {
  // Defense in depth: truncate any accidentally-long string argument so a
  // caller that slips in raw user/prompt content doesn't dump it in full.
  return args.map((arg) => {
    if (typeof arg === "string" && arg.length > 200) {
      return arg.slice(0, 200) + "…(truncated)";
    }
    return arg;
  });
}

export const logger = {
  debug(...args: unknown[]) {
    if (!env.isDevelopment) return;
    console.debug("[echo]", ...safeArgs(args));
  },
  info(...args: unknown[]) {
    if (!env.isDevelopment) return;
    console.info("[echo]", ...safeArgs(args));
  },
  warn(...args: unknown[]) {
    console.warn("[echo]", ...safeArgs(args));
  },
  error(...args: unknown[]) {
    console.error("[echo]", ...safeArgs(args));
  },
};
