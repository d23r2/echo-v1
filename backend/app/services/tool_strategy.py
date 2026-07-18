"""ECHO Layer 2D — Tool Strategy Engine (Phase 4).

Deliberately does not re-derive context classification: wraps
context_router.classify_context() (already a deterministic decision over
memory/library/schedule/projects/tasks/wiki/rss/web) and maps its
ContextSource values onto real, registered tool_registry.TOOLS entries —
never a fabricated tool. A source with no matching real tool (schedule,
direct_page, code_project_files) is honestly omitted from the plan rather
than invented. This module only *plans* — execution is always
tool_registry.run_tool(), unchanged (Phase 5).
"""

from app import schemas
from app.services import context_router
from app.services.tool_registry import TOOLS

# ContextSource -> tool_registry tool_name. Sources with no real matching
# tool (schedule, direct_page, code_project_files, normal_chat, unavailable)
# are deliberately absent — see module docstring.
_SOURCE_TO_TOOL: dict[str, str] = {
    "atlas_memory": "atlas_search",
    "previous_conversation": "previous_conversation_search",
    "library": "library_search",
    "wiki": "wiki_search",
    "rss": "rss_search",
    "web_search": "web_search",
    "projects": "project_search",
    "tasks": "task_search",
}

# Sources that answer a purely creative/rewriting request would never need —
# classify_context() already returns only ["normal_chat"] for those, so this
# set exists mainly as an explicit, testable statement of intent (Phase 4's
# "avoid tool calls for purely creative or rewriting tasks" rule).
_NO_TOOL_SOURCES = {"normal_chat", "code_project_files", "unavailable"}


def build_tool_plan(user_message: str, conversation_id: str | None = None, active_project_id: str | None = None) -> schemas.ToolPlanOut:
    """Never raises — classify_context() itself never raises, and every
    lookup here is a plain dict .get(). Deduplicates by tool_name (two
    ContextSources could in principle map to the same tool)."""
    route = context_router.classify_context(user_message, conversation_id, active_project_id)

    items: list[schemas.ToolPlanItemOut] = []
    seen_tool_names: set[str] = set()
    for source in route.selected_sources:
        if source in _NO_TOOL_SOURCES:
            continue
        tool_name = _SOURCE_TO_TOOL.get(source)
        if tool_name is None or tool_name in seen_tool_names:
            continue
        spec = TOOLS.get(tool_name)
        if spec is None:
            continue
        seen_tool_names.add(tool_name)
        items.append(
            schemas.ToolPlanItemOut(
                tool_name=tool_name,
                purpose=f"Answer using {source.replace('_', ' ')} — {route.reason}.",
                expected_evidence=spec.description,
                risk_level=spec.risk_level,
                requires_confirmation=spec.requires_confirmation or spec.risk_level in ("high", "destructive"),
            )
        )

    return schemas.ToolPlanOut(items=items, routing_reason=route.reason)
