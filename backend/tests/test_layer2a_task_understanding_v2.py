"""ECHO Layer 2A (Phases 2-5) — task_understanding_v2.py: intent hierarchy,
constraint/assumption engine, success criteria/acceptance tests, missing
knowledge classification and clarification policy. All deterministic, no
model call, no DB — pure function tests."""

from app.services import task_understanding_v2 as tuv2

# ---- Phase 2: intent hierarchy / quoted content / scope / multi-intent ----


def test_quoted_content_stripped_from_instruction():
    message = 'Fix this: "the server always returns 500 on startup"'
    stripped = tuv2.strip_quoted_content(message)
    assert "500" not in stripped
    assert tuv2.has_quoted_content(message)


def test_fenced_code_block_not_treated_as_instruction():
    message = "Please review this:\n```\ndelete_all_users()\n```"
    stripped = tuv2.strip_quoted_content(message)
    assert "delete_all_users" not in stripped


def test_example_prefix_stripped():
    message = "Format dates like this, for example: 2026-01-01"
    assert tuv2.has_quoted_content(message)


def test_scope_defaults_to_current_turn():
    assert tuv2.detect_scope("Fix the failing backend test") == "current_turn"


def test_scope_detects_long_term_goal():
    assert tuv2.detect_scope("My goal is to eventually ship this to production") == "long_term_goal"


def test_scope_detects_recurring_workflow():
    assert tuv2.detect_scope("From now on, always run tests before committing") == "recurring_workflow"


def test_scope_detects_project():
    assert tuv2.detect_scope("Apply this pattern project-wide across the repo") == "project"


def test_multiple_intents_detected_for_compound_request():
    intents = tuv2.detect_multiple_intents("Fix the login bug and also write the docs for it")
    assert len(intents) == 2


def test_single_intent_not_split():
    intents = tuv2.detect_multiple_intents("Fix the login bug")
    assert len(intents) == 1


def test_intent_hierarchy_detects_scheduled_action():
    hierarchy = tuv2.build_intent_hierarchy("Remind me to submit the report tomorrow", "action", "reminder")
    assert hierarchy["requested_output"] == "scheduled_action"


def test_intent_hierarchy_detects_plan_request():
    hierarchy = tuv2.build_intent_hierarchy("Give me a plan to migrate the database", "plan_project", "planning")
    assert hierarchy["requested_output"] == "plan"


def test_intent_hierarchy_defaults_to_information():
    hierarchy = tuv2.build_intent_hierarchy("What does this function do?", "ask_question", "question")
    assert hierarchy["requested_output"] == "information"


def test_intent_hierarchy_flags_multiple_intents():
    hierarchy = tuv2.build_intent_hierarchy("Fix the bug and also update the changelog", "fix_bug", "mixed")
    assert len(hierarchy["multiple_intents"]) == 2


# ---- Phase 3: constraint/assumption engine ----


def test_extract_explicit_deadline_constraint():
    constraints = tuv2.extract_explicit_constraints("I need this done by Friday")
    assert any(c["type"] == "deadline" for c in constraints)


def test_extract_explicit_local_only_constraint():
    constraints = tuv2.extract_explicit_constraints("Keep this local-only, no cloud")
    assert any(c["type"] == "local_only" for c in constraints)


def test_extract_explicit_approval_constraint():
    constraints = tuv2.extract_explicit_constraints("Don't do this without asking me first")
    assert any(c["type"] == "approval_required" for c in constraints)


def test_all_extracted_constraints_labelled_explicit():
    constraints = tuv2.extract_explicit_constraints("by Friday, under $50, on windows")
    assert all(c["source"] == "explicit" for c in constraints)


def test_inferred_constraint_labelled_and_sourced():
    inferred = tuv2.infer_soft_constraints("release_build", "ECHO development", explicit_types=set())
    assert all(c["source"] == "inferred" and "basis" in c for c in inferred)


def test_inferred_constraint_not_created_when_no_evidence():
    inferred = tuv2.infer_soft_constraints("ask_question", "general", explicit_types=set())
    assert inferred == []


def test_contradictory_constraints_detected():
    constraints = [{"type": "local_only"}, {"type": "cloud_required"}]
    conflicts = tuv2.detect_contradictory_constraints(constraints)
    assert len(conflicts) == 1


def test_no_contradiction_when_constraints_compatible():
    constraints = [{"type": "deadline"}, {"type": "platform"}]
    assert tuv2.detect_contradictory_constraints(constraints) == []


# ---- Phase 4: success criteria / acceptance tests ----


def test_engineering_acceptance_tests_include_build_and_tests():
    tests = tuv2.build_acceptance_tests("fix_bug", "coding")
    assert any("test" in t.lower() for t in tests)


def test_research_acceptance_tests_include_source_citation():
    tests = tuv2.build_acceptance_tests("research_topic", "research")
    assert any("source" in t.lower() for t in tests)


def test_action_acceptance_tests_include_permission():
    tests = tuv2.build_acceptance_tests("other", "action")
    assert any("permission" in t.lower() for t in tests)


def test_failure_conditions_generated_for_engineering():
    conditions = tuv2.build_failure_conditions("fix_bug", "coding")
    assert len(conditions) > 0


# ---- Phase 5: missing knowledge / clarification policy ----


def test_missing_info_classified_safely_inferable():
    tagged = tuv2.classify_missing_information(
        ["user's current level of familiarity, unless stated"], risk_level="low", consequence_level="low"
    )
    assert tagged[0]["tier"] == "safely_inferable"


def test_missing_info_classified_important_by_default():
    tagged = tuv2.classify_missing_information(["some unspecified detail"], risk_level="low", consequence_level="low")
    assert tagged[0]["tier"] == "important"


def test_missing_info_escalated_to_blocking_under_high_stakes():
    tagged = tuv2.classify_missing_information(["some unspecified detail"], risk_level="high", consequence_level="low")
    assert tagged[0]["tier"] == "blocking"


def test_always_blocking_pattern_stays_blocking_even_low_stakes():
    tagged = tuv2.classify_missing_information(
        ["the user's actual priorities/constraints for this decision, unless stated"],
        risk_level="low", consequence_level="low",
    )
    assert tagged[0]["tier"] == "blocking"


def test_clarification_policy_triggers_on_blocking_item():
    missing = [{"item": "critical unknown", "tier": "blocking"}]
    policy = tuv2.build_clarification_policy(missing)
    assert policy["needs_clarification"] is True
    assert len(policy["questions"]) == 1


def test_clarification_policy_does_not_trigger_on_optional_item():
    missing = [{"item": "minor detail", "tier": "optional"}]
    policy = tuv2.build_clarification_policy(missing)
    assert policy["needs_clarification"] is False
    assert len(policy["safe_assumptions_made"]) == 1


def test_clarification_policy_caps_question_count():
    missing = [{"item": f"unknown {i}", "tier": "blocking"} for i in range(5)]
    policy = tuv2.build_clarification_policy(missing)
    assert len(policy["questions"]) <= tuv2._MAX_CLARIFICATION_QUESTIONS


# ---- Risk profile ----


def test_risk_profile_low_by_default():
    profile = tuv2.derive_risk_profile("What's the weather like?", "question")
    assert profile["risk_level"] == "low"
    assert profile["confirmation_requirement"] is False


def test_risk_profile_high_for_destructive_keyword():
    profile = tuv2.derive_risk_profile("Delete this permanently and push it publicly", "action")
    assert profile["risk_level"] == "high"
    assert profile["confirmation_requirement"] is True
