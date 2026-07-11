import { useState } from "react";
import { AtlasEntryOut, EpistemicStatus, MEMORY_TYPES, MemoryType } from "../../api/client";

const STATUSES: EpistemicStatus[] = ["Verified", "Inferred", "Hypothesis", "Narrative"];

export interface AtlasEntryFormValue {
  content: string;
  epistemic_status: EpistemicStatus;
  memory_type: MemoryType;
  tags: string[];
  confidence: number;
  source: string;
}

export default function AtlasEntryForm({
  initial,
  onCancel,
  onSubmit,
}: {
  initial?: AtlasEntryOut;
  onCancel: () => void;
  onSubmit: (value: AtlasEntryFormValue) => void;
}) {
  const [content, setContent] = useState(initial?.content ?? "");
  const [status, setStatus] = useState<EpistemicStatus>(initial?.epistemic_status ?? "Hypothesis");
  const [memoryType, setMemoryType] = useState<MemoryType>(initial?.memory_type ?? "fact");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [confidence, setConfidence] = useState(initial?.confidence ?? 0.5);
  const [source, setSource] = useState(initial?.source ?? "");

  return (
    <div className="rounded-xl border border-accent/40 bg-zinc-900 p-4 space-y-3">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="What should Atlas remember?"
        rows={3}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
      />
      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as EpistemicStatus)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          Type
          <select
            value={memoryType}
            onChange={(e) => setMemoryType(e.target.value as MemoryType)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
          >
            {MEMORY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          Confidence
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(e) => setConfidence(parseFloat(e.target.value))}
          />
          <span className="w-8 text-right">{Math.round(confidence * 100)}%</span>
        </label>
      </div>
      <div className="flex flex-wrap gap-3">
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="tags, comma, separated"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 focus:border-accent focus:outline-none"
        />
        <input
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="source (optional)"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 focus:border-accent focus:outline-none"
        />
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200">
          Cancel
        </button>
        <button
          onClick={() =>
            onSubmit({
              content,
              epistemic_status: status,
              memory_type: memoryType,
              tags: tags
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
              confidence,
              source,
            })
          }
          disabled={!content.trim()}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950 disabled:opacity-40"
        >
          Save
        </button>
      </div>
    </div>
  );
}
