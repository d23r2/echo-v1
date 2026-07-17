"""ECHO Layer 0 — Feature Flag Registry."""

from app.config import Settings
from app.core.feature_flags import get_flag, list_feature_flags


def test_registry_lists_all_core_subsystems():
    settings = Settings(_env_file=None)
    flags = list_feature_flags(settings)
    keys = {f.key for f in flags}
    expected = {
        "chat", "ollama", "cloud_fallback", "atlas", "cognitive_core",
        "local_intelligence", "human_persona", "operational_self_model",
        "skill_engine", "action_system", "permission_center", "evaluation_lab",
        "knowledge_vault", "projects", "tasks", "schedule", "library",
        "wiki", "rss", "searxng", "direct_page_fetch", "voice", "camera",
        "image_generation", "android_support", "windows_support",
        "developer_mode", "advanced_navigation",
    }
    assert expected.issubset(keys)


def test_enabled_feature_is_available():
    settings = Settings(_env_file=None)
    flag = get_flag(settings, "ollama")
    assert flag.enabled is True
    assert flag.available is True
    assert flag.unavailable_reason is None


def test_disabled_feature_reports_clean_reason():
    settings = Settings(_env_file=None, cloud_fallback_enabled=False)
    flag = get_flag(settings, "cloud_fallback")
    assert flag.enabled is False
    assert flag.available is False
    assert flag.unavailable_reason is not None
    assert "Traceback" not in flag.unavailable_reason


def test_missing_dependency_reported_cleanly_for_rss():
    settings = Settings(_env_file=None, rss_search_enabled=True, rss_feed_urls="")
    flag = get_flag(settings, "rss")
    assert flag.enabled is True
    assert flag.available is False
    assert flag.dependency_status == "missing_dependency"
    assert "RSS_FEED_URLS" in flag.unavailable_reason


def test_missing_dependency_reported_cleanly_for_searxng():
    settings = Settings(_env_file=None, web_search_enabled=True, web_search_provider="searxng", searxng_base_url=None)
    flag = get_flag(settings, "searxng")
    assert flag.available is False
    assert "SEARXNG_BASE_URL" in flag.unavailable_reason


def test_cognitive_core_disabled_does_not_crash_registry():
    settings = Settings(_env_file=None, cognitive_core_enabled=False)
    flags = list_feature_flags(settings)
    assert len(flags) > 0
    cc = get_flag(settings, "cognitive_core")
    assert cc.enabled is False


def test_developer_only_flags_have_no_secret_content():
    settings = Settings(_env_file=None, anthropic_api_key="sk-should-never-appear-here")
    flags = list_feature_flags(settings)
    for flag in flags:
        assert "sk-should-never-appear-here" not in str(flag.unavailable_reason)


def test_unknown_flag_key_returns_none():
    settings = Settings(_env_file=None)
    assert get_flag(settings, "not_a_real_feature") is None
