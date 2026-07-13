"""Phase 6: image generation provider architecture (app/image_router.py).

No real Gemini/Imagen/ComfyUI calls anywhere — GEMINI_API_KEY presence and
COMFYUI_BASE_URL reachability are both driven by a monkeypatched Settings
object, and ComfyUI's HTTP health check itself is monkeypatched at the
function level so no real network call happens even for "is it reachable".
"""

from types import SimpleNamespace

from app.image_router import ImageGenerationRouter


def _settings(**overrides):
    base = dict(
        gemini_api_key=None,
        comfyui_base_url=None,
        image_provider="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# 1. Nothing configured -> clean "unavailable", not an exception, not a fake success.
def test_auto_mode_reports_clean_unavailable_when_nothing_configured(monkeypatch):
    monkeypatch.setattr("app.image_router.get_settings", lambda: _settings())
    router = ImageGenerationRouter()

    provider, reason = router.select_provider()

    assert provider is None
    assert reason is not None and "no image generation provider" in reason.lower()


# 2. Gemini configured -> auto mode selects it as the real, working provider.
def test_auto_mode_selects_gemini_when_configured(monkeypatch):
    monkeypatch.setattr("app.image_router.get_settings", lambda: _settings(gemini_api_key="fake-key"))
    router = ImageGenerationRouter()

    provider, reason = router.select_provider()

    assert provider == "gemini"
    assert reason is None


# 3. Ollama never reports itself as an image-generation provider, regardless
#    of pinning — no image-capable model is wired up in this build.
def test_ollama_pinned_is_always_unavailable(monkeypatch):
    monkeypatch.setattr("app.image_router.get_settings", lambda: _settings(image_provider="ollama"))
    router = ImageGenerationRouter()

    provider, reason = router.select_provider()

    assert provider is None
    assert "does not support" in reason.lower()


# 4. ComfyUI configured and reachable -> distinct "reachable but not implemented"
#    reason, never silently selected as an active generator (avoids promising a
#    generation the backend can't actually perform yet).
def test_comfyui_reachable_reports_stub_reason_not_selected(monkeypatch):
    monkeypatch.setattr(
        "app.image_router.get_settings",
        lambda: _settings(comfyui_base_url="http://localhost:8188", image_provider="auto"),
    )
    monkeypatch.setattr("app.image_router.comfyui_health_check", lambda base_url, timeout=2.0: True)
    router = ImageGenerationRouter()

    statuses = router.statuses()
    provider, reason = router.select_provider()

    assert statuses["comfyui"].available is False
    assert "isn't implemented" in statuses["comfyui"].reason.lower()
    assert provider is None  # nothing else configured either in this test


# 5. IMAGE_PROVIDER=disabled turns image generation off entirely, even if
#    Gemini is otherwise fully configured.
def test_image_provider_disabled_overrides_configured_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.image_router.get_settings",
        lambda: _settings(gemini_api_key="fake-key", image_provider="disabled"),
    )
    router = ImageGenerationRouter()

    provider, reason = router.select_provider()

    assert provider is None
    assert "disabled" in reason.lower()
