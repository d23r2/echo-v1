import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import AtlasNotes from "./AtlasNotes";
import { DisplayMessage } from "./ChatView";

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

  // An auto-extracted candidate isn't saved directly anymore — it's queued for
  // review in Atlas's "Memory Candidates" section (see app/routers/chat.py).
  if (update.pending_review) {
    return (
      <div className="mt-1 flex items-start gap-1 px-1 text-[11px] text-blue-400">
        <span>📋</span>
        <span>Added as a memory candidate — review it in Atlas.</span>
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
        {!isUser && (
          <div className="w-full px-1">
            {/* Reasoning is intentionally not rendered here — it's internal
                processing detail, not meant for normal-use display. The data
                (message.reasoning, envelope_status, envelope_degradation_reason)
                still flows through the API response unchanged; only the UI
                stopped showing it. See ReasoningTrace.tsx if this needs to
                come back later (e.g. behind a debug toggle). */}
            <AtlasNotes message={message} />
          </div>
        )}
        {!isUser && <MemoryNote message={message} />}
        {!isUser && message.provider && (
          <div className="mt-1 px-1 text-[10px] uppercase tracking-wide text-zinc-600">
            via {message.provider}
            {message.fallback_note && (
              <span
                className="ml-1.5 lowercase tracking-normal text-amber-600/80"
                title={message.fallback_note}
              >
                ⚠ fallback
              </span>
            )}
          </div>
        )}
        {!isUser && message.independence_nudge_reason && (
          <div
            className="mt-0.5 px-1 text-[10px] text-zinc-700"
            title={`Independence nudge (debug): ${message.independence_nudge_reason}`}
          >
            · independence nudge: {message.independence_nudge_reason.replace(/_/g, " ")}
          </div>
        )}
      </div>
    </div>
  );
}
