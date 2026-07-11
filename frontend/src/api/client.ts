// Nullish (not ||) coalescing: an explicitly empty string means "same origin"
// (used in the production Docker build, proxied by nginx), vs. unset falling
// back to the local dev API port.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Distinct from ApiError: the request never got an HTTP response at all
// (DNS failure, connection refused, CORS block, mixed-content block, etc).
// Carries the URL that was attempted so a remote/mobile repro is diagnosable
// from the on-screen message alone, without needing devtools.
export class NetworkError extends Error {
  url: string;
  constructor(url: string, cause: unknown) {
    const causeMessage = cause instanceof Error ? cause.message : String(cause);
    super(`Network error reaching ${url}: ${causeMessage}`);
    this.url = url;
  }
}

async function _handleResponse<T>(res: Response, url: string): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    let bodyText: string | null = null;
    try {
      bodyText = await res.text();
      detail = JSON.parse(bodyText).detail || detail;
    } catch {
      // response wasn't JSON (e.g. an nginx/proxy error page) — fall back to
      // whatever text we got, or statusText if we couldn't even read that.
      if (bodyText) detail = bodyText.slice(0, 300);
    }
    console.error(`[api] ${res.status} from ${url}: ${detail}`);
    throw new ApiError(res.status, `${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch (err) {
    console.error(`[api] fetch failed for ${url}`, err);
    throw new NetworkError(url, err);
  }
  return _handleResponse<T>(res, url);
}

// No Content-Type header here — the browser must set its own multipart boundary,
// which it can only do if fetch() computes the header itself from the FormData body.
async function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, { method: "POST", body: formData });
  } catch (err) {
    console.error(`[api] fetch failed for ${url}`, err);
    throw new NetworkError(url, err);
  }
  return _handleResponse<T>(res, url);
}

// ---- Types ----
export type EpistemicStatus = "Verified" | "Inferred" | "Hypothesis" | "Narrative";
export type Role = "founder" | "guardian_a" | "guardian_b" | "guardian_c" | "verifier";
export type MemoryType =
  | "fact"
  | "preference"
  | "mood"
  | "goal"
  | "fear"
  | "capability"
  | "project"
  | "relationship"
  | "event";
export const MEMORY_TYPES: MemoryType[] = [
  "fact",
  "preference",
  "mood",
  "goal",
  "fear",
  "capability",
  "project",
  "relationship",
  "event",
];

export interface AtlasCitation {
  id: string;
  content: string;
  epistemic_status: EpistemicStatus;
  confidence: number;
}

export interface MemoryUpdate {
  saved: boolean;
  explicit: boolean;
  content: string | null;
  error: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  reasoning: string | null;
  provider_used: string;
  atlas_citations: AtlasCitation[];
  memory_update: MemoryUpdate | null;
}

export interface AttachmentOut {
  filename: string;
  mime_type: string;
  size_bytes: number;
  understood: boolean;
}

export interface MessageOut {
  id: string;
  role: string;
  content: string;
  reasoning: string | null;
  provider: string | null;
  atlas_citations: AtlasCitation[];
  attachments: AttachmentOut[];
  created_at: string;
}

export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
}

export interface ConversationDetailOut extends ConversationOut {
  messages: MessageOut[];
}

export interface WelcomeResponse {
  greeting: string;
  referenced_memories: string[];
}

export interface DeleteConversationResponse {
  ok: boolean;
  deleted_id: string;
}

export interface SendWithFilesResponse {
  conversation_id: string;
  message: MessageOut;
}

export interface AtlasEntryOut {
  id: string;
  content: string;
  epistemic_status: EpistemicStatus;
  memory_type: MemoryType;
  tags: string[];
  confidence: number;
  source: string | null;
  observed_at: string;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface AtlasSearchResult extends AtlasEntryOut {
  distance: number | null;
}

export interface CoreValueOut {
  rank: number;
  name: string;
  description: string;
}

export interface ValueInvariantOut {
  id: string;
  text: string;
}

export interface EdgeCaseProtocolOut {
  id: string;
  scenario: string;
  resolution: string;
}

export interface AmendmentLogEntryOut {
  id: string;
  title: string;
  text: string;
  ratified_at: string | null;
}

export interface ConstitutionOut {
  version: string;
  codename: string;
  philosophy: string;
  core_values: CoreValueOut[];
  value_invariants: ValueInvariantOut[];
  edge_case_protocols: EdgeCaseProtocolOut[];
  amendment_log: AmendmentLogEntryOut[];
  full_text: string;
}

export interface VoteOut {
  role: string;
  decision: string;
  comment: string | null;
  created_at: string;
}

export interface AmendmentOut {
  id: string;
  title: string;
  text: string;
  rationale: string | null;
  proposed_by: string;
  status: string;
  created_at: string;
  decided_at: string | null;
  votes: VoteOut[];
  tally: {
    guardian_approvals: number;
    guardian_rejections: number;
    guardian_quorum_met: boolean;
    guardian_blocked: boolean;
    verifier_decision: string | null;
    ready_to_ratify: boolean;
    ready_to_reject: boolean;
  };
}

export interface ProviderStatus {
  name: string;
  label: string;
  available: boolean;
  reason: string | null;
}

// ---- Chat ----
export const sendChatMessage = (message: string, provider: string, conversationId?: string) =>
  request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, provider, conversation_id: conversationId ?? null }),
  });

export const sendChatMessageWithFiles = (
  message: string,
  provider: string,
  files: File[],
  conversationId?: string
) => {
  const form = new FormData();
  form.append("message", message);
  form.append("provider", provider);
  if (conversationId) form.append("conversation_id", conversationId);
  for (const file of files) form.append("files", file);
  return requestMultipart<SendWithFilesResponse>("/api/chat/send-with-files", form);
};

export const deleteConversation = (id: string) =>
  request<DeleteConversationResponse>(`/api/conversations/${id}`, { method: "DELETE" });

export const listConversations = () => request<ConversationOut[]>("/api/conversations");

export const getWelcomeGreeting = () => request<WelcomeResponse>("/api/chat/welcome");

export const getConversation = (id: string) =>
  request<ConversationDetailOut>(`/api/conversations/${id}`);

// ---- Atlas ----
export const listAtlasEntries = (memoryType?: MemoryType) =>
  request<AtlasEntryOut[]>(
    `/api/atlas${memoryType ? `?memory_type=${encodeURIComponent(memoryType)}` : ""}`
  );

export const searchAtlas = (q: string, topK = 5) =>
  request<AtlasSearchResult[]>(`/api/atlas/search?q=${encodeURIComponent(q)}&top_k=${topK}`);

export const createAtlasEntry = (payload: Partial<AtlasEntryOut> & { content: string }) =>
  request<AtlasEntryOut>("/api/atlas", { method: "POST", body: JSON.stringify(payload) });

export const updateAtlasEntry = (id: string, payload: Partial<AtlasEntryOut>) =>
  request<AtlasEntryOut>(`/api/atlas/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

export const deleteAtlasEntry = (id: string) =>
  request<void>(`/api/atlas/${id}`, { method: "DELETE" });

// ---- Constitution ----
export const getConstitution = () => request<ConstitutionOut>("/api/constitution");

// ---- Amendments ----
export const listAmendments = () => request<AmendmentOut[]>("/api/amendments");

export const proposeAmendment = (payload: {
  title: string;
  text: string;
  rationale?: string;
  proposed_by: Role;
}) => request<AmendmentOut>("/api/amendments", { method: "POST", body: JSON.stringify(payload) });

export const voteOnAmendment = (
  id: string,
  payload: { role: Role; decision: "approve" | "reject"; comment?: string }
) =>
  request<AmendmentOut>(`/api/amendments/${id}/vote`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

// ---- Models ----
export const listModelProviders = () => request<ProviderStatus[]>("/api/models");
