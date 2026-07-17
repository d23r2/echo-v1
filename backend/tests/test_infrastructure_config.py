"""ECHO Layer 0 — config defaults, startup validation, and secret exclusion.
No real provider keys or network calls anywhere in this file."""

from app.config import Settings, get_settings


def test_settings_defaults_are_safe_and_local_first():
    settings = Settings(_env_file=None)
    assert settings.ollama_enabled is True
    assert settings.cloud_fallback_enabled is False
    assert settings.free_mode is False
    assert settings.azure_openai_enabled is False
    assert settings.web_search_enabled is False
    assert settings.file_write_enabled is False
    assert settings.code_execution_enabled is False
    assert settings.destructive_actions_enabled is False
    assert settings.public_push_enabled is False
    assert settings.developer_mode is False


def test_settings_frontend_and_ports_match_expected_dev_urls():
    settings = Settings(_env_file=None)
    assert settings.port == 8000
    assert settings.frontend_url == "http://localhost:5174"


def test_validate_startup_reports_no_problems_for_defaults():
    settings = Settings(_env_file=None)
    assert settings.validate_startup() == []


def test_validate_startup_flags_bad_port():
    settings = Settings(_env_file=None, port=99999)
    problems = settings.validate_startup()
    assert any("port" in p for p in problems)


def test_validate_startup_flags_bad_log_level():
    settings = Settings(_env_file=None, log_level="NOISY")
    problems = settings.validate_startup()
    assert any("log_level" in p for p in problems)


def test_validate_startup_flags_bad_app_env():
    settings = Settings(_env_file=None, app_env="staging-prod-mixup")
    problems = settings.validate_startup()
    assert any("app_env" in p for p in problems)


def test_validate_startup_flags_non_positive_timeout():
    settings = Settings(_env_file=None, request_timeout_seconds=0)
    problems = settings.validate_startup()
    assert any("request_timeout_seconds" in p for p in problems)


def test_missing_optional_provider_keys_do_not_break_settings():
    """No provider keys configured at all — Settings() must still construct
    cleanly, matching this app's local-first-by-default posture."""
    settings = Settings(
        _env_file=None,
        anthropic_api_key=None,
        openai_api_key=None,
        gemini_api_key=None,
        xai_api_key=None,
    )
    assert settings.anthropic_api_key is None
    assert settings.gemini_api_key is None


def test_malformed_boolean_env_var_raises_clean_validation_error():
    """pydantic-settings itself rejects a non-boolean string for a bool
    field — confirms invalid values fail loudly at construction time rather
    than silently coercing to a wrong default."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, debug="not-a-boolean")


def test_public_dict_excludes_all_api_key_fields():
    settings = Settings(_env_file=None, anthropic_api_key="sk-real-secret-value")
    public = settings.public_dict()
    assert "anthropic_api_key" not in public
    assert "openai_api_key" not in public
    assert "gemini_api_key" not in public
    assert "xai_api_key" not in public
    assert "azure_openai_api_key" not in public
    assert "openrouter_api_key" not in public
    assert "groq_api_key" not in public
    # non-secret fields survive
    assert "app_name" in public
    assert "ollama_base_url" in public


def test_public_dict_never_contains_the_actual_secret_value():
    settings = Settings(_env_file=None, anthropic_api_key="sk-super-secret-12345")
    public = settings.public_dict()
    serialized = str(public)
    assert "sk-super-secret-12345" not in serialized


def test_get_settings_is_cached_singleton():
    a = get_settings()
    b = get_settings()
    assert a is b
