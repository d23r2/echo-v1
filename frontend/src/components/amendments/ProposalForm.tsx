import { useState } from "react";

export interface ProposalValue {
  title: string;
  text: string;
  rationale: string;
}

export default function ProposalForm({
  onCancel,
  onSubmit,
}: {
  onCancel: () => void;
  onSubmit: (value: ProposalValue) => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [rationale, setRationale] = useState("");

  return (
    <div className="space-y-3 rounded-xl border border-accent/40 bg-zinc-900 p-4">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Amendment title"
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
      />
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Proposed amendment text"
        rows={3}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
      />
      <textarea
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        placeholder="Rationale (optional)"
        rows={2}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 focus:border-accent focus:outline-none"
      />
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200">
          Cancel
        </button>
        <button
          onClick={() => onSubmit({ title, text, rationale })}
          disabled={!title.trim() || !text.trim()}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950 disabled:opacity-40"
        >
          Propose as Founder
        </button>
      </div>
    </div>
  );
}
