"""ECHO Layer 2D — tool_strategy.py: build_tool_plan(). Wraps
context_router.classify_context() and maps its sources onto real
tool_registry.TOOLS entries — never calls a real search/tool backend."""

from app import schemas
from app.services import tool_strategy


def test_creative_task_selects_no_tools():
    plan = tool_strategy.build_tool_plan("Write me a short poem about the ocean.")
    assert plan.items == []


def test_current_info_task_selects_a_search_tool():
    plan = tool_strategy.build_tool_plan("What's the latest news on the election results today?")
    tool_names = {item.tool_name for item in plan.items}
    assert tool_names & {"web_search", "rss_search", "wiki_search"}


def test_library_source_maps_to_library_search_tool(monkeypatch):
    from app.services import context_router as cr

    fake_route = cr.ContextRoute(selected_sources=["library"], reason="uploaded file reference detected", confidence=0.9)
    monkeypatch.setattr(tool_strategy.context_router, "classify_context", lambda *a, **k: fake_route)

    plan = tool_strategy.build_tool_plan("Summarize the file I uploaded earlier")
    assert plan.items[0].tool_name == "library_search"
    assert plan.items[0].purpose.startswith("Answer using library")


def test_projects_and_tasks_sources_both_get_distinct_tools(monkeypatch):
    from app.services import context_router as cr

    fake_route = cr.ContextRoute(selected_sources=["projects", "tasks"], reason="mission control reference", confidence=0.9)
    monkeypatch.setattr(tool_strategy.context_router, "classify_context", lambda *a, **k: fake_route)

    plan = tool_strategy.build_tool_plan("what are my active projects and open tasks?")
    tool_names = [item.tool_name for item in plan.items]
    assert tool_names == ["project_search", "task_search"]


def test_no_tool_sources_never_produce_a_tool_item(monkeypatch):
    from app.services import context_router as cr

    fake_route = cr.ContextRoute(selected_sources=["normal_chat", "code_project_files"], reason="ordinary conversation", confidence=0.9)
    monkeypatch.setattr(tool_strategy.context_router, "classify_context", lambda *a, **k: fake_route)

    plan = tool_strategy.build_tool_plan("hey, how's it going?")
    assert plan.items == []


def test_duplicate_sources_mapping_to_same_tool_are_suppressed(monkeypatch):
    from app.services import context_router as cr

    fake_route = cr.ContextRoute(selected_sources=["atlas_memory", "previous_conversation", "atlas_memory"], reason="memory recall", confidence=0.9)
    monkeypatch.setattr(tool_strategy.context_router, "classify_context", lambda *a, **k: fake_route)

    plan = tool_strategy.build_tool_plan("what did we talk about last time?")
    tool_names = [item.tool_name for item in plan.items]
    assert tool_names.count("atlas_search") == 1
    assert set(tool_names) == {"atlas_search", "previous_conversation_search"}


def test_unknown_source_with_no_registered_tool_is_honestly_omitted(monkeypatch):
    from app.services import context_router as cr

    fake_route = cr.ContextRoute(selected_sources=["schedule", "direct_page"], reason="schedule reference", confidence=0.9)
    monkeypatch.setattr(tool_strategy.context_router, "classify_context", lambda *a, **k: fake_route)

    plan = tool_strategy.build_tool_plan("remind me about my appointment")
    assert plan.items == []  # honestly empty, not a fabricated tool


def test_tool_plan_out_shape_is_typed_and_clean():
    plan = tool_strategy.build_tool_plan("What's the weather like right now?")
    assert isinstance(plan, schemas.ToolPlanOut)
    for item in plan.items:
        assert isinstance(item, schemas.ToolPlanItemOut)
        assert item.tool_name
        assert item.risk_level in ("low", "medium", "high", "destructive")
