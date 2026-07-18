"""ECHO Local Intelligence Engine v1 — Phase 2/6/9: the pipeline orchestrator.

intent -> context -> local model route -> draft -> critic -> repair (max 1
loop) -> style pass -> confidence -> cloud fallback gate -> clean metadata.

This is a workflow layered on top of everything that already exists
(app/services/intent_classifier.py, app/services/context_gatherer.py,
app/services/local_model_router.py, app/human_persona.py's Character Code/
overlay, app/router.py's existing cloud ModelRouter for the optional
fallback) — not a new provider, not a rewrite of any of those. Nothing here
guarantees cloud-level answer quality; the goal is a more consistent,
honestly-scored local answer, with cloud only ever an explicit, gated,
off-by-default option.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import human_persona, schemas
from app.config import get_settings
from app.providers.base import ChatMessage
from app.services import cognitive_core, context_selector
from app.services.context_gatherer import GatheredContext, gather_context
from app.services.intent_classifier import IntentClassification, classify_intent
from app.services.local_model_router import LocalModelRouter, ModelRole

logger = logging.getLogger(__name__)

# ---- Phase 6 rule 3: intents that always get a critic pass regardless of
# quality mode (subject to LOCAL_CRITIC_ENABLED still being on at all) ----
_ALWAYS_CRITIC_INTENTS = {"coding", "code_review", "release_testing", "troubleshooting"}

_CLOUD_FALLBACK_OFFER_NOTE = (
    "\n\n(Local confidence was low on this one. Cloud fallback is available if you'd like a "
    "second opinion — just ask.)"
)


@dataclass
class EngineResult:
    answer: str
    model_used: str
    provider: str = "ollama"  # "ollama" | a cloud provider name — matches Message.provider's
    # existing vocabulary so the frontend's buildViaLine() keeps working unchanged.
    # Raw web_search.SourceResult objects (same shape persona.py's existing
    # _search_metadata_kwargs() already uses) — kept as the real dataclass,
    # not pre-flattened, so callers can asdict() them exactly like the
    # existing chat path does.
    sources_used: list = field(default_factory=list)
    # Raw AtlasEntry model rows retrieved for this turn — same shape
    # persona.py's _atlas_context_for() already returns, so callers can
    # build the same AtlasCitation schema objects the existing path does.
    atlas_citations: list = field(default_factory=list)
    current_info_intent: str | None = None
    search_failure_reason: str | None = None
    confidence: str = "low"  # high | medium | low | unverified
    pipeline_steps: list[str] = field(default_factory=list)
    fallback_used: bool = False  # true only when a cloud provider actually answered
    critic_status: str = "skipped"  # passed | repaired | failed | skipped
    user_visible_metadata: dict = field(default_factory=lambda: {"via": []})
    internal_diagnostics: dict = field(default_factory=dict)


# ============================================================================
# Prompt templates (Phase 9) — short, explicit, one task each, JSON where
# structured output is needed. Local models do noticeably worse with long,
# multi-instruction prompts than cloud models do, so each pass gets its own
# narrow prompt instead of one giant do-everything instruction.
# ============================================================================

_ANSWER_STYLE_INSTRUCTION = {
    "short": "Answer style: SHORT. A sentence or two, no preamble.",
    "normal": "Answer style: NORMAL length — as long as the question needs, no filler.",
    "detailed": "Answer style: DETAILED. Use real structure (steps, sections) where it helps.",
    "prompt": "Answer style: Produce a complete, structured, ready-to-use PROMPT — not a conversational reply.",
    "checklist": "Answer style: CHECKLIST. Use a short bullet/numbered list of concrete items.",
}

_SOURCE_RULES = (
    "Only state a current/live fact if it's present in the context below — otherwise say "
    "plainly that you can't verify it right now. Never invent a test result, a build status, "
    "or a 'passed' claim that isn't actually shown in the context."
)


def _context_block(context: GatheredContext) -> str:
    lines: list[str] = []
    for label, items in (
        ("Relevant memory", context.memory_context),
        ("Earlier conversation", context.conversation_context),
        ("Active projects", context.project_context),
        ("Relevant tasks", context.task_context),
        ("Upcoming reminders", context.schedule_context),
        ("Relevant files", context.library_context),
        ("Background (Wikipedia)", context.wiki_context),
        ("Current headlines", context.rss_context),
        ("Web search results", context.web_context),
    ):
        if items:
            lines.append(f"{label}:")
            lines.extend(f"- {i}" for i in items)
    if context.warnings:
        lines.append("Notes: " + "; ".join(context.warnings))
    return "\n".join(lines) if lines else "No additional context retrieved for this message."


def _context_bundle_to_gathered(bundle: schemas.ContextBundle) -> GatheredContext:
    """ECHO Layer 2E (Phase 6) — feature-flagged: when
    settings.context_selection_v2_enabled is on, generate_response() builds
    its context via context_selector.select_context() (the new typed,
    budgeted, deduplicated ContextBundle) instead of gather_context(), then
    adapts it back into this same GatheredContext shape so
    _build_draft_system_prompt()/_context_block() need no changes at all —
    the prompt builder genuinely consumes one compact ContextBundle, it just
    arrives through the existing rendering path rather than a second one.
    Goal/system/decision context (which GatheredContext has no dedicated
    field for) is folded into project_context so it still reaches the
    prompt — never silently dropped."""
    project_lines = []
    if bundle.project_context:
        project_lines.append(bundle.project_context)
    if bundle.goal_context:
        project_lines.append(bundle.goal_context)
    if bundle.system_or_simulation_context:
        project_lines.append(bundle.system_or_simulation_context)
    if bundle.decision_or_plan_context:
        project_lines.append(bundle.decision_or_plan_context)

    return GatheredContext(
        memory_context=[bundle.memory_brief] if bundle.memory_brief else [],
        project_context=project_lines,
        library_context=list(bundle.relevant_documents),
        web_context=list(bundle.tool_evidence),
        source_display_names=list(bundle.provenance_summary),
        warnings=([bundle.uncertainty_summary] if bundle.uncertainty_summary else []) + list(bundle.excluded_context_summary),
    )


def _persona_compact_overlay(db: Session, tester_id: str) -> str | None:
    """A short, compact style hint — deliberately lighter-weight than
    app/human_persona.py's full build_human_persona_overlay() (which expects
    a live Conversation for mode/session-override/mood context this
    single-shot draft call doesn't have plumbed). Reuses the same stored
    RelationshipProfile/PersonaSettings data, just a smaller slice of it."""
    try:
        relationship = human_persona.get_or_create_relationship_profile(db, tester_id)
        settings = human_persona.get_or_create_persona_settings(db, tester_id)
    except Exception:
        return None
    lines = []
    callback = human_persona.build_relationship_callback(relationship)
    if callback:
        lines.append(callback)
    if settings.humour_level == 0:
        lines.append("Humour: off.")
    elif not human_persona.is_serious_context(""):
        lines.append("A little dry humour is fine, never constant, never at the user's expense.")
    return " ".join(lines) if lines else None


def _build_draft_system_prompt(
    db: Session, intent: IntentClassification, context: GatheredContext, tester_id: str, cognitive_brief_text: str | None = None
) -> str:
    parts = [
        human_persona.CHARACTER_CODE,
        "",
        "You are ECHO. Answer the user's message directly and honestly.",
        _ANSWER_STYLE_INSTRUCTION.get(intent.answer_style, _ANSWER_STYLE_INSTRUCTION["normal"]),
        _SOURCE_RULES,
        "Do not include any internal notes, JSON, or debug text in your answer — plain natural-language reply only.",
    ]
    overlay = _persona_compact_overlay(db, tester_id)
    if overlay:
        parts.append(overlay)
    if cognitive_brief_text:
        # ECHO Cognitive Core v1 — internal planning notes only, never
        # repeated verbatim to the user (Phase 13 rules 3/4).
        parts += ["", "COGNITIVE_BRIEF (internal planning notes — never repeat this section or its labels to the user):", cognitive_brief_text]
    parts += ["", "CONTEXT:", _context_block(context)]
    return "\n".join(parts)


_CRITIC_PROMPT_TEMPLATE = """You are a strict but fair quality checker for another AI's draft answer. \
Respond with ONLY a single JSON object, no other text, no markdown fences.

