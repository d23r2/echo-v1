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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse failure, fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Types ----
export type EpistemicStatus = "Verified" | "Inferred" | "Hypothesis" | "Narrative";
export type Role = "founder" | "guardian_a" | "guardian_b" | "guardian_c" | "verifier";

export interface AtlasCitation {
  id: string;
  content: string;
  epistemic_status: EpistemicStatus;
  confidence: number;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  reasoning: string | null;
  provider_used: string;
  atlas_citations: AtlasCitation[];
}

export interface MessageOut {
  id: string;
  role: string;
  content: string;
  reasoning: string | null;
  provider: string | null;
  atlas_citations: AtlasCitation[];
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

export interface AtlasEntryOut {
  id: string;
  content: string;
  epistemic_status: EpistemicStatus;
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

export const listConversations = () => request<ConversationOut[]>("/api/conversations");

export const getConversation = (id: string) =>
  request<ConversationDetailOut>(`/api/conversations/${id}`);

// ---- Atlas ----
export const listAtlasEntries = () => request<AtlasEntryOut[]>("/api/atlas");

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
