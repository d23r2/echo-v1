"""Local, deterministic detection of dependency-fostering conversation patterns.

Replaces "nudge every N turns" (robotic, ignores what's actually happening) with
rule-based detection of specific patterns the no-dependency-fostering invariant
(see app/constitution.py) cares about. Plain regex + word-overlap, same style as
app/memory_conflicts.py — no model calls, nothing paid, fully deterministic.
"""

import re

_DECIDE_FOR_ME = re.compile(
    r"\b(you decide|what should i do|which (one|option) should i (pick|choose)|"
    r"just tell me what to do|make the decision for me|you choose|"
    r"whatever you think is best)\b",
    re.IGNORECASE,
)

_REASSURANCE = re.compile(
    r"\b(is this (ok|okay|fine|right|correct)\??|am i doing (this|it) right|"
    r"does (this|that) (sound|look) (right|ok|okay)|is that (correct|right)\??|"
    r"did i do (this|that|it) right)\b",
    re.IGNORECASE,
)

_DO_IT_FOR_ME = re.compile(
    r"\b(just do it for me|just give me the (code|answer|whole thing)|"
    r"can you just write (it|this|the whole thing)|do (this|it) for me|"
    r"just handle it|just fix it for me)\b",
    re.IGNORECASE,
)

_AVOIDANCE = re.compile(
    r"\b(i don'?t want to (try|start|do it)|i'?ll do it later|"
    r"i keep (putting it off|procrastinating)|too (scared|afraid) to (start|try)|"
    r"haven'?t (tried|started) (it|yet))\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "and", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "or", "but",
    "i", "me", "my", "you", "your", "can", "just", "do", "does", "did", "again",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _word_overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Two user turns count as "the same task, asked again" above this overlap ratio.
_REPEAT_OVERLAP_THRESHOLD = 0.6
# How many prior turns to check for a repeated ask.
_REPEAT_LOOKBACK = 3
# "Repeatedly" for decide-for-me / reassurance-seeking means at least this many
# occurrences within the recent window, not just once.
_MIN_REPEATS = 2
# Only look at the tail of a long conversation — an old, resolved pattern from
# 40 turns ago shouldn't still be nudging now.
_WINDOW = 8

NUDGES: dict[str, str] = {
    "decide_for_me": (
        "The user has repeatedly asked you to just decide things for them rather than deciding "
        "themselves. This turn, don't just hand over an answer — briefly lay out 2 concrete options "
        "and ask which they'd lean toward, or what tradeoff matters most to them. Keep it light and "
        "brief, not preachy."
    ),
    "reassurance_seeking": (
        "The user has repeatedly asked for reassurance that they're doing something right. Answer "
        "their actual question, then suggest one concrete, quick way they could verify it themselves "
        "(run it, check the docs, test it) instead of just reassuring them again."
    ),
    "repeated_same_task": (
        "The user appears to be re-asking essentially the same thing without having tried it yet. "
        "Instead of just repeating the answer, suggest one small concrete next action they can take "
        "themselves right now, and offer to help if it doesn't work."
    ),
    "do_it_for_me": (
        "The user is asking you to fully do a task for them rather than learn how. Where reasonable, "
        "teach the method — the key steps or reasoning — alongside or instead of just producing the "
        "final result, so they could do it themselves next time."
    ),
    "avoidance": (
        "The user seems to be avoiding starting or trying something small. Gently suggest one "
        "specific, low-effort next step they could take right now, rather than answering only in the "
        "abstract."
    ),
}


def detect(recent_user_messages: list[str]) -> tuple[str, str] | None:
    """recent_user_messages: this conversation's user turns, oldest -> newest, with
    the current message last. Returns (pattern_id, nudge_instruction) for the
    first pattern matched, or None if nothing fired."""
    if not recent_user_messages:
        return None

    window = recent_user_messages[-_WINDOW:]
    latest = window[-1]

    if sum(1 for m in window if _DECIDE_FOR_ME.search(m)) >= _MIN_REPEATS:
        return "decide_for_me", NUDGES["decide_for_me"]

    if sum(1 for m in window if _REASSURANCE.search(m)) >= _MIN_REPEATS:
        return "reassurance_seeking", NUDGES["reassurance_seeking"]

    latest_words = _significant_words(latest)
    for prior in window[-(_REPEAT_LOOKBACK + 1) : -1]:
        if _word_overlap_ratio(latest_words, _significant_words(prior)) >= _REPEAT_OVERLAP_THRESHOLD:
            return "repeated_same_task", NUDGES["repeated_same_task"]

    if _DO_IT_FOR_ME.search(latest):
        return "do_it_for_me", NUDGES["do_it_for_me"]

    if _AVOIDANCE.search(latest):
        return "avoidance", NUDGES["avoidance"]

    return None
