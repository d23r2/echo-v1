import { DisplayMessage } from "./ChatView";

// Short, human labels for the "via ..." line — deliberately different from
// ModelPicker's verbose labels ("Claude (Anthropic)", "Local (Ollama)"),
// which are too long for an inline metadata line.
const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  anthropic: "Claude",
  openai: "GPT",
  gemini: "Gemini",
  grok: "Grok",
  azure: "Azure",
  ollama: "Ollama",
};

function providerDisplayName(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] || provider;
}

// Source display name mapping (see backend SourceUsed.source_type) — kept
// here rather than trusting the backend to send a pre-formatted string, so
// the frontend controls exactly what's short/clean enough for this line.
function sourceDisplayName(s: NonNullable<DisplayMessage["sources_used"]>[number]): string {
  switch (s.source_type) {
    case "wiki":
      return "Wikipedia";
    case "web_search":
      return "SearXNG";
    case "rss":
      return s.feed_title || "RSS";
    case "direct_page":
      return s.domain || "direct page";
    case "atlas_memory":
      return "Atlas";
    case "previous_conversation":
      return "previous conversation";
    case "library_file":
      return "Library";
    default:
      return s.provider || "source";
  }
}

/** Builds the single small "via X, Y" line shown under an assistant reply —
 * the only source/provider transparency normal chat shows. Everything else
 * (reasoning, Atlas notes, memory-candidate details, raw source dumps) stays
 * out of the normal chat view; see MessageBubble.tsx. */
export function buildViaLine(message: DisplayMessage): string | null {
  if (!message.provider) return null;

  const names: string[] = [];
  for (const s of message.sources_used || []) {
    const name = sourceDisplayName(s);
    if (!names.includes(name)) names.push(name);
  }
  if ((message.atlas_citations?.length ?? 0) > 0 && !names.includes("Atlas")) {
    names.push("Atlas");
  }
  if ((message.conversation_snippets?.length ?? 0) > 0 && !names.includes("previous conversation")) {
    names.push("previous conversation");
  }
  if (message.fallback_note && !names.includes("fallback")) {
    names.push("fallback");
  }

  const parts = [providerDisplayName(message.provider), ...names];
  return `via ${parts.join(", ")}`;
}
