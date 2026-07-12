import { useEffect, useRef, useState } from "react";
import { ConversationSearchResult, searchConversations } from "../../api/client";
import { useConversations } from "../../state/conversationsContext";

const SEARCH_DEBOUNCE_MS = 300;

function matchLabel(role: ConversationSearchResult["matched_role"]): string {
  if (role === "title") return "title";
  if (role === "user") return "you said";
  return "Echo said";
}

export default function ConversationList({
  onSelect,
  compact = false,
}: {
  /** Called after starting/selecting a conversation — used to close the mobile drawer. */
  onSelect?: () => void;
  /** Desktop aside uses the original (smaller) row sizing; the mobile drawer needs ~44px tap targets. */
  compact?: boolean;
}) {
  const { conversations, conversationId, selectConversation, startNewConversation, removeConversation } =
    useConversations();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ConversationSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeq = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (!trimmed) {
      // Don't show/run search on empty input — just the normal conversation list.
      setSearchResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      const seq = ++searchSeq.current;
      try {
        const results = await searchConversations(trimmed);
        // Ignore stale responses from an earlier keystroke that resolves after a
        // more recent one — otherwise a fast typer can see results flicker back to
        // an outdated query's set.
        if (seq === searchSeq.current) setSearchResults(results);
      } catch {
        if (seq === searchSeq.current) setSearchResults([]);
      } finally {
        if (seq === searchSeq.current) setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const rowSizing = compact ? "" : "min-h-[44px]";
  // Nested flex containers each need their own min-h-0 to shrink below content size and
  // become independently scrollable, rather than growing past their parent and getting
  // clipped by it. Desktop's aside has no overflow-hidden ancestor so this was never
  // visible there; the mobile drawer does, so without this the list was invisible.
  const listSizing = compact ? "" : "min-h-0";
  // Trash icon: hover-reveal on desktop (mouse), always visible on mobile (no hover).
  const trashVisibility = compact
    ? "opacity-0 group-hover:opacity-100 focus:opacity-100"
    : "opacity-100";
  const trashSize = compact ? "h-7 w-7" : "h-11 w-11";

  async function handleDelete(id: string, title: string) {
    if (!window.confirm(`Delete "${title}"? This can't be undone.`)) return;
    setRowError(null);
    setDeletingId(id);
    const result = await removeConversation(id);
    setDeletingId(null);
    if (!result.ok) {
      setRowError({ id, message: result.error || "Failed to delete conversation." });
    }
  }

  return (
    <>
      <button
        onClick={() => {
          startNewConversation();
          onSelect?.();
        }}
        className={`mb-3 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900 ${
          compact ? "" : "min-h-[44px] flex items-center"
        }`}
      >
        + New conversation
      </button>
      <div className="relative mb-3">
        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500">
          🔎
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations…"
          aria-label="Search past conversations"
          className={`w-full rounded-lg border border-zinc-700 bg-zinc-900 py-2 pl-8 pr-3 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-accent focus:outline-none ${
            compact ? "" : "min-h-[44px]"
          }`}
        />
      </div>
      {searchResults !== null ? (
        <div className={`flex-1 space-y-1 overflow-y-auto ${listSizing}`}>
          {searching && searchResults.length === 0 && (
            <p className="px-3 py-2 text-xs text-zinc-500">Searching…</p>
          )}
          {!searching && searchResults.length === 0 && (
            <p className="px-3 py-2 text-xs text-zinc-500">No conversations match "{query.trim()}".</p>
          )}
          {searchResults.map((r) => (
            <button
              key={r.conversation_id}
              onClick={() => {
                selectConversation(r.conversation_id);
                onSelect?.();
              }}
              className={`block w-full rounded-lg px-3 py-2 text-left hover:bg-zinc-900 ${
                r.conversation_id === conversationId ? "bg-accent/15" : ""
              }`}
            >
              <div
                className={`truncate text-sm ${
                  r.conversation_id === conversationId ? "text-accent" : "text-zinc-200"
                }`}
              >
                {r.title}
              </div>
              <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-600">
                  {matchLabel(r.matched_role)}
                </span>
                <span className="truncate text-xs text-zinc-500">{r.snippet}</span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className={`flex-1 space-y-1 overflow-y-auto ${listSizing}`}>
          {conversations.map((c) => (
            <div key={c.id} className="group">
              <div
                className={`flex items-center rounded-lg ${rowSizing} ${
                  c.id === conversationId ? "bg-accent/15" : "hover:bg-zinc-900"
                }`}
              >
                <button
                  onClick={() => {
                    selectConversation(c.id);
                    onSelect?.();
                  }}
                  className={`min-w-0 flex-1 truncate px-3 py-2 text-left text-sm ${
                    c.id === conversationId ? "text-accent" : "text-zinc-400"
                  }`}
                >
                  {c.title}
                </button>
                <button
                  onClick={() => handleDelete(c.id, c.title)}
                  disabled={deletingId === c.id}
                  aria-label={`Delete conversation "${c.title}"`}
                  title="Delete conversation"
                  className={`mr-1 flex shrink-0 items-center justify-center rounded-md text-zinc-500 transition-opacity hover:bg-red-950/50 hover:text-red-400 disabled:opacity-40 ${trashSize} ${trashVisibility}`}
                >
                  {deletingId === c.id ? "…" : "🗑"}
                </button>
              </div>
              {rowError?.id === c.id && (
                <p className="px-3 py-1 text-[10px] text-red-400">{rowError.message}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
