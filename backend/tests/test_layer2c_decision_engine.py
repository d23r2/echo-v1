"""ECHO Layer 2C — decision_engine.py: hard-constraint elimination, weighted
scoring, Pareto detection, no-clear-winner outcomes, DecisionReport
generation. Deterministic, DB-backed via the isolated db_session fixture."""

import pytest

from app import schemas
from app.services import decision_engine as de


def _case(db_session, **kw):
    payload = schemas.DecisionCaseCreate(question=kw.pop("question", "q"), objective=kw.pop("objective", "o"), **kw)
    return de.create_decision_case(db_session, payload)


# ---- Hard-constraint elimination ----


def test_hard_constraint_eliminates_violating_option(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="local-only", hard_or_soft="hard")],
        options=[
            schemas.DecisionOptionCreate(label="Cloud", violates_criteria=["local-only"]),
            schemas.DecisionOptionCreate(label="Local"),
        ],
    )
    de.eliminate_hard_constraints(case)
    cloud = next(o for o in case.options if o.label == "Cloud")
    local = next(o for o in case.options if o.label == "Local")
    assert cloud.eliminated is True
    assert "local-only" in cloud.eliminated_reason
    assert local.eliminated is False


def test_soft_criterion_never_eliminates(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="cost", hard_or_soft="soft")],
        options=[schemas.DecisionOptionCreate(label="A", violates_criteria=["cost"])],
    )
    de.eliminate_hard_constraints(case)
    assert case.options[0].eliminated is False


def test_hard_constraint_elimination_idempotent(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[schemas.DecisionOptionCreate(label="A", violates_criteria=["x"])],
    )
    de.eliminate_hard_constraints(case)
    reason_after_first = case.options[0].eliminated_reason
    de.eliminate_hard_constraints(case)
    assert case.options[0].eliminated_reason == reason_after_first


# ---- Weighted scoring ----


def test_weighted_scoring_not_used_without_weights(db_session):
    case = _case(db_session, options=[schemas.DecisionOptionCreate(label="A"), schemas.DecisionOptionCreate(label="B")])
    used = de.compute_weighted_scores(case)
    assert used is False
    assert all(o.score is None for o in case.options)


def test_weighted_scoring_changes_only_when_weights_change(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="speed"), schemas.DecisionCriterionCreate(name="quality")],
        options=[schemas.DecisionOptionCreate(label="A"), schemas.DecisionOptionCreate(label="B")],
    )
    crit_speed, crit_quality = case.criteria[0], case.criteria[1]
    opt_a, opt_b = case.options[0], case.options[1]

    # No weights yet — scoring is not applied.
    assert de.compute_weighted_scores(case) is False

    de.set_criterion_weight(db_session, crit_speed.id, 0.6)
    de.set_criterion_weight(db_session, crit_quality.id, 0.4)
    de.set_option_ratings(db_session, opt_a.id, {crit_speed.id: 0.9, crit_quality.id: 0.5})
    de.set_option_ratings(db_session, opt_b.id, {crit_speed.id: 0.2, crit_quality.id: 0.9})
    db_session.refresh(case)
    assert de.compute_weighted_scores(case) is True
    score_a_before = case.options[0].score
    assert score_a_before is not None

    # Re-running analysis with the SAME weights produces the SAME score.
    assert de.compute_weighted_scores(case) is True
    assert case.options[0].score == score_a_before

    # Changing a weight changes the score.
    de.set_criterion_weight(db_session, crit_speed.id, 0.1)
    db_session.refresh(case)
    de.compute_weighted_scores(case)
    assert case.options[0].score != score_a_before


def test_weighted_score_ignores_eliminated_options(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[schemas.DecisionOptionCreate(label="A", violates_criteria=["x"])],
    )
    de.set_criterion_weight(db_session, case.criteria[0].id, 1.0)
    db_session.refresh(case)
    de.eliminate_hard_constraints(case)
    de.compute_weighted_scores(case)
    assert case.options[0].score is None


# ---- Pareto detection ----


def test_pareto_dominated_option_flagged(db_session):
    case = _case(
        db_session,
        options=[
            schemas.DecisionOptionCreate(label="Strictly better", benefits=["b1", "b2"], risks=[]),
            schemas.DecisionOptionCreate(label="Strictly worse", benefits=["b1"], risks=["r1"]),
        ],
    )
    de.detect_pareto_dominated(case)
    better = next(o for o in case.options if o.label == "Strictly better")
    worse = next(o for o in case.options if o.label == "Strictly worse")
    assert better.pareto_dominated is False
    assert worse.pareto_dominated is True


# ---- No-clear-winner outcomes ----


