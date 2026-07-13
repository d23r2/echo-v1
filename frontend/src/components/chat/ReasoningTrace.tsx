import { useState } from "react";

// Echo's own stated reasoning for this reply (from the REASONING: section of
// the envelope — see backend/app/envelope_stream.py and providers/base.py).
// Collapsed by default; hides entirely when there's no reasoning to show
// (e.g. a model that didn't follow the envelope format this turn).
export default function ReasoningTrace({ reasoning }: { reasoning: string | null }) {
  const [open, setOpen] = useState(false);
  if (!reasoning) return null;

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-zinc-500 hover:text-zinc-300"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>Reasoning</span>
      </button>
      {open && (
        <div className="mt-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
          <p className="whitespace-pre-wrap text-zinc-400">{reasoning}</p>
        </div>
      )}
    </div>
  );
}
