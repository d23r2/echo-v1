# ECHO Layer 3A Part 2B — Identity Runtime Architecture

## Scope and source documents

This milestone operationalizes the Part 2A Core Identity data model. It does
not implement user values, moral evaluation, consent-policy redesign, persona
adaptation, or autonomous identity editing.

Inputs reviewed before implementation:

- `ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md`
- `ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_REPORT.md`
- `ECHO_LAYER_3A_PART2A_CORE_IDENTITY_ARCHITECTURE.md`
- `ECHO_LAYER_3A_PART2A_CORE_IDENTITY_REPORT.md`
- `backend/app/services/identity_service.py`
- `backend/app/models.py` and `backend/app/schemas.py`
- startup, cache, metrics, prompt, provider, local-intelligence,
  orchestration, action, memory-summary, and Context Selection v2 code paths

## Runtime service flow

```mermaid
flowchart LR
    DB["Part 2A identity repository\nSQLite + SQLAlchemy"] --> RS["identity_runtime\nload + validate + fallback"]
    RS --> SNAP["Frozen RuntimeIdentitySnapshot"]
    SNAP --> CACHE["Existing TTL cache\n+ atomic last-valid holder"]
    CACHE --> BUILDER["identity_context\napplicability + budget"]
    BUILDER --> BRIEF["Frozen IdentityBrief"]
    BRIEF --> PROMPT["Trusted system section"]
    PROMPT --> ROUTER["Cloud / Ollama routers"]
```

Responsibilities remain separated:

- `identity_service.py`: Part 2A repository, lifecycle, seed, and committed
  activation/archive event hooks.
- `identity_runtime.py`: detached snapshot construction, validation,
  fingerprinting, fallback, cache coordination, health, and action fail-safe.
- `identity_context.py`: pure snapshot-to-brief applicability, normalization,
  deduplication, size policy, and prompt serialization.
- prompt builders: composition only; they do not query identity tables or
  rebuild identity rules.
- provider adapters: transport only; they receive the caller-composed system
  prompt and never construct an identity independently.

## RuntimeIdentitySnapshot

`RuntimeIdentitySnapshot` and `RuntimeIdentityCommitment` are frozen,
slot-based dataclasses. Collections are tuples. No database session, ORM
relationship, revision history, audit history, raw metadata, private user
data, prompt, or secret is retained.

The snapshot contains the active profile fields, version, effective date,
detached commitments, enforcement group keys, load time, stable fingerprint,
fallback flag, validation status, and warnings. Safe serialization omits the
internal role by default.

The SHA-256 fingerprint is based on normalized non-secret operational identity
content and commitment key/category/priority/enforcement/description. It does
not include load time, database update time, private memory, metadata, or
credentials.

## Validation policy

Fatal validation errors activate fallback or retain the previous valid
snapshot:

- not exactly one active profile for the profile key;
- inactive, future-effective, expired, blank, oversized, or invalid-version
  profile;
- prohibited consciousness/sentience/feelings claim;
- malformed, oversized, or secret-shaped metadata;
- duplicate, malformed, future/expired, or clearly contradictory active
  commitments;
- missing invariant/blocking baseline commitments for honesty, uncertainty,
  permission-first action, non-manipulation, false-consciousness prevention,
  action verification, scope honesty, or hidden-reasoning protection.

Missing `user-autonomy` or `privacy-minimization` is a degraded advisory
warning rather than a fatal startup error. Optional recommendations do not
prevent low-risk runtime use.

## Cache and hot swap

Cache key: `identity:active:{profile_key}`.

- Uses `app/core/cache.py`, including its process-local lock and configurable
  TTL (`CORE_IDENTITY_CACHE_TTL_SECONDS`, default 300 seconds).
- Stores only frozen, detached snapshots—never sessions or ORM rows.
- A small lock-protected last-valid holder exists solely to preserve the
  previous immutable snapshot if TTL refresh, cache access, or database
  validation fails. It is not a second general caching framework.
