import { useEffect, useState } from "react";
import { MemoryExtractionLogOut, listMemoryDiagnostics } from "../../api/client";

// Human-readable outcome summary for one memory-extraction attempt — mirrors
// exactly what app/memory_extraction.py's parse_memory_json_with_diagnostics()
// and routers/chat.py's _extract_memory() actually decided, not a guess.
function outcomeLabel(log: MemoryExtractionLogOut): { text: string; tone: "ok" | "info" | "muted" } {
  if (log.saved) {
    return { text: log.explicit_request ? "Saved (explicit request)" : "Saved", tone: "ok" };
  }
  if (log.parse_succeeded) {
    return { text: "Queued as a memory candidate", tone: "info" };
  }
  return { text: log.rejection_reason || "Not saved", tone: "muted" };
}

const TONE_CLASSES: Record<"ok" | "info" | "muted", string> = {
  ok: "text-emerald-400",
  info: "text-blue-400",
  muted: "text-zinc-500",
};

// Small debug/diagnostics section answering "why isn't Atlas remembering more?" —
// collapsed by default, not a dashboard.
export default function MemoryDiagnostics() {
  const [logs, setLogs] = useState<MemoryExtractionLogOut[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      setLogs(await listMemoryDiagnostics(20));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm text-zinc-200"
      >
        <span className="font-medium">Debug: Memory Extraction</span>
        <span className="text-zinc-500">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="space-y-1.5 border-t border-zinc-800 p-3">
          <p className="mb-1 text-[11px] text-zinc-500">
            Recent chat turns and what happened when Echo considered saving a memory.
          </p>
          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
          {logs.length === 0 && !error && (
            <p className="py-3 text-center text-xs text-zinc-500">No memory-extraction activity yet.</p>
          )}
          {logs.map((log) => {
            const outcome = outcomeLabel(log);
            return (
              <div
                key={log.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs"
              >
                <span className="text-zinc-500">{new Date(log.created_at).toLocaleTimeString()}</span>
                <span className={`flex-1 truncate text-right ${TONE_CLASSES[outcome.tone]}`}>
                  {outcome.text}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
