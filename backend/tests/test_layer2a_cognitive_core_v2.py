"""ECHO Layer 2A (Phases 1, 6, 7) — cognitive_core.py's v2 orchestration:
build_task_understanding()'s new fields, re-analysis/staleness caching,
correction handling, and CognitiveBrief v2. Uses the isolated db_session
fixture, no model call anywhere."""

from app.models import CognitiveBrief, TaskUnderstanding
from app.services import cognitive_core


def test_simple_message_still_returns_none(db_session):
    # Backward compatibility: v1's own gating behavior is untouched.
    assert cognitive_core.build_task_understanding(db_session, "hi", conversation_id="c1") is None


def test_complex_message_populates_v2_fields(db_session):
    tu = cognitive_core.build_task_understanding(
        db_session, "Fix the failing backend test by Friday", conversation_id="c2"
    )
    assert tu is not None
    assert tu.task_category in ("debugging", "coding")
    assert tu.scope in ("current_turn", "conversation", "project", "recurring_workflow", "long_term_goal")
    assert isinstance(tu.acceptance_tests_json, list) and tu.acceptance_tests_json
    assert isinstance(tu.missing_information_json, list)
    assert tu.content_fingerprint is not None


def test_legacy_task_type_and_v1_fields_unaffected(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Is ECHO Green now?", conversation_id="c3")
    assert tu.task_type == "release_build"  # v1 field, unchanged behavior
    assert tu.goal_summary  # v1 field still populated


def test_high_stakes_message_requires_clarification(db_session):
    # "fix the failing test" guarantees the is_complex_task gate passes;
    # "delete...permanently"/"push...publicly"/"production" trip the
    # high-risk keyword profile in task_understanding_v2.derive_risk_profile.
    tu = cognitive_core.build_task_understanding(
        db_session,
        "Fix the failing test, then delete the old backup files permanently and push publicly to production",
        conversation_id="c4",
    )
    assert tu is not None
    assert tu.confirmation_requirement is True
    assert tu.status in ("needs_clarification", "ready")


def test_repeated_identical_message_reuses_existing_task(db_session):
    first = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c5")
    second = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c5")
    assert first.id == second.id  # no duplicate re-analysis
    assert db_session.query(TaskUnderstanding).filter(TaskUnderstanding.conversation_id == "c5").count() == 1


def test_materially_different_message_creates_new_task(db_session):
    first = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c6")
    second = cognitive_core.build_task_understanding(db_session, "Research the latest Python release notes", conversation_id="c6")
    assert first.id != second.id


def test_reanalyse_creates_new_task_and_supersedes_old(db_session):
    original = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c7")
    reanalysed = cognitive_core.reanalyse_task_understanding(db_session, original.id)
    assert reanalysed is not None
    assert reanalysed.id != original.id
    assert reanalysed.parent_task_id == original.id
    db_session.refresh(original)
    assert original.status == "superseded"


def test_reanalyse_unknown_id_returns_none(db_session):
    assert cognitive_core.reanalyse_task_understanding(db_session, "does-not-exist") is None


def test_apply_correction_updates_goal(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c8")
    corrected = cognitive_core.apply_task_correction(db_session, tu.id, {"primary_goal": "Actually fix the frontend build instead"})
    assert corrected.primary_goal == "Actually fix the frontend build instead"
    assert corrected.goal_summary == "Actually fix the frontend build instead"
    assert corrected.status == "ready"


def test_apply_correction_rebuilds_linked_brief(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c9")
    brief = cognitive_core.build_cognitive_brief(db_session, tu, "c9")
    cognitive_core.apply_task_correction(db_session, tu.id, {"expected_output": "a written summary, not a fix"})
    briefs = db_session.query(CognitiveBrief).filter(CognitiveBrief.task_understanding_id == tu.id).all()
    assert len(briefs) == 2  # original + rebuilt, history preserved
    assert brief.id != briefs[-1].id


def test_apply_correction_unknown_id_returns_none(db_session):
    assert cognitive_core.apply_task_correction(db_session, "does-not-exist", {"primary_goal": "x"}) is None


def test_cognitive_brief_v2_fields_populated(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test", conversation_id="c10")
    brief = cognitive_core.build_cognitive_brief(db_session, tu, "c10")
    assert brief.confidence == tu.confidence
    assert brief.next_reasoning_stage in ("clarify", "answer")


def test_brief_text_includes_blocking_missing_info_but_not_raw_json():
    tu = TaskUnderstanding(
        goal_summary="Test goal", domain="general", task_type="other",
        missing_information_json=[{"item": "critical unknown", "tier": "blocking"}],
    )
    from app.services.cognitive_core import _build_brief_text

    text = _build_brief_text(tu, [], [], [])
    assert "critical unknown" in text
    assert "{" not in text  # never a raw JSON dump
    assert "tier" not in text


def test_project_scoped_task_stores_project_id(db_session):
    tu = cognitive_core.build_task_understanding(
        db_session, "Fix the failing backend test", conversation_id="c11", project_id="proj-1"
    )
    assert tu.project_id == "proj-1"
    # Full project-scoped context *filtering* (excluding another project's
    # memories/concepts) is Layer 2E's job (Context Selection v2) — this
    # milestone only guarantees the scope is captured and round-trips, which
    # is what a later filtering layer needs to exist at all.
    other = cognitive_core.build_task_understanding(
        db_session, "Research the latest Python release notes", conversation_id="c11b", project_id="proj-2"
    )
    assert other.project_id != tu.project_id


def test_explicit_constraint_preserved_end_to_end(db_session):
    tu = cognitive_core.build_task_understanding(
        db_session, "Fix the failing backend test, keep this local-only, no cloud", conversation_id="c12"
    )
    assert any("local-only" in c.lower() for c in tu.constraints_json)


def test_cognitive_brief_stays_within_compact_budget(db_session):
    # A generous but real budget — the brief must never balloon into a
    # multi-KB dump regardless of how many constraints/skills/concepts match.
    tu = cognitive_core.build_task_understanding(
        db_session, "Fix the failing backend test, keep this local-only, by Friday, under $50", conversation_id="c13"
    )
    brief = cognitive_core.build_cognitive_brief(db_session, tu, "c13")
    assert len(brief.brief_text) < 2000
