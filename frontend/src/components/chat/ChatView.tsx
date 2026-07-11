import { useEffect, useRef, useState } from "react";
import {
  MemoryUpdate,
  MessageOut,
  WelcomeResponse,
  getConversation,
  getWelcomeGreeting,
  sendChatMessage,
  sendChatMessageWithFiles,
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

const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;

// Mirrors backend/app/attachments.py's classify() — purely cosmetic for the
// optimistic chip shown before the server round-trip confirms the real value.
function guessUnderstood(file: File): boolean {
  const mime = file.type;
  if (
    mime.startsWith("image/") ||
    mime.startsWith("audio/") ||
    mime.startsWith("video/") ||
    mime.startsWith("text/") ||
    mime === "application/pdf"
  ) {
    return true;
  }
  const codeExts = [
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".csv", ".yaml", ".yml",
    ".html", ".css", ".sh", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php", ".sql",
  ];
  const name = file.name.toLowerCase();
  return codeExts.some((ext) => name.endsWith(ext));
}

function fileTypeIcon(mime: string): string {
  if (mime.startsWith("image/")) return "🖼️";
  if (mime.startsWith("audio/")) return "🎵";
  if (mime.startsWith("video/")) return "🎬";
  if (mime === "application/pdf") return "📄";
  if (mime.startsWith("text/")) return "📝";
  return "📎";
}

const SpeechRecognitionCtor: any =
  typeof window !== "undefined" && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
const speechSynthesisSupported = typeof window !== "undefined" && "speechSynthesis" in window;

export default function ChatView() {
  const { provider } = useRole();
  const { conversationId, selectConversation, refreshConversations } = useConversations();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [welcome, setWelcome] = useState<WelcomeResponse | null>(null);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [speakEnabled, setSpeakEnabled] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);

  const { run: runSend, loading: sendingText, error: sendError } = useApi(sendChatMessage);
  const { run: runSendWithFiles, loading: sendingFiles, error: filesError } = useApi(sendChatMessageWithFiles);
  const { run: runLoadConversation } = useApi(getConversation);
  // Errors intentionally not surfaced anywhere — a failed welcome fetch should be
  // invisible and just leave the plain empty-state placeholder in place.
  const { run: runWelcome, loading: welcomeLoading } = useApi(getWelcomeGreeting);

  const sending = sendingText || sendingFiles;
  const error = sendError || filesError;

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
  }, [messages, sending]);

  // Stop any in-flight speech when navigating away from Chat entirely.
  useEffect(() => {
    return () => {
      if (speechSynthesisSupported) window.speechSynthesis.cancel();
    };
  }, []);

  function speak(text: string) {
    if (!speakEnabled || !speechSynthesisSupported) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }

  function handleSpeakerClick() {
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }
    setSpeakEnabled((v) => !v);
  }

  function toggleListening() {
    if (!SpeechRecognitionCtor) return;
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results)
        .map((r: any) => r[0].transcript)
        .join(" ");
      setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  function handleFilesSelected(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    const combined = [...attachedFiles, ...Array.from(fileList)];
    const totalBytes = combined.reduce((sum, f) => sum + f.size, 0);
    if (totalBytes > MAX_ATTACHMENT_BYTES) {
      setAttachmentError(
        `Attachments must be under 15MB total (currently ${(totalBytes / (1024 * 1024)).toFixed(1)}MB) — remove something and try again.`
      );
      return;
    }
    setAttachmentError(null);
    setAttachedFiles(combined);
  }

  function removeAttachedFile(index: number) {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
    setAttachmentError(null);
  }

  async function handleSend() {
    const text = input.trim();
    if ((!text && attachedFiles.length === 0) || sending) return;
    const filesToSend = attachedFiles;
    setInput("");
    setAttachedFiles([]);
    setAttachmentError(null);

    const optimisticUser: DisplayMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: text || "(files attached)",
      reasoning: null,
      provider: null,
      atlas_citations: [],
      attachments: filesToSend.map((f) => ({
        filename: f.name,
        mime_type: f.type || "application/octet-stream",
        size_bytes: f.size,
        understood: guessUnderstood(f),
      })),
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    if (filesToSend.length > 0) {
      const result = await runSendWithFiles(text, provider, filesToSend, conversationId);
      if (!result) return;
      selectConversation(result.conversation_id);
      setMessages((prev) => [...prev, { ...result.message, memory_update: null }]);
      speak(result.message.content);
      refreshConversations();
      return;
    }

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
        attachments: [],
        memory_update: result.memory_update,
        created_at: new Date().toISOString(),
      },
    ]);
    speak(result.content);
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
          <div className="flex items-center gap-2">
            {speechSynthesisSupported && (
              <button
                onClick={handleSpeakerClick}
                title={
                  isSpeaking
                    ? "Stop speaking"
                    : speakEnabled
                      ? "Voice replies: on (click to turn off)"
                      : "Voice replies: off (click to turn on)"
                }
                className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm transition-colors ${
                  speakEnabled
                    ? "bg-accent/15 text-accent"
                    : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
                }`}
              >
                {isSpeaking ? "⏹" : speakEnabled ? "🔊" : "🔈"}
              </button>
            )}
            <ModelPicker />
          </div>
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
          {sending && (
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
          {attachmentError && (
            <div className="mb-2 rounded-lg border border-red-900 bg-red-950/50 px-3 py-1.5 text-xs text-red-300">
              {attachmentError}
            </div>
          )}
          {attachedFiles.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {attachedFiles.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300"
                >
                  <span>{fileTypeIcon(f.type)}</span>
                  <span className="max-w-[140px] truncate">{f.name}</span>
                  <button
                    onClick={() => removeAttachedFile(i)}
                    aria-label={`Remove ${f.name}`}
                    className="text-zinc-500 hover:text-red-400"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                handleFilesSelected(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              title="Attach files"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-zinc-700 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            >
              📎
            </button>
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
            {SpeechRecognitionCtor && (
              <button
                onClick={toggleListening}
                title={listening ? "Stop listening" : "Speak your message"}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors ${
                  listening
                    ? "border-accent bg-accent/15 text-accent animate-pulse"
                    : "border-zinc-700 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                }`}
              >
                🎤
              </button>
            )}
            <button
              onClick={handleSend}
              disabled={sending || (!input.trim() && attachedFiles.length === 0)}
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
