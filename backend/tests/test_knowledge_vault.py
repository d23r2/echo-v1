"""ECHO Action + Reliability Core v1 — Personal Knowledge Vault."""

import pytest

from app.services import knowledge_vault


def test_create_list_update_archive_item(db_session):
    item = knowledge_vault.create_item(db_session, title="Use SearXNG as primary no-billing search", body="Chosen because it's free and self-hostable.", item_type="decision")
    assert item.id
    assert item.item_type == "decision"

    items = knowledge_vault.list_items(db_session)
    assert any(i.id == item.id for i in items)

    updated = knowledge_vault.update_item(db_session, item.id, {"body": "Updated rationale."})
    assert updated.body == "Updated rationale."

    archived = knowledge_vault.archive_item(db_session, item.id)
    assert archived.archived_at is not None
    assert all(i.id != item.id for i in knowledge_vault.list_items(db_session))
    assert any(i.id == item.id for i in knowledge_vault.list_items(db_session, include_archived=True))


def test_search_knowledge_item(db_session):
    knowledge_vault.create_item(db_session, title="Docker frontend build notes", body="nginx proxies /api to backend:8000")
    knowledge_vault.create_item(db_session, title="Unrelated note", body="something else entirely")

    results = knowledge_vault.search_items(db_session, "nginx")
    assert len(results) == 1
    assert "Docker" in results[0].title


def test_create_decision_item(db_session):
    item = knowledge_vault.create_item(db_session, title="Decision: local-first", body="ECHO stays Ollama-first.", item_type="decision", confidence="high")
    assert item.item_type == "decision"
    assert item.confidence == "high"


def test_link_to_project_and_task(db_session):
    from app.models import Project, Task

    project = Project(title="Test project")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    task = Task(title="Test task", project_id=project.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    item = knowledge_vault.create_item(db_session, title="Note", project_id=project.id, task_id=task.id)
    assert item.project_id == project.id
    assert item.task_id == task.id


def test_empty_title_rejected(db_session):
    with pytest.raises(ValueError):
        knowledge_vault.create_item(db_session, title="   ")


def test_no_raw_file_paths_exposed(db_session):
    """KnowledgeItem has no file_path-shaped field at all — this is a
    structural guarantee, not a runtime scrub."""
    from app.models import KnowledgeItem

    assert "file_path" not in KnowledgeItem.__table__.columns.keys()
