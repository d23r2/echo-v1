import { useEffect, useState } from "react";
import {
  AtlasEntryOut,
  AtlasSearchResult,
  MEMORY_TYPES,
  MemoryType,
  createAtlasEntry,
  deleteAtlasEntry,
  listAtlasEntries,
  searchAtlas,
  updateAtlasEntry,
} from "../../api/client";
import { useApi } from "../../api/useApi";
import AtlasEntryCard from "./AtlasEntryCard";
import AtlasEntryForm, { AtlasEntryFormValue } from "./AtlasEntryForm";
import AtlasSearchBar from "./AtlasSearchBar";

export default function AtlasView() {
  const [entries, setEntries] = useState<AtlasEntryOut[]>([]);
  const [searchResults, setSearchResults] = useState<AtlasSearchResult[] | null>(null);
  const [query, setQuery] = useState("");
  const [memoryTypeFilter, setMemoryTypeFilter] = useState<MemoryType | "">("");
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { run: runList, loading: loadingList, error: listError } = useApi(listAtlasEntries);
  const { run: runSearch, loading: loadingSearch, error: searchError } = useApi(searchAtlas);
  const { run: runCreate } = useApi(createAtlasEntry);
  const { run: runUpdate } = useApi(updateAtlasEntry);
  const { run: runDelete } = useApi(deleteAtlasEntry);

  async function refresh() {
    const list = await runList(memoryTypeFilter || undefined);
    if (list) setEntries(list);
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

  const editingEntry = entries.find((e) => e.id === editingId);
  // Search doesn't support server-side memory_type filtering, so filter results
  // client-side; the plain list is already filtered server-side via refresh().
  const displayed = searchResults
    ? searchResults.filter((r) => !memoryTypeFilter || r.memory_type === memoryTypeFilter)
    : entries;
  const loading = loadingList || loadingSearch;
  const error = listError || searchError;

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
      </div>

      {creating && (
        <AtlasEntryForm onCancel={() => setCreating(false)} onSubmit={handleCreate} />
      )}

      {loading && <div className="text-xs text-zinc-500">Loading…</div>}
      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
      {!loading && displayed.length === 0 && (
        <div className="py-12 text-center text-sm text-zinc-500">
          {searchResults ? "No matching memories." : "No memories yet — add the first one."}
        </div>
      )}

      <div className="space-y-3">
        {displayed.map((entry) =>
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
              onEdit={() => setEditingId(entry.id)}
              onDelete={() => handleDelete(entry.id)}
            />
          )
        )}
      </div>
    </div>
  );
}
