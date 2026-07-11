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
  const { conversations, conversationId, selectConversation, startNewConversation } = useConversations();
  const rowSizing = compact ? "" : "min-h-[44px] flex items-center";

  return (
    <>
      <button
        onClick={() => {
          startNewConversation();
          onSelect?.();
        }}
        className={`mb-3 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900 ${rowSizing}`}
      >
        + New conversation
      </button>
      <div className="flex-1 space-y-1 overflow-y-auto">
        {conversations.map((c) => (
          <button
            key={c.id}
            onClick={() => {
              selectConversation(c.id);
              onSelect?.();
            }}
            className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${rowSizing} ${
              c.id === conversationId
                ? "bg-accent/15 text-accent"
                : "text-zinc-400 hover:bg-zinc-900"
            }`}
          >
            {c.title}
          </button>
        ))}
      </div>
    </>
  );
}
