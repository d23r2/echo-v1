"""ECHO Action + Reliability Core v1 — Action System."""

import pytest

from app.models import ActionDefinition, Project
from app.services import action_system, permission_center


def test_low_risk_action_runs_directly(db_session):
    run = action_system.run_action(db_session, "create_task", {"title": "Buy milk"})
    assert run.status == "completed"
    assert run.result_json["title"] == "Buy milk"


def test_medium_risk_action_requires_confirmation(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "file_read", "ask_first")
    run = action_system.run_action(db_session, "summarize_file", {"library_item_id": "nonexistent"})
    assert run.status == "pending"
    assert run.user_confirmed is False


def test_medium_risk_action_confirmed_runs(db_session):
    permission_center.ensure_defaults(db_session)
    run = action_system.run_action(db_session, "summarize_file", {"library_item_id": "nonexistent"}, confirm=True)
    # Runs (attempts execution) rather than staying pending — fails cleanly
    # since the library item doesn't exist, but that's a completed attempt.
    assert run.status == "failed"
    assert run.error_summary == "That Library item doesn't exist."


def test_high_risk_action_requires_confirmation(db_session):
    action_system.ensure_registered(db_session)
    run = action_system.run_action(db_session, "run_release_checklist", {"release_id": "nonexistent"})
    assert run.status == "pending"


def test_destructive_action_cannot_run_silently(db_session):
    run = action_system.run_action(db_session, "delete_archive_data", {"kind": "project", "id": "nonexistent"})
    assert run.status == "pending"
    assert run.risk_level == "destructive"


def test_destructive_action_runs_after_confirmation_and_only_archives(db_session):
    project = Project(title="Old project")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    run = action_system.run_action(db_session, "delete_archive_data", {"kind": "project", "id": project.id}, confirm=True)
    assert run.status == "completed"
    db_session.refresh(project)
    assert project.status == "archived"
    assert project.archived_at is not None
    # Still exists — never a hard delete.
    assert db_session.get(Project, project.id) is not None


def test_disabled_action_cannot_run(db_session):
    action_system.ensure_registered(db_session)
    definition = db_session.query(ActionDefinition).filter(ActionDefinition.name == "create_task").first()
    definition.enabled = False
    db_session.commit()

    run = action_system.run_action(db_session, "create_task", {"title": "Should not happen"})
    assert run.status == "cancelled"
    assert "disabled" in run.error_summary.lower()


def test_permission_disabled_blocks_action(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "web_search", "disabled")
    run = action_system.run_action(db_session, "search_web", {"query": "test"})
    assert run.status == "cancelled"
    assert "disabled" in run.error_summary.lower()


def test_failed_action_returns_clean_error(db_session):
    run = action_system.run_action(db_session, "create_task", {"title": ""})
    assert run.status == "failed"
    assert run.error_summary == "A task title is required."
    # No stack trace / traceback text leaked.
    assert "Traceback" not in (run.error_summary or "")
    assert ".py" not in (run.error_summary or "")


def test_unexpected_exception_degrades_to_generic_message(db_session, monkeypatch):
    import dataclasses

    def _boom(db, input):
        raise RuntimeError("some internal detail with a /secret/path")

    broken_spec = dataclasses.replace(action_system.ACTIONS["create_task"], handler=_boom)
    monkeypatch.setitem(action_system.ACTIONS, "create_task", broken_spec)
    run = action_system.run_action(db_session, "create_task", {"title": "x"})
    assert run.status == "failed"
    assert "/secret/path" not in run.error_summary
    assert run.error_summary == "This action couldn't be completed due to an internal error."


def test_action_history_stored(db_session):
    action_system.run_action(db_session, "create_task", {"title": "First"})
    action_system.run_action(db_session, "create_task", {"title": "Second"})
    runs = action_system.list_runs(db_session)
    assert len(runs) >= 2


def test_list_actions_includes_all_registered(db_session):
    definitions = action_system.list_actions(db_session)
    names = {d.name for d in definitions}
    for action_name in action_system.ACTIONS:
        assert action_name in names


def test_approve_pending_run(db_session):
    run = action_system.run_action(db_session, "delete_archive_data", {"kind": "project", "id": "nonexistent"})
    assert run.status == "pending"
    approved = action_system.approve_run(db_session, run.id)
    assert approved.id == run.id
    assert approved.status == "failed"  # project doesn't exist, so it fails cleanly, but it DID run
    assert approved.user_confirmed is True


def test_cancel_pending_run(db_session):
    run = action_system.run_action(db_session, "delete_archive_data", {"kind": "project", "id": "nonexistent"})
    cancelled = action_system.cancel_run(db_session, run.id)
    assert cancelled.status == "cancelled"


def test_cancel_completed_run_raises(db_session):
    run = action_system.run_action(db_session, "create_task", {"title": "Done already"})
    assert run.status == "completed"
    with pytest.raises(ValueError):
        action_system.cancel_run(db_session, run.id)


def test_unknown_action_raises(db_session):
    with pytest.raises(ValueError):
        action_system.run_action(db_session, "not_a_real_action", {})
