import { MessageOut } from "../../api/client";
import ReasoningTrace from "./ReasoningTrace";

export default function MessageBubble({ message }: { message: MessageOut }) {
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
        {!isUser && message.provider && (
          <div className="mt-1 px-1 text-[10px] uppercase tracking-wide text-zinc-600">
            via {message.provider}
          </div>
        )}
      </div>
    </div>
  );
}
