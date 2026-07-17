import { getCurrentTesterId } from "../state/testerContext";

// Nullish (not ||) coalescing: an explicitly empty string means "same origin"
// (used in the production Docker build, proxied by nginx), vs. unset falling
// back to the local dev API port.
//
// A configured value that still points at localhost is only correct when the
// page itself was also loaded from localhost. vite.config.ts sets `host: true`
// specifically so the dev server can be reached from a phone/other device over
// LAN/Tailscale (e.g. http://100.x.x.x:5174) — in that case "localhost:8000"
// resolves to the *phone*, not the dev machine, and every API call silently
// fails, which is what makes the whole app look like it's not loading. Match
// the page's own hostname instead whenever that's the situation.
function resolveBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (typeof window !== "undefined") {
    const pageHost = window.location.hostname;
    const isLoopback = pageHost === "localhost" || pageHost === "127.0.0.1";
    const configuredIsLoopback = configured === undefined || /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(configured);
    if (!isLoopback && configuredIsLoopback) {
      return `http://${pageHost}:8000`;
    }
  }
  return configured ?? "http://localhost:8000";
}

export const BASE_URL = resolveBaseUrl();

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
        // Lightweight tester identity (Human Persona Layer) — attached to every
        // request so relationship/persona/mood/thread data stays scoped to
        // whichever tester this browser is currently acting as. Defaults to
        // "default" (the primary user) when nothing's been chosen yet.
        "X-Tester-Id": getCurrentTesterId(),
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
    res = await fetch(url, {
      method: "POST",
      body: formData,
      headers: { "X-Tester-Id": getCurrentTesterId() },
    });
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
  sources_used: SourceUsed[];
  current_info_intent: string | null;
  search_failure_reason: string | null;
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

// A single retrieved-and-used source (web search, wiki, RSS, direct page
// fetch, Atlas memory, previous conversation, Library file) — see
// backend/app/web_search.py's SourceResult. Only source_type/provider are
// guaranteed; the rest depend on which provider produced it.
export type SourceType =
  | "web_search"
  | "wiki"
  | "rss"
  | "direct_page"
  | "official_source"
  | "previous_conversation"
  | "atlas_memory"
  | "library_file"
  | "unavailable";

export interface SourceUsed {
  source_type: SourceType;
  provider: string;
  title?: string | null;
  url?: string | null;
  domain?: string | null;
  feed_title?: string | null;
  snippet?: string | null;
  retrieved_at?: string | null;
  published_at?: string | null;
  reliability_note?: string | null;
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
  sources_used: SourceUsed[];
  current_info_intent: string | null;
  search_failure_reason: string | null;
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

// ECHO Layer 1: Memory Foundation v1 taxonomy — see backend/app/schemas.py.
export type MemoryCategory =
  | "profile"
  | "preference"
  | "project"
  | "task"
  | "episodic"
  | "semantic"
  | "skill"
  | "relationship"
  | "environment"
  | "temporary";
export const MEMORY_CATEGORIES: MemoryCategory[] = [
  "profile", "preference", "project", "task", "episodic", "semantic", "skill", "relationship", "environment", "temporary",
];
export type VerificationStatus = "verified" | "partially_verified" | "unverified" | "disputed" | "outdated" | "not_applicable";
export type MemoryLifecycleStatus = "active" | "pending_review" | "archived" | "superseded" | "rejected" | "deleted";
export type MemoryImportance = "critical" | "high" | "medium" | "low";

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
  // ECHO Layer 1
  category: MemoryCategory;
  verification_status: VerificationStatus;
  importance: MemoryImportance;
  status: MemoryLifecycleStatus;
  review_state: "none" | "pending_review" | "reviewed";
  capture_method: string;
  project_id: string | null;
  task_id: string | null;
  source_type: string | null;
  source_reference: string | null;
  last_verified_at: string | null;
  last_accessed_at: string | null;
  access_count: number;
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
  // ECHO Layer 1
  category: MemoryCategory | null;
  sensitivity_level: "public" | "ordinary_personal" | "private" | "highly_sensitive" | "secret";
  recommendation: string | null;
  capture_reason: string | null;
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
  // Config-level flags (is a source configured at all), not live reachability —
  // a per-turn search failure still surfaces via that message's own
  // search_failure_reason, same as before this was added.
  web_search_enabled: boolean;
  wiki_enabled: boolean;
  rss_enabled: boolean;
  library: boolean;
  schedule: boolean;
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
  sources_used: SourceUsed[];
  current_info_intent: string | null;
  search_failure_reason: string | null;
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

// ---- ECHO Layer 1: Memory Foundation — /api/memory/* (additive to /api/atlas
// and /api/memory-candidates above, not a replacement for either) ----
export interface MemorySearchResultOut {
  memory_id: string;
  content: string;
  category: MemoryCategory;
  relevance_score: number;
  confidence: number;
  verification_status: VerificationStatus;
  provenance_summary: string;
  freshness_status: string;
  conflict_warning: string | null;
  retrieval_reason: string;
  epistemic_status: EpistemicStatus;
  tags: string[];
}

export interface MemoryConflictOut {
  id: string;
  memory_ids_json: string[];
  conflict_type: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "auto_resolved" | "user_review_required" | "resolved" | "ignored";
  recommended_resolution: string | null;
  resolution: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface MemoryStatsOut {
  total_active: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  pending_candidates: number;
  accepted_candidates: number;
  rejected_candidates: number;
  open_conflicts: number;
  resolved_conflicts: number;
  consolidation_events: number;
}

export interface MemoryMetricsOut {
  retrieval_counters: Record<string, number>;
  provenance_coverage_pct: number;
  verification_coverage_pct: number;
  stale_memory_pct: number;
  unresolved_conflict_pct: number;
  duplicate_consolidation_events: number;
  total_active: number;
}

export interface MemoryIndexStatusOut {
  backend: string;
  collection: string;
  embedding_model: string;
  persist_dir: string;
  healthy: boolean;
  error: string | null;
  sql_row_count: number;
  indexed_count: number;
  in_sync: boolean;
}

export interface MemoryMaintenanceResultOut {
  checked: number;
  expired: number;
  needs_review: number;
  run_at: string;
}

export interface MemoryListFilters {
  category?: MemoryCategory;
  status?: MemoryLifecycleStatus;
  project_id?: string;
  needs_review?: boolean;
}

function _qs(params: object): string {
  const parts = Object.entries(params as Record<string, unknown>)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const listMemories = (filters: MemoryListFilters = {}) =>
  request<AtlasEntryOut[]>(`/api/memory${_qs(filters)}`);

export const getMemory = (id: string) => request<AtlasEntryOut>(`/api/memory/${id}`);

export const updateMemory = (id: string, payload: Partial<AtlasEntryOut>) =>
  request<AtlasEntryOut>(`/api/memory/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

export const deleteMemory = (id: string) => request<void>(`/api/memory/${id}`, { method: "DELETE" });

export const archiveMemory = (id: string) => request<AtlasEntryOut>(`/api/memory/${id}/archive`, { method: "POST" });

export const restoreMemory = (id: string) => request<AtlasEntryOut>(`/api/memory/${id}/restore`, { method: "POST" });

export const confirmMemory = (id: string) => request<AtlasEntryOut>(`/api/memory/${id}/confirm`, { method: "POST" });

export const markMemoryOutdated = (id: string) =>
  request<AtlasEntryOut>(`/api/memory/${id}/mark-outdated`, { method: "POST" });

export interface MemorySearchRequest {
  query: string;
  project_id?: string;
  max_results?: number;
  include_archived?: boolean;
  minimum_confidence?: number;
  purpose?: string;
}

export const searchMemories = (payload: MemorySearchRequest) =>
  request<MemorySearchResultOut[]>("/api/memory/search", { method: "POST", body: JSON.stringify(payload) });

export const previewMemoryContext = (query: string) =>
  request<{ brief_text: string; results: MemorySearchResultOut[] }>("/api/memory/context-preview", {
    method: "POST",
    body: JSON.stringify({ query }),
  });

export const listMemoryConflicts = (status?: string) =>
  request<MemoryConflictOut[]>(`/api/memory/conflicts${_qs({ status })}`);

export const resolveMemoryConflict = (id: string, resolution: string) =>
  request<MemoryConflictOut>(`/api/memory/conflicts/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution }),
  });

