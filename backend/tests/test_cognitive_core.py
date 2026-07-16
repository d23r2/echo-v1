"""ECHO Cognitive Core v1 — data model, task understanding, graph, skill, and
causal note tests. Everything here is deterministic (regex/keyword-based) —
no model call anywhere, matching the rest of this codebase's classifier
layer convention.
"""

import pytest

from app.models import CausalNote, CognitiveConcept, TaskUnderstanding
from app.services import cognitive_core, concept_extractor, skill_library

# ============================================================================
# A. Data model tests
# ============================================================================


def test_create_concept(db_session):
    concept = cognitive_core.create_or_update_concept(db_session, name="Test Concept", concept_type="tool")
    assert concept.id
    assert concept.name == "Test Concept"
    assert concept.confidence == "medium"


def test_create_relationship(db_session):
    a = cognitive_core.create_or_update_concept(db_session, name="A")
    b = cognitive_core.create_or_update_concept(db_session, name="B")
    rel = cognitive_core.create_relationship(db_session, from_concept_id=a.id, to_concept_id=b.id, relation_type="uses")
    assert rel.id
    assert rel.from_concept_id == a.id
    assert rel.to_concept_id == b.id


def test_create_task_understanding(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test for chat.")
    assert tu is not None
    assert tu.task_type in ("fix_bug", "troubleshoot")
    assert db_session.get(TaskUnderstanding, tu.id) is not None


def test_create_skill_pattern(db_session):
    skill = skill_library.create_skill(db_session, name="Custom Skill", description="A test skill", category="other", steps=["step 1"])
    assert skill.id
    assert skill.steps_json == ["step 1"]


def test_create_causal_note(db_session):
    note = CausalNote(title="Test note", cause="X happens", effect="Y happens", explanation="because Z")
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    assert note.id


def test_create_cognitive_brief(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Give me a prompt to update the Android APK.")
    assert tu is not None
    brief = cognitive_core.build_cognitive_brief(db_session, tu)
    assert brief.id
    assert brief.brief_text
    assert "Goal:" in brief.brief_text


# ============================================================================
# B. Task understanding tests
# ============================================================================


def test_apk_task_identifies_goal_unknowns_success(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Give me a prompt to update Android APK.")
    assert tu is not None
    assert tu.domain == "Android"
    assert tu.task_type == "create_prompt"
    assert any("backend URL" in u for u in tu.unknowns_json)
    assert len(tu.success_criteria_json) > 0


def test_release_status_task_requires_proof(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Is ECHO Green now?")
    assert tu is not None
    assert tu.task_type == "release_build"
    assert any("evidence" in c.lower() or "green" in c.lower() for c in tu.constraints_json)
    assert any("test" in u.lower() or "build" in u.lower() for u in tu.unknowns_json)


def test_current_info_task_requires_source(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "What is the latest Liverpool score?")
    assert tu is not None
    assert tu.task_type == "research_topic"
    assert any("source" in u.lower() or "current" in u.lower() for u in tu.unknowns_json)


def test_prompt_request_identifies_prompt_success_criteria(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Give me a Claude Code prompt to fix the release pipeline.")
    assert tu is not None
    assert tu.task_type == "create_prompt"
    joined = " ".join(tu.success_criteria_json).lower()
    assert "context" in joined or "rules" in joined or "final report" in joined


def test_simple_greeting_uses_lightweight_path(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "hello")
    assert tu is None
    assert db_session.query(TaskUnderstanding).count() == 0


def test_task_understanding_stores_unknowns_and_success_criteria(db_session):
    tu = cognitive_core.build_task_understanding(db_session, "Fix the failing backend test for chat streaming.")
    assert tu is not None
    assert isinstance(tu.unknowns_json, list)
    assert isinstance(tu.success_criteria_json, list)
    assert len(tu.success_criteria_json) > 0


# ============================================================================
# C. Graph tests
# ============================================================================


def test_search_concept(db_session):
    cognitive_core.create_or_update_concept(db_session, name="Ollama", description="local model runtime")
    results = cognitive_core.search_world_model(db_session, "Ollama")
    assert len(results) == 1
    assert results[0]["concept"].name == "Ollama"


def test_retrieve_related_concepts(db_session):
    a = cognitive_core.create_or_update_concept(db_session, name="Android APK")
    b = cognitive_core.create_or_update_concept(db_session, name="Capacitor")
    cognitive_core.create_relationship(db_session, from_concept_id=a.id, to_concept_id=b.id, relation_type="depends_on")
    results = cognitive_core.search_world_model(db_session, "Android APK")
    assert len(results) == 1
    assert len(results[0]["relationships"]) == 1
    assert results[0]["relationships"][0].relation_type == "depends_on"


def test_relationship_confidence_preserved(db_session):
    a = cognitive_core.create_or_update_concept(db_session, name="A2")
    b = cognitive_core.create_or_update_concept(db_session, name="B2")
    rel = cognitive_core.create_relationship(db_session, from_concept_id=a.id, to_concept_id=b.id, relation_type="uses", confidence="inferred")
    assert rel.confidence == "inferred"


def test_archived_concept_excluded_by_default(db_session):
    from app.models import _now

    concept = cognitive_core.create_or_update_concept(db_session, name="Archived Thing")
    concept.archived_at = _now()
    db_session.commit()
    results = cognitive_core.search_world_model(db_session, "Archived Thing")
    assert results == []


# ============================================================================
# D. Skill tests
# ============================================================================


def test_seed_skills_exist(db_session):
    skill_library.seed_skills(db_session)
    names = {s.name for s in skill_library.list_skills(db_session)}
    for expected in ["Build Android APK", "Build Windows App", "Run ECHO Release Verification", "Fix Failing Backend Test", "Create Claude Code Prompt"]:
        assert expected in names


def test_apk_request_matches_build_android_apk_skill(db_session):
    skill_library.seed_skills(db_session)
    matches = cognitive_core.select_relevant_skills(db_session, "How do I build the Android APK?")
    assert any(s.name == "Build Android APK" for s in matches)


def test_failing_test_request_matches_fix_failing_backend_test_skill(db_session):
    skill_library.seed_skills(db_session)
    matches = cognitive_core.select_relevant_skills(db_session, "I have a failing test in the backend, can you fix it?")
    assert any(s.name == "Fix Failing Backend Test" for s in matches)


def test_prompt_request_matches_create_claude_code_prompt_skill(db_session):
    skill_library.seed_skills(db_session)
    matches = cognitive_core.select_relevant_skills(db_session, "Give me a Claude Code prompt for this.")
    assert any(s.name == "Create Claude Code Prompt" for s in matches)


def test_skill_create_update_archive(db_session):
    skill = skill_library.create_skill(db_session, name="Temp Skill", steps=["a"])
    updated = skill_library.update_skill(db_session, skill.id, {"steps": ["a", "b"]})
    assert updated.steps_json == ["a", "b"]
    archived = skill_library.archive_skill(db_session, skill.id)
    assert archived.archived_at is not None
    assert all(s.id != skill.id for s in skill_library.list_skills(db_session))


# ============================================================================
# E. Causal tests
# ============================================================================


def test_android_localhost_causal_note_retrieved_for_apk_context(db_session):
    cognitive_core.seed_world_model(db_session)
    notes = cognitive_core.select_relevant_causal_notes(db_session, "create_prompt", "Android")
    assert any("localhost" in n.cause.lower() for n in notes)


def test_tests_not_run_note_retrieved_for_green_status(db_session):
    cognitive_core.seed_world_model(db_session)
    notes = cognitive_core.select_relevant_causal_notes(db_session, "release_build", "deployment")
    assert any("green" in n.effect.lower() or "test" in n.cause.lower() for n in notes)


def test_current_info_unavailable_note_retrieved_for_live_query(db_session):
    cognitive_core.seed_world_model(db_session)
    notes = cognitive_core.select_relevant_causal_notes(db_session, "research_topic", "research")
    assert any("current" in n.title.lower() or "source" in n.title.lower() for n in notes)


def test_causal_note_create_list_works(db_session):
    note = CausalNote(title="X", cause="a", effect="b", explanation="c")
    db_session.add(note)
    db_session.commit()
    assert db_session.query(CausalNote).filter(CausalNote.archived_at.is_(None)).count() == 1


# ============================================================================
# Seeding + concept extraction
# ============================================================================


def test_seed_world_model_idempotent(db_session):
    cognitive_core.seed_world_model(db_session)
    count_after_first = db_session.query(CognitiveConcept).count()
    cognitive_core.seed_world_model(db_session)
    count_after_second = db_session.query(CognitiveConcept).count()
    assert count_after_first == count_after_second
    assert count_after_first > 0


def test_seed_concepts_marked_system_source(db_session):
    cognitive_core.seed_world_model(db_session)
    echo_concept = db_session.query(CognitiveConcept).filter(CognitiveConcept.name == "ECHO").first()
    assert echo_concept is not None
    assert echo_concept.source_type == "system"


def test_durable_echo_architecture_message_creates_concepts(db_session):
    concepts = concept_extractor.extract_concepts(db_session, "ECHO uses Ollama and SearXNG for no-billing search.")
    names = {c.name for c in concepts}
    assert "ECHO" in names
    assert "Ollama" in names
    assert "SearXNG" in names


def test_temporary_mood_message_does_not_create_permanent_concept(db_session):
    concepts = concept_extractor.extract_concepts(db_session, "I'm feeling a bit tired today.")
    assert concepts == []


def test_sensitive_personal_attribute_not_inferred(db_session):
    concepts = concept_extractor.extract_concepts(db_session, "My health condition and medication are private, don't mention ECHO here.")
    # Even though "ECHO" appears, the sensitive-topic guard blocks extraction entirely for this message.
    assert concepts == []


def test_duplicate_concepts_are_deduplicated(db_session):
    concept_extractor.extract_concepts(db_session, "ECHO is great.")
    concept_extractor.extract_concepts(db_session, "ECHO is still great.")
    count = db_session.query(CognitiveConcept).filter(CognitiveConcept.name == "ECHO").count()
    assert count == 1


def test_concept_extraction_records_source_type(db_session):
    concepts = concept_extractor.extract_concepts(db_session, "ECHO uses Ollama.", conversation_id="conv-123")
    echo = next(c for c in concepts if c.name == "ECHO")
    assert echo.source_type == "conversation"
    assert echo.source_id == "conv-123"


def test_create_or_update_concept_requires_name(db_session):
    with pytest.raises(ValueError):
        cognitive_core.create_or_update_concept(db_session, name="   ")


def test_create_relationship_requires_existing_concepts(db_session):
    with pytest.raises(ValueError):
        cognitive_core.create_relationship(db_session, from_concept_id="nonexistent", to_concept_id="also-nonexistent", relation_type="uses")


def test_cognitive_settings_get_or_create_and_update(db_session):
    settings = cognitive_core.get_or_create_settings(db_session)
    assert settings.cognitive_core_enabled is True
    updated = cognitive_core.update_settings(db_session, {"cognitive_core_enabled": False})
    assert updated.cognitive_core_enabled is False
