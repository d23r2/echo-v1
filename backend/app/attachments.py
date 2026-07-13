"""Chat file attachments: on-disk storage, MIME-based "understood" classification,
and best-effort text extraction for the types we can actually feed to a model.

Important limitation: the provider abstraction (ChatMessage) is plain text only,
except for images via Gemini (see gemini_provider.py) — no provider has real
audio/video understanding wired in. `understood` (classify()) is a coarse "is this
a file type we intend to support at all" flag; `analysis_status` (below) is the
honest, specific record of what actually happened to a given file's *content* this
turn, and is what the UI should show the user. Never let `understood=True` alone
be read as "the model saw this" — check analysis_status instead.
"""

import mimetypes
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.config import get_settings

_UNDERSTOOD_PREFIXES = ("image/", "audio/", "video/", "text/")
_UNDERSTOOD_EXACT = {"application/pdf"}
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".csv", ".yaml", ".yml",
    ".html", ".css", ".sh", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php", ".sql",
}

# Honest labels for what actually happened to an attachment's content this turn —
# never implies more understanding than actually occurred.
ANALYSIS_STATUSES = (
    "text_extracted",  # real text content was pulled out and given to the model
    "vision_analyzed",  # an image, and this turn actually used a vision-capable provider
    "stored",  # saved to disk, but its content was not analyzed (audio/video, or an
    # image when no vision-capable provider was available/used this turn)
    "unsupported",  # not a file type this app attempts to read at all
)


def determine_analysis_status(
    *, mime_type: str, understood: bool, extracted: str | None, vision_capable: bool
) -> str:
    """The single source of truth for what to honestly tell the user about a file."""
    if not understood:
        return "unsupported"
    if mime_type.startswith("image/"):
        return "vision_analyzed" if vision_capable else "stored"
    if extracted:
        return "text_extracted"
    return "stored"


def guess_mime_type(filename: str, provided: str | None) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or provided or "application/octet-stream"


def classify(filename: str, mime_type: str) -> bool:
    """Whether this file type is one Echo is meant to natively read (see module docstring)."""
    if mime_type.startswith(_UNDERSTOOD_PREFIXES) or mime_type in _UNDERSTOOD_EXACT:
        return True
    # Code files sometimes arrive with a generic octet-stream MIME type from the
    # browser — fall back to extension for those.
    return Path(filename).suffix.lower() in _CODE_EXTENSIONS


def save_to_disk(filename: str, content: bytes) -> str:
    settings = get_settings()
    attachments_dir = Path(settings.attachments_dir)
    attachments_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid4()}_{Path(filename).name}"
    path = attachments_dir / safe_name
    path.write_bytes(content)
    return str(path)


def extract_text_for_prompt(
    filename: str, mime_type: str, content: bytes, max_chars: int = 4000
) -> str | None:
    """Best-effort extraction of file content to inject into the model prompt.
    Only implemented for text/code (decode directly) and PDF (via pypdf) — the
    types actually readable today. Returns None if nothing could be extracted."""
    if mime_type.startswith("text/") or Path(filename).suffix.lower() in _CODE_EXTENSIONS:
        try:
            return content.decode("utf-8", errors="replace")[:max_chars]
        except Exception:
            return None

    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text[:max_chars] if text.strip() else None
        except Exception:
            return None

    return None
