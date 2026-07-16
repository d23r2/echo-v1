"""ECHO Action + Reliability Core v1 — Safety and Permission Center."""

from app.services import permission_center


def test_defaults_seed_all_keys(db_session):
    permission_center.ensure_defaults(db_session)
    keys = {p.permission_key for p in permission_center.list_permissions(db_session)}
    for perm in permission_center.DEFAULT_PERMISSIONS:
        assert perm["key"] in keys


def test_defaults_are_safe(db_session):
    permission_center.ensure_defaults(db_session)
    cloud = permission_center.get_permission(db_session, "cloud_api_use")
    assert cloud.level == "disabled"
    delete = permission_center.get_permission(db_session, "delete_archive_data")
    assert delete.level == "ask_first"
    image_gen = permission_center.get_permission(db_session, "image_generation")
    assert image_gen.level == "disabled"


def test_set_permission_level(db_session):
    updated = permission_center.set_permission_level(db_session, "web_search", "disabled")
    assert updated.level == "disabled"


def test_set_unknown_permission_raises(db_session):
    import pytest

    with pytest.raises(ValueError):
        permission_center.set_permission_level(db_session, "not_a_real_key", "allowed")


def test_check_disabled_blocks(db_session):
    permission_center.set_permission_level(db_session, "web_search", "disabled")
    result = permission_center.check(db_session, "web_search")
    assert result.allowed is False


def test_check_ask_first_needs_confirmation(db_session):
    permission_center.set_permission_level(db_session, "action_update_task", "ask_first")
    result = permission_center.check(db_session, "action_update_task")
    assert result.allowed is True
    assert result.needs_confirmation is True


def test_check_allowed_runs_without_confirmation(db_session):
    permission_center.set_permission_level(db_session, "action_create_task", "allowed")
    result = permission_center.check(db_session, "action_create_task")
    assert result.allowed is True
    assert result.needs_confirmation is False


def test_check_none_key_always_allowed(db_session):
    result = permission_center.check(db_session, None)
    assert result.allowed is True
    assert result.needs_confirmation is False


def test_check_falls_back_to_default_when_unseeded(db_session):
    """Before ensure_defaults() has ever run against this DB, check() must
    still return the correct safe default rather than erroring or silently
    allowing everything."""
    result = permission_center.check(db_session, "cloud_api_use")
    assert result.allowed is False
