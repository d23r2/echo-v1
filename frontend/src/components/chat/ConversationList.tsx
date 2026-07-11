import { useState } from "react";
import { useConversations } from "../../state/conversationsContext";

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
    </>
  );
}
