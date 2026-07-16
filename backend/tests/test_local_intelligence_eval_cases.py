"""ECHO Local Intelligence Engine v1, Phase 14 — verifies routing/pipeline
decisions against tests/fixtures/local_intelligence_eval_cases.json without
needing any real LLM call: only the deterministic classifier/role-selection/
critic-gating functions are exercised, using default (balanced quality
mode, cloud fallback disabled) settings.
"""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.intent_classifier import classify_intent
from app.services.local_intelligence_engine import _select_role, _should_run_critic

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "local_intelligence_eval_cases.json"
_CASES = json.loads(_FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_eval_case_intent_and_source_need(case):
    intent = classify_intent(case["message"])
    assert intent.intent == case["expect"]["intent"], case["id"]
    assert intent.source_need == case["expect"]["source_need"], case["id"]


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_eval_case_model_role(case):
    intent = classify_intent(case["message"])
    role = _select_role(intent, "balanced")
    assert role == case["expect"]["model_role"], case["id"]


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_eval_case_critic_required(case):
    intent = classify_intent(case["message"])
    settings = get_settings()
    assert _should_run_critic(intent, "balanced", settings) == case["expect"]["critic_required"], case["id"]


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_eval_case_cloud_never_used_by_default(case):
    """Every case in the eval set must default to should_use_cloud=false —
    cloud fallback is off by default at the config level, so this holds
    regardless of what a given case's intent/confidence would be."""
    settings = get_settings()
    assert settings.cloud_fallback_enabled is False
    assert case["expect"]["should_use_cloud"] is False


def test_fixture_file_has_all_ten_spec_cases():
    assert len(_CASES) == 10
