import { useEffect, useRef, useState } from "react";
import { ConversationSearchResult, searchConversations } from "../../api/client";

function matchLabel(role: ConversationSearchResult["matched_role"]): string {
  if (role === "title") return "title";
  if (role === "user") return "you said";
  return "Echo said";
}

export default function SearchView({ onOpenConversation }: { onOpenConversation: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConversationSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (!trimmed) {
      setResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      const mySeq = ++seq.current;
      try {
        const found = await searchConversations(trimmed);
        if (mySeq === seq.current) setResults(found);
      } catch {
        if (mySeq === seq.current) setResults([]);
      } finally {
        if (mySeq === seq.current) setSearching(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Search Conversations</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Plain keyword search over past chats — matches conversation titles and message text.
        </p>
      </div>

      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">🔎</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search everything you've said to Echo…"
          autoFocus
          className="min-h-[44px] w-full rounded-xl border border-zinc-700 bg-zinc-900 py-2 pl-10 pr-3 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-accent focus:outline-none"
        />
      </div>

      {query.trim() && (
        <div className="space-y-2">
          {searching && (results === null || results.length === 0) && (
            <p className="text-sm text-zinc-500">Searching…</p>
          )}
          {!searching && results !== null && results.length === 0 && (
            <p className="text-sm text-zinc-500">No conversations match "{query.trim()}".</p>
          )}
          {results?.map((r) => (
            <button
              key={r.conversation_id}
              onClick={() => onOpenConversation(r.conversation_id)}
              className="block w-full rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-left hover:border-accent/50 hover:bg-zinc-900/80"
            >
              <div className="truncate text-sm font-medium text-zinc-100">{r.title}</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-600">
                  {matchLabel(r.matched_role)}
                </span>
                <span className="truncate text-xs text-zinc-400">{r.snippet}</span>
              </div>
              <div className="mt-1 text-[10px] text-zinc-600">{new Date(r.updated_at).toLocaleString()}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
