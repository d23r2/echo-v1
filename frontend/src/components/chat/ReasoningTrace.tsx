import { useState } from "react";
import { AtlasCitation } from "../../api/client";

export default function ReasoningTrace({
  reasoning,
  citations,
}: {
  reasoning: string | null;
  citations: AtlasCitation[];
}) {
  const [open, setOpen] = useState(false);
  if (!reasoning && citations.length === 0) return null;

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-zinc-500 hover:text-zinc-300"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>Reasoning{citations.length > 0 ? ` & ${citations.length} Atlas memory` : ""}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
          {reasoning && <p className="whitespace-pre-wrap text-zinc-400">{reasoning}</p>}
          {citations.length > 0 && (
            <div className="space-y-1 border-t border-zinc-800 pt-2">
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
          )}
        </div>
      )}
    </div>
  );
}
