import { useState } from "react";
import { EnvelopeStatus } from "../../api/client";

// Echo's own stated reasoning for this reply (from the REASONING: section of
// the envelope — see backend/app/envelope_stream.py and providers/base.py).
// Collapsed by default. If reasoning is genuinely absent because the provider
// didn't follow the envelope format, says so honestly instead of showing
// nothing (or, worse, inventing a reasoning value that was never returned) —
// but only when we actually know why (envelope_status + degradation_reason
// are set); older messages/pre-Phase-1 records with neither just render
// nothing, same as before.
export default function ReasoningTrace({
  reasoning,
  envelopeStatus,
  envelopeDegradationReason,
}: {
  reasoning: string | null;
  envelopeStatus?: EnvelopeStatus;
  envelopeDegradationReason?: string | null;
}) {
  const [open, setOpen] = useState(false);

  if (reasoning) {
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

  if (envelopeStatus && envelopeStatus !== "complete" && envelopeDegradationReason) {
    return (
      <div className="mt-2 px-1 text-[11px] italic text-zinc-600">
        Reasoning unavailable — {envelopeDegradationReason}
      </div>
    );
  }

  return null;
}
