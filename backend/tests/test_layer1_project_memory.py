"""ECHO Layer 1 (Phase 11/12) — lightweight project memory profile fields
and the auto-update hook on task completion."""

from app import chat_actions, schemas
from app.models import ConversationSummary, Project, Task


def _project(db, title="Test project"):
    project = Project(title=title)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_project_memory_fields_default_empty(db_session):
    project = _project(db_session)
    assert project.objective is None
    assert project.constraints_json == []
    assert project.decisions_json == []
    assert project.blockers_json == []
    assert project.last_reviewed_at is None


def test_project_update_sets_last_reviewed_at(db_session):
    from app.routers.projects import update_project

    project = _project(db_session)
    update_project(
        project.id,
        schemas.ProjectUpdate(objective="Ship Layer 1", decisions_json=["Extended AtlasEntry in place"]),
        db_session,
    )
    db_session.refresh(project)
    assert project.objective == "Ship Layer 1"
    assert project.decisions_json == ["Extended AtlasEntry in place"]
    assert project.last_reviewed_at is not None


def test_task_completion_auto_updates_project_decisions(db_session):
    project = _project(db_session, title="Auto-update test project")
    task = Task(title="Finish the audit", project_id=project.id, status="todo")
    db_session.add(task)
    db_session.commit()

    result = chat_actions._mark_task_done(db_session, "Finish the audit")
    assert result.action_type == "mark_task_done"

    db_session.refresh(project)
    assert any("Finish the audit" in note for note in project.decisions_json)


def test_task_completion_without_project_does_not_crash(db_session):
    task = Task(title="Standalone task", status="todo")
    db_session.add(task)
    db_session.commit()
    result = chat_actions._mark_task_done(db_session, "Standalone task")
    assert result.action_type == "mark_task_done"


def test_conversation_summary_defaults_to_final_type(db_session):
    from app.models import Conversation, Message

    conversation = Conversation(title="Summary type test")
    db_session.add(conversation)
    db_session.commit()
    summary = ConversationSummary(conversation_id=conversation.id, title="x", summary="y")
    db_session.add(summary)
    db_session.commit()
    db_session.refresh(summary)
    assert summary.summary_type == "final"
    assert summary.candidate_memory_ids_json == []
    assert Message  # keep import referenced