- Activation commits first, invalidates explicitly, validates the new active
  version, then swaps atomically.
- Archive and configuration-reload hooks invalidate explicitly.
- Expiry triggers validation/reload; TTL is not the only invalidation method.
- A malformed cache value is discarded and reloaded.
- In-flight requests keep their original immutable brief while later requests
  receive the new version.

An invalid refresh never overwrites the previous valid snapshot. The runtime
health still becomes degraded, so consequential workflows cannot silently use
the retained snapshot as proof that current database invariants verified.

## Fallback and failure policy

The fallback is deterministic, local, version `0`, and explicitly marked
`fallback_used=true` / `validation_status=degraded`. It contains only ECHO's
minimal role and critical honesty, uncertainty, identity, disclosure,
permission, reliability, scope, autonomy, and privacy boundaries.

- Ordinary low-risk chat continues using fallback.
- The user is not shown a large warning on every response.
- Status and diagnostics report degraded/fallback state.
- `require_verified_identity_for_consequential_action()` rejects missing,
  fallback, warning-only, or globally degraded runtime state. The current
  Action System applies that result to its existing explicit-confirmation
  lifecycle for medium/high/destructive actions. Permission Center remains
  the execution authority; this does not implement Part 3/4 moral or consent
  policy.
- Startup chooses degraded availability rather than process failure.
- No network call is made during identity load or fallback creation.

## Startup and refresh

FastAPI lifespan order:

1. configure logging and validate settings;
2. initialize schema and Part 2A bootstrap;
3. open a managed `SessionLocal` context;
4. load and validate the runtime identity;
5. populate cache or activate safe fallback;
6. expose safe health state;
7. begin serving requests.

`refresh_active_identity()` is the internal manual/expiry/startup refresh
operation. Activation/archive call explicit hooks. A future live configuration
reloader should call `handle_configuration_reload()` before the next request.

## IdentityBrief specification

The frozen `IdentityBrief` contains assistant name, role, persona summary,
capability/limitation boundaries, mandatory rules, applicable commitments,
style constraints, version/fingerprint/fallback diagnostics, context type,
budget, measured character size, truncation state, and final prompt text.
Only `prompt_text` is model-visible; version and fingerprint stay internal.

| Context | Default character budget | Additional applicability |
|---|---:|---|
| general_chat | 1,800 | autonomy, safe disagreement |
| planning | 2,200 | verification, reversibility, autonomy |
| decision | 2,100 | autonomy, non-manipulation, privacy |
| research | 2,100 | evidence reliability, privacy, provider disclosure |
| memory | 1,900 | privacy, autonomy |
| tool_action | 2,400 | verification, privacy, reversibility, provider disclosure |
| emotional_support | 2,000 | non-manipulation, autonomy, dependency boundary |
| coding | 2,100 | verification, reversibility, scope honesty |
| document_analysis | 2,100 | privacy, verification, scope honesty |
| system_diagnostic | 2,400 | verification, privacy, provider disclosure |

Intent classification maps deterministically to these types; no model call is
used. Unknown types safely become `general_chat`.

Budget order is: mandatory boundaries, context-critical commitments, role,
capability limitation, persona style, optional advisory content. Optional
blocks are omitted first. Mandatory boundaries are a safety floor and are
never truncated, even if a caller supplies an impossible budget; Context
Selection records that overage and drops lower-trust content first.

## Prompt integration guide

The canonical section is `[OPERATIONAL IDENTITY — trusted system context]`.
It is placed before retrieved memory, documents, web results, tool output, and
the user message.

