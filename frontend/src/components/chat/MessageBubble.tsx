import { DisplayMessage } from "./ChatView";
import ReasoningTrace from "./ReasoningTrace";

function MemoryNote({ message }: { message: DisplayMessage }) {
  const update = message.memory_update;
  if (!update) return null;

  if (update.saved) {
    return (
      <div className="mt-1 flex items-start gap-1 px-1 text-[11px] text-emerald-400">
        <span>📌</span>
        <span>
          {update.explicit ? "Remembered: " : "Noted for later: "}
          {update.content}
        </span>
      </div>
    );
  }

  // Only surface failures for explicit asks — implicit auto-extraction failing is
  // expected background noise, not something worth interrupting the chat over.
  if (update.explicit) {
    return (
      <div className="mt-1 flex items-start gap-1 px-1 text-[11px] text-red-400">
        <span>⚠️</span>
        <span>Couldn't save that to Atlas: {update.error}</span>
      </div>
    );
  }

  return null;
}

export default function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-accent text-zinc-950"
              : "bg-zinc-900 text-zinc-100 border border-zinc-800"
          }`}
        >
          {message.content}
        </div>
        {!isUser && (
          <div className="w-full px-1">
            <ReasoningTrace reasoning={message.reasoning} citations={message.atlas_citations} />
          </div>
        )}
        {!isUser && <MemoryNote message={message} />}
        {!isUser && message.provider && (
          <div className="mt-1 px-1 text-[10px] uppercase tracking-wide text-zinc-600">
            via {message.provider}
          </div>
        )}
      </div>
    </div>
  );
}
