import { useEffect, useRef, useState } from "react";
import {
  AttachmentAnalysisStatus,
  FeatureAvailability,
  MemoryUpdate,
  MessageOut,
  StreamDoneEvent,
  WelcomeResponse,
  generateImage,
  getConversation,
  getFeatureAvailability,
  getWelcomeGreeting,
  sendChatMessage,
  sendChatMessageWithFiles,
  streamChatMessage,
} from "../../api/client";
import { useApi } from "../../api/useApi";
import { useConversations } from "../../state/conversationsContext";
import { useRole } from "../../state/roleContext";
import ChatActionMenu from "./ChatActionMenu";
import ConversationList from "./ConversationList";
import EchoPresence, { PresenceState } from "./EchoPresence";
import MessageBubble from "./MessageBubble";
import ModelPicker from "./ModelPicker";
import UsageStatus from "./UsageStatus";

export interface DisplayMessage extends MessageOut {
  memory_update?: MemoryUpdate | null;
  // True only while this specific reply is still receiving tokens from
  // POST /api/chat/stream — lets MessageBubble show a live typing indicator
  // and lets a cancel wipe just this one message's in-progress state.
  streaming?: boolean;
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

// Best-effort cosmetic guess for the optimistic chip only — the server's real
// analysis_status (set once it knows which provider actually handled the turn)
// is what gets shown for every message that came back from the backend.
function guessAnalysisStatus(file: File, understood: boolean): AttachmentAnalysisStatus {
  if (!understood) return "unsupported";
  const mime = file.type;
  if (mime.startsWith("text/") || mime === "application/pdf") return "text_extracted";
  return "stored";
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

const VOICE_LANG = "en-US";
const SILENCE_STOP_MS = 1800;

// Strip markdown so SpeechSynthesis doesn't read out literal asterisks/backticks/
// header hashes/link syntax — only the reply's actual words should be spoken.
function stripMarkdownForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " code block omitted ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^>\s+/gm, "")
    .replace(/^[-*+]\s+/gm, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\s+/g, " ")
    .trim();
}

export default function ChatView() {
  const { provider } = useRole();
  const { conversationId, selectConversation, refreshConversations } = useConversations();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [welcome, setWelcome] = useState<WelcomeResponse | null>(null);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [features, setFeatures] = useState<FeatureAvailability | null>(null);
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [speakEnabled, setSpeakEnabled] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preferredVoiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  const { run: runSend, loading: sendingText, error: sendError } = useApi(sendChatMessage);
  const { run: runSendWithFiles, loading: sendingFiles, error: filesError } = useApi(sendChatMessageWithFiles);
  const { run: runLoadConversation } = useApi(getConversation);
  // Errors intentionally not surfaced anywhere — a failed welcome fetch should be
  // invisible and just leave the plain empty-state placeholder in place.
  const { run: runWelcome, loading: welcomeLoading } = useApi(getWelcomeGreeting);
  // Deliberately separate from runSend/runSendWithFiles — this hits a PAID model, so
  // its own loading/error state must never get silently merged into normal chat's.
  const { run: runGenerateImage, loading: generatingImage, error: generateImageError } =
    useApi(generateImage);

  const sending = sendingText || sendingFiles || isStreaming;
  const error = sendError || filesError || streamError;
  const presenceState: PresenceState = listening
    ? "listening"
    : isSpeaking
      ? "speaking"
      : sending
        ? "thinking"
        : "idle";

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

  useEffect(() => {
    getFeatureAvailability()
      .then(setFeatures)
      .catch(() => setFeatures(null));
  }, []);

  const geminiAvailable = features ? features.vision.available : null;
  const hasImageAttached = attachedFiles.some((f) => f.type.startsWith("image/"));
  const visionWarning =
    hasImageAttached && geminiAvailable === false
      ? "Image understanding is unavailable right now (Gemini isn't configured/reachable) — Echo won't be able to see this image's contents."
      : hasImageAttached && geminiAvailable === true && provider !== "auto" && provider !== "gemini"
        ? "This provider can't see images. Switch to Auto or Gemini above to have this image analyzed."
        : null;

  const canGenerateImage = features?.image_generation ?? true; // default permissive until the fetch resolves
  // image_generation_detail.reason is the image-generation-specific reason
  // (e.g. "COMFYUI_BASE_URL not set", "Ollama does not support image
  // generation in this build") — vision.reason is a different concern
  // (image *understanding*, used above for visionWarning) and would show a
  // misleading reason here (e.g. blaming Gemini vision config for an
  // unrelated image-gen provider being unavailable).
  const imageGenerationUnavailableReason = features && !features.image_generation
    ? features.image_generation_detail.reason || "not configured"
    : null;

  // Stop any in-flight speech when navigating away from Chat entirely.
  useEffect(() => {
    return () => {
      if (speechSynthesisSupported) window.speechSynthesis.cancel();
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      try {
        recognitionRef.current?.abort();
      } catch {
        // already stopped
      }
    };
  }, []);

  // getVoices() is notoriously async in some browsers — the list is empty until
  // the voiceschanged event fires, so this needs both an immediate attempt and a
  // listener for when the real list shows up.
  useEffect(() => {
    if (!speechSynthesisSupported) return;
    function pickVoice() {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length === 0) return;
      const preferred =
        voices.find((v) => /natural|enhanced/i.test(v.name) && v.lang.startsWith("en")) ||
        voices.find((v) => /natural|enhanced/i.test(v.name)) ||
        voices.find((v) => v.lang.startsWith("en") && v.default) ||
        voices.find((v) => v.lang.startsWith("en")) ||
        voices[0];
      preferredVoiceRef.current = preferred ?? null;
    }
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  function speak(text: string) {
    if (!speakEnabled || !speechSynthesisSupported) return;
    const cleaned = stripMarkdownForSpeech(text);
    if (!cleaned) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleaned);
    if (preferredVoiceRef.current) utterance.voice = preferredVoiceRef.current;
    utterance.rate = 0.97;
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

  function clearSilenceTimer() {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }

  // Resets on every result (interim or final) — only fires after genuine silence,
  // so someone mid-thought with pauses between phrases doesn't get cut off, but a
  // real stop (~1.5-2s of nothing) ends listening automatically.
  function armSilenceTimer() {
    clearSilenceTimer();
    silenceTimerRef.current = setTimeout(() => {
      try {
        recognitionRef.current?.stop();
      } catch {
        // already stopped
      }
    }, SILENCE_STOP_MS);
  }

  function stopListening() {
    clearSilenceTimer();
    try {
      recognitionRef.current?.stop();
    } catch {
      // already stopped
    }
    // Belt-and-suspenders: onend should fire and do this too, but a tap-to-stop
    // must always feel immediate regardless of current recognition internal state.
    setListening(false);
  }

  function startListening() {
    setVoiceError(null);
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = VOICE_LANG;
    recognition.interimResults = true;
    recognition.continuous = true;

    let finalTranscript = "";
    const baseInput = input.trim();

    recognition.onresult = (event: any) => {
      armSilenceTimer();
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += (finalTranscript ? " " : "") + result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }
      const pieces = [baseInput, finalTranscript, interim].filter(Boolean);
      setInput(pieces.join(" "));
    };

    recognition.onerror = (event: any) => {
      clearSilenceTimer();
      if (event.error === "no-speech") {
        setVoiceError("Didn't catch any speech — try again.");
      } else if (event.error === "audio-capture") {
        setVoiceError("No microphone found.");
      } else if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setVoiceError("Microphone access was denied.");
      } else {
        setVoiceError(`Voice input error: ${event.error}`);
      }
      setListening(false);
      recognitionRef.current = null;
    };

    recognition.onend = () => {
      clearSilenceTimer();
      setListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
    // Also arm on start, not just after the first result — otherwise a session
    // with genuinely zero speech would rely solely on the no-speech error event,
    // which not all browsers fire promptly.
    armSilenceTimer();
  }

  function toggleListening() {
    if (!SpeechRecognitionCtor) return;
    if (listening) {
      stopListening();
      return;
    }
    startListening();
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
      attachments: filesToSend.map((f) => {
        const understood = guessUnderstood(f);
        return {
          filename: f.name,
          mime_type: f.type || "application/octet-stream",
          size_bytes: f.size,
          understood,
          analysis_status: guessAnalysisStatus(f, understood),
          generated: false,
          base64_preview: null,
        };
      }),
      fallback_note: null,
      independence_nudge_reason: null,
      conversation_snippets: [],
      envelope_status: "missing",
      envelope_degradation_reason: null,
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

    // Streaming path (text-only — file uploads use the non-streaming branch
    // above, since POST /api/chat/stream doesn't accept attachments).
    const streamingId = `streaming-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: streamingId,
        role: "echo",
        content: "",
        reasoning: null,
        provider: null,
        atlas_citations: [],
        attachments: [],
        fallback_note: null,
        independence_nudge_reason: null,
        conversation_snippets: [],
        envelope_status: "missing",
        envelope_degradation_reason: null,
        created_at: new Date().toISOString(),
        streaming: true,
      },
    ]);

    const controller = new AbortController();
    streamAbortRef.current = controller;
    setIsStreaming(true);
    setStreamError(null);

    await streamChatMessage(
      text,
      provider,
      conversationId,
      {
        onToken: (piece) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingId ? { ...m, content: m.content + piece } : m))
          );
        },
        onDone: (data: StreamDoneEvent) => {
          selectConversation(data.conversation_id);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId
                ? {
                    id: data.message_id,
                    role: "echo",
                    content: data.content,
                    reasoning: data.reasoning,
                    provider: data.provider_used,
                    atlas_citations: data.atlas_citations,
                    attachments: [],
                    memory_update: data.memory_update,
                    fallback_note: data.fallback_note,
                    independence_nudge_reason: data.independence_nudge_reason,
                    conversation_snippets: data.conversation_snippets,
                    envelope_status: data.envelope_status,
                    envelope_degradation_reason: data.envelope_degradation_reason,
                    created_at: m.created_at,
                  }
                : m
            )
          );
          speak(data.content);
          refreshConversations();
          setIsStreaming(false);
          streamAbortRef.current = null;
        },
        onError: (detail) => {
          setStreamError(detail);
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingId ? { ...m, streaming: false } : m))
          );
          setIsStreaming(false);
          streamAbortRef.current = null;
        },
      },
      controller.signal
    );
  }

  // Aborts the in-flight stream request. The server-side generator sees the
  // dropped connection and stops before saving anything (see
  // POST /api/chat/stream) — so on cancel, nothing gets persisted for this
  // turn; the partial text stays visible locally for reference this session
  // only, clearly marked as no longer streaming.
  function handleStopStreaming() {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsStreaming(false);
    setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
  }

  // Deliberately separate action from handleSend — must only ever run from an
  // explicit click on the dedicated "Generate image" button, never automatically.
  async function handleGenerateImage() {
    const prompt = input.trim();
    if (!prompt || generatingImage || sending) return;
    setInput("");

    const optimisticUser: DisplayMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: `Generate image: ${prompt}`,
      reasoning: null,
      provider: null,
      atlas_citations: [],
      attachments: [],
      fallback_note: null,
      independence_nudge_reason: null,
      conversation_snippets: [],
      envelope_status: "missing",
      envelope_degradation_reason: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    const result = await runGenerateImage(prompt, conversationId);
    if (!result) return;

    selectConversation(result.conversation_id);
    setMessages((prev) => [...prev, result.message]);
    refreshConversations();
  }

  return (
    <div className="flex h-full">
      <aside className="hidden lg:flex w-60 flex-col border-r border-zinc-800 bg-zinc-950 p-3">
        <ConversationList compact />
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
          <EchoPresence state={presenceState} showLabel />
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
            <UsageStatus />
          </div>
        </header>

        <div className="relative flex-1 overflow-y-auto p-4 space-y-4">
          {/* Ambient atmosphere: two large, very low-opacity blurred blobs drifting
              slowly. Fixed behind content (not scrolling with it), transform/opacity
              only so it's cheap, and off entirely under prefers-reduced-motion. */}
          <div className="pointer-events-none fixed inset-x-0 top-24 bottom-0 -z-10 overflow-hidden">
            <div
              className="motion-safe:animate-ambient-drift absolute left-1/4 top-10 h-72 w-72 rounded-full opacity-[0.07] blur-3xl"
              style={{ background: "radial-gradient(circle, #7c9eff 0%, transparent 70%)" }}
            />
            <div
              className="motion-safe:animate-ambient-drift absolute right-1/4 bottom-20 h-80 w-80 rounded-full opacity-[0.05] blur-3xl [animation-delay:-11s]"
              style={{ background: "radial-gradient(circle, #a8c0ff 0%, transparent 70%)" }}
            />
          </div>
          {messages.length === 0 && (
            <div className="mx-auto flex max-w-md flex-col items-center pt-12">
              <div className="mb-5">
                <EchoPresence state={welcomeLoading ? "thinking" : "idle"} size="lg" />
              </div>
              {welcome ? (
                <div className="flex w-full justify-start">
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
                <div className="text-xs text-zinc-500">Echo is remembering…</div>
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
            <div className="flex items-center pl-1">
              <EchoPresence state="thinking" size="sm" showLabel />
            </div>
          )}
          {generatingImage && (
            <div className="flex items-center gap-2 pl-1 text-xs text-zinc-500">
              <span className="animate-pulse">🎨</span>
              <span>Generating image… this can take several seconds.</span>
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
          {generateImageError && (
            <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
              Image generation failed: {generateImageError}
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
          {visionWarning && (
            <div className="mb-2 rounded-lg border border-amber-900 bg-amber-950/40 px-3 py-1.5 text-xs text-amber-300">
              ⚠ {visionWarning}
            </div>
          )}
          {voiceError && (
            <div className="mb-2 rounded-lg border border-red-900 bg-red-950/50 px-3 py-1.5 text-xs text-red-300">
              {voiceError}
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
          {listening && (
            <div className="mb-2 flex items-center gap-1.5 pl-1 text-xs text-accent">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              Listening…
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
            <ChatActionMenu
              onAttachFile={() => fileInputRef.current?.click()}
              onToggleVoice={toggleListening}
              onGenerateImage={handleGenerateImage}
              voiceSupported={!!SpeechRecognitionCtor}
              listening={listening}
              canGenerateImage={canGenerateImage}
              imageGenerationUnavailableReason={imageGenerationUnavailableReason}
            />
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
            {isStreaming ? (
              <button
                onClick={handleStopStreaming}
                className="rounded-xl border border-red-800 bg-red-950/40 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-950/70"
              >
                Stop
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={sending || (!input.trim() && attachedFiles.length === 0)}
                className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
              >
                Send
              </button>
            )}
          </div>
          {generatingImage && (
            <p className="mt-1.5 pl-1 text-[10px] text-amber-600/80">
              🎨 Generating image… uses a paid model, a few cents per image.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
