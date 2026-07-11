import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { ConversationOut, listConversations } from "../api/client";
import { useApi } from "../api/useApi";

interface ConversationsContextValue {
  conversations: ConversationOut[];
  conversationId: string | undefined;
  selectConversation: (id: string) => void;
  startNewConversation: () => void;
  refreshConversations: () => Promise<void>;
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

  return (
    <ConversationsContext.Provider
      value={{
        conversations,
        conversationId,
        selectConversation: setConversationId,
        startNewConversation: () => setConversationId(undefined),
        refreshConversations,
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
