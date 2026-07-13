import { AtlasEntryOut } from "../../api/client";

const STATUS_COLORS: Record<string, string> = {
  Verified: "bg-emerald-500/15 text-emerald-400",
  Inferred: "bg-sky-500/15 text-sky-400",
  Hypothesis: "bg-amber-500/15 text-amber-400",
  Narrative: "bg-fuchsia-500/15 text-fuchsia-400",
};

const MEMORY_TYPE_COLORS: Record<string, string> = {
  fact: "bg-zinc-700/50 text-zinc-300",
  preference: "bg-sky-500/15 text-sky-400",
  mood: "bg-pink-500/15 text-pink-400",
  goal: "bg-emerald-500/15 text-emerald-400",
  fear: "bg-red-500/15 text-red-400",
  capability: "bg-indigo-500/15 text-indigo-400",
  project: "bg-amber-500/15 text-amber-400",
  relationship: "bg-purple-500/15 text-purple-400",
  event: "bg-teal-500/15 text-teal-400",
};

export default function AtlasEntryCard({
  entry,
  distance,
  conflictCount = 0,
  mergeSelected = false,
  onEdit,
  onDelete,
  onConfirm,
  onToggleOutdated,
  onToggleMergeSelect,
}: {
  entry: AtlasEntryOut;
  distance?: number | null;
  conflictCount?: number;
  mergeSelected?: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onConfirm?: () => void;
  onToggleOutdated?: () => void;
  onToggleMergeSelect?: () => void;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        entry.outdated ? "border-zinc-800/60 bg-zinc-900/30 opacity-60" : "border-zinc-800 bg-zinc-900/60"
      } ${mergeSelected ? "ring-1 ring-accent" : ""}`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            STATUS_COLORS[entry.epistemic_status] || "bg-zinc-800 text-zinc-400"
          }`}
        >
          {entry.epistemic_status}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            MEMORY_TYPE_COLORS[entry.memory_type] || "bg-zinc-800 text-zinc-400"
          }`}
        >
          {entry.memory_type}
        </span>
        <span className="text-[10px] text-zinc-500">
          confidence {Math.round(entry.confidence * 100)}%
        </span>
        {typeof distance === "number" && (
          <span className="text-[10px] text-zinc-600">match {(1 - distance).toFixed(2)}</span>
        )}
        {entry.outdated && (
          <span className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide bg-zinc-700 text-zinc-400">
            Outdated
          </span>
        )}
        {conflictCount > 0 && (
          <span className="rounded-full bg-amber-900/50 px-2 py-0.5 text-[10px] text-amber-300">
            ⚠ {conflictCount} possible conflict{conflictCount === 1 ? "" : "s"}
          </span>
        )}
        {entry.tags.map((t) => (
          <span key={t} className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
            #{t}
          </span>
        ))}
      </div>
      <p className="text-sm text-zinc-200">{entry.content}</p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-zinc-600">
        <span>
          {entry.source ? `source: ${entry.source} · ` : ""}
          observed {new Date(entry.observed_at).toLocaleDateString()}
        </span>
        <div className="flex flex-wrap gap-2">
          {onConfirm && entry.epistemic_status !== "Verified" && (
            <button onClick={onConfirm} className="hover:text-emerald-400">
              Confirm
            </button>
          )}
          {onToggleOutdated && (
            <button onClick={onToggleOutdated} className="hover:text-amber-400">
              {entry.outdated ? "Restore" : "Mark outdated"}
            </button>
          )}
          {onToggleMergeSelect && (
            <button onClick={onToggleMergeSelect} className={mergeSelected ? "text-accent" : "hover:text-zinc-300"}>
              {mergeSelected ? "Selected for merge" : "Select to merge"}
            </button>
          )}
          <button onClick={onEdit} className="hover:text-zinc-300">
            Edit
          </button>
          <button onClick={onDelete} className="hover:text-red-400">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
