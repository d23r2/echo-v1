import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
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

// Custom element-by-element styling rather than the `prose` plugin's defaults —
// gives precise control over spacing/contrast against this app's dark palette
// without fighting prose's own opinions on colors sized for a light-first system.
const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 leading-[1.7] last:mb-0">{children}</p>,
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-lg font-semibold text-zinc-50 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-base font-semibold text-zinc-50 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-sm font-semibold text-zinc-50 first:mt-0">{children}</h3>
  ),
  strong: ({ children }) => <strong className="font-bold text-zinc-50">{children}</strong>,
  em: ({ children }) => <em className="italic text-zinc-200">{children}</em>,
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1.5 pl-5 marker:text-accent last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1.5 pl-5 marker:text-accent last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-accent/50 pl-3 text-zinc-400">
      {children}
    </blockquote>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-accent underline underline-offset-2 hover:text-accent-bright"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-zinc-800" />,
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-[0.85em] leading-relaxed [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-zinc-200">
      {children}
    </pre>
  ),
  code: ({ children }) => (
    <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.85em] text-accent-bright">
      {children}
    </code>
  ),
};

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`rounded-2xl px-4 py-2.5 ${
            isUser
              ? "bg-accent text-sm leading-[1.65] text-zinc-950 whitespace-pre-wrap"
              : "border border-zinc-800 bg-zinc-900 text-zinc-100"
          }`}
        >
          {isUser ? message.content : <MarkdownContent content={message.content} />}
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
