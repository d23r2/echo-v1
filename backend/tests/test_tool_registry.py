"""ECHO Action + Reliability Core v1 — Internal Plugin / Tool System."""

from app.models import ToolDefinition
from app.services import permission_center, tool_registry


def test_tool_registry_loads(db_session):
    tools = tool_registry.list_tools(db_session)
    names = {t.tool_name for t in tools}
    for tool_name in tool_registry.TOOLS:
        assert tool_name in names


def test_disabled_tool_blocked(db_session):
    tool_registry.ensure_registered(db_session)
    definition = db_session.query(ToolDefinition).filter(ToolDefinition.tool_name == "web_search").first()
    definition.enabled = False
    db_session.commit()

    run = tool_registry.run_tool(db_session, "web_search", {"query": "test"})
    assert run.status == "blocked"
    assert "disabled" in run.error_summary.lower()


def test_tool_permission_enforced(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "wiki_search", "disabled")
    run = tool_registry.run_tool(db_session, "wiki_search", {"query": "test"})
    assert run.status == "blocked"


def test_low_risk_tool_runs(db_session):
    run = tool_registry.run_tool(db_session, "create_task", {"title": "From a tool"})
    assert run.status == "completed"
    assert run.output_json["title"] == "From a tool"


def test_high_risk_tool_requires_confirmation(db_session):
    run = tool_registry.run_tool(db_session, "create_release_check", {"release_id": "nonexistent"})
    assert run.status == "blocked"
    assert "confirmation" in run.error_summary.lower()


def test_high_risk_tool_confirmed_runs(db_session):
    from app.services import release_manager

    release = release_manager.create_release(db_session, version_name="v1")
    run = tool_registry.run_tool(db_session, "create_release_check", {"release_id": release.id}, confirm=True)
    assert run.status == "completed"


def test_tool_error_sanitized(db_session):
    run = tool_registry.run_tool(db_session, "create_task", {"title": ""})
    assert run.status == "failed"
    assert run.error_summary == "A task title is required."
    assert "Traceback" not in run.error_summary


def test_camera_placeholder_clean_unavailable(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "camera_input", "allowed")
    run = tool_registry.run_tool(db_session, "camera_capture_placeholder", {})
    assert run.status == "completed"
    assert run.output_json["available"] is False


def test_voice_placeholder_clean_unavailable(db_session):
    run = tool_registry.run_tool(db_session, "voice_input_placeholder", {})
    assert run.status == "completed"
    assert run.output_json["available"] is False


def test_unknown_tool_raises(db_session):
    import pytest

    with pytest.raises(ValueError):
        tool_registry.run_tool(db_session, "not_a_real_tool", {})


def test_tool_run_history_stored(db_session):
    tool_registry.run_tool(db_session, "create_task", {"title": "A"})
    tool_registry.run_tool(db_session, "create_task", {"title": "B"})
    runs = tool_registry.list_runs(db_session)
    assert len(runs) >= 2