export const runMemoryMaintenance = () =>
  request<MemoryMaintenanceResultOut>("/api/memory/maintenance/run", { method: "POST" });

export const getMemoryIndexStatus = () => request<MemoryIndexStatusOut>("/api/memory/index/status");

export const rebuildMemoryIndex = () => request<{ rebuilt: number; failed: number }>("/api/memory/index/rebuild", { method: "POST" });

export const repairMemoryIndex = () => request<{ repaired: number; removed: number }>("/api/memory/index/repair", { method: "POST" });

export const getMemoryStats = () => request<MemoryStatsOut>("/api/memory/stats");

export const getMemoryMetrics = () => request<MemoryMetricsOut>("/api/memory/metrics");

export const submitMemoryFeedback = (id: string, feedbackType: string, reason?: string) =>
  request<unknown>(`/api/memory/${id}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback_type: feedbackType, reason }),
  });

export const exportMemories = (includeArchived = false) =>
  request<{ schema_version: number; memory_count: number; memories: unknown[] }>(
    `/api/memory/export${_qs({ include_archived: includeArchived })}`
  );

export const previewMemoryImport = (payload: { schema_version: number; memories: unknown[] }) =>
  request<{ valid: boolean; error: string | null; total: number; new: number; duplicates: string[]; secrets_rejected: number }>(
    "/api/memory/import/preview",
    { method: "POST", body: JSON.stringify(payload) }
  );

export const commitMemoryImport = (payload: { schema_version: number; memories: unknown[] }) =>
  request<{ valid: boolean; staged: number; skipped_duplicates: number; skipped_secrets: number }>(
    "/api/memory/import/commit",
    { method: "POST", body: JSON.stringify(payload) }
  );

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
// No file_path — that's a server-absolute filesystem path with no meaning
// here; download/open goes through getLibraryItemDownloadUrl(id) below.
export interface LibraryItemOut {
  id: string;
  title: string;
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

// ---- Projects (ECHO Personal OS v1) ----
export type ProjectStatus = "active" | "paused" | "completed" | "archived";
export type TaskPriority = "low" | "medium" | "high";

export interface ProjectOut {
  id: string;
  title: string;
  description: string | null;
  status: ProjectStatus;
  priority: TaskPriority;
  category: string | null;
  tags: string[];
  last_touched_at: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface ProjectDetailOut extends ProjectOut {
  tasks: TaskOut[];
}

export const createProject = (payload: {
  title: string;
  description?: string;
  priority?: TaskPriority;
  category?: string;
  tags?: string[];
}) => request<ProjectOut>("/api/projects", { method: "POST", body: JSON.stringify(payload) });

export const listProjects = (status?: ProjectStatus) =>
  request<ProjectOut[]>(`/api/projects${status ? `?status=${status}` : ""}`);

export const getProject = (id: string) => request<ProjectDetailOut>(`/api/projects/${id}`);

export const updateProject = (
  id: string,
  payload: Partial<{
    title: string;
    description: string;
    status: ProjectStatus;
    priority: TaskPriority;
    category: string;
    tags: string[];
  }>
) => request<ProjectOut>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

// Soft-archive, not a hard delete — matches deleteScheduleItem's naming but
// the backend response is the archived ProjectOut, not a { deleted } flag.
export const archiveProject = (id: string) => request<ProjectOut>(`/api/projects/${id}`, { method: "DELETE" });

export const listProjectTasks = (id: string) => request<TaskOut[]>(`/api/projects/${id}/tasks`);

// ---- Tasks (ECHO Personal OS v1) ----
export type TaskStatus = "todo" | "in_progress" | "blocked" | "done" | "cancelled";

export interface TaskOut {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  project_id: string | null;
  project_title: string | null;
  due_at: string | null;
  scheduled_item_id: string | null;
  source_type: string | null;
  source_id: string | null;
  tags: string[];
  sort_order: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export const createTask = (payload: {
  title: string;
  description?: string;
  priority?: TaskPriority;
  project_id?: string;
  due_at?: string;
  tags?: string[];
}) => request<TaskOut>("/api/tasks", { method: "POST", body: JSON.stringify(payload) });

export const listTasks = (filters?: {
  status?: TaskStatus;
  project_id?: string;
  due_before?: string;
  due_after?: string;
}) => {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.project_id) params.set("project_id", filters.project_id);
  if (filters?.due_before) params.set("due_before", filters.due_before);
  if (filters?.due_after) params.set("due_after", filters.due_after);
  const qs = params.toString();
  return request<TaskOut[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
};

export const updateTask = (
  id: string,
  payload: Partial<{
    title: string;
    description: string;
    status: TaskStatus;
    priority: TaskPriority;
    project_id: string;
    due_at: string;
    tags: string[];
    sort_order: number;
  }>
) => request<TaskOut>(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

export const completeTask = (id: string) => request<TaskOut>(`/api/tasks/${id}/complete`, { method: "POST" });

// Soft-cancel, not a hard delete — same posture as archiveProject.
export const cancelTask = (id: string) => request<TaskOut>(`/api/tasks/${id}`, { method: "DELETE" });

// ---- Mission Control (ECHO Personal OS v1) ----
export interface ContinueSuggestion {
  id: string;
  title: string;
  reason: string;
  source_type: string;
  source_id: string | null;
  action_label: string;
  created_at: string;
}

export interface SystemStatusOut {
  ollama: boolean;
  wiki: boolean;
  rss: boolean;
  searxng: boolean;
  image_generation: boolean;
  library: boolean;
  schedule: boolean;
}

export interface MissionControlOut {
  today_tasks: TaskOut[];
  overdue_tasks: TaskOut[];
  upcoming_tasks: TaskOut[];
  active_projects: ProjectOut[];
  recently_touched_projects: ProjectOut[];
  recent_conversations: ConversationOut[];
  recent_library_files: LibraryItemOut[];
  upcoming_schedule_items: ScheduleItemOut[];
  pending_memory_candidates: MemoryCandidateOut[];
  system_status: SystemStatusOut | null;
  continue_where_left_off: ContinueSuggestion[];
  warnings: string[];
}

// ---- Human Persona Layer v1 ----
export type FollowupFrequency = "low" | "medium" | "high";
export type ChallengeStyle = "gentle" | "direct" | "strict";
export type ComfortStyle = "practical" | "warm" | "minimal";
export type DetailLevel = "minimal" | "short" | "normal" | "detailed" | "exhaustive";
export type DisagreementStyle = "soft" | "direct" | "firm";
export type HumourSafetyMode = "normal" | "serious_context_low_humour";
export type OperationalMode =
  | "normal"
  | "coding_assistant"
  | "research"
  | "planning"
  | "low_energy_support"
  | "strict_coach"
  | "study_tutor"
  | "release_testing"
  | "troubleshooting"
  | "quick_answer";
export type MoodMode =
  | "neutral"
  | "focused"
  | "confused"
  | "stressed"
  | "excited"
  | "low_energy"
  | "coding_mode"
  | "planning_mode"
  | "reassurance_needed"
  | "overwhelmed"
  | "urgent";
export type MoodConfidence = "low" | "medium" | "high";
export type RitualType =
  | "morning_check_in"
  | "coding_session_start"
  | "coding_session_wrap_up"
  | "weekly_review"
  | "release_checklist"
  | "low_energy_reset"
  | "study_session_start";

export const OPERATIONAL_MODES: OperationalMode[] = [
  "normal",
  "coding_assistant",
  "research",
  "planning",
  "low_energy_support",
  "strict_coach",
  "study_tutor",
  "release_testing",
  "troubleshooting",
  "quick_answer",
];

export const RITUAL_TYPES: RitualType[] = [
  "morning_check_in",
  "coding_session_start",
  "coding_session_wrap_up",
  "weekly_review",
  "release_checklist",
  "low_energy_reset",
  "study_session_start",
];

export interface PersonaSettingsOut {
  tester_id: string;
  preferred_name: string | null;
  allowed_nicknames: string[];
  disliked_names: string[];
  formality_level: number;
  emoji_level: number;
  asks_followup_questions: FollowupFrequency;
  bullet_points_preferred: boolean;
  examples_first: boolean;
  challenge_style: ChallengeStyle;
  comfort_style: ComfortStyle;
  humour_level: number;
  sarcasm_level: number;
  dry_wit_enabled: boolean;
  humour_safety_mode: HumourSafetyMode;
  detail_level: DetailLevel;
  proactivity_level: number;
  default_operational_mode: OperationalMode;
  recommendation_strength: number;
  disagreement_style: DisagreementStyle;
  local_answer_quality_mode: AnswerQualityMode;
  voice_mode: VoiceMode;
  tts_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export type VoiceMode = "off" | "push_to_talk" | "hands_free_placeholder";

export type PersonaSettingsUpdate = Partial<{
  preferred_name: string;
  allowed_nicknames: string[];
  disliked_names: string[];
  formality_level: number;
  emoji_level: number;
  asks_followup_questions: FollowupFrequency;
  bullet_points_preferred: boolean;
  examples_first: boolean;
  challenge_style: ChallengeStyle;
  comfort_style: ComfortStyle;
  humour_level: number;
  sarcasm_level: number;
  dry_wit_enabled: boolean;
  humour_safety_mode: HumourSafetyMode;
  detail_level: DetailLevel;
  proactivity_level: number;
  default_operational_mode: OperationalMode;
  recommendation_strength: number;
  disagreement_style: DisagreementStyle;
  local_answer_quality_mode: AnswerQualityMode;
  voice_mode: VoiceMode;
  tts_enabled: boolean;
}>;

export const getPersonaSettings = () => request<PersonaSettingsOut>("/api/persona-settings");

export const updatePersonaSettings = (payload: PersonaSettingsUpdate) =>
  request<PersonaSettingsOut>("/api/persona-settings", { method: "PATCH", body: JSON.stringify(payload) });

export const resetPersonaSettings = () =>
  request<PersonaSettingsOut>("/api/persona-settings/reset", { method: "POST" });

export interface RelationshipProfileOut {
  tester_id: string;
  relationship_summary: string;
  working_style_summary: string;
  trust_notes: string | null;
  support_preferences: string | null;
  communication_preferences: string | null;
  project_preferences: string | null;
  version: number;
  created_at: string;
  last_updated_at: string;
}

export type RelationshipProfileUpdate = Partial<{
  relationship_summary: string;
  working_style_summary: string;
  trust_notes: string;
  support_preferences: string;
  communication_preferences: string;
  project_preferences: string;
}>;

export const getRelationshipProfile = () => request<RelationshipProfileOut>("/api/relationship-profile");

export const updateRelationshipProfile = (payload: RelationshipProfileUpdate) =>
  request<RelationshipProfileOut>("/api/relationship-profile", { method: "PATCH", body: JSON.stringify(payload) });

export interface PersonalRitualOut {
  id: string;
  tester_id: string;
  ritual_type: RitualType;
  enabled: boolean;
  preferred_time: string | null;
  prompt_text: string;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export const listRituals = () => request<PersonalRitualOut[]>("/api/rituals");

export const updateRitual = (
  ritualType: RitualType,
  payload: Partial<{ enabled: boolean; preferred_time: string; prompt_text: string }>
) => request<PersonalRitualOut>(`/api/rituals/${ritualType}`, { method: "PATCH", body: JSON.stringify(payload) });

export interface ConversationModeOut {
  conversation_id: string;
  active_operational_mode: OperationalMode | null;
  default_operational_mode: OperationalMode;
  session_style_override: Record<string, unknown>;
}

export const getConversationMode = (conversationId: string) =>
  request<ConversationModeOut>(`/api/conversations/${conversationId}/mode`);

export const setConversationMode = (conversationId: string, mode: OperationalMode) =>
  request<ConversationModeOut>(`/api/conversations/${conversationId}/mode`, {
    method: "PATCH",
    body: JSON.stringify({ mode }),
  });

export interface ConversationMoodStateOut {
  conversation_id: string;
  detected_mode: MoodMode;
  confidence: MoodConfidence;
  reason_summary: string | null;
  updated_at: string;
}

// 404s until the conversation has had at least one turn — caller should
// treat a thrown ApiError with status 404 as "no mood yet", not a failure.
export const getConversationMood = (conversationId: string) =>
  request<ConversationMoodStateOut>(`/api/conversations/${conversationId}/mood`);

export const getMissionControl = () => request<MissionControlOut>("/api/mission-control");

// ---- ECHO Local Intelligence Engine v1 ----
export type AnswerQualityMode = "fast" | "balanced" | "deep";

export interface LocalIntelligenceSettingsOut {
  local_intelligence_engine_enabled: boolean;
  local_model_routing_enabled: boolean;
  local_answer_quality_mode: AnswerQualityMode;
  local_critic_enabled: boolean;
  cloud_fallback_enabled: boolean;
  cloud_fallback_require_user_confirmation: boolean;
  ollama_available: boolean;
  ollama_status_reason: string | null;
  installed_models: string[];
}

export const getLocalIntelligenceSettings = () =>
  request<LocalIntelligenceSettingsOut>("/api/local-intelligence/settings");

// ============================================================================
// ECHO Action + Reliability Core v1
// ============================================================================

export type ConfidenceLevel = "high" | "medium" | "low" | "unverified";

// ---- Action System ----
export type RiskLevel = "low" | "medium" | "high" | "destructive";
export type ActionRunStatus = "pending" | "approved" | "running" | "completed" | "failed" | "cancelled";

export interface ActionDefinitionOut {
  name: string;
  description: string;
  category: string;
  risk_level: RiskLevel;
  enabled: boolean;
  requires_confirmation: boolean;
  requires_permission_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActionRunOut {
  id: string;
  action_name: string;
  status: ActionRunStatus;
  risk_level: RiskLevel;
  input_json: Record<string, unknown>;
  result_json: Record<string, unknown> | null;
  error_summary: string | null;
  user_confirmed: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export const listActions = () => request<ActionDefinitionOut[]>("/api/actions");
export const listActionRuns = () => request<ActionRunOut[]>("/api/actions/runs");
export const runAction = (action_name: string, input: Record<string, unknown> = {}, confirm = false) =>
  request<ActionRunOut>("/api/actions/run", { method: "POST", body: JSON.stringify({ action_name, input, confirm }) });
export const approveActionRun = (id: string) => request<ActionRunOut>(`/api/actions/runs/${id}/approve`, { method: "POST" });
export const cancelActionRun = (id: string) => request<ActionRunOut>(`/api/actions/runs/${id}/cancel`, { method: "POST" });

// ---- Permission Center ----
export type PermissionLevel = "allowed" | "ask_first" | "disabled";

export interface PermissionSettingOut {
  permission_key: string;
  level: PermissionLevel;
  description: string;
  risk_level: RiskLevel;
  updated_at: string;
}

export const listPermissions = () => request<PermissionSettingOut[]>("/api/permissions");
export const updatePermission = (key: string, level: PermissionLevel) =>
  request<PermissionSettingOut>(`/api/permissions/${key}`, { method: "PATCH", body: JSON.stringify({ level }) });
export const resetPermissionDefaults = () => request<PermissionSettingOut[]>("/api/permissions/reset-defaults", { method: "POST" });

// ---- Reliability / Evaluation Lab ----
export type EvalResultStatus = "pass" | "fail" | "warning";
export type EvalSummary = "green" | "yellow" | "red" | "unknown";

export interface EvaluationCaseOut {
  id: string;
  name: string;
  category: string;
  user_message: string;
  notes: string | null;
}

export interface EvaluationResultOut {
  id: string;
  case_id: string;
  status: EvalResultStatus;
  reason: string;
  observed_json: Record<string, unknown>;
  created_at: string;
}

export interface EvaluationRunOut {
  id: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  result_summary: EvalSummary;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  warnings: number;
}

export interface EvaluationRunDetailOut extends EvaluationRunOut {
  results: EvaluationResultOut[];
}

export const listEvaluationCases = () => request<EvaluationCaseOut[]>("/api/evaluations/cases");
export const runEvaluation = () => request<EvaluationRunOut>("/api/evaluations/run", { method: "POST" });
export const listEvaluationRuns = () => request<EvaluationRunOut[]>("/api/evaluations/runs");
export const getEvaluationRun = (id: string) => request<EvaluationRunDetailOut>(`/api/evaluations/runs/${id}`);

// ---- Personal Knowledge Vault ----
export type KnowledgeItemType =
  | "note" | "decision" | "source" | "summary" | "idea" | "bug" | "release_note" | "study_note" | "prompt" | "reference" | "personal_rule";

export interface KnowledgeItemOut {
  id: string;
  title: string;
  body: string;
  item_type: KnowledgeItemType;
  source_type: string | null;
  source_id: string | null;
  project_id: string | null;
  task_id: string | null;
  tags: string[];
  confidence: ConfidenceLevel;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export const listKnowledgeItems = (item_type?: KnowledgeItemType) =>
  request<KnowledgeItemOut[]>(`/api/knowledge${item_type ? `?item_type=${item_type}` : ""}`);
export const searchKnowledgeItems = (q: string) => request<KnowledgeItemOut[]>(`/api/knowledge/search?q=${encodeURIComponent(q)}`);
export const createKnowledgeItem = (payload: {
  title: string;
  body?: string;
  item_type?: KnowledgeItemType;
  tags?: string[];
  confidence?: ConfidenceLevel;
  project_id?: string;
  task_id?: string;
}) => request<KnowledgeItemOut>("/api/knowledge", { method: "POST", body: JSON.stringify(payload) });
export const updateKnowledgeItem = (id: string, payload: Partial<{ title: string; body: string; item_type: KnowledgeItemType; tags: string[]; confidence: ConfidenceLevel }>) =>
  request<KnowledgeItemOut>(`/api/knowledge/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const archiveKnowledgeItem = (id: string) => request<KnowledgeItemOut>(`/api/knowledge/${id}`, { method: "DELETE" });

// ---- Conversation Auto-Summary ----
export interface ConversationSummaryOut {
  id: string;
  conversation_id: string;
  title: string;
  summary: string;
  decisions_json: string[];
  tasks_json: string[];
  open_questions_json: string[];
  next_steps_json: string[];
  memories_to_review_json: string[];
  created_at: string;
  updated_at: string;
}

export const summarizeConversation = (conversationId: string, saveToKnowledgeVault = false) =>
  request<ConversationSummaryOut>(`/api/conversations/${conversationId}/summarize`, {
    method: "POST",
    body: JSON.stringify({ save_to_knowledge_vault: saveToKnowledgeVault }),
  });
export const getConversationSummary = (conversationId: string) => request<ConversationSummaryOut>(`/api/conversations/${conversationId}/summary`);

// ---- Release / Build Manager ----
export type ReleaseStatus = "draft" | "testing" | "green" | "yellow" | "red" | "released";
export type ReleasePlatform = "backend" | "web" | "android" | "windows" | "docs" | "manual";
export type ReleaseCheckStatus = "pass" | "fail" | "warning" | "not_run";

export interface ReleaseCheckOut {
  id: string;
  check_name: string;
  platform: ReleasePlatform;
  command: string | null;
  status: ReleaseCheckStatus;
  output_summary: string | null;
  artifact_path: string | null;
  created_at: string;
}

export interface ReleaseArtifactOut {
  id: string;
  platform: ReleasePlatform;
  artifact_type: string;
  path: string;
  created_at: string;
}

export interface ReleaseOut {
  id: string;
  version_name: string;
  status: ReleaseStatus;
  summary: string;
  git_commit: string | null;
  git_tag: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleaseDetailOut extends ReleaseOut {
  checks: ReleaseCheckOut[];
  artifacts: ReleaseArtifactOut[];
}

export const listReleases = () => request<ReleaseOut[]>("/api/releases");
export const createRelease = (payload: { version_name: string; summary?: string; git_commit?: string; git_tag?: string }) =>
  request<ReleaseOut>("/api/releases", { method: "POST", body: JSON.stringify(payload) });
export const getRelease = (id: string) => request<ReleaseDetailOut>(`/api/releases/${id}`);
export const addReleaseCheck = (
  id: string,
  payload: { check_name: string; platform: ReleasePlatform; command?: string; status?: ReleaseCheckStatus; output_summary?: string; artifact_path?: string }
) => request<ReleaseCheckOut>(`/api/releases/${id}/checks`, { method: "POST", body: JSON.stringify(payload) });
export const seedReleaseChecklist = (id: string) => request<ReleaseCheckOut[]>(`/api/releases/${id}/checklist/seed`, { method: "POST" });
export const addReleaseArtifact = (id: string, payload: { platform: ReleasePlatform; artifact_type: string; path: string }) =>
  request<ReleaseArtifactOut>(`/api/releases/${id}/artifacts`, { method: "POST", body: JSON.stringify(payload) });
export const markReleaseStatus = (id: string, status: ReleaseStatus) =>
  request<ReleaseOut>(`/api/releases/${id}/mark-status`, { method: "POST", body: JSON.stringify({ status }) });

// ---- Internal Plugin / Tool System ----
export type ToolRunStatus = "pending" | "running" | "completed" | "failed" | "blocked";

export interface ToolDefinitionOut {
  tool_name: string;
  display_name: string;
  description: string;
  category: string;
  enabled: boolean;
  risk_level: RiskLevel;
  requires_confirmation: boolean;
  permission_key: string | null;
  input_schema_json: Record<string, unknown>;
  output_schema_json: Record<string, unknown>;
}

export interface ToolRunOut {
  id: string;
  tool_name: string;
  status: ToolRunStatus;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown> | null;
  error_summary: string | null;
  created_at: string;
  completed_at: string | null;
}

export const listTools = () => request<ToolDefinitionOut[]>("/api/tools");
export const listToolRuns = () => request<ToolRunOut[]>("/api/tools/runs");
export const runTool = (toolName: string, input: Record<string, unknown> = {}, confirm = false) =>
  request<ToolRunOut>(`/api/tools/${toolName}/run`, { method: "POST", body: JSON.stringify({ input, confirm }) });

// ============================================================================
// ECHO Cognitive Core v1 — World Model + Task Understanding Engine
// ============================================================================

export type ConceptType = "project" | "system" | "tool" | "file" | "process" | "person_preference" | "domain" | "technical" | "goal" | "constraint" | "risk" | "source" | "other";
export type CognitiveConfidence = "high" | "medium" | "low" | "inferred";
export type RelationType = "uses" | "depends_on" | "causes" | "blocks" | "enables" | "part_of" | "conflicts_with" | "similar_to" | "requires" | "produces" | "verifies" | "belongs_to";
export type TaskType =
  | "ask_question" | "build_feature" | "fix_bug" | "run_test" | "plan_project" | "research_topic" | "summarize_file"
  | "make_decision" | "create_prompt" | "release_build" | "troubleshoot" | "study_learn" | "personal_support" | "other";
export type TaskConfidence = "high" | "medium" | "low" | "incomplete";
export type SkillCategory = "coding" | "release" | "research" | "study" | "planning" | "troubleshooting" | "writing" | "personal" | "system" | "other";

export interface CognitiveConceptOut {
  id: string;
  name: string;
  description: string | null;
  concept_type: ConceptType;
  confidence: CognitiveConfidence;
  source_type: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface CognitiveRelationshipOut {
  id: string;
  from_concept_id: string;
  to_concept_id: string;
  relation_type: RelationType;
  description: string | null;
  confidence: CognitiveConfidence;
  source_type: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface GraphNodeOut {
  concept: CognitiveConceptOut;
  relationships: CognitiveRelationshipOut[];
}

// ECHO Layer 2A: Cognitive Core v2 taxonomy — see backend/app/schemas.py.
export type TaskCategory =
  | "question" | "explanation" | "research" | "coding" | "debugging" | "planning" | "decision"
  | "document" | "action" | "reminder" | "learning" | "emotional_support" | "creative" | "mixed";
export type TaskUrgency = "low" | "normal" | "high" | "urgent";
export type TaskComplexity = "trivial" | "simple" | "moderate" | "complex";
export type TaskRiskLevel = "low" | "medium" | "high" | "critical";
export type TaskReversibility = "reversible" | "hard_to_reverse" | "irreversible";
export type CognitiveTaskStatus = "draft" | "analyzing" | "ready" | "needs_clarification" | "stale" | "superseded";
export type TaskScope = "current_turn" | "conversation" | "project" | "recurring_workflow" | "long_term_goal";

export interface TaskUnderstandingOut {
  id: string;
  conversation_id: string | null;
  user_message: string;
  goal_summary: string;
  domain: string;
  task_type: TaskType;
  known_facts_json: string[];
  unknowns_json: string[];
  constraints_json: string[];
  assumptions_json: string[];
  success_criteria_json: string[];
  risks_json: string[];
  relevant_concepts_json: string[];
  recommended_next_step: string | null;
  confidence: TaskConfidence;
  created_at: string;
  // ECHO Layer 2A
  project_id: string | null;
  parent_task_id: string | null;
  normalized_request: string | null;
  task_category: TaskCategory;
  urgency: TaskUrgency;
  complexity: TaskComplexity;
  primary_goal: string | null;
  secondary_goals_json: string[];
  user_intent: string | null;
  expected_output: string | null;
  inferred_constraints_json: string[];
  preferences_json: string[];
  forbidden_actions_json: string[];
  uncertainties_json: string[];
  missing_information_json: { item: string; tier: string }[];
  failure_conditions_json: string[];
  acceptance_tests_json: string[];
  required_capabilities_json: string[];
  candidate_skills_json: string[];
  candidate_tools_json: string[];
  required_sources_json: string[];
  risk_level: TaskRiskLevel;
  consequence_level: TaskRiskLevel;
  reversibility: TaskReversibility;
  confirmation_requirement: boolean;
  status: CognitiveTaskStatus;
  scope: TaskScope;
  clarification_questions_json: string[];
  updated_at: string | null;
}

export interface SkillPatternOut {
  id: string;
  name: string;
  description: string;
  category: SkillCategory;
  trigger_patterns_json: string[];
  steps_json: string[];
  required_tools_json: string[];
  success_criteria_json: string[];
  common_failures_json: string[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface SuggestPlanOut {
  skill: SkillPatternOut;
  plan_steps: string[];
}

export interface CausalNoteOut {
  id: string;
  title: string;
  cause: string;
  effect: string;
  explanation: string;
  confidence: CognitiveConfidence;
  source_type: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface CognitiveBriefOut {
  id: string;
  conversation_id: string | null;
  task_understanding_id: string | null;
  brief_text: string;
  selected_concepts_json: string[];
  selected_skills_json: string[];
  selected_context_sources_json: string[];
  created_at: string;
  // ECHO Layer 2A
  candidate_tools_json: string[];
  risk_and_confirmation_summary: string | null;
  confidence: TaskConfidence;
  next_reasoning_stage: string | null;
}

export interface ClarificationViewOut {
  needs_clarification: boolean;
  questions: string[];
  blocking_items: string[];
  safe_assumptions_made: string[];
}

export interface ContextPreviewOut {
  task_understanding: TaskUnderstandingOut | null;
  brief_text: string | null;
  clarification: ClarificationViewOut;
}

export interface TaskUnderstandingCorrection {
  primary_goal?: string;
  expected_output?: string;
  explicit_constraints?: string[];
  forbidden_actions?: string[];
  scope?: TaskScope;
}

export interface TaskTypeInfo {
  value: string;
  label: string;
  description: string;
}

export interface TaskTypesOut {
  task_types: TaskTypeInfo[];
  task_categories: TaskTypeInfo[];
}

export interface CognitiveSettingsOut {
  cognitive_core_enabled: boolean;
  cognitive_concept_extraction_enabled: boolean;
  cognitive_skill_matching_enabled: boolean;
  cognitive_show_developer_diagnostics: boolean;
}

// ---- Task understanding + briefs ----
export const understandTask = (user_message: string, conversation_id?: string) =>
  request<TaskUnderstandingOut | null>("/api/cognitive/understand", { method: "POST", body: JSON.stringify({ user_message, conversation_id }) });
export const listTaskUnderstandings = () => request<TaskUnderstandingOut[]>("/api/cognitive/task-understandings");
export const listCognitiveBriefs = () => request<CognitiveBriefOut[]>("/api/cognitive/briefs");

// ---- ECHO Layer 2A: /api/intelligence/* (additive to /api/cognitive/* above) ----
export const getTaskUnderstanding = (id: string) => request<TaskUnderstandingOut>(`/api/intelligence/tasks/${id}`);

export const correctTaskUnderstanding = (id: string, correction: TaskUnderstandingCorrection) =>
  request<TaskUnderstandingOut>(`/api/intelligence/tasks/${id}`, { method: "PATCH", body: JSON.stringify(correction) });

export const reanalyseTaskUnderstanding = (id: string) =>
  request<TaskUnderstandingOut>(`/api/intelligence/tasks/${id}/reanalyse`, { method: "POST" });

export const previewIntelligenceContext = (user_message: string, conversation_id?: string, project_id?: string) =>
  request<ContextPreviewOut>("/api/intelligence/context-preview", {
    method: "POST",
    body: JSON.stringify({ user_message, conversation_id, project_id }),
  });

export const listTaskTypes = () => request<TaskTypesOut>("/api/intelligence/task-types");

// ---- Concepts (World Model) ----
export const listConcepts = (params?: { concept_type?: string; q?: string }) => {
  const search = new URLSearchParams();
  if (params?.concept_type) search.set("concept_type", params.concept_type);
  if (params?.q) search.set("q", params.q);
  const qs = search.toString();
  return request<CognitiveConceptOut[]>(`/api/cognitive/concepts${qs ? `?${qs}` : ""}`);
};
export const createConcept = (payload: { name: string; description?: string; concept_type?: ConceptType; confidence?: CognitiveConfidence }) =>
  request<CognitiveConceptOut>("/api/cognitive/concepts", { method: "POST", body: JSON.stringify(payload) });
export const getConcept = (id: string) => request<CognitiveConceptOut>(`/api/cognitive/concepts/${id}`);
export const archiveConcept = (id: string) => request<CognitiveConceptOut>(`/api/cognitive/concepts/${id}`, { method: "DELETE" });

// ---- Relationships ----
export const listRelationships = (conceptId?: string) =>
  request<CognitiveRelationshipOut[]>(`/api/cognitive/relationships${conceptId ? `?concept_id=${conceptId}` : ""}`);
export const graphSearch = (query: string) => request<GraphNodeOut[]>(`/api/cognitive/graph?query=${encodeURIComponent(query)}`);

// ---- Skills ----
export const listSkills = (category?: string) => request<SkillPatternOut[]>(`/api/cognitive/skills${category ? `?category=${category}` : ""}`);
export const archiveSkill = (id: string) => request<SkillPatternOut>(`/api/cognitive/skills/${id}`, { method: "DELETE" });
export const suggestPlan = (skillId: string, userMessage: string) =>
  request<SuggestPlanOut>(`/api/cognitive/skills/${skillId}/suggest-plan`, { method: "POST", body: JSON.stringify({ user_message: userMessage }) });

// ---- Causal notes ----
export const listCausalNotes = () => request<CausalNoteOut[]>("/api/cognitive/causal-notes");
export const createCausalNote = (payload: { title: string; cause: string; effect: string; explanation?: string; confidence?: CognitiveConfidence }) =>
  request<CausalNoteOut>("/api/cognitive/causal-notes", { method: "POST", body: JSON.stringify(payload) });
export const archiveCausalNote = (id: string) => request<CausalNoteOut>(`/api/cognitive/causal-notes/${id}`, { method: "DELETE" });

// ---- Settings ----
export const getCognitiveSettings = () => request<CognitiveSettingsOut>("/api/cognitive/settings");
export const updateCognitiveSettings = (payload: Partial<CognitiveSettingsOut>) =>
  request<CognitiveSettingsOut>("/api/cognitive/settings", { method: "PATCH", body: JSON.stringify(payload) });

// ============================================================================
// ECHO Operational Self-Model v1 + Interface Simplification v1
// ============================================================================

export type ShowInnerState = "never" | "only_when_helpful" | "developer_mode_only";

export interface InterfaceSettingsOut {
  show_advanced_nav: boolean;
  compact_sidebar: boolean;
  show_developer_controls: boolean;
  show_usage_in_topbar: boolean;
  show_model_selector: boolean;
  poetic_language_enabled: boolean;
  operational_self_model_enabled: boolean;
  show_inner_state: ShowInnerState;
}

export interface OperationalStateSnapshotOut {
  id: string;
  conversation_id: string | null;
  current_goal: string;
  current_mode: string;
  confidence: string;
  known_limits_json: string[];
  active_risks_json: string[];
  relevant_memory_summary: string | null;
  relationship_summary: string | null;
  permissions_summary: string | null;
  next_best_action: string | null;
  should_ask_confirmation: boolean;
  should_use_tools_json: string[];
  should_not_do_json: string[];
  intensity: number;
  expires_at: string | null;
  created_at: string;
}

export const getInterfaceSettings = () => request<InterfaceSettingsOut>("/api/interface-settings");
export const updateInterfaceSettings = (payload: Partial<InterfaceSettingsOut>) =>
  request<InterfaceSettingsOut>("/api/interface-settings", { method: "PATCH", body: JSON.stringify(payload) });
export const listRecentSelfModelSnapshots = (conversationId?: string) =>
  request<OperationalStateSnapshotOut[]>(`/api/self-model/recent${conversationId ? `?conversation_id=${conversationId}` : ""}`);

// ============================================================================
// ECHO Layer 0 — Infrastructure Foundation v1
// ============================================================================

// Named InfraSystemStatusOut (not SystemStatusOut) — that name is already
// taken by Mission Control's own status type above; this is a different,
// broader shape (GET /api/system/status) from Layer 0.
export interface InfraSystemStatusOut {
  status: "green" | "yellow" | "red";
  backend: string;
  database: string;
  ollama: string;
  frontend_expected_url: string;
  backend_url: string;
  wiki: string;
  rss: string;
  searxng: string;
  atlas: string;
  cognitive_core: string;
  version: string;
  warnings: string[];
}

export interface SystemVersionOut {
  application_version: string;
  backend_version: string;
  frontend_expected_version: string;
  schema_version: number;
  api_version: string;
}

export const getInfraSystemStatus = () => request<InfraSystemStatusOut>("/api/system/status");
export const getSystemVersion = () => request<SystemVersionOut>("/api/system/version");
