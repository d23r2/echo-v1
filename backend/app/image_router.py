"""Image generation provider selection (Phase 6).

Ollama's standard chat models cannot generate images at all — unlike text
chat, there is no always-available local fallback here. This module is
deliberately honest about what actually works in this build:

- gemini: real, working (Imagen via app/providers/gemini_provider.py),
  gated on GEMINI_API_KEY same as chat.
- comfyui: a reachability-check-only stub. A configured, reachable ComfyUI
  server is reported with a distinct reason from "not configured" or
  "unreachable" so the frontend/user can tell those apart, but this build
  never actually submits a generation job to it — so it's never selected as
  the active provider. Wiring a real ComfyUI workflow (queueing a prompt,
  polling /history, decoding the result) is real, untested-in-this-sandbox
  work and out of scope for a safe pass; see PROJECT_HEALTH_REPORT.md.
- ollama: always unavailable — no image-capable model is wired up.

IMAGE_PROVIDER controls selection: "auto" tries gemini only (the sole
provider that can currently generate); "gemini"/"ollama"/"comfyui" pin to
that provider's own status; "disabled" turns image generation off entirely.
"""

from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass
class ImageProviderStatus:
    available: bool
    reason: str | None = None


def _gemini_status() -> ImageProviderStatus:
    settings = get_settings()
    if not settings.gemini_api_key:
        return ImageProviderStatus(False, "GEMINI_API_KEY not set")
    return ImageProviderStatus(True, None)


def _ollama_status() -> ImageProviderStatus:
    return ImageProviderStatus(False, "Ollama does not support image generation in this build")


def comfyui_health_check(base_url: str, timeout: float = 2.0) -> bool:
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/system_stats", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _comfyui_status() -> ImageProviderStatus:
    settings = get_settings()
    if not settings.comfyui_base_url:
        return ImageProviderStatus(False, "COMFYUI_BASE_URL not set")
    if not comfyui_health_check(settings.comfyui_base_url):
        return ImageProviderStatus(False, "ComfyUI is configured but not reachable")
    return ImageProviderStatus(
        False, "ComfyUI is reachable, but image generation isn't implemented in this build yet"
    )


_STATUS_CHECKS = {
    "gemini": _gemini_status,
    "ollama": _ollama_status,
    "comfyui": _comfyui_status,
}


def clean_unavailable_reason(raw_reason: str | None) -> str:
    """Translates a select_provider() reason (which may name a config field
    like GEMINI_API_KEY/COMFYUI_BASE_URL/IMAGE_PROVIDER for server-side/log
    clarity — see the raw strings above) into a short, human-readable message
    with no internal config/env-var names. Use this wherever a reason crosses
    into an HTTP response or the chat UI (routers/chat.py's generate-image
    endpoint, routers/features.py's image_generation_detail.reason); the raw
    form stays fine for statuses()'s per-provider breakdown, which is API/log
    detail that the frontend never renders directly."""
    if not raw_reason:
        return "Image generation is unavailable right now."
    lower = raw_reason.lower()
    if "disabled" in lower:
        return "Image generation is turned off."
    if "does not support" in lower:
        return "Image generation isn't available for this provider."
    if "not implemented" in lower:
        return "Image generation isn't available right now."
    if "not reachable" in lower or "unreachable" in lower:
        return "Image generation isn't reachable right now."
    if "not set" in lower or "not configured" in lower or "no image generation provider" in lower:
        return "Image generation isn't configured yet."
    return "Image generation is unavailable right now."


class ImageGenerationRouter:
    def statuses(self) -> dict[str, ImageProviderStatus]:
        return {name: check() for name, check in _STATUS_CHECKS.items()}

    def select_provider(self) -> tuple[str | None, str | None]:
        """Returns (active_provider_name, None) if something can generate an
        image right now, or (None, reason) if nothing can. Only "gemini" can
        currently win this — see module docstring for why comfyui/ollama
        never do, regardless of IMAGE_PROVIDER."""
        settings = get_settings()
        mode = settings.image_provider

        if mode == "disabled":
            return None, "Image generation is disabled (IMAGE_PROVIDER=disabled)"

        if mode in _STATUS_CHECKS:
            status = _STATUS_CHECKS[mode]()
            return (mode, None) if status.available else (None, status.reason)

        # "auto" (default): try each real candidate in order.
        for name in ("gemini", "comfyui", "ollama"):
            status = _STATUS_CHECKS[name]()
            if status.available:
                return name, None
        return None, "No image generation provider is available (configure GEMINI_API_KEY or COMFYUI_BASE_URL)"


image_router = ImageGenerationRouter()
