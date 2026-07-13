import { useEffect, useMemo, useState } from "react";
import {
  AtlasEntryOut,
  AtlasSearchResult,
  EPISTEMIC_STATUSES,
  EpistemicStatus,
  MEMORY_TYPES,
  MemoryType,
  createAtlasEntry,
  deleteAtlasEntry,
  getAtlasConflicts,
  listAtlasEntries,
  mergeAtlasEntries,
  searchAtlas,
  updateAtlasEntry,
} from "../../api/client";
import { useApi } from "../../api/useApi";
import AtlasEntryCard from "./AtlasEntryCard";
import AtlasEntryForm, { AtlasEntryFormValue } from "./AtlasEntryForm";
import AtlasSearchBar from "./AtlasSearchBar";
import MemoryCandidates from "./MemoryCandidates";
import MemoryDiagnostics from "./MemoryDiagnostics";

type QuickFilter =
  | "all"
  | "facts"
  | "projects"
  | "goals"
  | "preferences"
  | "recent"
  | "low_confidence"
  | "conflicts";

const QUICK_FILTERS: { id: QuickFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "facts", label: "Important facts" },
  { id: "projects", label: "Current projects" },
  { id: "goals", label: "Open goals" },
  { id: "preferences", label: "Preferences" },
  { id: "recent", label: "Recent" },
  { id: "low_confidence", label: "Low-confidence" },
  { id: "conflicts", label: "Conflicts" },
];

type SortKey = "recent" | "confidence" | "observed_at";

const LOW_CONFIDENCE_THRESHOLD = 0.5;
const RECENT_COUNT = 10;

