"""ECHO Layer 0 — Provider and Model Registry. No real provider calls —
uses tests/fake_providers.py's FakeProvider throughout."""

from app.config import Settings
from app.providers.registry import build_local_model_roles, build_provider_registry
from app.router import ModelRouter
from tests.fake_providers import FakeProvider


def test_registry_loads_with_default_router():
    settings = Settings(_env_file=None)
    router = ModelRouter()
    records = build_provider_registry(settings, router)
    ids = {r.provider_id for r in records}
    assert "ollama" in ids
    assert "anthropic" in ids
    assert "wiki" in ids
    assert "rss" in ids
    assert "searxng" in ids


def test_ollama_reported_local_and_not_requiring_api_key():
    settings = Settings(_env_file=None)
    router = ModelRouter([FakeProvider("ollama", available=True)])
    records = build_provider_registry(settings, router)
    ollama = next(r for r in records if r.provider_id == "ollama")
    assert ollama.requires_api_key is False
    assert ollama.is_paid_or_metered is False
    assert ollama.category == "local_llm"
    assert ollama.available is True


def test_missing_cloud_key_reported_as_not_configured():
    settings = Settings(_env_file=None)
    router = ModelRouter([FakeProvider("anthropic", available=False, unavailable_reason="ANTHROPIC_API_KEY not set")])
    records = build_provider_registry(settings, router)
    anthropic = next(r for r in records if r.provider_id == "anthropic")
    assert anthropic.available is False
    assert anthropic.health == "not_configured"
    assert anthropic.configured is False


def test_missing_cloud_key_does_not_break_local_operation():
    """No cloud provider configured at all — registry still builds and
    reports ollama as available, matching this app's local-first posture."""
    settings = Settings(_env_file=None)
    router = ModelRouter(
        [
            FakeProvider("anthropic", available=False, unavailable_reason="ANTHROPIC_API_KEY not set"),
            FakeProvider("openai", available=False, unavailable_reason="OPENAI_API_KEY not set"),
            FakeProvider("ollama", available=True),
        ]
    )
    records = build_provider_registry(settings, router)
    ollama = next(r for r in records if r.provider_id == "ollama")
    assert ollama.available is True


def test_local_model_role_falls_back_to_default_when_unset():
    settings = Settings(_env_file=None, ollama_model="llama3.1", ollama_model_coding=None)
    roles = build_local_model_roles(settings)
    coding = next(r for r in roles if r.role == "coding")
    assert coding.configured_model == "llama3.1"
    assert coding.falls_back_to_default is True


def test_local_model_role_uses_override_when_set():
    settings = Settings(_env_file=None, ollama_model="llama3.1", ollama_model_coding="codellama")
    roles = build_local_model_roles(settings)
    coding = next(r for r in roles if r.role == "coding")
    assert coding.configured_model == "codellama"
    assert coding.falls_back_to_default is False


def test_registry_never_leaks_api_key_value():
    settings = Settings(_env_file=None, anthropic_api_key="sk-should-never-be-in-registry-output")
    router = ModelRouter()
    records = build_provider_registry(settings, router)
    serialized = str(records)
    assert "sk-should-never-be-in-registry-output" not in serialized


def test_search_provider_missing_dependency_gives_clean_reason():
    settings = Settings(_env_file=None, rss_search_enabled=True, rss_feed_urls="")
    router = ModelRouter()
    records = build_provider_registry(settings, router)
    rss = next(r for r in records if r.provider_id == "rss")
    assert rss.available is False
    assert rss.configured is False
