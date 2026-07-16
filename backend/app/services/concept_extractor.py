"""ECHO Cognitive Core v1 — Concept Map extraction (Phase 6, optional).

Extracts durable, useful concepts from a message into the world model —
deliberately narrow: a fixed allowlist of known ECHO-architecture/tool
vocabulary, not freeform NLP entity extraction. This is what keeps it safe:
there is structurally no path from "user mentioned something" to "a
sensitive personal attribute got inferred and stored," because nothing
outside the allowlist is ever extracted. Temporary chatter (mood, small
talk) never matches anything here and creates nothing.
"""

import re

from sqlalchemy.orm import Session

from app.models import CognitiveConcept
from app.services.cognitive_core import create_or_update_concept

# name -> (regex, concept_type, description). Matches Phase 6's own example
# list. Deliberately a fixed allowlist, not general-purpose entity
# extraction — see module docstring for why.
_KNOWN_CONCEPTS: list[tuple[str, re.Pattern, str, str]] = [
    ("ECHO", re.compile(r"\bECHO\b"), "system", "The adaptive personal AI this repository builds."),
    ("Atlas memory", re.compile(r"\bAtlas\b", re.IGNORECASE), "system", "ECHO's internal, adaptive long-term memory."),
    ("Ollama", re.compile(r"\bOllama\b", re.IGNORECASE), "tool", "Local model runtime ECHO uses for local-first chat."),
    ("SearXNG", re.compile(r"\bSearXNG\b", re.IGNORECASE), "tool", "Self-hosted, no-billing web search meta-engine."),
    ("Wiki provider", re.compile(r"\bWikipedia\b", re.IGNORECASE), "tool", "Free Wikipedia lookups for stable background facts."),
    ("RSS provider", re.compile(r"\bRSS\b"), "tool", "Configured RSS feeds for current headlines."),
    ("Android APK", re.compile(r"\b(Android APK|\.apk\b)", re.IGNORECASE), "file", "ECHO's Android app build artifact."),
    ("Tauri Windows app", re.compile(r"\bTauri\b", re.IGNORECASE), "system", "ECHO's Windows desktop app build."),
    ("Release Manager", re.compile(r"\bRelease Manager\b", re.IGNORECASE), "system", "Tracks recorded test/build results."),
    ("Claude Code prompt", re.compile(r"\bClaude Code prompt\b", re.IGNORECASE), "process", "A structured prompt used to direct Claude Code work."),
    ("API key problem", re.compile(r"\bAPI key\b", re.IGNORECASE), "risk", "Cloud provider credential configuration/cost concern."),
    ("local-first workflow", re.compile(r"\blocal[- ]first\b", re.IGNORECASE), "domain", "Answering primarily from local models, cloud as optional fallback."),
    ("backend tests", re.compile(r"\bbackend tests?\b", re.IGNORECASE), "process", "ECHO's pytest suite."),
    ("frontend build", re.compile(r"\bfrontend build\b", re.IGNORECASE), "process", "The Vite production build."),
]

# Never extracted as a concept even if mentioned — these are the kinds of
# sensitive/personal attributes Atlas's own memory-candidate review already
# handles deliberately and carefully; Cognitive Core's world model is about
# durable ECHO-architecture concepts, not personal facts about the user.
_SENSITIVE_TOPIC_RE = re.compile(
    r"\b(health condition|diagnosis|medication|sexual|religion|political party|immigration status|salary|income)\b",
    re.IGNORECASE,
)


def extract_concepts(db: Session, message: str, conversation_id: str | None = None) -> list[CognitiveConcept]:
    """Never raises, never invents. Returns the concepts that were
    created/touched for this message (empty list for temporary chatter —
    Phase 6 rule 2)."""
    if _SENSITIVE_TOPIC_RE.search(message):
        return []

    touched: list[CognitiveConcept] = []
    for name, pattern, concept_type, description in _KNOWN_CONCEPTS:
        if not pattern.search(message):
            continue
        concept = create_or_update_concept(
            db,
            name=name,
            description=description,
            concept_type=concept_type,
            confidence="medium",
            source_type="conversation",
            source_id=conversation_id,
        )
        touched.append(concept)
    return touched