export default function AtlasView() {
  const [entries, setEntries] = useState<AtlasEntryOut[]>([]);
  const [searchResults, setSearchResults] = useState<AtlasSearchResult[] | null>(null);
  const [query, setQuery] = useState("");
  const [memoryTypeFilter, setMemoryTypeFilter] = useState<MemoryType | "">("");
  const [statusFilter, setStatusFilter] = useState<EpistemicStatus | "">("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("recent");
  const [conflicts, setConflicts] = useState<Record<string, string[]>>({});
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [mergeContent, setMergeContent] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { run: runList, loading: loadingList, error: listError } = useApi(listAtlasEntries);
  const { run: runSearch, loading: loadingSearch, error: searchError } = useApi(searchAtlas);
  const { run: runCreate } = useApi(createAtlasEntry);
  const { run: runUpdate } = useApi(updateAtlasEntry);
  const { run: runDelete } = useApi(deleteAtlasEntry);

  async function refresh() {
    const list = await runList(memoryTypeFilter || undefined);
    if (list) setEntries(list);
    try {
      setConflicts(await getAtlasConflicts());
    } catch {
      // Conflict detection is a bonus signal, not load-bearing — don't block the view on it.
    }
  }

  // Re-fetch (server-side filter) whenever the memory_type filter changes, including
  // the initial mount.
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memoryTypeFilter]);

  async function handleSearch() {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    const results = await runSearch(query, 8);
    if (results) setSearchResults(results);
  }

  async function handleCreate(value: AtlasEntryFormValue) {
    const created = await runCreate(value);
    if (created) {
      setCreating(false);
      refresh();
    }
  }

  async function handleUpdate(id: string, value: AtlasEntryFormValue) {
    const updated = await runUpdate(id, value);
    if (updated) {
      setEditingId(null);
      refresh();
    }
  }

  async function handleDelete(id: string) {
    await runDelete(id);
    refresh();
  }

  async function handleConfirm(entry: AtlasEntryOut) {
    await runUpdate(entry.id, { epistemic_status: "Verified", confidence: Math.max(entry.confidence, 0.9) });
    refresh();
  }

  async function handleToggleOutdated(entry: AtlasEntryOut) {
    await runUpdate(entry.id, { outdated: !entry.outdated });
    refresh();
  }

  function toggleMergeSelect(id: string) {
    setMergeSelection((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  }

  const mergeCandidates = mergeSelection
    .map((id) => entries.find((e) => e.id === id))
    .filter((e): e is AtlasEntryOut => Boolean(e));

  useEffect(() => {
    if (mergeCandidates.length === 2) {
      setMergeContent(mergeCandidates[0].content);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mergeSelection.join(",")]);

  async function handleMerge(keepId: string) {
    const removeId = mergeSelection.find((id) => id !== keepId);
    if (!removeId) return;
    setActionError(null);
    try {
      await mergeAtlasEntries(keepId, removeId, mergeContent.trim() || undefined);
      setMergeSelection([]);
      setMergeContent("");
      refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Merge failed.");
    }
  }

  const editingEntry = entries.find((e) => e.id === editingId);
  // Search doesn't support server-side memory_type filtering, so filter results
  // client-side; the plain list is already filtered server-side via refresh().
  const baseList: (AtlasEntryOut | AtlasSearchResult)[] = searchResults ?? entries;

  const filtered = useMemo(() => {
    let list = baseList.filter((e) => !memoryTypeFilter || e.memory_type === memoryTypeFilter);
    if (statusFilter) list = list.filter((e) => e.epistemic_status === statusFilter);

    switch (quickFilter) {
      case "facts":
        list = list.filter((e) => e.memory_type === "fact");
        break;
      case "projects":
        list = list.filter((e) => e.memory_type === "project");
        break;
      case "goals":
        list = list.filter((e) => e.memory_type === "goal");
        break;
      case "preferences":
        list = list.filter((e) => e.memory_type === "preference");
        break;
      case "low_confidence":
        list = list.filter((e) => e.confidence < LOW_CONFIDENCE_THRESHOLD);
        break;
      case "conflicts":
        list = list.filter((e) => (conflicts[e.id]?.length ?? 0) > 0);
        break;
      case "recent":
        list = [...list]
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, RECENT_COUNT);
        break;
      case "all":
      default:
        break;
    }

    if (quickFilter !== "recent") {
      list = [...list].sort((a, b) => {
        if (sortKey === "confidence") return b.confidence - a.confidence;
        if (sortKey === "observed_at") return new Date(b.observed_at).getTime() - new Date(a.observed_at).getTime();
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
    }

    return list;
  }, [baseList, memoryTypeFilter, statusFilter, quickFilter, sortKey, conflicts]);

  const loading = loadingList || loadingSearch;
  const error = listError || searchError;
  const conflictTotal = Object.keys(conflicts).length;

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Atlas</h1>
          <p className="text-xs text-zinc-500">Persistent memory with epistemic status &amp; semantic search.</p>
        </div>
        <button
          onClick={() => setCreating((c) => !c)}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950"
        >
          + New memory
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {QUICK_FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setQuickFilter(f.id)}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${
              quickFilter === f.id
                ? "border-accent bg-accent/10 text-accent"
                : "border-zinc-700 text-zinc-400 hover:bg-zinc-900"
            }`}
          >
            {f.label}
            {f.id === "conflicts" && conflictTotal > 0 && ` (${conflictTotal})`}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <AtlasSearchBar
            value={query}
            onChange={(v) => {
              setQuery(v);
              if (!v.trim()) setSearchResults(null);
            }}
            onSubmit={handleSearch}
          />
        </div>
        <select
          value={memoryTypeFilter}
          onChange={(e) => setMemoryTypeFilter(e.target.value as MemoryType | "")}
          className="rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 focus:border-accent focus:outline-none"
        >
          <option value="">All types</option>
          {MEMORY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as EpistemicStatus | "")}
          className="rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 focus:border-accent focus:outline-none"
        >
          <option value="">All statuses</option>
          {EPISTEMIC_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 focus:border-accent focus:outline-none"
        >
          <option value="recent">Sort: most recent</option>
          <option value="confidence">Sort: confidence</option>
          <option value="observed_at">Sort: observed at</option>
        </select>
      </div>

      {creating && (
        <AtlasEntryForm onCancel={() => setCreating(false)} onSubmit={handleCreate} />
      )}

      <MemoryCandidates />
      <MemoryDiagnostics />

      {mergeCandidates.length === 2 && (
        <div className="rounded-xl border border-accent/50 bg-zinc-900/60 p-3 text-sm">
          <p className="mb-2 text-xs text-zinc-400">
            Merging 2 memories into one. Edit the combined content below, then pick which entry to keep.
          </p>
          <textarea
            value={mergeContent}
            onChange={(e) => setMergeContent(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
          />
          {actionError && <p className="mt-1 text-xs text-red-400">{actionError}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {mergeCandidates.map((c) => (
              <button
                key={c.id}
                onClick={() => handleMerge(c.id)}
                className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-zinc-950"
              >
                Keep this one ({c.content.slice(0, 24)}
                {c.content.length > 24 ? "…" : ""})
              </button>
            ))}
            <button
              onClick={() => setMergeSelection([])}
              className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-900"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading && <div className="text-xs text-zinc-500">Loading…</div>}
      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
      {!loading && filtered.length === 0 && (
        <div className="py-12 text-center text-sm text-zinc-500">
          {searchResults ? "No matching memories." : "Nothing in this view yet."}
        </div>
      )}

      <div className="space-y-3">
        {filtered.map((entry) =>
          editingId === entry.id && editingEntry ? (
            <AtlasEntryForm
              key={entry.id}
              initial={editingEntry}
              onCancel={() => setEditingId(null)}
              onSubmit={(v) => handleUpdate(entry.id, v)}
            />
          ) : (
            <AtlasEntryCard
              key={entry.id}
              entry={entry}
              distance={"distance" in entry ? (entry as AtlasSearchResult).distance : undefined}
              conflictCount={conflicts[entry.id]?.length ?? 0}
              mergeSelected={mergeSelection.includes(entry.id)}
              onEdit={() => setEditingId(entry.id)}
              onDelete={() => handleDelete(entry.id)}
              onConfirm={() => handleConfirm(entry)}
              onToggleOutdated={() => handleToggleOutdated(entry)}
              onToggleMergeSelect={() => toggleMergeSelect(entry.id)}
            />
          )
        )}
      </div>
    </div>
  );
}
