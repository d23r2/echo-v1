// Nullish (not ||) coalescing: an explicitly empty string means "same origin"
// (used in the production Docker build, proxied by nginx), vs. unset falling
// back to the local dev API port.
export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
export const EPISTEMIC_STATUSES: EpistemicStatus[] = ["Verified", "Inferred", "Hypothesis", "Narrative"];
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
  pending_review: boolean;
  content: string | null;
  error: string | null;
}

export interface ConversationSnippetOut {
  message_id: string;
  conversation_id: string;
  conversation_title: string;
  role: string;
  created_at: string | null;
  snippet: string;
  relevance: number | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  reasoning: string | null;
  provider_used: string;
  atlas_citations: AtlasCitation[];
  memory_update: MemoryUpdate | null;
  fallback_note: string | null;
  independence_nudge_reason: string | null;
  conversation_snippets: ConversationSnippetOut[];
  envelope_status: EnvelopeStatus;
  envelope_degradation_reason: string | null;
}

export type EnvelopeStatus = "complete" | "partial" | "missing" | "malformed";

export type AttachmentAnalysisStatus = "text_extracted" | "vision_analyzed" | "stored" | "unsupported";

export interface AttachmentOut {
  filename: string;
  mime_type: string;
  size_bytes: number;
  understood: boolean;
  analysis_status: AttachmentAnalysisStatus;
  generated: boolean;
  base64_preview: string | null;
}

export interface MessageOut {
  id: string;
  role: string;
  content: string;
  reasoning: string | null;
  provider: string | null;
  atlas_citations: AtlasCitation[];
  attachments: AttachmentOut[];
  fallback_note: string | null;
  independence_nudge_reason: string | null;
  conversation_snippets: ConversationSnippetOut[];
  envelope_status: EnvelopeStatus;
  envelope_degradation_reason: string | null;
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

export interface VerificationCheckOut {
  command: string;
  status: "passed" | "failed" | "unavailable";
  exit_code: number | null;
  stdout_summary: string;
  stderr_summary: string;
  timestamp: string;
}

export interface SelfImprovementRequestOut {
  id: string;
  title: string;
  description: string;
  proposed_by: string;
  status: string;
  patch_summary: string | null;
  verification_status: string;
  verification_notes: string | null;
  verification_checks: VerificationCheckOut[];
  verified_at: string | null;
  created_at: string;
  updated_at: string;
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
  outdated: boolean;
  created_at: string;
  updated_at: string;
}

export interface AtlasSearchResult extends AtlasEntryOut {
  distance: number | null;
}

export interface MemoryExtractionLogOut {
  id: string;
  conversation_id: string | null;
  message_id: string | null;
  explicit_request: boolean;
  memory_block_present: boolean;
  was_none: boolean;
  json_detected: boolean;
  parse_succeeded: boolean;
  saved: boolean;
  rejection_reason: string | null;
  created_at: string;
}

export type MemoryCandidateStatus = "pending" | "accepted" | "rejected";

export interface MemoryCandidateOut {
  id: string;
  content: string;
  epistemic_status: EpistemicStatus;
  memory_type: MemoryType;
  tags: string[];
  confidence: number;
  source: string | null;
  conversation_id: string | null;
  status: MemoryCandidateStatus;
  conflict_with: string[];
  review_note: string | null;
  created_at: string;
  updated_at: string;
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

export interface VisionAvailability {
  available: boolean;
  provider: string;
  reason: string | null;
}

// Provider status labels — see backend/app/routers/features.py's
// _provider_status_label(). "available"/"available_local" are the only two
// go-ahead states; every other string is some flavor of "not right now."
export type ProviderStatusLabel =
  | "available"
  | "available_local"
  | "not_configured"
  | "unavailable"
  | "rate_limited"
  | "quota_exceeded"
  | "credit_exhausted"
  | "billing_required"
  | "cooldown_active"
  | "daily_limit_reached";

export interface ImageGenerationAvailability {
  available: boolean;
  active_provider: string | null;
  reason: string | null;
  providers: Record<string, string>;
}

export interface FeatureAvailability {
  chat: boolean;
  voice_input: boolean;
  file_upload: boolean;
  image_generation: boolean;
  vision: VisionAvailability;
  image_generation_detail: ImageGenerationAvailability;
  providers: Record<string, ProviderStatusLabel>;
}

export const getFeatureAvailability = () => request<FeatureAvailability>("/api/features");

export interface ConversationSearchResult {
  conversation_id: string;
  title: string;
  snippet: string;
  matched_role: "user" | "echo" | "title";
  updated_at: string;
}

export interface ProviderUsageOut {
  requests_today: number;
  last_429_at: string | null;
}

export type UsageSummary = Record<string, ProviderUsageOut>;

// ---- Chat ----
export const sendChatMessage = (message: string, provider: string, conversationId?: string) =>
  request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, provider, conversation_id: conversationId ?? null }),
  });

export interface StreamDoneEvent {
  conversation_id: string;
  message_id: string;
  content: string;
  reasoning: string | null;
  provider_used: string;
  atlas_citations: AtlasCitation[];
  memory_update: MemoryUpdate | null;
  fallback_note: string | null;
  independence_nudge_reason: string | null;
  conversation_snippets: ConversationSnippetOut[];
  envelope_status: EnvelopeStatus;
  envelope_degradation_reason: string | null;
}

export interface StreamCallbacks {
  onToken?: (text: string) => void;
  onDone?: (data: StreamDoneEvent) => void;
  onError?: (detail: string) => void;
}