def test_no_clear_winner_when_all_eliminated(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[schemas.DecisionOptionCreate(label="A", violates_criteria=["x"])],
    )
    result = de.analyse(db_session, case.id)
    assert result.no_clear_winner is True
    assert result.recommended_option_id is None


def test_no_clear_winner_when_multiple_non_dominated_and_no_weights(db_session):
    case = _case(
        db_session,
        options=[
            schemas.DecisionOptionCreate(label="A", benefits=["b1"], risks=["r1"]),
            schemas.DecisionOptionCreate(label="B", benefits=["b1", "b2"], risks=["r1", "r2"]),
        ],
    )
    result = de.analyse(db_session, case.id)
    assert result.no_clear_winner is True


def test_single_remaining_option_is_recommended(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[
            schemas.DecisionOptionCreate(label="Eliminated", violates_criteria=["x"]),
            schemas.DecisionOptionCreate(label="Survivor"),
        ],
    )
    result = de.analyse(db_session, case.id)
    assert result.no_clear_winner is False
    assert result.report_json["recommended_option_label"] == "Survivor"


def test_tied_weighted_scores_produce_no_clear_winner(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="speed")],
        options=[schemas.DecisionOptionCreate(label="A"), schemas.DecisionOptionCreate(label="B")],
    )
    crit = case.criteria[0]
    de.set_criterion_weight(db_session, crit.id, 1.0)
    de.set_option_ratings(db_session, case.options[0].id, {crit.id: 0.7})
    de.set_option_ratings(db_session, case.options[1].id, {crit.id: 0.7})
    db_session.refresh(case)
    result = de.analyse(db_session, case.id)
    assert result.no_clear_winner is True


# ---- Low evidence reduces confidence ----


def test_low_evidence_option_yields_wide_confidence_band(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[
            schemas.DecisionOptionCreate(label="Eliminated", violates_criteria=["x"]),
            schemas.DecisionOptionCreate(label="Only one", evidence_quality="low"),
        ],
    )
    result = de.analyse(db_session, case.id)
    assert result.report_json["evidence_quality"] == "low"
    assert result.report_json["confidence_band"] == "wide"


def test_high_evidence_option_yields_narrow_confidence_band(db_session):
    case = _case(
        db_session,
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[
            schemas.DecisionOptionCreate(label="Eliminated", violates_criteria=["x"]),
            schemas.DecisionOptionCreate(label="Only one", evidence_quality="high"),
        ],
    )
    result = de.analyse(db_session, case.id)
    assert result.report_json["confidence_band"] == "narrow"


# ---- Recommendation includes alternatives and uncertainty ----


def test_report_includes_alternatives_and_uncertainty(db_session):
    case = _case(
        db_session,
        uncertainty="We don't know real-world load yet.",
        criteria=[schemas.DecisionCriterionCreate(name="x", hard_or_soft="hard")],
        options=[
            schemas.DecisionOptionCreate(label="Eliminated", violates_criteria=["x"]),
            schemas.DecisionOptionCreate(label="Kept A"),
        ],
    )
    result = de.analyse(db_session, case.id)
    report = result.report_json
    assert "We don't know real-world load yet." in report["major_uncertainties"]
    assert any("Eliminated" in u for u in report["major_uncertainties"])
    # alternatives excludes the recommended option itself
    assert report["recommended_option_label"] not in report["alternatives"]


def test_report_never_fabricates_recommendation_when_no_options(db_session):
    case = _case(db_session)
    result = de.analyse(db_session, case.id)
    assert result.no_clear_winner is True
    assert result.report_json["recommended_option_label"] is None


# ---- select_option ----


def test_select_option_marks_case_selected(db_session):
    case = _case(db_session, options=[schemas.DecisionOptionCreate(label="A")])
    updated = de.select_option(db_session, case.id, case.options[0].id)
    assert updated.status == "selected"
    assert updated.recommended_option_id == case.options[0].id


def test_select_option_rejects_option_from_other_case(db_session):
    case1 = _case(db_session, options=[schemas.DecisionOptionCreate(label="A")])
    case2 = _case(db_session, options=[schemas.DecisionOptionCreate(label="B")])
    with pytest.raises(ValueError):
        de.select_option(db_session, case1.id, case2.options[0].id)


# ---- Seeding options from a Layer 2B simulation ----


def test_seed_options_from_simulation(db_session):
    from app.services import simulation_engine as se

    sim = se.run_simulation(db_session, objective="Reduce risk", max_scenarios=2, max_steps=3)
    case = _case(db_session, simulation_id=sim.id)
    created = de.seed_options_from_simulation(db_session, case, sim.id)
    assert len(created) == len(sim.scenarios)
    assert {o.source_scenario_id for o in created} == {s.id for s in sim.scenarios}
