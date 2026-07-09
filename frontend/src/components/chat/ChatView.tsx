import { useEffect, useRef, useState } from "react";
import {
  ConversationOut,
  MessageOut,
  getConversation,
  listConversations,
  sendChatMessage,
} from "../../api/client";
import { useApi } from "../../api/useApi";
import { useRole } from "../../state/roleContext";
import MessageBubble from "./MessageBubble";
import ModelPicker from "./ModelPicker";

export default function ChatView() {
  const { provider } = useRole();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { run: runSend, loading, error } = useApi(sendChatMessage);
  const { run: runLoadConversations } = useApi(listConversations);
  const { run: runLoadConversation } = useApi(getConversation);

  useEffect(() => {
    refreshConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function refreshConversations() {
    const list = await runLoadConversations();
    if (list) setConversations(list);
  }

  async function openConversation(id: string) {
    const detail = await runLoadConversation(id);
    if (detail) {
      setConversationId(detail.id);
      setMessages(detail.messages);
    }
  }

  function startNewConversation() {
    setConversationId(undefined);
    setMessages([]);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");

    const optimisticUser: MessageOut = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: text,
      reasoning: null,
      provider: null,
      atlas_citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    const result = await runSend(text, provider, conversationId);
    if (!result) return;

    setConversationId(result.conversation_id);
    setMessages((prev) => [
      ...prev,
      {
        id: result.message_id,
        role: "echo",
        content: result.content,
        reasoning: result.reasoning,
        provider: result.provider_used,
        atlas_citations: result.atlas_citations,
        created_at: new Date().toISOString(),
      },
    ]);
    refreshConversations();
  }

  return (
    <div className="flex h-full">
      <aside className="hidden lg:flex w-60 flex-col border-r border-zinc-800 bg-zinc-950 p-3">
        <button
          onClick={startNewConversation}
          className="mb-3 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
        >
          + New conversation
        </button>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                c.id === conversationId
                  ? "bg-accent/15 text-accent"
                  : "text-zinc-400 hover:bg-zinc-900"
              }`}
            >
              {c.title}
            </button>
          ))}
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
          <h1 className="text-sm font-medium text-zinc-300">Echo</h1>
          <ModelPicker />
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="mx-auto max-w-md pt-16 text-center text-sm text-zinc-500">
              Ask Echo anything. It will show its reasoning and cite any relevant Atlas memories
              it draws on.
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
              Echo is thinking…
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-zinc-800 p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={1}
              placeholder="Message Echo…"
              className="flex-1 resize-none rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none"
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
