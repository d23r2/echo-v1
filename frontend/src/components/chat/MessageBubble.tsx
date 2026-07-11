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

function fileTypeIcon(mime: string): string {
  if (mime.startsWith("image/")) return "🖼️";
  if (mime.startsWith("audio/")) return "🎵";
  if (mime.startsWith("video/")) return "🎬";
  if (mime === "application/pdf") return "📄";
  if (mime.startsWith("text/")) return "📝";
  return "📎";
}

function AttachmentChips({ message }: { message: DisplayMessage }) {
  if (!message.attachments || message.attachments.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {message.attachments.map((a, i) => (
        <div
          key={i}
          title={a.understood ? a.filename : `${a.filename} — Echo couldn't read this file's content`}
          className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${
            a.understood
              ? "border-zinc-700 bg-zinc-900 text-zinc-300"
              : "border-zinc-800 bg-zinc-900/50 text-zinc-500"
          }`}
        >
          <span>{fileTypeIcon(a.mime_type)}</span>
          <span className="max-w-[120px] truncate">{a.filename}</span>
          {!a.understood && <span aria-label="Not readable by Echo">⚠️</span>}
        </div>
      ))}
    </div>
  );
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
        <div className="w-full px-1">
          <AttachmentChips message={message} />
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
