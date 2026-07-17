import { useEffect, useState } from "react";
import {
  archiveMemory,
  AtlasEntryOut,
  confirmMemory,
  deleteMemory,
  exportMemories,
  getMemoryStats,
  listMemories,
  listMemoryConflicts,
  markMemoryOutdated,
  MemoryCategory,
  MEMORY_CATEGORIES,
  MemoryConflictOut,
  MemoryLifecycleStatus,
  MemoryStatsOut,
  restoreMemory,
  resolveMemoryConflict,
  runMemoryMaintenance,
} from "../../api/client";

const STATUS_OPTIONS: MemoryLifecycleStatus[] = ["active", "archived", "superseded"];

const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  profile: "Profile", preference: "Preference", project: "Project", task: "Task",
  episodic: "Episodic", semantic: "Semantic", skill: "Skill", relationship: "Relationship",
  environment: "Environment", temporary: "Temporary",
};

function StatusBadge({ status }: { status: MemoryLifecycleStatus }) {
  const colors: Record<string, string> = {
    active: "text-emerald-400 border-emerald-900",
    archived: "text-zinc-400 border-zinc-700",
    superseded: "text-amber-400 border-amber-900",
    pending_review: "text-amber-400 border-amber-900",
    rejected: "text-red-400 border-red-900",
    deleted: "text-red-400 border-red-900",
  };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wide ${colors[status] || "text-zinc-400 border-zinc-700"}`}>
      {status}
    </span>
  );
}

function MemoryCard({ entry, onAction }: { entry: AtlasEntryOut; onAction: () => void }) {
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      onAction();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
        <span className="rounded-full border border-zinc-700 px-2 py-0.5">{CATEGORY_LABELS[entry.category] || entry.category}</span>
        <StatusBadge status={entry.status} />
        <span>{entry.epistemic_status}</span>
        <span>confidence {entry.confidence.toFixed(2)}</span>
        {entry.review_state === "pending_review" && (
          <span className="rounded-full border border-amber-900 px-2 py-0.5 text-amber-400">needs review</span>
        )}
        {entry.outdated && <span className="rounded-full border border-red-900 px-2 py-0.5 text-red-400">outdated</span>}
      </div>
      <p className="text-sm text-zinc-100">{entry.content}</p>
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-500">
        <span>captured via {entry.capture_method.replace(/_/g, " ")}</span>
        {entry.last_verified_at && <span>verified {new Date(entry.last_verified_at).toLocaleDateString()}</span>}
        <span>accessed {entry.access_count}×</span>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        {entry.status === "active" ? (
          <button disabled={busy} onClick={() => run(() => archiveMemory(entry.id))} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500">
            Archive
          </button>
        ) : (
          <button disabled={busy} onClick={() => run(() => restoreMemory(entry.id))} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500">
            Restore
          </button>
        )}
        <button disabled={busy} onClick={() => run(() => confirmMemory(entry.id))} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500">
          Confirm verified
        </button>
        <button disabled={busy} onClick={() => run(() => markMemoryOutdated(entry.id))} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500">
          Mark outdated
        </button>
        <button
          disabled={busy}
          onClick={() => {
            if (window.confirm("Permanently delete this memory? This cannot be undone — use Archive if you might want it back.")) {
              void run(() => deleteMemory(entry.id));
            }
          }}
          className="rounded-lg border border-red-900 px-2 py-1 text-xs text-red-400 hover:border-red-700"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function ConflictCard({ conflict, onResolved }: { conflict: MemoryConflictOut; onResolved: () => void }) {
  const [busy, setBusy] = useState(false);
  async function resolve(resolution: string) {
    setBusy(true);
    try {
      await resolveMemoryConflict(conflict.id, resolution);
      onResolved();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-amber-900/60 bg-amber-950/10 p-4">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-amber-400">
        <span className="rounded-full border border-amber-900 px-2 py-0.5 uppercase">{conflict.conflict_type.replace(/_/g, " ")}</span>
        <span>severity {conflict.severity}</span>
      </div>
      <p className="text-sm text-zinc-200">{conflict.description}</p>
      {conflict.recommended_resolution && (
        <p className="text-xs text-zinc-500">Suggested: {conflict.recommended_resolution.replace(/_/g, " ")}</p>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        {["choose_newer", "choose_verified", "retain_both_with_scope", "mark_outdated", "user_decision"].map((r) => (
          <button key={r} disabled={busy} onClick={() => void resolve(r)} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500">
            {r.replace(/_/g, " ")}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function MemoryCenterView() {
  const [entries, setEntries] = useState<AtlasEntryOut[]>([]);
  const [conflicts, setConflicts] = useState<MemoryConflictOut[]>([]);
  const [stats, setStats] = useState<MemoryStatsOut | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<MemoryCategory | "">("");
  const [statusFilter, setStatusFilter] = useState<MemoryLifecycleStatus | "">("active");
  const [needsReview, setNeedsReview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function refresh() {
    try {
      const [entriesResp, conflictsResp, statsResp] = await Promise.all([
        listMemories({
          category: categoryFilter || undefined,
          status: statusFilter || undefined,
          needs_review: needsReview || undefined,
        }),
        listMemoryConflicts(),
        getMemoryStats(),
      ]);
      setEntries(entriesResp);
      setConflicts(conflictsResp);
      setStats(statsResp);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Memory Center.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter, statusFilter, needsReview]);

  async function handleMaintenance() {
    const result = await runMemoryMaintenance();
    setNote(`Checked ${result.checked} memories — ${result.expired} expired, ${result.needs_review} flagged for review.`);
    await refresh();
  }

  async function handleExport() {
    const data = await exportMemories(false);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `echo-memory-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Memory Center</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Everything ECHO remembers about you — with source, confidence, and lifecycle status. Never
          infallible: review, correct, archive, or delete anything here at any time.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}
      {note && <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-300">{note}</div>}

      {stats && (
        <div className="grid grid-cols-2 gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm sm:grid-cols-4">
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{stats.total_active}</div>
            <div className="text-xs text-zinc-500">Active memories</div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{stats.pending_candidates}</div>
            <div className="text-xs text-zinc-500">Pending candidates</div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-amber-400">{stats.open_conflicts}</div>
            <div className="text-xs text-zinc-500">Open conflicts</div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{stats.consolidation_events}</div>
            <div className="text-xs text-zinc-500">Consolidation events</div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as MemoryCategory | "")}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-2 text-sm"
        >
          <option value="">All categories</option>
          {MEMORY_CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as MemoryLifecycleStatus | "")}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-2 text-sm"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input type="checkbox" checked={needsReview} onChange={(e) => setNeedsReview(e.target.checked)} />
          Needs review only
        </label>
        <div className="ml-auto flex gap-2">
          <button onClick={() => void handleMaintenance()} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500">
            Run maintenance
          </button>
          <button onClick={() => void handleExport()} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500">
            Export JSON
          </button>
        </div>
      </div>

      {conflicts.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-amber-400">Conflicts needing review ({conflicts.length})</h3>
          {conflicts.map((c) => (
            <ConflictCard key={c.id} conflict={c} onResolved={refresh} />
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-zinc-300">Memories ({entries.length})</h3>
        {entries.length === 0 && <p className="text-sm text-zinc-500">Nothing matches these filters.</p>}
        {entries.map((entry) => (
          <MemoryCard key={entry.id} entry={entry} onAction={refresh} />
        ))}
      </div>
    </div>
  );
}
