"""Smart Context Router v1 — classifies a user message into the context
source(s) that should inform Echo's reply, before any of them are actually
queried. Deterministic, regex-only, no model calls — same style as
app/search_intent.py, and deliberately reuses that module's classifier for
the current-info/wiki/web/rss decision rather than re-deriving it.

Priority order (first match wins):
1. Explicit "continue where we left off" — projects + tasks + previous
   conversation + schedule + library, the broadest personal-context pull.
2. Task queries ("what tasks are due today?") — tasks + schedule.
3. Project queries ("what projects are active?") — projects.
4. Personal memory ("what did we decide about X?", "do you remember...")
   — atlas_memory + previous_conversation, never wiki/rss/web.
5. Library lookups ("find the PDF I uploaded") — library.
6. Code/file help (content already in front of Echo) — normal_chat only.
7. Everything else — delegate to detect_search_intent for sports/news/web/
   wiki/docs/encyclopedia/general_chat, mapped onto ContextSource values.

This module only classifies; it doesn't execute any of the searches/queries
itself (see Phase 5's fallback clause — routing metadata now, execution can
follow once each source's retrieval is wired up). Normal chat UI must not
show this reasoning verbatim — only a short "via X, Y" style summary of
sources actually used, same posture as the existing search metadata line.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from app.search_intent import detect_search_intent

ContextSource = Literal[
    "normal_chat",
    "atlas_memory",
    "previous_conversation",
    "library",
    "schedule",
    "projects",
    "tasks",
    "wiki",
    "rss",
    "web_search",
    "direct_page",
    "code_project_files",
    "unavailable",
]


@dataclass(frozen=True)
class ContextRoute:
    selected_sources: list[ContextSource]
    reason: str
    confidence: float
    should_search_web: bool = False
    should_search_wiki: bool = False
    should_search_rss: bool = False
    should_search_atlas: bool = False
    should_search_library: bool = False
    should_search_projects: bool = False
    should_search_tasks: bool = False
    also_used: list[str] = field(default_factory=list)


_CONTINUE_PATTERN = re.compile(
    r"\bcontinue where (we|i)('d| had|'ve| have)? left off\b|\bpick up where (we|i) left off\b",
    re.IGNORECASE,
)

_TASK_QUERY_PATTERN = re.compile(
    r"\b(my |show( me)? )?tasks?\b.{0,20}\b(today|due|overdue|pending|left|remaining)\b|"
    r"\bwhat (tasks?|to[- ]?dos?) (do i have|are due|is due)\b",
    re.IGNORECASE,
)

_PROJECT_QUERY_PATTERN = re.compile(
    r"\b(active|current|my|show( me)? (my |the )?) projects?\b|\bwhat projects?\b",
    re.IGNORECASE,
)

_MEMORY_PATTERNS = [
    re.compile(r"\bwhat did we (decide|agree|conclude)\b", re.IGNORECASE),
    re.compile(r"\bdid we (decide|agree|discuss|talk about)\b", re.IGNORECASE),
    re.compile(r"\bwe (decided|agreed|discussed)\b", re.IGNORECASE),
    re.compile(r"\bdo you remember\b", re.IGNORECASE),
    re.compile(r"\bwhat did i (tell|say to) you\b", re.IGNORECASE),
    re.compile(r"\bearlier (chat|conversation)\b", re.IGNORECASE),
    re.compile(r"\bprevious conversation\b", re.IGNORECASE),
    re.compile(r"\blast time\b", re.IGNORECASE),
]

_LIBRARY_PATTERN = re.compile(
    r"\b(find|search for|where is|open|summarize|summarise|read|tell me about) (the |my )?"
    r"(pdf|file|document|upload|attachment|image|photo)\b.*\b(i |we )?(uploaded|attached|added|saved)?\b|"
    r"\bfiles? i (uploaded|attached|saved)\b",
    re.IGNORECASE,
)

_CODE_HELP_TASK_TYPES = {"code_help"}
_WEB_TASK_TYPES = {"web_search", "sports_update", "news_lookup", "docs_lookup"}
_WIKI_TASK_TYPES = {"encyclopedia_lookup", "background_lookup", "definition_lookup", "historical_lookup"}
# Catches live-update phrasing (e.g. "Liverpool score now") that search_intent's
# own is_sports check misses because it requires a recognized sport/competition
# name — a bare team name isn't enough there. Widening it here, locally, avoids
# touching search_intent.py's stricter classification (reused elsewhere) just
# to satisfy the router's own "score/match/result -> also check rss" rule.
_LIVE_UPDATE_KEYWORDS = re.compile(r"\b(score|match|game|fixture|result)\b", re.IGNORECASE)


def classify_context(
    message: str,
    conversation_id: str | None = None,
    active_project_id: str | None = None,
) -> ContextRoute:
    """Never raises. Returns normal_chat for anything ambiguous — the safe
    default is a plain reply, not a speculative multi-source fetch."""
    if not message or not message.strip():
        return ContextRoute(["normal_chat"], "empty message", 1.0)

    text = message.strip()

    if _CONTINUE_PATTERN.search(text):
        return ContextRoute(
            selected_sources=["projects", "tasks", "previous_conversation", "schedule", "library"],
            reason="explicit 'continue where we left off' request",
            confidence=0.9,
            should_search_projects=True,
            should_search_tasks=True,
        )

    if _TASK_QUERY_PATTERN.search(text):
        return ContextRoute(
            selected_sources=["tasks", "schedule"],
            reason="asks about tasks/to-dos and their due dates",
            confidence=0.85,
            should_search_tasks=True,
        )

    if _PROJECT_QUERY_PATTERN.search(text):
        return ContextRoute(
            selected_sources=["projects"],
            reason="asks about active/current projects",
            confidence=0.8,
            should_search_projects=True,
        )

    if any(p.search(text) for p in _MEMORY_PATTERNS):
        return ContextRoute(
            selected_sources=["atlas_memory", "previous_conversation"],
            reason="asks to recall something previously said or decided",
            confidence=0.85,
            should_search_atlas=True,
        )

    if _LIBRARY_PATTERN.search(text):
        return ContextRoute(
            selected_sources=["library"],
            reason="asks to find a previously uploaded/saved file",
            confidence=0.75,
            should_search_library=True,
        )

    intent = detect_search_intent(text)

    if intent.task_type in _CODE_HELP_TASK_TYPES:
        return ContextRoute(
            selected_sources=["normal_chat", "code_project_files"],
            reason=intent.reason,
            confidence=intent.confidence,
        )

    if intent.task_type in _WEB_TASK_TYPES:
        sources: list[ContextSource] = ["web_search"]
        # Sports/news are naturally covered by a live feed too, matching the
        # "Liverpool score now" -> web_search + rss (not wiki alone) example.
        if intent.task_type in ("sports_update", "news_lookup") or _LIVE_UPDATE_KEYWORDS.search(text):
            sources.append("rss")
        if intent.also_needs_wiki:
            sources.append("wiki")
        return ContextRoute(
            selected_sources=sources,
            reason=intent.reason,
            confidence=intent.confidence,
            should_search_web=True,
            should_search_rss="rss" in sources,
            should_search_wiki="wiki" in sources,
        )

    if intent.task_type in _WIKI_TASK_TYPES:
        return ContextRoute(
            selected_sources=["wiki", "normal_chat"],
            reason=intent.reason,
            confidence=intent.confidence,
            should_search_wiki=True,
        )

    return ContextRoute(
        selected_sources=["normal_chat"],
        reason=intent.reason,
        confidence=intent.confidence,
    )
