import { useEffect, useRef, useState } from "react";

interface ChatActionMenuProps {
  onAttachFile: () => void;
  onToggleVoice: () => void;
  onGenerateImage: () => void;
  voiceSupported: boolean;
  listening: boolean;
  canGenerateImage: boolean;
  imageGenerationUnavailableReason: string | null;
}

// A single "+" entry point for chat actions (attach/voice/image-gen/future
// tools) instead of a row of separate buttons — keeps the input area simple
// while still surfacing everything in one place. Closes on selection, Escape,
// or a click outside; each item disables cleanly (with a reason) rather than
// letting the user hit a failure.
export default function ChatActionMenu({
  onAttachFile,
  onToggleVoice,
  onGenerateImage,
  voiceSupported,
  listening,
  canGenerateImage,
  imageGenerationUnavailableReason,
}: ChatActionMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function choose(action: () => void) {
    action();
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions"
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-lg transition-colors ${
          open
            ? "border-accent bg-accent/15 text-accent"
            : "border-zinc-700 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
        }`}
      >
        +
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-10 mb-2 w-56 rounded-xl border border-zinc-700 bg-zinc-900 p-1 shadow-xl"
        >
          <button
            role="menuitem"
            onClick={() => choose(onAttachFile)}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800"
          >
            📎 Attach file
          </button>

          {voiceSupported && (
            <button
              role="menuitem"
              onClick={() => choose(onToggleVoice)}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800"
            >
              🎤 {listening ? "Stop voice input" : "Voice input"}
            </button>
          )}

          <button
            role="menuitem"
            onClick={() => canGenerateImage && choose(onGenerateImage)}
            disabled={!canGenerateImage}
            title={canGenerateImage ? "Uses a paid image model — a few cents per image." : imageGenerationUnavailableReason || undefined}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:text-zinc-600 disabled:hover:bg-transparent"
          >
            🎨 {canGenerateImage ? "Generate image" : `Generate image (${imageGenerationUnavailableReason || "unavailable"})`}
          </button>

          <button
            role="menuitem"
            disabled
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-600"
          >
            🔧 More tools coming later
          </button>
        </div>
      )}
    </div>
  );
}
