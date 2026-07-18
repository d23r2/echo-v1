"""ECHO Layer 2D — Phase 1: capability/speed/privacy/context-size tagging on
top of the existing Layer 0 provider registry, plus role-based model mapping
capability tags and the health-metrics reader. No real provider calls —
FakeProvider throughout, same convention as
tests/test_infrastructure_provider_registry.py."""

from app.config import Settings
from app.core import metrics
from app.providers.registry import _health_metrics, build_local_model_roles, build_provider_registry
from app.router import ModelRouter
from tests.fake_providers import FakeProvider


def test_provider_records_carry_capability_metadata():
    settings = Settings(_env_file=None)
    router = ModelRouter()  # default provider list — includes ollama + every cloud provider
    records = build_provider_registry(settings, router)
    ollama = next(r for r in records if r.provider_id == "ollama")
    anthropic = next(r for r in records if r.provider_id == "anthropic")

    assert ollama.privacy_class == "local"
    assert anthropic.privacy_class == "cloud"
    assert isinstance(ollama.capabilities, list) and ollama.capabilities
    assert ollama.speed_class in ("fast", "medium", "slow")
    assert ollama.context_size > 0


def test_measured_health_fields_none_when_nothing_recorded():
    metrics.reset()  # metrics counters are process-global — start from a clean slate
    settings = Settings(_env_file=None)
    router = ModelRouter([FakeProvider("ollama", available=True)])
    records = build_provider_registry(settings, router)
    ollama = next(r for r in records if r.provider_id == "ollama")
    assert ollama.measured_avg_latency_ms is None
    assert ollama.measured_failure_rate is None
    assert ollama.measured_sample_count == 0


def test_health_metrics_reads_recorded_success_and_duration():
    metrics.reset()
    metrics.increment("model_calls_total", provider="ollama", outcome="success")
    metrics.record_duration("model_call_duration_ms", 42.0, provider="ollama")

    avg_latency, failure_rate, sample_count = _health_metrics("ollama")
    assert avg_latency is not None
    assert failure_rate == 0.0
    assert sample_count >= 1


def test_local_model_roles_carry_role_specific_capabilities():
    settings = Settings(_env_file=None)
    roles = build_local_model_roles(settings)
    role_map = {r.role: r for r in roles}
    assert set(role_map.keys()) == {"fast", "reasoning", "coding", "critic", "writing"}
    assert "coding" in role_map["coding"].capabilities
    assert "critique" in role_map["critic"].capabilities
