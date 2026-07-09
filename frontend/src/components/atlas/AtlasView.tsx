import { useEffect, useState } from "react";
import {
  AtlasEntryOut,
  AtlasSearchResult,
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
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { run: runList, loading: loadingList, error: listError } = useApi(listAtlasEntries);
  const { run: runSearch, loading: loadingSearch, error: searchError } = useApi(searchAtlas);
  const { run: runCreate } = useApi(createAtlasEntry);
  const { run: runUpdate } = useApi(updateAtlasEntry);
  const { run: runDelete } = useApi(deleteAtlasEntry);

  async function refresh() {
    const list = await runList();
    if (list) setEntries(list);
  }

  useEffect(() => {
    refresh();
  }, []);

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
  const displayed = searchResults ?? entries;
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

      <AtlasSearchBar
        value={query}
        onChange={(v) => {
          setQuery(v);
          if (!v.trim()) setSearchResults(null);
        }}
        onSubmit={handleSearch}
      />

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
