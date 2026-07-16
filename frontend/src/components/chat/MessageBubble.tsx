import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildViaLine } from "./chatMetadata";
import { DisplayMessage } from "./ChatView";

// Only ever renders for an EXPLICIT "remember that..." request — a direct
// confirmation of something the user just asked for, not internal noise.
// Auto-extracted memory candidates are queued for review in Atlas's own
// "Memory Candidates" section (see app/routers/chat.py) and deliberately
// never surface under a normal reply — that's internal/debug detail, not
// something every chat turn should announce.
function MemoryNote({ message }: { message: DisplayMessage }) {
  const update = message.memory_update;
  if (!update || !update.explicit) return null;

  if (update.saved) {
    return (
      <div className="mt-1 flex items-start gap-1 px-1 text-[11px] text-emerald-400">
        <span>📌</span>
        <span>Remembered: {update.content}</span>
      </div>
    );
  }

  if (update.error) {
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

// Generated images render as real inline images (via a data URI) rather than a
// filename chip, so they read as part of the conversation, not a throwaway
// attachment — matching how a normal image reply would look.
function GeneratedImages({ message }: { message: DisplayMessage }) {
  const images = (message.attachments || []).filter((a) => a.generated && a.base64_preview);
  if (images.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-col gap-2">
      {images.map((a, i) => (
        <img
          key={i}
          src={`data:${a.mime_type};base64,${a.base64_preview}`}
          alt={message.content}
          className="max-w-full rounded-lg border border-zinc-800 sm:max-w-sm"
        />
      ))}
    </div>
  );
}

// Honest, specific labels for what actually happened to a file's content — never
// implies more understanding than actually occurred (see backend/app/attachments.py).
const ANALYSIS_STATUS_LABELS: Record<string, string> = {
  text_extracted: "text read",
  vision_analyzed: "image analyzed",
  stored: "stored, not analyzed",
  unsupported: "unsupported format",
};

function analysisStatusTitle(a: DisplayMessage["attachments"][number]): string {
  const label = ANALYSIS_STATUS_LABELS[a.analysis_status] || a.analysis_status;
  return `${a.filename} — ${label}`;
}

function AttachmentChips({ message }: { message: DisplayMessage }) {
  const chips = (message.attachments || []).filter((a) => !a.generated);
  if (chips.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {chips.map((a, i) => {
        const wasAnalyzed = a.analysis_status === "text_extracted" || a.analysis_status === "vision_analyzed";
        return (
          <div
            key={i}
            title={analysisStatusTitle(a)}
            className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${
              wasAnalyzed
                ? "border-zinc-700 bg-zinc-900 text-zinc-300"
                : "border-zinc-800 bg-zinc-900/50 text-zinc-500"
            }`}
          >
            <span>{fileTypeIcon(a.mime_type)}</span>
            <span className="max-w-[120px] truncate">{a.filename}</span>
            <span className="text-[9px] uppercase tracking-wide text-zinc-500">
              {ANALYSIS_STATUS_LABELS[a.analysis_status] || a.analysis_status}
            </span>
            {a.analysis_status === "unsupported" && <span aria-label="Not readable by Echo">⚠️</span>}
          </div>
        );
      })}
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

// CommonMark treats a bare "<digits>." or "<digits>)" at the start of a line as an
// ordered-list marker. A short numeric answer like "84." with nothing else on that
// line gets swallowed into an empty, invisible list item — escape it so it renders
// as plain text instead.
function escapeLeadingBareOrdinal(content: string): string {
  return content.replace(/^(\d{1,9})([.)])(?=\s*(?:\n|$))/, "$1\\$2");
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {escapeLeadingBareOrdinal(content)}
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
          {isUser ? (
            message.content
          ) : message.streaming && !message.content ? (
            <span className="inline-flex gap-1 py-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500 [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500 [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500" />
            </span>
          ) : (
            <>
              <MarkdownContent content={message.content} />
              {message.streaming && (
                <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-zinc-400 align-text-bottom" />
              )}
            </>
          )}
        </div>
        <div className="w-full px-1">
          <GeneratedImages message={message} />
          <AttachmentChips message={message} />
        </div>
        {/* Internal processing detail — reasoning, Atlas memory-usage notes,
            auto-extracted memory-candidate notices, and independence-nudge
            debug reasons — is deliberately not rendered here. It's for
            ECHO's own memory/tools/debugging, not the person using the chat.
            The underlying data (reasoning, atlas_citations,
            conversation_snippets, independence_nudge_reason, etc.) still
            flows through the API response unchanged; only the UI stopped
            showing it in the normal chat view. Atlas usage is still
            reviewable in the Atlas UI itself (memory candidates, entries). */}
        {!isUser && <MemoryNote message={message} />}
        {!isUser && buildViaLine(message) && (
          <div className="mt-1 px-1 text-[10px] uppercase tracking-wide text-zinc-600">
            {buildViaLine(message)}
          </div>
        )}
      </div>
    </div>
  );
}
