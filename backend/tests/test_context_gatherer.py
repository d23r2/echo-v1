"""ECHO Local Intelligence Engine v1, Phase 4 — app/services/context_gatherer.py.
Uses the isolated db_session fixture; web_search.gather_sources() is
monkeypatched to a canned result so no test ever makes a real network call
(wiki/SearXNG/RSS mechanics are already covered by test_web_search.py).
"""

from app.models import Project, ScheduleItem, Task
from app.services.context_gatherer import gather_context
from app.services.intent_classifier import classify_intent
from app.web_search import GatherResult, SourceResult


def _canned_wiki_result() -> GatherResult:
    return GatherResult(
        sources=[
            SourceResult(
                source_type="wiki",
                provider="wikimedia",
                title="Nikola Tesla",
                url="https://en.wikipedia.org/wiki/Nikola_Tesla",
                retrieved_at="2026-07-16T00:00:00Z",
                snippet="Serbian-American inventor and engineer.",
            )
        ],
        wiki_search_used=True,
        task_type="encyclopedia_lookup",
    )


def _canned_failure_result() -> GatherResult:
    return GatherResult(sources=[], search_failure_reason="web search disabled", task_type="web_search")


def test_normal_chat_does_not_call_web_search(db_session, monkeypatch):
    called = {"count": 0}

    def _fail_if_called(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("gather_sources should not be called for normal chat")

    monkeypatch.setattr("app.services.context_gatherer.web_search.gather_sources", _fail_if_called)

    intent = classify_intent("Explain entropy simply.")
    ctx = gather_context(db_session, intent, "Explain entropy simply.")
    assert called["count"] == 0
    assert ctx.web_context == []
    assert ctx.wiki_context == []


def test_current_info_retrieves_web(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.context_gatherer.web_search.gather_sources",
        lambda intent, query: GatherResult(
            sources=[
                SourceResult(
                    source_type="web_search",
                    provider="searxng",
                    title="Liverpool 2-0",
                    retrieved_at="2026-07-16T00:00:00Z",
                    snippet="Final score",
                )
            ],
            web_search_used=True,
            task_type="web_search",
        ),
    )
    intent = classify_intent("What is the Liverpool score now?")
    ctx = gather_context(db_session, intent, "What is the Liverpool score now?")
    assert len(ctx.web_context) == 1
    assert "SearXNG" in ctx.source_display_names


def test_wiki_background_retrieves_wiki(db_session, monkeypatch):
    monkeypatch.setattr("app.services.context_gatherer.web_search.gather_sources", lambda intent, query: _canned_wiki_result())
    intent = classify_intent("Who was Nikola Tesla?")
    ctx = gather_context(db_session, intent, "Who was Nikola Tesla?")
    assert len(ctx.wiki_context) == 1
    assert "Wikipedia" in ctx.source_display_names


def test_memory_query_retrieves_atlas_and_conversation(db_session):
    from app import atlas, schemas

    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="We chose Ollama first, SearXNG for search.", epistemic_status="Verified", confidence=0.9, tags=["decision"]),
    )
    intent = classify_intent("What did we decide about search?")
    ctx = gather_context(db_session, intent, "What did we decide about search?")
    assert len(ctx.memory_context) >= 1
    assert "Atlas" in ctx.source_display_names


def test_library_query_retrieves_files(db_session):
    from app import library

    library.register_item(db_session, title="ECHO release checklist", file_path="/tmp/x.md", file_type="document", source="upload")
    intent = classify_intent("Summarize the file I uploaded.")
    ctx = gather_context(db_session, intent, "Summarize the file I uploaded.")
    assert len(ctx.library_context) >= 1
    assert "Library" in ctx.source_display_names


def test_source_display_names_are_deduplicated(db_session, monkeypatch):
    monkeypatch.setattr("app.services.context_gatherer.web_search.gather_sources", lambda intent, query: _canned_wiki_result())
    intent = classify_intent("Who was Nikola Tesla?")
    ctx = gather_context(db_session, intent, "Who was Nikola Tesla?")
    assert ctx.source_display_names.count("Wikipedia") == 1


def test_unavailable_source_produces_clean_warning_not_raw_error(db_session, monkeypatch):
    monkeypatch.setattr("app.services.context_gatherer.web_search.gather_sources", lambda intent, query: _canned_failure_result())
    intent = classify_intent("What is the Liverpool score now?")
    ctx = gather_context(db_session, intent, "What is the Liverpool score now?")
    assert ctx.warnings == ["Could not verify current information."]
    for w in ctx.warnings:
        assert "Traceback" not in w
        assert "Exception" not in w


def test_project_task_intent_gathers_projects_and_tasks(db_session):
    project = Project(title="Test Project", status="active")
    db_session.add(project)
    db_session.commit()
    task = Task(title="Do the thing", project_id=project.id, status="todo")
    db_session.add(task)
    db_session.commit()

    intent = classify_intent("What tasks are due today?")
    ctx = gather_context(db_session, intent, "What tasks are due today?")
    assert any("Do the thing" in t for t in ctx.task_context)
    assert any("Test Project" in p for p in ctx.project_context)


def test_schedule_intent_gathers_schedule_items(db_session):
    item = ScheduleItem(title="Take a break", status="pending")
    db_session.add(item)
    db_session.commit()

    # force schedule-specific gather path directly since "what's on my
    # schedule" isn't one of context_router's own trigger phrases yet
    from app.services.context_gatherer import GatheredContext, _gather_schedule

    ctx = GatheredContext()
    _gather_schedule(db_session, ctx)
    assert any("Take a break" in s for s in ctx.schedule_context)
    assert "Schedule" in ctx.source_display_names


def test_gather_context_never_raises_on_empty_db(db_session):
    intent = classify_intent("hello")
    ctx = gather_context(db_session, intent, "hello")
    assert ctx.as_dict()["warnings"] == []


def test_context_stays_within_char_budget(db_session, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LOCAL_CONTEXT_MAX_CHARS", "200")
    get_settings.cache_clear()
    try:
        from app import atlas, schemas

        for i in range(10):
            atlas.create_entry(
                db_session,
                schemas.AtlasEntryCreate(
                    content=f"Some fairly long memory entry number {i} with enough text to add up quickly.",
                    epistemic_status="Verified",
                    confidence=0.8,
                    tags=["test"],
                ),
            )
        intent = classify_intent("What did we decide about SearXNG?")
        ctx = gather_context(db_session, intent, "What did we decide about SearXNG?")
        total_chars = sum(len(line) for line in ctx.memory_context + ctx.conversation_context)
        assert total_chars <= 200
    finally:
        get_settings.cache_clear()
