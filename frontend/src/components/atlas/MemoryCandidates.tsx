import { useEffect, useState } from "react";
import {
  MemoryCandidateOut,
  acceptMemoryCandidate,
  editMemoryCandidate,
  listMemoryCandidates,
  rejectMemoryCandidate,
} from "../../api/client";

// A small, self-contained review queue for auto-extracted (implicit) memories —
// explicit "remember that..." requests bypass this entirely and save straight to
// Atlas, same as before. Kept separate from the main Atlas entry list/search
// above since these aren't real memories yet, just candidates awaiting a decision.
export default function MemoryCandidates() {
  const [candidates, setCandidates] = useState<MemoryCandidateOut[]>([]);
  const [open, setOpen] = useState(false);
  const [onlyConflicts, setOnlyConflicts] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      setCandidates(await listMemoryCandidates("pending"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  async function handleAccept(id: string) {
    await acceptMemoryCandidate(id);
    refresh();
  }

  async function handleReject(id: string) {
    await rejectMemoryCandidate(id);
    refresh();
  }

  function startEdit(candidate: MemoryCandidateOut) {
    setEditingId(candidate.id);
    setEditDraft(candidate.content);
  }

  async function saveEdit(id: string) {
    await editMemoryCandidate(id, { content: editDraft });
    setEditingId(null);
    refresh();
  }

  const displayed = onlyConflicts ? candidates.filter((c) => c.conflict_with.length > 0) : candidates;
  const conflictCount = candidates.filter((c) => c.conflict_with.length > 0).length;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm text-zinc-200"
      >
        <span className="font-medium">
          Memory Candidates{candidates.length > 0 && ` (${candidates.length})`}
        </span>
        <span className="flex items-center gap-2">
          {conflictCount > 0 && (
            <span className="rounded-full bg-amber-900/50 px-2 py-0.5 text-[10px] text-amber-300">
              {conflictCount} conflict{conflictCount === 1 ? "" : "s"}
            </span>
          )}
          <span className="text-zinc-500">{open ? "▾" : "▸"}</span>
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-zinc-800 p-3">
          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={onlyConflicts}
              onChange={(e) => setOnlyConflicts(e.target.checked)}
              className="accent-accent"
            />
            Show only conflicts
          </label>

          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          {displayed.length === 0 && (
            <p className="py-4 text-center text-xs text-zinc-500">
              {onlyConflicts ? "No pending candidates with conflicts." : "No pending memory candidates."}
            </p>
          )}

          {displayed.map((c) => (
            <div key={c.id} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-500">
                <span className="rounded bg-zinc-800 px-1.5 py-0.5">{c.epistemic_status}</span>
                <span className="rounded bg-zinc-800 px-1.5 py-0.5">{c.memory_type}</span>
                <span>confidence {(c.confidence * 100).toFixed(0)}%</span>
                {c.conflict_with.length > 0 && (
                  <span className="rounded-full bg-amber-900/50 px-2 py-0.5 text-amber-300 normal-case tracking-normal">
                    ⚠ {c.conflict_with.length} possible conflict{c.conflict_with.length === 1 ? "" : "s"}
                  </span>
                )}
              </div>

              {editingId === c.id ? (
                <textarea
                  value={editDraft}
                  onChange={(e) => setEditDraft(e.target.value)}
                  rows={2}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
                />
              ) : (
                <p className="text-sm text-zinc-200">{c.content}</p>
              )}

              <p className="mt-1.5 text-[10px] text-zinc-600">source: {c.source || "unknown"}</p>

              <div className="mt-2 flex gap-2">
                {editingId === c.id ? (
                  <>
                    <button
                      onClick={() => saveEdit(c.id)}
                      className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-zinc-950"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-900"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => handleAccept(c.id)}
                      className="rounded-md bg-emerald-800 px-2.5 py-1 text-xs font-medium text-emerald-50 hover:bg-emerald-700"
                    >
                      Accept
                    </button>
                    <button
                      onClick={() => startEdit(c)}
                      className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-900"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleReject(c.id)}
                      className="rounded-md border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/50"
                    >
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
