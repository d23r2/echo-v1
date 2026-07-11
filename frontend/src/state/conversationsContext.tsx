import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { ConversationOut, deleteConversation as apiDeleteConversation, listConversations } from "../api/client";
import { useApi } from "../api/useApi";

interface ConversationsContextValue {
  conversations: ConversationOut[];
  conversationId: string | undefined;
  selectConversation: (id: string) => void;
  startNewConversation: () => void;
  refreshConversations: () => Promise<void>;
  removeConversation: (id: string) => Promise<{ ok: boolean; error?: string }>;
}

const ConversationsContext = createContext<ConversationsContextValue | null>(null);

export function ConversationsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const { run: runLoadConversations } = useApi(listConversations);

  async function refreshConversations() {
    const list = await runLoadConversations();
    if (list) setConversations(list);
  }

  useEffect(() => {
    refreshConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Deliberately bypasses useApi: callers need the per-row success/failure result
  // immediately (to decide whether to remove that row or show an inline error on
  // it), not a shared loading/error state tied to one hook instance.
  async function removeConversation(id: string): Promise<{ ok: boolean; error?: string }> {
    try {
      await apiDeleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (conversationId === id) setConversationId(undefined);
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }

  return (
    <ConversationsContext.Provider
      value={{
        conversations,
        conversationId,
        selectConversation: setConversationId,
        startNewConversation: () => setConversationId(undefined),
        refreshConversations,
        removeConversation,
      }}
    >
      {children}
    </ConversationsContext.Provider>
  );
}

export function useConversations() {
  const ctx = useContext(ConversationsContext);
  if (!ctx) throw new Error("useConversations must be used within ConversationsProvider");
  return ctx;
}
