import { useEffect, useRef, useState } from "react";
import {
  MemoryUpdate,
  MessageOut,
  WelcomeResponse,
  getConversation,
  getWelcomeGreeting,
  sendChatMessage,
} from "../../api/client";
import { useApi } from "../../api/useApi";
import { useConversations } from "../../state/conversationsContext";
import { useRole } from "../../state/roleContext";
import ConversationList from "./ConversationList";
import MessageBubble from "./MessageBubble";
import ModelPicker from "./ModelPicker";

export interface DisplayMessage extends MessageOut {
  memory_update?: MemoryUpdate | null;
}

// Module-level (not component state): persists across ChatView remounts caused by
// switching nav sections and back, but naturally resets on an actual page reload —
// which is exactly the "once per app load" semantics this needs.
let welcomeFetchedThisLoad = false;

export default function ChatView() {
  const { provider } = useRole();
  const { conversationId, selectConversation, refreshConversations } = useConversations();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [welcome, setWelcome] = useState<WelcomeResponse | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { run: runSend, loading, error } = useApi(sendChatMessage);
  const { run: runLoadConversation } = useApi(getConversation);
  // Errors intentionally not surfaced anywhere — a failed welcome fetch should be
  // invisible and just leave the plain empty-state placeholder in place.
  const { run: runWelcome, loading: welcomeLoading } = useApi(getWelcomeGreeting);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    // Once the user has opened/started any conversation, the one-time welcome
    // greeting is "used up" — don't resurrect it on a later empty state (e.g.
    // after clicking "+ New conversation" mid-session).
    setWelcome(null);
    runLoadConversation(conversationId).then((detail) => {
      if (detail) setMessages(detail.messages);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    if (conversationId || welcomeFetchedThisLoad) return;
    welcomeFetchedThisLoad = true;
    runWelcome().then((res) => {
      if (res) setWelcome(res);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");

    const optimisticUser: DisplayMessage = {
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

    selectConversation(result.conversation_id);
    setMessages((prev) => [
      ...prev,
      {
        id: result.message_id,
        role: "echo",
        content: result.content,
        reasoning: result.reasoning,
        provider: result.provider_used,
        atlas_citations: result.atlas_citations,
        memory_update: result.memory_update,
        created_at: new Date().toISOString(),
      },
    ]);
    refreshConversations();
  }

  return (
    <div className="flex h-full">
      <aside className="hidden lg:flex w-60 flex-col border-r border-zinc-800 bg-zinc-950 p-3">
        <ConversationList compact />
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
          <h1 className="text-sm font-medium text-zinc-300">Echo</h1>
          <ModelPicker />
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="mx-auto max-w-md pt-16">
              {welcome ? (
                <div className="flex justify-start">
                  <div className="flex max-w-[90%] flex-col items-start">
                    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap">
                      {welcome.greeting}
                    </div>
                    {welcome.referenced_memories.length > 0 && (
                      <div className="mt-1 px-1 text-[10px] text-zinc-600">
                        recalling: {welcome.referenced_memories.join(" · ")}
                      </div>
                    )}
                  </div>
                </div>
              ) : welcomeLoading ? (
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                  Echo is remembering…
                </div>
              ) : (
                <div className="text-center text-sm text-zinc-500">
                  Ask Echo anything. It will show its reasoning and cite any relevant Atlas
                  memories it draws on.
                </div>
              )}
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
