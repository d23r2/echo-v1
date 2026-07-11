"""Chat file attachments: on-disk storage, MIME-based "understood" classification,
and best-effort text extraction for the types we can actually feed to a model.

Important limitation: the provider abstraction (ChatMessage) is plain text only —
there is no multimodal (vision/audio/video) support wired into any provider today.
`understood` reflects the file TYPE this app intends to support per the product
spec (images/PDF/audio/video/text/code = True, binary Office formats = False), not
that the model literally saw the file's bytes. Only text/code and PDF content is
actually extracted and injected into the prompt below — images/audio/video are
stored and shown to the user as "understood", but their content is not currently
analyzed by the model. Wiring up real multimodal provider calls is future work.
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
