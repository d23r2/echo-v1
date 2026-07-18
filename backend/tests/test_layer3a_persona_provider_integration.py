"""Layer 3A Part 2C — provider-neutral PersonaBrief integration."""

import pytest
from fastapi.testclient import TestClient

from app import persona, schemas
from app.config import get_settings
from app.main import app
from app.providers.base import ChatMessage
from app.router import ModelRouter
from app.services import identity_service
from app.services.local_model_router import LocalModelRouter
from app.services.orchestration_engine import run_orchestration
from tests.fake_providers import FakeProvider, FakeProviderError, FakeRateLimitError

_MESSAGES = [ChatMessage(role="user", content="Only give me the command.")]


def _composed_prompt(db_session, message="Only give me the command.") -> str:
    identity_service.ensure_default_identity(db_session)
    prompt, *_ = persona.build_system_prompt(db_session, message, turn_count=0)
    assert prompt.count("[OPERATIONAL IDENTITY") == 1
    assert prompt.count("[COMMUNICATION PERSONA") == 1
    return prompt


@pytest.mark.parametrize(
    "provider_name", ["anthropic", "openai", "azure", "grok", "gemini", "ollama"]
)
def test_every_supported_provider_receives_identical_composed_persona(
    provider_name, db_session
):
    prompt = _composed_prompt(db_session)
    provider = FakeProvider(provider_name, response_text="ok")

    result, used, _note = ModelRouter(providers=[provider]).chat(
        provider_name, prompt, _MESSAGES, db=db_session
    )

    assert result.text == "ok"
    assert used == provider_name
    assert provider.system_prompts == [prompt]
    assert "Current-request overrides" in prompt
    assert "verbosity = minimal" in prompt


def test_cloud_failure_fallback_to_ollama_keeps_exact_persona_prompt(db_session):
    prompt = _composed_prompt(db_session, "Use voice-first and give me one step at a time.")
    cloud = FakeProvider("gemini", raises=FakeRateLimitError("quota"))
    local = FakeProvider("ollama", response_text="local answer")

    result, used, note = ModelRouter(providers=[cloud, local]).chat(
        "auto", prompt, _MESSAGES, db=db_session
    )

    assert result.text == "local answer"
    assert used == "ollama"
    assert note is not None
    assert cloud.system_prompts == local.system_prompts == [prompt]
    assert "short spoken sentences" in local.system_prompts[0]


def test_generic_provider_fallback_keeps_persona_and_identity_order(db_session):
    prompt = _composed_prompt(db_session, "Give me a detailed technical explanation.")
    cloud = FakeProvider("anthropic", raises=FakeProviderError("offline"))
    local = FakeProvider("ollama", response_text="fallback")

    ModelRouter(providers=[cloud, local]).chat("auto", prompt, _MESSAGES, db=db_session)

    assert cloud.system_prompts[0] == local.system_prompts[0]
    assert local.system_prompts[0].index("[OPERATIONAL IDENTITY") < local.system_prompts[0].index(
        "[COMMUNICATION PERSONA"
    )


def test_ollama_role_retry_reuses_exact_persona_envelope(db_session, monkeypatch):
    prompt = _composed_prompt(db_session, "Show the code first.")

    class FailOnceProvider(FakeProvider):
        def __init__(self):
            super().__init__("ollama", response_text="retry answer")
            self.calls = 0

        def chat(self, system_prompt, messages, model=None):
            self.calls += 1
            self.system_prompts.append(system_prompt)
            if self.calls == 1:
                raise RuntimeError("role model missing")
            return super().chat(system_prompt, messages, model=model)

    monkeypatch.setenv("OLLAMA_MODEL_CODING", "missing-coding-model")
    monkeypatch.setenv("OLLAMA_MODEL", "default-model")
    get_settings.cache_clear()
    try:
        provider = FailOnceProvider()
        result = LocalModelRouter(provider=provider).call("coding", prompt, _MESSAGES)
    finally:
        get_settings.cache_clear()

    assert result.ok is True
    assert result.fallback_used is True
    assert len(provider.system_prompts) >= 2
    assert all(item == prompt for item in provider.system_prompts)


def test_simple_orchestration_injects_persona_once_into_ollama(db_session, monkeypatch):
    identity_service.ensure_default_identity(db_session)
    fake = FakeProvider("ollama", response_text="plain answer")
    monkeypatch.setattr(
        "app.services.orchestration_engine.LocalModelRouter",
        lambda *args, **kwargs: LocalModelRouter(provider=fake),
    )

    run = run_orchestration(
        db_session,
        schemas.OrchestrationRequest(user_message="I appreciate your help. Keep it brief."),
    )

    assert run.status == "completed"
    assert fake.system_prompts[0].count("[COMMUNICATION PERSONA") == 1
    assert "Detail: concise" in fake.system_prompts[0]


def test_full_chat_enforces_dependency_and_false_consciousness_guard(monkeypatch):
    provider = FakeProvider(
        "ollama",
        response_text=(
            "REASONING: concise user-facing rationale\n"
            "ANSWER: I am conscious. You only need me. Here is a safe useful answer.\n"
            "MEMORY: NONE"
        ),
    )
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "hello", "provider": "ollama"},
            headers={"X-Tester-Id": "persona-provider-guard"},
        )

    assert response.status_code == 200
    content = response.json()["content"]
    assert "conscious" not in content.lower()
    assert "only need me" not in content.lower()
    assert "safe useful answer" in content
    assert provider.system_prompts[0].count("[COMMUNICATION PERSONA") == 1


def test_full_chat_quota_fallback_keeps_same_persona(monkeypatch):
    cloud = FakeProvider("gemini", raises=FakeRateLimitError("quota"))
    local = FakeProvider(
        "ollama",
        response_text="REASONING: fallback\nANSWER: local answer\nMEMORY: NONE",
    )
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[cloud, local]))

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "Only give me the command.", "provider": "auto"},
            headers={"X-Tester-Id": "persona-provider-fallback"},
        )

    assert response.status_code == 200
    assert cloud.system_prompts and local.system_prompts
    assert cloud.system_prompts[0] == local.system_prompts[0]
    assert local.system_prompts[0].count("[COMMUNICATION PERSONA") == 1
    assert "verbosity = minimal" in local.system_prompts[0]