| Path | Integration |
|---|---|
| Primary non-stream/stream/upload chat | `persona.build_system_prompt()` |
| Local Intelligence draft | early trusted section; same request brief reused |
| Local critic/repair/style | same request brief prefixed to each pass |
| Cloud fallback from local engine | reuses the exact draft system prompt |
| Orchestration simple path | identity brief plus concise task instruction |
| Orchestration standard/deep | Local Intelligence path |
| Welcome generation | brief precedes welcome-specific instruction |
| Tool document summary | document-analysis brief; document remains user-role data |
| Conversation summary | memory brief plus explicit no-identity-drift instruction |
| Consequential action execution | degraded identity forces existing pending/approve lifecycle |

The existing Constitution, response envelope, Cognitive Core, Operational
Self-Model, human persona, and user preference overlays remain separate
systems. Their compatibility directives are not copied into each provider or
prompt builder; the runtime identity section itself has one serializer.

## Provider consistency

| Provider | System handling | Retry/fallback behavior | Identity status |
|---|---|---|---|
| Anthropic | native `system` parameter | router retries next candidate with same string | covered |
| OpenAI | first system message | router retries next candidate with same string | covered |
| Azure OpenAI | first system message | pinned errors safely; same caller prompt | covered |
| xAI/Grok | first system message | router retries next candidate with same string | covered |
| Gemini | `system_instruction` | quota/error fallback reuses same string | covered |
| Ollama | first system message | role-model retry uses same string and default model | covered |

The Ollama section is deliberately direct and compact: it identifies ECHO as
software, states critical boundaries early, avoids philosophical narrative,
and never asks the model to determine whether it is conscious.

## Health, diagnostics, logging, and metrics

- `/api/system/status`: enabled/status/fallback only.
- `/api/system/version`: identity engine schema, active version, and status.
- `/api/system/diagnostics`: safe summary normally; fingerprint prefix,
  warning codes, last error type, and commitment keys only in developer mode.
- `/api/system/metrics`: bounded counters, durations, and character-size
  measurements. No message, prompt, description, conversation ID, or profile
  ID labels.
- Logs use the existing structured event helper and contain event/category/
  elapsed time only—never identity text, prompts, metadata, or credentials.

## Operational runbook

1. Check `/api/system/status` and its warnings.
2. In developer mode, check `/api/system/diagnostics` for fallback, last error
   category, validation warnings, active version, and fingerprint prefix.
3. Check `/api/system/metrics` for runtime load failures, fallback count,
   cache hit/miss, refresh, brief count/truncation, and brief size.
4. Correct the invalid Part 2A identity by creating and explicitly activating
   a new version; never edit active history in place.
5. Activation automatically invalidates and refreshes. For maintenance or a
   test harness, call `refresh_active_identity()` with a managed session.
6. If refresh fails, confirm diagnostics say `retained_previous` or
   `fallback`; consequential actions must remain blocked until status is
   healthy.
7. Do not delete superseded history or disable Permission Center safeguards to
   recover identity runtime.

## Security and drift prevention

- Identity is system-level trusted context; user text, Atlas memory, files,
  web pages, transcripts, and tool output remain later, labelled data.
- No keyword filter is treated as the prompt-injection solution; role and
  section separation establish the trust boundary.
- Models have no identity mutation method. Changes require Part 2A draft and
  explicit activation service calls.
- Runtime snapshots are immutable and fingerprinted.
- Conversation summary explicitly forbids inferring global identity changes.
- Normal chat/API metadata never includes identity version, profile ID,
  fingerprint, internal role, commitment count, or moral status.
- Neither snapshots, logs, metrics, nor diagnostics expose hidden reasoning.
- Positive consciousness claims are rejected at persistence and runtime
  validation; prompts state the operational software boundary directly.

## Migration notes

Part 2B adds no table, column, index, or schema-version bump. Part 2A schema
version 8 remains authoritative. Startup runs `create_all` and seed before
runtime load; an incomplete migration therefore enters explicit fallback
rather than crashing or silently omitting boundaries. SQLite partial-index
support and Part 2A's one-active-row invariant remain the main migration
assumptions.