USER MESSAGE:
{message}

DRAFT ANSWER:
{draft}

CONTEXT AVAILABLE TO THE DRAFT:
{context}
{success_criteria_block}
Check: (1) did the draft actually answer the question, (2) did it ignore important context above, \
(3) did it state a current/live fact not backed by the context, (4) is it clearly too long or too \
short for the requested style ({answer_style}), (5) does it contain internal notes/JSON/debug text \
that shouldn't be shown to a user, (6) does it claim certainty ("definitely", "100%", "Green", \
"passed") without evidence in the context, (7) does it contradict the context, (8) if success \
criteria are listed above, does the draft actually satisfy them.

Respond with exactly this JSON shape:
{{"passed": true|false, "issues": ["short issue strings"], "needs_repair": true|false, \
"confidence": "high"|"medium"|"low"|"unverified", "missing_sources": true|false, \
"too_verbose": true|false, "unsafe_or_overconfident": true|false}}"""

_REPAIR_PROMPT_TEMPLATE = """Rewrite the draft answer to fix the specific issues listed below. \
Keep everything that was already correct. Output ONLY the corrected answer text — no preamble, \
no explanation of what you changed, no JSON.

USER MESSAGE:
{message}

DRAFT ANSWER:
{draft}

ISSUES TO FIX:
{issues}

