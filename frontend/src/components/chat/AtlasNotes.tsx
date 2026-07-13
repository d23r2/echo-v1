import { useState } from "react";
import { DisplayMessage } from "./ChatView";

// Honest, specific summary of what Atlas actually did on this turn — memories
// retrieved and used, what got saved/queued/skipped, and whether previous
// conversation history was consulted. Collapsed by default so the chat stays
// clean; hides entirely if there's nothing to show (e.g. an older reloaded
// message that predates this feature, or a turn where nothing happened).
export default function AtlasNotes({ message }: { message: DisplayMessage }) {
  const [open, setOpen] = useState(false);

  const citations = message.atlas_citations || [];
  const update = message.memory_update;
  const snippets = message.conversation_snippets || [];

  const hasAnything = citations.length > 0 || !!update || snippets.length > 0;
  if (!hasAnything) return null;

  const summaryParts: string[] = [];
  if (citations.length > 0) summaryParts.push(`${citations.length} memor${citations.length === 1 ? "y" : "ies"} used`);
  if (update?.saved) summaryParts.push("saved");
  if (update?.pending_review) summaryParts.push("candidate queued");
  if (snippets.length > 0) summaryParts.push("previous conversation used");

  return (
    <div className="mt-1 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-zinc-500 hover:text-zinc-300"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>Atlas notes{summaryParts.length > 0 ? ` — ${summaryParts.join(", ")}` : ""}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
          {citations.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-zinc-600">
                Memories retrieved &amp; used
              </p>
              <div className="space-y-1">
                {citations.map((c) => (
                  <div key={c.id} className="flex gap-2 text-zinc-500">
                    <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-accent">
                      {c.epistemic_status}
                    </span>
                    <span>
                      {c.content}{" "}
                      <span className="text-zinc-600">({Math.round(c.confidence * 100)}% confidence)</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {update && (
            <div className={citations.length > 0 ? "border-t border-zinc-800 pt-2" : ""}>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-zinc-600">This turn</p>
              {update.saved && (
                <p className="text-emerald-400">
                  📌 {update.explicit ? "Remembered" : "Noted for later"}: {update.content}
                </p>
              )}
              {!update.saved && update.pending_review && (
                <p className="text-blue-400">📋 Queued as a memory candidate for review in Atlas.</p>
              )}
              {!update.saved && !update.pending_review && update.explicit && update.error && (
                <p className="text-red-400">⚠️ Couldn't save that to Atlas: {update.error}</p>
              )}
              {!update.saved && !update.pending_review && !update.explicit && (
                <p className="text-zinc-500">No memory saved from this turn.</p>
              )}
            </div>
          )}

          {snippets.length > 0 && (
            <div className={citations.length > 0 || update ? "border-t border-zinc-800 pt-2" : ""}>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-zinc-600">
                Used previous conversation context
              </p>
              <div className="space-y-1.5">
                {snippets.map((s) => (
                  <div key={s.message_id} className="text-zinc-500">
                    <span className="text-zinc-600">
                      [{s.created_at ? new Date(s.created_at).toLocaleDateString() : "unknown date"}, "
                      {s.conversation_title}", {s.role}]{" "}
                    </span>
                    {s.snippet}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
