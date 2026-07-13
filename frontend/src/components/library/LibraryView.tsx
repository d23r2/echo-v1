import { useEffect, useRef, useState } from "react";
import { deleteLibraryItem, getLibraryItemDownloadUrl, LibraryItemOut, listLibraryItems } from "../../api/client";

const FILE_TYPES = ["image", "document", "exported_conversation", "report", "code", "other"];

const TYPE_ICONS: Record<string, string> = {
  image: "🖼️",
  document: "📄",
  exported_conversation: "💬",
  report: "📊",
  code: "🧩",
  other: "📁",
};

export default function LibraryView() {
  const [items, setItems] = useState<LibraryItemOut[]>([]);
  const [query, setQuery] = useState("");
  const [fileType, setFileType] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function refresh(q: string, type: string) {
    setLoading(true);
    setError(null);
    try {
      const data = await listLibraryItems(q, type || undefined);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Library items.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void refresh(query, fileType), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, fileType]);

  async function handleDelete(id: string, title: string) {
    if (!window.confirm(`Delete "${title}" from the Library? This removes the file too and can't be undone.`)) return;
    setDeletingId(id);
    try {
      await deleteLibraryItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete item.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Library</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Everything Echo has generated or you've uploaded — images, reports, exports, and more — in one place.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search Library…"
          className="min-h-[44px] flex-1 rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-accent focus:outline-none"
        />
        <select
          value={fileType}
          onChange={(e) => setFileType(e.target.value)}
          className="min-h-[44px] rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 focus:border-accent focus:outline-none"
        >
          <option value="">All types</option>
          {FILE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      )}

      {loading && items.length === 0 && <p className="text-sm text-zinc-500">Loading…</p>}
      {!loading && items.length === 0 && !error && (
        <p className="text-sm text-zinc-500">
          Nothing here yet. Generated images, self-improvement reports, and exported conversations will show up
          here automatically.
        </p>
      )}

      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3"
          >
            <span className="text-xl leading-none">{TYPE_ICONS[item.file_type] ?? "📁"}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-zinc-100">{item.title}</div>
              {item.description && (
                <div className="mt-0.5 truncate text-xs text-zinc-500">{item.description}</div>
              )}
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
                <span>{item.file_type.replace(/_/g, " ")}</span>
                <span>·</span>
                <span>{item.source.replace(/_/g, " ")}</span>
                <span>·</span>
                <span>{new Date(item.created_at).toLocaleString()}</span>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <a
                href={getLibraryItemDownloadUrl(item.id)}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-900"
              >
                Download
              </a>
              <button
                onClick={() => handleDelete(item.id, item.title)}
                disabled={deletingId === item.id}
                className="rounded-lg border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/50 disabled:opacity-40"
              >
                {deletingId === item.id ? "…" : "Delete"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