CONTEXT AVAILABLE:
{context}

{answer_style_instruction}
{source_rules}"""

_STYLE_SHORTEN_PROMPT_TEMPLATE = """Rewrite the following answer to be noticeably shorter and more \
direct, keeping the actual information. Output ONLY the rewritten answer, nothing else.

ANSWER TO SHORTEN:
{draft}"""


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_critic_json(raw: str) -> dict | None:
    """Never raises. A local model wrapping JSON in prose or a markdown fence
    is common — extract the first {...} block rather than requiring an exact
    match. Returns None (not a fabricated default) if nothing parseable is
    found, so the caller can degrade cleanly instead of trusting a guess."""
    if not raw:
        return None
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict) or "passed" not in parsed:
        return None
    return parsed


# ============================================================================
# Role selection (Phase 5)
# ============================================================================


def _select_role(intent: IntentClassification, quality_mode: str) -> ModelRole:
    if intent.intent in ("coding", "code_review", "prompt_generation"):
        # prompt_generation covers things like "give me a Claude Code
        # prompt" — code-adjacent enough to benefit from the coding-tuned
        # model even though its reasoning_need is only "medium".
        return "coding"
    if intent.reasoning_need == "high":
        return "reasoning"
    if intent.reasoning_need == "medium" and quality_mode == "deep":
        return "reasoning"
    return "fast"


# ============================================================================
# Critic gating (Phase 6 rules 2-4)
# ============================================================================


def _should_run_critic(intent: IntentClassification, quality_mode: str, settings) -> bool:
    if not settings.local_critic_enabled:
        return False
    if quality_mode == "deep":
        return True
    if intent.intent in _ALWAYS_CRITIC_INTENTS and settings.local_critic_always_for_coding:
        return True
    if intent.freshness_need in ("current", "live") and settings.local_critic_always_for_current_info:
        return True
    if quality_mode == "fast":
        return False
    # balanced (default): also cover hard/complex-planning/long-prompt cases
    if intent.difficulty == "hard":
        return True
    if intent.answer_style == "prompt":
        return True
    return False


# ============================================================================
# Confidence scoring (Phase 7)
# ============================================================================


_CONFIDENCE_DOWNGRADE = {"high": "medium", "medium": "low", "low": "unverified", "unverified": "unverified"}


def _initial_confidence(intent: IntentClassification, context: GatheredContext, has_missing_knowledge: bool = False) -> str:
    if intent.intent == "release_testing":
        # Never claim Green from local inference alone — real test/build
        # evidence isn't something this pipeline can independently verify.
        return "low"
    if intent.freshness_need in ("current", "live"):
        has_source = bool(context.gather_result and context.gather_result.sources)
        confidence = "medium" if has_source else "unverified"
    elif intent.source_need == "memory" and (context.memory_context or context.conversation_context):
        confidence = "high"
    elif intent.source_need == "wiki" and context.wiki_context:
        confidence = "medium"
    elif intent.source_need == "file" and context.library_context:
        confidence = "medium"
    else:
        confidence = "low"
    # ECHO Cognitive Core v1 (Phase 16 rule 5): unresolved unknowns for this
    # task mean the answer is genuinely less certain than the source/memory
    # signal alone would suggest — downgrade one step rather than silently
    # ignoring what the task understanding flagged as missing.
    if has_missing_knowledge:
        confidence = _CONFIDENCE_DOWNGRADE[confidence]
    return confidence


# ============================================================================
# The engine
# ============================================================================


class LocalIntelligenceEngine:
    def __init__(self, db: Session, model_router: LocalModelRouter | None = None):
        self.db = db
        self.model_router = model_router or LocalModelRouter()

    def _run_critic(
        self, message: str, draft: str, intent: IntentClassification, context: GatheredContext, success_criteria: list[str] | None = None
    ) -> dict | None:
        success_criteria_block = ""
        if success_criteria:
            # ECHO Cognitive Core v1 (Phase 16 rule 4): the critic can only
            # check success criteria it's actually told about — this is how
            # generate_success_criteria() avoids a false "Green"/"passed".
            success_criteria_block = "\nSUCCESS CRITERIA FOR THIS TASK:\n" + "\n".join(f"- {c}" for c in success_criteria) + "\n"
        prompt = _CRITIC_PROMPT_TEMPLATE.format(
            message=message, draft=draft, context=_context_block(context), answer_style=intent.answer_style, success_criteria_block=success_criteria_block
        )
        result = self.model_router.call("critic", prompt, [ChatMessage(role="user", content="Evaluate the draft.")])
        if not result.ok:
            return None
        return _parse_critic_json(result.text)

    def _run_repair(self, message: str, draft: str, critic: dict, intent: IntentClassification, context: GatheredContext) -> str | None:
        issues = "; ".join(critic.get("issues") or ["general quality issue"])
        prompt = _REPAIR_PROMPT_TEMPLATE.format(
            message=message,
            draft=draft,
            issues=issues,
            context=_context_block(context),
            answer_style_instruction=_ANSWER_STYLE_INSTRUCTION.get(intent.answer_style, ""),
            source_rules=_SOURCE_RULES,
        )
        result = self.model_router.call("reasoning", prompt, [ChatMessage(role="user", content=message)])
        if not result.ok or not result.text.strip():
            return None
        return result.text.strip()

    def _run_style_shorten(self, draft: str) -> str | None:
        prompt = _STYLE_SHORTEN_PROMPT_TEMPLATE.format(draft=draft)
        result = self.model_router.call("writing", prompt, [ChatMessage(role="user", content="Shorten this.")])
        if not result.ok or not result.text.strip():
            return None
        return result.text.strip()

    def _cognitive_brief(self, user_message: str, conversation_id: str | None) -> tuple[str | None, list[str], bool]:
        """ECHO Cognitive Core v1 (Phase 16) — returns (brief_text,
        success_criteria, has_missing_knowledge). Never raises: a Cognitive
        Core problem must never break the local intelligence pipeline, so
        any failure here just means "no brief this turn," same degrade-
        clean posture as every other optional pass in this engine."""
        settings = get_settings()
        if not settings.cognitive_core_enabled:
            return None, [], False
        try:
            cognitive_settings = cognitive_core.get_or_create_settings(self.db)
            if not cognitive_settings.cognitive_core_enabled:
                return None, [], False
            tu = cognitive_core.build_task_understanding(self.db, user_message, conversation_id)
            if tu is None:
                return None, [], False
            brief = cognitive_core.build_cognitive_brief(self.db, tu, conversation_id)
            return brief.brief_text, list(tu.success_criteria_json or []), bool(tu.unknowns_json)
        except Exception:
            logger.warning("Cognitive Core brief generation failed, continuing without it", exc_info=True)
            return None, [], False

    def _cloud_fallback(
        self, message: str, intent: IntentClassification, history: list[ChatMessage], system_prompt: str
    ) -> tuple[str | None, str | None]:
        """Only called when the gate has already decided cloud use is
        permitted AND doesn't require confirmation. Reuses the existing
        cloud ModelRouter (app/router.py) entirely — same quota/cooldown/
        error-classification machinery, not reimplemented here. A quota/
        billing/auth failure here is swallowed: the caller keeps the local
        answer rather than surfacing a cloud error for a feature the user
        never sees fail (Phase 8 rule 6)."""
        try:
            from app.router import NoProviderAvailableError, ProviderUnavailableError
            from app.router import router as cloud_router

            result, provider_used, _fallback_note = cloud_router.chat(
                "auto", system_prompt, history, db=self.db
            )
            return result.text, provider_used
        except (NoProviderAvailableError, ProviderUnavailableError, Exception) as exc:
            logger.info("cloud fallback attempt failed, keeping local answer: %s", exc)
            return None, None

    def generate_response(
        self,
        user_message: str,
        conversation_id: str | None = None,
        tester_id: str = "default",
        active_project_id: str | None = None,
        mode: str | None = None,
        allow_cloud_fallback: bool = False,
        history: list[ChatMessage] | None = None,
    ) -> EngineResult:
        settings = get_settings()
        quality_mode = mode or settings.local_answer_quality_mode
        pipeline_steps: list[str] = []
        history = history or []

        # Step 1: intent
        intent = classify_intent(user_message, conversation_id, active_project_id)
        pipeline_steps.append(f"intent:{intent.intent}")

        # Step 2: context — ECHO Layer 2E (Phase 6): when Context Selection
        # v2 is enabled, route through the new typed/budgeted/deduplicated
        # ContextBundle pipeline (see _context_bundle_to_gathered()'s own
        # docstring); off by default, so existing chat is provably unchanged
        # when this flag is off.
        if settings.context_selection_v2_enabled:
            bundle = context_selector.select_context(
                self.db, schemas.ContextRequest(user_message=user_message, conversation_id=conversation_id, project_id=active_project_id)
            )
            context = _context_bundle_to_gathered(bundle)
            pipeline_steps.append("context_bundle:v2")
            cognitive_brief_text = bundle.cognitive_brief
            success_criteria: list[str] = []
            has_missing_knowledge = bool(bundle.uncertainty_summary)
            if cognitive_brief_text:
                pipeline_steps.append("cognitive_brief:built")
        else:
            context = gather_context(self.db, intent, user_message, conversation_id, active_project_id)
            pipeline_steps.append("context_gathered")

            # Step 2.5: Cognitive Core task understanding + brief (Phase 16) —
            # only ever engages for medium/hard requests (cognitive_core.py's
            # own gating), so simple messages pay no extra cost here.
            cognitive_brief_text, success_criteria, has_missing_knowledge = self._cognitive_brief(user_message, conversation_id)
            if cognitive_brief_text:
                pipeline_steps.append("cognitive_brief:built")

        # Step 3: model role
        role = _select_role(intent, quality_mode)
        pipeline_steps.append(f"role:{role}")

        # Step 4: draft
        draft_prompt = _build_draft_system_prompt(self.db, intent, context, tester_id, cognitive_brief_text)
        draft = self.model_router.call(role, draft_prompt, [*history, ChatMessage(role="user", content=user_message)])
        pipeline_steps.append("draft:" + ("ok" if draft.ok else "failed"))

        if not draft.ok:
            return EngineResult(
                answer="I can't reach the local model right now — check that Ollama is running.",
                model_used="none",
                provider="ollama",
                confidence="unverified",
                pipeline_steps=pipeline_steps,
                critic_status="skipped",
                user_visible_metadata={"via": []},
                internal_diagnostics={"error": draft.error, "intent": intent.intent, "quality_mode": quality_mode},
            )

        answer = draft.text
        model_used = draft.model_used or "unknown"
        provider_name = "ollama"
        confidence = _initial_confidence(intent, context, has_missing_knowledge)
        critic_status = "skipped"
        critic_diag: dict = {}

        # Steps 5-6: critic + repair (max LOCAL_CRITIC_MAX_REPAIR_LOOPS)
        if _should_run_critic(intent, quality_mode, settings):
            critic = self._run_critic(user_message, answer, intent, context, success_criteria)
            if critic is None:
                critic_status = "failed"
                pipeline_steps.append("critic:failed")
            else:
                critic_diag = critic
                pipeline_steps.append("critic:" + ("passed" if critic.get("passed") else "flagged"))
                confidence = critic.get("confidence") or confidence
                repair_loops = 0
                while (
                    critic.get("needs_repair")
                    and repair_loops < settings.local_critic_max_repair_loops
                ):
                    repaired = self._run_repair(user_message, answer, critic, intent, context)
                    repair_loops += 1
                    if repaired is None:
                        break
                    answer = repaired
                    critic_status = "repaired"
                    pipeline_steps.append("repair:done")
                    # Re-check once after repair so we don't claim "repaired"
                    # without at least one verification pass — but never loop
                    # past the configured max.
                    if repair_loops < settings.local_critic_max_repair_loops:
                        recheck = self._run_critic(user_message, answer, intent, context)
                        if recheck is not None:
                            critic = recheck
                            confidence = recheck.get("confidence") or confidence
                    else:
                        break
                if critic_status == "skipped":
                    critic_status = "passed" if critic.get("passed") else "failed"

        # Step 7: style pass — only when the critic flagged it too verbose,
        # or the intent explicitly wants "short" and the draft clearly isn't.
        needs_shortening = critic_diag.get("too_verbose") or (
            intent.answer_style == "short" and len(answer) > 400
        )
        if needs_shortening:
            shortened = self._run_style_shorten(answer)
            if shortened:
                answer = shortened
                pipeline_steps.append("style:shortened")

        # Cloud Fallback Gate (Phase 8) — decision only; the actual call
        # happens below only in the one path where it's fully permitted.
        fallback_used = False
        gate_reason = None
        if (
            settings.cloud_fallback_enabled
            and allow_cloud_fallback
            and intent.intent in settings.cloud_fallback_allowed_intent_list
            and confidence in ("low", "unverified")
        ):
            if settings.cloud_fallback_require_user_confirmation:
                # The enclosing `if` above already narrowed confidence to
                # low/unverified, so the offer is always relevant here.
                gate_reason = "confirmation_required"
                answer += _CLOUD_FALLBACK_OFFER_NOTE
            else:
                cloud_text, cloud_provider = self._cloud_fallback(
                    user_message, intent, [*history, ChatMessage(role="user", content=user_message)], draft_prompt
                )
                if cloud_text:
                    answer = cloud_text
                    model_used = cloud_provider or model_used
                    provider_name = cloud_provider or provider_name
                    fallback_used = True
                    confidence = "medium"
                    pipeline_steps.append(f"cloud_fallback:{cloud_provider}")
                else:
                    gate_reason = "cloud_attempt_failed"

        via_names = list(context.source_display_names)

        return EngineResult(
            answer=answer,
            model_used=model_used,
            provider=provider_name,
            sources_used=list(context.gather_result.sources) if context.gather_result else [],
            atlas_citations=list(context.atlas_citations),
            current_info_intent=context.gather_result.task_type if context.gather_result else None,
            search_failure_reason=context.gather_result.search_failure_reason if context.gather_result else None,
            confidence=confidence,
            pipeline_steps=pipeline_steps,
            fallback_used=fallback_used,
            critic_status=critic_status,
            user_visible_metadata={"via": via_names},
            internal_diagnostics={
                "intent": intent.intent,
                "difficulty": intent.difficulty,
                "quality_mode": quality_mode,
                "critic": critic_diag,
                "cloud_gate_reason": gate_reason,
                "local_model_fallback_used": draft.fallback_used,
            },
        )
