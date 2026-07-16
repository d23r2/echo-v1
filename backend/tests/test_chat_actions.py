"""ECHO Personal OS v1, Phase 9: app/chat_actions.py's deterministic command
parser, plus its integration into POST /api/chat (app/routers/chat.py).
Unit tests use the isolated db_session fixture (fresh SQLite per test);
integration tests hit the real shared app DB via TestClient like the other
route-level test files, with a FakeProvider swapped in so any message that
does NOT match a command still goes through normal chat without a real
network/model call.
"""

from fastapi.testclient import TestClient

from app import chat_actions
from app.db import init_db
from app.main import app
from app.models import Project, Task
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


# --- Unit tests: parser + execution (isolated db_session) -----------------


def test_create_project_command(db_session):
    result = chat_actions.try_handle_action(db_session, "Create a project called Kitchen Remodel")
    assert result is not None
    assert result.action_type == "create_project"
    assert "Kitchen Remodel" in result.response_text
    project = db_session.get(Project, result.target_id)
    assert project.title == "Kitchen Remodel"


def test_add_task_command_creates_standalone_task(db_session):
    result = chat_actions.try_handle_action(db_session, "Add a task to test Android APK tomorrow")
    assert result is not None
    assert result.action_type == "add_task"
    task = db_session.get(Task, result.target_id)
    assert task.project_id is None
    assert task.source_type == "chat"


def test_add_task_to_named_project_command(db_session):
    project = Project(title="Website Redesign")
    db_session.add(project)
    db_session.commit()

    result = chat_actions.try_handle_action(
        db_session, "add a task to Website Redesign called Pick a font"
    )
    assert result is not None
    assert result.action_type == "add_task_to_project"
    task = db_session.get(Task, result.target_id)
    assert task.project_id == project.id
    assert task.title == "Pick a font"


def test_add_task_to_unknown_project_reports_not_found(db_session):
    result = chat_actions.try_handle_action(db_session, "add a task to Nonexistent Project called Do X")
    assert result is not None
    assert result.action_type == "add_task_project_not_found"
    assert db_session.query(Task).count() == 0


def test_mark_task_done_command(db_session):
    task = Task(title="Buy groceries")
    db_session.add(task)
    db_session.commit()

    result = chat_actions.try_handle_action(db_session, "mark task Buy groceries done")
    assert result is not None
    assert result.action_type == "mark_task_done"
    db_session.refresh(task)
    assert task.status == "done"
    assert task.completed_at is not None


def test_mark_task_done_unambiguous_only(db_session):
    db_session.add(Task(title="Write report"))
    db_session.add(Task(title="Write report"))
    db_session.commit()

    result = chat_actions.try_handle_action(db_session, "mark task Write report done")
    assert result is not None
    assert result.action_type == "mark_task_done_ambiguous"
    assert all(t.status != "done" for t in db_session.query(Task).all())


def test_mark_task_done_not_found(db_session):
    result = chat_actions.try_handle_action(db_session, "mark task Nonexistent Task done")
    assert result is not None
    assert result.action_type == "mark_task_done_not_found"


def test_show_tasks_today_empty_state(db_session):
    result = chat_actions.try_handle_action(db_session, "show my tasks today")
    assert result is not None
    assert result.response_text == "No tasks due today."


def test_show_active_projects_empty_state(db_session):
    result = chat_actions.try_handle_action(db_session, "What projects are active?")
    assert result is not None
    assert "No active projects" in result.response_text


def test_continue_where_left_off_empty_state(db_session):
    result = chat_actions.try_handle_action(db_session, "Continue where we left off")
    assert result is not None
    assert result.response_text == "No active work yet. Create a project or task to begin."


def test_ordinary_message_returns_none(db_session):
    assert chat_actions.try_handle_action(db_session, "How does photosynthesis work?") is None
    assert chat_actions.try_handle_action(db_session, "hey what's up") is None


def test_empty_message_returns_none(db_session):
    assert chat_actions.try_handle_action(db_session, "") is None
    assert chat_actions.try_handle_action(db_session, "   ") is None


# --- Integration: POST /api/chat -------------------------------------------


def test_chat_endpoint_handles_create_project_without_calling_model(monkeypatch):
    """A FakeProvider that raises is wired in so this test would fail loudly
    if the command parser didn't intercept the message before it reached
    model_router.chat()."""

    class ExplodingProvider(FakeProvider):
        def chat(self, *args, **kwargs):
            raise AssertionError("model should not have been called for a matched command")

    fake_router = ModelRouter(providers=[ExplodingProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "Create a project called Chat Test Project", "provider": "auto"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_used"] == "system"
    assert "Chat Test Project" in body["content"]


def test_chat_endpoint_falls_through_to_model_for_ordinary_message(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="a normal reply")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "Tell me a joke", "provider": "auto"})
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "gemini"


def test_chat_endpoint_action_turn_persists_to_conversation_history(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat", json={"message": "Create a project called Persisted History Project", "provider": "auto"}
    )
    conversation_id = resp.json()["conversation_id"]

    detail = client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    contents = [m["content"] for m in detail.json()["messages"]]
    assert "Create a project called Persisted History Project" in contents
    assert any("Persisted History Project" in c for c in contents)


def test_chat_action_response_never_contains_raw_debug_text(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "show active projects", "provider": "auto"})
    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "Traceback" not in content
    assert "sqlalchemy" not in content.lower()
    assert "route" not in content.lower()
