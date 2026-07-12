import { useEffect, useState } from "react";
import { getUsage, UsageSummary } from "../../api/client";

// A 429 counts as "rate limited right now" only within this window — otherwise a
// 429 from hours ago would keep showing as if it were still happening.
const RECENT_429_WINDOW_MS = 5 * 60 * 1000;
const POLL_MS = 30_000;

function isRecentlyRateLimited(last429At: string | null): boolean {
  if (!last429At) return false;
  return Date.now() - new Date(last429At).getTime() < RECENT_429_WINDOW_MS;
}

function label(provider: string): string {
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

// Small, unobtrusive per-provider usage list — a status readout, not a dashboard.
// Only ever shows providers /api/usage actually returns (i.e. ones with a key set).
export default function UsageStatus() {
  const [usage, setUsage] = useState<UsageSummary>({});
  const [open, setOpen] = useState(false);

  async function refresh() {
    try {
      setUsage(await getUsage());
    } catch {
      // Usage is a nice-to-have status readout — a failed fetch just leaves the
      // last-known values in place rather than surfacing an error anywhere.
    }
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_MS);
    return () => clearInterval(interval);
  }, []);

  const providers = Object.entries(usage);
  if (providers.length === 0) return null;

  const anyRateLimited = providers.some(([, u]) => isRecentlyRateLimited(u.last_429_at));

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Model usage today"
        className={`flex h-8 items-center gap-1 rounded-lg px-2 text-xs transition-colors ${
          anyRateLimited
            ? "text-amber-400 hover:bg-amber-950/30"
            : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
        }`}
      >
        📊 <span className="hidden lg:inline">Usage</span>
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-10 w-56 rounded-lg border border-zinc-800 bg-zinc-900 p-2 shadow-lg">
          <div className="mb-1 px-1 text-[10px] uppercase tracking-wide text-zinc-600">
            Requests today
          </div>
          <div className="space-y-1">
            {providers.map(([provider, u]) => {
              const limited = isRecentlyRateLimited(u.last_429_at);
              return (
                <div key={provider} className="flex items-center justify-between px-1 text-xs">
                  <span className={limited ? "text-amber-400" : "text-zinc-300"}>
                    {label(provider)}
                  </span>
                  {limited ? (
                    <span className="text-amber-400">rate limited now</span>
                  ) : (
                    <span className="text-zinc-500">{u.requests_today}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
