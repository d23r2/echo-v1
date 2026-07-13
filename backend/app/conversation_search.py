"""Search across PAST conversations — a fallback/supplement to Atlas for
information the user said that was never distilled into a saved memory (the
motivating case: "when you explain technical things to me, lead with an
example" wasn't saved to Atlas, but it's still sitting in a prior message).

Distinction from Atlas: Atlas is distilled long-term memory; this searches raw
conversation history. Two layers, combined:
- Keyword search over SQLite (`Message.content`) — always available, no index
  needed, deterministic.
- Semantic search over a Chroma collection mirroring message content, reusing
  the same local `all-MiniLM-L6-v2` embedding model Atlas already uses — no new
  dependency, no paid service. The index is incrementally updated as messages
  are saved (see index_message()) and fully rebuildable from SQLite at any time
  (see rebuild_index()) if it's ever missing or stale.

Never returns more than a small number of short snippets — this is meant to be
injected into a prompt alongside Atlas memories, not to dump whole
conversations into context.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings

_COLLECTION_NAME = "conversation_messages"
_SNIPPET_MAX_CHARS = 220


@lru_cache
def _get_collection():
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=embedding_fn)


@dataclass(frozen=True)
class MessageSnippet:
    message_id: str
    conversation_id: str
    conversation_title: str
    role: str
    created_at: datetime | None
    snippet: str
    relevance: float | None  # Chroma distance for semantic hits; None for keyword-only hits


def _snippet_text(content: str) -> str:
    content = content.strip()
    if len(content) <= _SNIPPET_MAX_CHARS:
        return content
    return content[:_SNIPPET_MAX_CHARS].rstrip() + "…"


def _to_snippet(message: models.Message, *, relevance: float | None) -> MessageSnippet:
    title = message.conversation.title if message.conversation is not None else ""
    return MessageSnippet(
        message_id=message.id,
        conversation_id=message.conversation_id,
        conversation_title=title,
        role=message.role,
        created_at=message.created_at,
        snippet=_snippet_text(message.content),
        relevance=relevance,
    )


def index_message(message: models.Message) -> None:
    """Best-effort — mirrors one message into the semantic index. Never raises;
    a failure here must not break saving the chat turn itself."""
    try:
        title = message.conversation.title if message.conversation is not None else ""
        _get_collection().upsert(
            ids=[message.id],
            documents=[message.content],
            metadatas=[
                {
                    "conversation_id": message.conversation_id,
                    "role": message.role,
                    "created_at": message.created_at.isoformat() if message.created_at else "",
                    "conversation_title": title,
                }
            ],
        )
    except Exception:
        pass


def rebuild_index(db: Session) -> int:
    """Re-index every message from SQLite — the source of truth. Recovery path
    for a missing/stale Chroma index; safe to call any time."""
    count = 0
    for message in db.query(models.Message).all():
        index_message(message)
        count += 1
    return count


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "and", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "or", "but",
    "i", "me", "my", "you", "your", "did", "do", "does", "what", "we", "our",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def keyword_search(
    db: Session, query: str, *, exclude_conversation_id: str | None = None, top_k: int = 5
) -> list[MessageSnippet]:
    words = _significant_words(query)
    if not words:
        return []

    q = db.query(models.Message)
    if exclude_conversation_id:
        q = q.filter(models.Message.conversation_id != exclude_conversation_id)
    q = q.filter(or_(*(models.Message.content.ilike(f"%{w}%") for w in words)))
    candidates = q.order_by(models.Message.created_at.desc()).limit(top_k * 5).all()

    scored = []
    for m in candidates:
        content_lower = m.content.lower()
        score = sum(1 for w in words if w in content_lower)
        if score > 0:
            scored.append((score, m))
    scored.sort(key=lambda pair: (-pair[0], -(pair[1].created_at.timestamp() if pair[1].created_at else 0)))

    return [_to_snippet(m, relevance=None) for _, m in scored[:top_k]]


def semantic_search(
    db: Session, query: str, *, exclude_conversation_id: str | None = None, top_k: int = 5
) -> list[MessageSnippet]:
    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(query_texts=[query], n_results=min(top_k * 3, count))
    except Exception:
        # Never let a Chroma hiccup break the chat turn — keyword search still works.
        return []

    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    snippets: list[MessageSnippet] = []
    for message_id, distance, meta in zip(ids, distances, metadatas, strict=True):
        if exclude_conversation_id and meta.get("conversation_id") == exclude_conversation_id:
            continue
        message = db.get(models.Message, message_id)
        if message is None:
            continue  # index can lag SQLite deletes; skip rather than error
        snippets.append(_to_snippet(message, relevance=distance))
        if len(snippets) >= top_k:
            break
    return snippets


def search_previous_conversations(
    db: Session,
    query: str,
    *,
    exclude_conversation_id: str | None = None,
    top_k: int = 4,
    prefer_user_messages: bool = False,
) -> list[MessageSnippet]:
    """Combined entry point: semantic hits first (when the index has anything in
    it), topped up with keyword hits, de-duplicated by message, capped at
    top_k. Never crashes on an empty database — just returns []."""
    by_id: dict[str, MessageSnippet] = {}
    for snippet in semantic_search(db, query, exclude_conversation_id=exclude_conversation_id, top_k=top_k):
        by_id[snippet.message_id] = snippet
    if len(by_id) < top_k:
        for snippet in keyword_search(db, query, exclude_conversation_id=exclude_conversation_id, top_k=top_k):
            by_id.setdefault(snippet.message_id, snippet)

    ordered = list(by_id.values())
    if prefer_user_messages:
        ordered.sort(key=lambda s: 0 if s.role == "user" else 1)
    return ordered[:top_k]


# ---- trigger detection ----

_RECALL_TRIGGER_PATTERNS = [
    re.compile(r"\bprevious conversation\b", re.IGNORECASE),
    re.compile(r"\bearlier (chat|conversation)\b", re.IGNORECASE),
    re.compile(r"\bearlier\b", re.IGNORECASE),
    re.compile(r"\blast time\b", re.IGNORECASE),
    re.compile(r"\bas i said\b", re.IGNORECASE),
    re.compile(r"\bdo you remember\b", re.IGNORECASE),
    re.compile(r"\bwe discussed\b", re.IGNORECASE),
    re.compile(r"\bfind (the conversation |where i said)\b", re.IGNORECASE),
    re.compile(r"\bwhat did i (tell|say to) you\b", re.IGNORECASE),
    re.compile(r"\blook through our\b.{0,20}\b(chats?|conversations?)\b", re.IGNORECASE),
    re.compile(r"\bbefore\b", re.IGNORECASE),
]

# Distinguishes "what did I say" (search user's own messages first) from a
# general recall query.
_PREFER_USER_MESSAGES_RE = re.compile(r"\bwhat did i (say|tell you)\b", re.IGNORECASE)


def should_search_previous_conversations(message: str) -> bool:
    return bool(message) and any(p.search(message) for p in _RECALL_TRIGGER_PATTERNS)


def prefers_user_messages(message: str) -> bool:
    return bool(_PREFER_USER_MESSAGES_RE.search(message))
