"""Tests for ModelRouter.stream_chat() (Goal 11) — the streaming counterpart to
chat(), covering fallback-before-first-chunk, no-fallback-after-first-chunk,
pinned-provider behavior, and usage tracking. No real network calls anywhere —
every provider is a FakeProvider (tests/fake_providers.py).
"""

import pytest

from app.models import ProviderUsageDaily
from app.providers.base import ChatMessage
from app.router import ModelRouter, NoProviderAvailableError, ProviderUnavailableError
from tests.fake_providers import FakeProvider, FakeProviderError, FakeRateLimitError

_MSG = [ChatMessage(role="user", content="hi")]


def test_auto_mode_streams_from_first_available_provider():
    first = FakeProvider("gemini", stream_chunks=["hel", "lo"])
    second = FakeProvider("ollama", stream_chunks=["nope"])
    router = ModelRouter(providers=[first, second])

    chunks = list(router.stream_chat("auto", "sys", _MSG))

    texts = [c[0] for c in chunks]
    providers_used = {c[1].name for c in chunks}
    assert texts == ["hel", "lo"]
    assert providers_used == {"gemini"}
    assert second.stream_call_count == 0


def test_falls_back_to_next_provider_when_first_fails_before_any_chunk():
    first = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"), stream_raises_after=0)
    second = FakeProvider("ollama", stream_chunks=["from ollama"])
    router = ModelRouter(providers=[first, second])

    chunks = list(router.stream_chat("auto", "sys", _MSG))

    assert [c[0] for c in chunks] == ["from ollama"]
    assert chunks[0][1].name == "ollama"
    assert chunks[0][2] == "Cloud providers were unavailable or quota-limited, so Echo replied using Ollama."


def test_does_not_switch_providers_after_first_chunk_already_yielded():
    provider = FakeProvider(
        "gemini",
        raises=FakeProviderError("connection dropped"),
        stream_chunks=["partial ", "reply"],
        stream_raises_after=1,  # fails after the first chunk
    )
    router = ModelRouter(providers=[provider])

    gen = router.stream_chat("auto", "sys", _MSG)
    first_chunk = next(gen)
    assert first_chunk[0] == "partial "

    with pytest.raises(FakeProviderError):
        next(gen)


def test_pinned_provider_streams_directly():
    provider = FakeProvider("anthropic", stream_chunks=["pinned reply"])
    other = FakeProvider("gemini", stream_chunks=["should not be used"])
    router = ModelRouter(providers=[provider, other])

    chunks = list(router.stream_chat("anthropic", "sys", _MSG))

    assert [c[0] for c in chunks] == ["pinned reply"]
    assert other.stream_call_count == 0


def test_pinned_provider_unavailable_raises_without_streaming():
    provider = FakeProvider("anthropic", available=False, unavailable_reason="no key")
    router = ModelRouter(providers=[provider])

    with pytest.raises(ProviderUnavailableError):
        list(router.stream_chat("anthropic", "sys", _MSG))


def test_pinned_provider_failure_does_not_fall_back():
    pinned = FakeProvider("anthropic", raises=FakeProviderError("down"), stream_raises_after=0)
    other = FakeProvider("gemini", stream_chunks=["should not be used"])
    router = ModelRouter(providers=[pinned, other])

    with pytest.raises(ProviderUnavailableError):
        list(router.stream_chat("anthropic", "sys", _MSG))
    assert other.stream_call_count == 0


def test_no_providers_available_raises():
    router = ModelRouter(providers=[FakeProvider("gemini", available=False, unavailable_reason="no key")])

    with pytest.raises(NoProviderAvailableError):
        list(router.stream_chat("auto", "sys", _MSG))


def test_default_stream_chat_with_no_envelope_yields_raw_text_unmodified():
    # No stream_chunks configured — exercises ModelProvider.stream_chat()'s base
    # default, which every non-Ollama provider still uses today. The provider's
    # chat() returned a plain, no-envelope ChatResult (envelope_status defaults
    # to "missing") — the default streaming path must NOT fabricate REASONING:/
    # ANSWER: markers that were never actually in the model's output.
    provider = FakeProvider("anthropic", response_text="whole reply at once")
    router = ModelRouter(providers=[provider])

    chunks = list(router.stream_chat("auto", "sys", _MSG))

    assert len(chunks) == 1
    assert chunks[0][0] == "whole reply at once"
    assert "ANSWER:" not in chunks[0][0]
    assert "REASONING:" not in chunks[0][0]


def test_default_stream_chat_with_full_envelope_round_trips_faithfully():
    from app.providers.base import ChatResult

    provider = FakeProvider(
        "anthropic",
        chat_result=ChatResult(
            text="the answer",
            reasoning="the reasoning",
            memory_json="NONE",
            envelope_status="complete",
        ),
    )
    router = ModelRouter(providers=[provider])

    chunks = list(router.stream_chat("auto", "sys", _MSG))
    assert len(chunks) == 1

    from app.envelope_stream import EnvelopeStreamParser

    parser = EnvelopeStreamParser()
    parser.feed(chunks[0][0])
    result = parser.result()

    assert result.text == "the answer"
    assert result.reasoning == "the reasoning"
    assert result.memory_json == "NONE"
    assert result.envelope_status == "complete"


def test_usage_tracks_successful_stream(db_session):
    provider = FakeProvider("gemini", stream_chunks=["ok"])
    router = ModelRouter(providers=[provider])

    list(router.stream_chat("auto", "sys", _MSG, db=db_session))

    row = db_session.query(ProviderUsageDaily).filter_by(provider="gemini").first()
    assert row is not None
    assert row.request_count == 1


def test_usage_tracks_429_on_first_chunk_failure(db_session):
    first = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"), stream_raises_after=0)
    second = FakeProvider("ollama", stream_chunks=["ok"])
    router = ModelRouter(providers=[first, second])

    list(router.stream_chat("auto", "sys", _MSG, db=db_session))

    row = db_session.query(ProviderUsageDaily).filter_by(provider="gemini").first()
    assert row is not None
    assert row.last_429_at is not None
