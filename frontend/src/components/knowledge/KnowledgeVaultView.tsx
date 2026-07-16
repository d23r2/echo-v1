import { useEffect, useState } from "react";
import {
  archiveKnowledgeItem,
  createKnowledgeItem,
  KnowledgeItemOut,
  KnowledgeItemType,
  listKnowledgeItems,
  searchKnowledgeItems,
} from "../../api/client";

const TYPE_OPTIONS: KnowledgeItemType[] = [
  "note", "decision", "source", "summary", "idea", "bug", "release_note", "study_note", "prompt", "reference", "personal_rule",
];

export default function KnowledgeVaultView() {
  const [items, setItems] = useState<KnowledgeItemOut[]>([]);
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [itemType, setItemType] = useState<KnowledgeItemType>("note");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setItems(query.trim() ? await searchKnowledgeItems(query.trim()) : await listKnowledgeItems());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load knowledge items.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await createKnowledgeItem({ title: title.trim(), body, item_type: itemType });
      setTitle("");
      setBody("");
      setItemType("note");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create note.");
    }
  }

  async function handleArchive(id: string) {
    if (!window.confirm("Archive this knowledge item? It will be hidden from the list but not deleted.")) return;
    await archiveKnowledgeItem(id);
    await refresh();
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Knowledge Vault</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Notes, decisions, prompts, and release notes you keep on purpose — different from Atlas
          (ECHO's internal, adaptive memory), which you never directly edit.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex flex-wrap gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (e.g. 'Use SearXNG as primary no-billing search')"
            className="min-h-[44px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <select
            value={itemType}
            onChange={(e) => setItemType(e.target.value as KnowledgeItemType)}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-2 text-sm"
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Body — e.g. the reasoning behind a decision"
          rows={2}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
        />
        <button disabled={!title.trim()} className="w-fit rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Save
        </button>
      </form>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search notes…"
        className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
      />

      <div className="space-y-2">
        {items.length === 0 && <p className="text-sm text-zinc-500">Nothing here yet — save a note above.</p>}
        {items.map((item) => (
          <div key={item.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-100">{item.title}</span>
                  <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500">{item.item_type}</span>
                </div>
                {item.body && <p className="mt-1 whitespace-pre-wrap text-xs text-zinc-400">{item.body}</p>}
              </div>
              <button
                onClick={() => void handleArchive(item.id)}
                className="shrink-0 rounded-lg border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/50"
              >
                Archive
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