// Manual SSE parsing (not the native EventSource API) because this needs a POST
// body — EventSource only supports GET. Falls silently through on AbortError:
// that's the expected shape of a deliberate user cancellation, not a failure to
// surface via onError.
export async function streamChatMessage(
  message: string,
  provider: string,
  conversationId: string | null | undefined,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const url = `${BASE_URL}/api/chat/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, provider, conversation_id: conversationId ?? null }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    callbacks.onError?.(err instanceof Error ? err.message : String(err));
    return;
  }

  if (!res.ok || !res.body) {
    callbacks.onError?.(`Stream request failed (${res.status} ${res.statusText})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex: number;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const lines = block.split("\n");
        const eventLine = lines.find((l) => l.startsWith("event: "));
        const dataLine = lines.find((l) => l.startsWith("data: "));
        if (!eventLine || !dataLine) continue;
        const event = eventLine.slice("event: ".length);
        const data = JSON.parse(dataLine.slice("data: ".length));
        if (event === "token") callbacks.onToken?.(data.text);
        else if (event === "done") callbacks.onDone?.(data as StreamDoneEvent);
        else if (event === "error") callbacks.onError?.(data.detail);
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    callbacks.onError?.(err instanceof Error ? err.message : String(err));
  }
}

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

// Plain substring search over past conversations — distinct from Atlas's semantic
// memory search below (searchAtlas).
export const searchConversations = (q: string) =>
  request<ConversationSearchResult[]>(`/api/chat/search?q=${encodeURIComponent(q)}`);

// Calls a PAID model server-side — only ever invoke from an explicit, deliberate
// user action, never automatically.
export const generateImage = (prompt: string, conversationId?: string) => {
  const form = new FormData();
  form.append("prompt", prompt);
  if (conversationId) form.append("conversation_id", conversationId);
  return requestMultipart<SendWithFilesResponse>("/api/chat/generate-image", form);
};

export const getUsage = () => request<UsageSummary>("/api/usage");

export const listSelfImprovementRequests = () =>
  request<SelfImprovementRequestOut[]>('/api/self-improvement');

export const createSelfImprovementRequest = (payload: { title: string; description: string; proposed_by?: string }) =>
  request<SelfImprovementRequestOut>('/api/self-improvement', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const approveSelfImprovementRequest = (id: string, approved: boolean, note?: string) =>
  request<SelfImprovementRequestOut>(`/api/self-improvement/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved, note }),
  });

export const verifySelfImprovementRequest = (id: string) =>
  request<SelfImprovementRequestOut>(`/api/self-improvement/${id}/verify`, { method: 'POST' });

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

export const getAtlasConflicts = () => request<Record<string, string[]>>("/api/atlas/conflicts");

export const mergeAtlasEntries = (keepId: string, removeId: string, mergedContent?: string) =>
  request<AtlasEntryOut>("/api/atlas/merge", {
    method: "POST",
    body: JSON.stringify({ keep_id: keepId, remove_id: removeId, merged_content: mergedContent }),
  });

export const listMemoryDiagnostics = (limit = 50) =>
  request<MemoryExtractionLogOut[]>(`/api/atlas/diagnostics?limit=${limit}`);

// ---- Memory candidates ----
export const listMemoryCandidates = (status: MemoryCandidateStatus | "" = "pending") =>
  request<MemoryCandidateOut[]>(`/api/memory-candidates${status ? `?status=${status}` : ""}`);

export const editMemoryCandidate = (id: string, payload: Partial<MemoryCandidateOut>) =>
  request<MemoryCandidateOut>(`/api/memory-candidates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const acceptMemoryCandidate = (id: string, note?: string) =>
  request<AtlasEntryOut>(`/api/memory-candidates/${id}/accept`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });

export const rejectMemoryCandidate = (id: string, note?: string) =>
  request<MemoryCandidateOut>(`/api/memory-candidates/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });

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

// ---- Library ----
export interface LibraryItemOut {
  id: string;
  title: string;
  file_path: string;
  file_type: string;
  source: string;
  conversation_id: string | null;
  message_id: string | null;
  tags: string[];
  description: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const listLibraryItems = (q = "", fileType?: string) => {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (fileType) params.set("file_type", fileType);
  const qs = params.toString();
  return request<LibraryItemOut[]>(`/api/library${qs ? `?${qs}` : ""}`);
};

export const deleteLibraryItem = (id: string) =>
  request<{ deleted: boolean }>(`/api/library/${id}`, { method: "DELETE" });

export const getLibraryItemDownloadUrl = (id: string) => `${BASE_URL}/api/library/${id}/download`;

// ---- Schedule ----
export type ScheduleItemStatus = "pending" | "completed" | "cancelled";

export interface ScheduleItemOut {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  recurrence_rule: string | null;
  status: ScheduleItemStatus;
  source_conversation_id: string | null;
  reminder_type: string;
  created_at: string;
  updated_at: string;
}

export const createScheduleItem = (payload: {
  title: string;
  description?: string;
  due_at?: string;
  recurrence_rule?: string;
}) =>
  request<ScheduleItemOut>("/api/schedule", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listScheduleItems = (status?: ScheduleItemStatus) =>
  request<ScheduleItemOut[]>(`/api/schedule${status ? `?status=${status}` : ""}`);

export const updateScheduleItem = (
  id: string,
  payload: Partial<{ title: string; description: string; due_at: string; recurrence_rule: string }>
) =>
  request<ScheduleItemOut>(`/api/schedule/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const completeScheduleItem = (id: string) =>
  request<ScheduleItemOut>(`/api/schedule/${id}/complete`, { method: "POST" });

export const cancelScheduleItem = (id: string) =>
  request<ScheduleItemOut>(`/api/schedule/${id}/cancel`, { method: "POST" });

export const deleteScheduleItem = (id: string) =>
  request<{ deleted: boolean }>(`/api/schedule/${id}`, { method: "DELETE" });
