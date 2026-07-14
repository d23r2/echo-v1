"""Deterministic classifier: does this message need external info beyond what
Ollama (or any other configured model) already knows from training, and if
so, what kind? Regex-only, no model calls — same style as
preference_detection.py/dependency_patterns.py. Feeds app/web_search.py's
SourceRouter (see that module for which provider each task_type maps to).

Priority order (first match wins, checked in this sequence):
1. Personal memory ("what did I say before...") — never web/wiki/RSS, always
   Atlas/previous-conversation instead. Reuses conversation_search's own
   trigger detector rather than duplicating it.
2. Code/file help ("explain this error", "summarize this file") — the user
   is asking about content already in front of Echo, not asking it to go
   find something new.
3. Sports — score/match/fixture keywords paired with a sport/competition
   name.
4. Current/live/news/price/weather/policy signals — anything time-sensitive
   that training data can't reliably answer.
5. Encyclopedia/background/definition/historical — stable, non-current
   knowledge that a free Wikipedia lookup can ground without needing "live"
   search at all.
6. Otherwise: general_chat, no search.

A message can match both a "current" signal and a "background" signal at
once (e.g. "Who is Messi and did he score today?") — also_needs_wiki flags
that case so the router fetches both instead of only the primary task_type.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.conversation_search import should_search_previous_conversations

TaskType = Literal[
    "memory_lookup",
    "code_help",
    "sports_update",
    "news_lookup",
    "web_search",
    "docs_lookup",
    "encyclopedia_lookup",
    "background_lookup",
    "definition_lookup",
    "historical_lookup",
    "general_chat",
]


@dataclass(frozen=True)
class SearchIntent:
    needs_current_info: bool
    task_type: TaskType
    confidence: float
    reason: str
    # True when the message also asks for stable background info alongside
    # a current-info request (mixed query) — the router should fetch Wiki
    # in addition to whatever the primary task_type triggers.
    also_needs_wiki: bool = False


_CODE_HELP_PATTERNS = [
    re.compile(
        r"\bexplain (this|the)\b.{0,25}\b(code|error|function|bug|exception|traceback|stack trace)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(fix|debug) (this|the) (code|bug|error|function)\b", re.IGNORECASE),
    re.compile(r"\bwhat does (this|the) (code|function|script) do\b", re.IGNORECASE),
    re.compile(r"\bsummar(y|ise|ize) (this|the) (file|document|upload|attachment)\b", re.IGNORECASE),
]

_SPORT_NAMES = re.compile(
    r"\b(football|soccer|cricket|epl|premier league|champions league|world cup|fifa|nba|nfl|"
    r"rugby|tennis|f1|formula 1|olympics)\b",
    re.IGNORECASE,
)
_SPORT_ACTION = re.compile(
    r"\b(match update|match details|live score|score|fixture|result|kick[- ]?off|"
    r"full[- ]?time|standings)\b",
    re.IGNORECASE,
)
_TEAM_VS_TEAM = re.compile(r"\b\w+(?:\s\w+)?\s+vs\.?\s+\w+(?:\s\w+)?\b", re.IGNORECASE)

_CURRENT_INFO_PATTERNS = [
    re.compile(r"\blatest\b", re.IGNORECASE),
    re.compile(r"\b(today|right now|currently|at the moment)\b", re.IGNORECASE),
    re.compile(r"\bcurrent\b", re.IGNORECASE),
    re.compile(r"\blive\b", re.IGNORECASE),
    re.compile(r"\bupdate[sd]?\b", re.IGNORECASE),
    re.compile(r"\b(now|these days)\b", re.IGNORECASE),
    re.compile(r"\bprice[sd]?\b", re.IGNORECASE),
    re.compile(r"\bweather\b", re.IGNORECASE),
    re.compile(r"\b(visa|law|policy|regulation) (change|update|rule)s?\b", re.IGNORECASE),
    re.compile(r"\bis (this|it) still true\b", re.IGNORECASE),
    re.compile(r"\bstill (valid|accurate|correct|true)\b", re.IGNORECASE),
    # "last match/game/result/score" is a very natural way to ask for the
    # most recent outcome of something ongoing — deliberately narrower than a
    # bare "\blast\b" (which would also match "last year", "last name", "at
    # last", none of which imply wanting current info).
    re.compile(r"\blast (match|game|result|score|fixture)\b", re.IGNORECASE),
]
_NEWS_KEYWORDS = re.compile(r"\bnews\b", re.IGNORECASE)
_DOCS_KEYWORDS = re.compile(
    r"\b(api docs?|documentation|changelog|release notes|latest version|current version)\b", re.IGNORECASE
)

_ENCYCLOPEDIA_PATTERNS = [
    (re.compile(r"\bwho (was|is)\b", re.IGNORECASE), "encyclopedia_lookup"),
    # "what is" alone is too generic an interrogative prefix — "what is the
    # latest news today?" is ONE current-info question, not a request for
    # background on some other subject, even though it starts with "what
    # is". Excluded when immediately followed by a current-info word so it
    # doesn't spuriously set also_needs_wiki (and inject irrelevant wiki
    # results) for what's really a single live/current question.
    (
        re.compile(
            r"\bwhat is\b(?!\s+(the\s+)?(latest|current(ly)?|today'?s?|now|live|weather|price)\b)",
            re.IGNORECASE,
        ),
        "definition_lookup",
    ),
    (re.compile(r"\bexplain the\b", re.IGNORECASE), "background_lookup"),
    (re.compile(r"\b(background on|history of|tell me about)\b", re.IGNORECASE), "background_lookup"),
]


def detect_search_intent(message: str) -> SearchIntent:
    """Never raises. Returns general_chat/needs_current_info=False for
    anything ambiguous — the safe default is "don't search", not "search
    speculatively"."""
    if not message or not message.strip():
        return SearchIntent(False, "general_chat", 1.0, "empty message")

    text = message.strip()

    if should_search_previous_conversations(text):
        return SearchIntent(
            False, "memory_lookup", 0.9, "matches a previous-conversation/personal-memory recall phrase"
        )

    if any(p.search(text) for p in _CODE_HELP_PATTERNS):
        return SearchIntent(False, "code_help", 0.85, "asks about code/content already in the conversation")

    is_sports = (bool(_SPORT_NAMES.search(text)) and bool(_SPORT_ACTION.search(text))) or (
        bool(_TEAM_VS_TEAM.search(text)) and bool(_SPORT_ACTION.search(text))
    )
    # "news"/docs keywords count as their own current-info signal, not just a
    # sub-classification applied after some other trigger fires — "any
    # breaking news about the election?" has no "latest/today/current/..."
    # word in it at all, so without this it fell all the way through to
    # general_chat instead of news_lookup.
    has_current_signal = (
        any(p.search(text) for p in _CURRENT_INFO_PATTERNS)
        or bool(_SPORT_ACTION.search(text))
        or bool(_NEWS_KEYWORDS.search(text))
        or bool(_DOCS_KEYWORDS.search(text))
    )
    has_background_signal = any(p.search(text) for p, _ in _ENCYCLOPEDIA_PATTERNS)

    if is_sports:
        return SearchIntent(
            True,
            "sports_update",
            0.85,
            "mentions a sport/competition alongside a score/match/fixture keyword",
            also_needs_wiki=has_background_signal,
        )

    if has_current_signal:
        if _DOCS_KEYWORDS.search(text):
            task_type: TaskType = "docs_lookup"
            reason = "asks about current/latest software or API documentation"
        elif _NEWS_KEYWORDS.search(text):
            task_type = "news_lookup"
            reason = "asks for current news"
        else:
            task_type = "web_search"
            reason = "contains a current/live/latest-info signal"
        return SearchIntent(True, task_type, 0.75, reason, also_needs_wiki=has_background_signal)

    for pattern, task_type in _ENCYCLOPEDIA_PATTERNS:
        if pattern.search(text):
            return SearchIntent(
                False, task_type, 0.7, "asks for stable background/definitional/historical knowledge"
            )

    return SearchIntent(False, "general_chat", 0.6, "no current-info or background-lookup signal detected")
