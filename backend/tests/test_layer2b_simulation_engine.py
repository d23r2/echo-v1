"""ECHO Layer 2B — simulation_engine.py: scenario generation, baseline
scenario, bounded execution, uncertainty labels, sensitivity analysis,
comparison/ranking, decision handoff. All deterministic, DB-backed via the
isolated db_session fixture."""

import inspect

from app.models import CognitiveConcept, CognitiveRelationship
from app.services import simulation_engine as se
from app.services import systems_thinking as st

# ---- Baseline scenario ----


def test_baseline_scenario_always_present(db_session):
    sim = se.run_simulation(db_session, objective="Improve reliability", max_scenarios=3, max_steps=5)
    labels = [s.label for s in sim.scenarios]
    assert "baseline" in labels


def test_baseline_scenario_is_reversible_and_high_evidence(db_session):
    sim = se.run_simulation(db_session, objective="Improve reliability", max_scenarios=1, max_steps=5)
    baseline = next(s for s in sim.scenarios if s.label == "baseline")
    assert baseline.reversibility == "reversible"
    assert baseline.evidence_quality == "high"
    assert baseline.sensitivity_label == "low"


# ---- Bounded scenario/step generation ----


def test_max_scenarios_bound_respected(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk and speed and cost", max_scenarios=2, max_steps=5)
    assert len(sim.scenarios) <= 2


def test_max_steps_bound_respected(db_session):
    model = st.create_system_model(db_session, name="Sys")
    hub = CognitiveConcept(name="Hub")
    db_session.add(hub)
    db_session.commit()
    db_session.refresh(hub)
    st.add_node(db_session, model.id, concept_id=hub.id)

    sim = se.run_simulation(db_session, objective="Fix the hub", system_model_id=model.id, max_scenarios=4, max_steps=1)
    for scenario in sim.scenarios:
        assert len(scenario.steps_json) <= 1


def test_max_scenarios_clamped_to_sane_range(db_session):
    sim = se.run_simulation(db_session, objective="Test clamping", max_scenarios=999, max_steps=999)
    assert sim.max_scenarios <= 8
    assert sim.max_steps <= 25


# ---- Scenario generation grounded in a system model ----


def test_scenario_generation_uses_bottleneck_from_system_model(db_session):
    model = st.create_system_model(db_session, name="Sys")
    hub = CognitiveConcept(name="Auth Service")
    db_session.add(hub)
    db_session.commit()
    db_session.refresh(hub)
    clients = []
    for i in range(4):
        c = CognitiveConcept(name=f"Client {i}")
        db_session.add(c)
        clients.append(c)
    db_session.commit()
    st.add_node(db_session, model.id, concept_id=hub.id)
    for c in clients:
        db_session.refresh(c)
        st.add_node(db_session, model.id, concept_id=c.id)
        db_session.add(CognitiveRelationship(from_concept_id=c.id, to_concept_id=hub.id, relation_type="depends_on"))
    db_session.commit()

    sim = se.run_simulation(db_session, objective="Reduce risk in this system", system_model_id=model.id, max_scenarios=4, max_steps=5)
    labels = [s.label for s in sim.scenarios]
    assert any("bottleneck" in label for label in labels)


def test_scenario_generation_falls_back_to_generic_without_system_model(db_session):
    sim = se.run_simulation(db_session, objective="Make things faster", max_scenarios=3, max_steps=5)
    non_baseline = [s for s in sim.scenarios if s.label != "baseline"]
    assert non_baseline
    for s in non_baseline:
        assert s.evidence_quality == "low"
        assert s.confidence_band == "wide"
        assert s.uncertainty_notes is not None


# ---- Uncertainty labels ----


def test_every_scenario_has_evidence_quality_and_confidence_band(db_session):
    sim = se.run_simulation(db_session, objective="Reduce cost", max_scenarios=3, max_steps=5)
    for s in sim.scenarios:
        assert s.evidence_quality in ("low", "medium", "high")
        assert s.confidence_band in ("narrow", "moderate", "wide")


# ---- Sensitivity analysis ----


def test_sensitivity_high_for_low_evidence_generic_scenario(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk", max_scenarios=2, max_steps=5)
    generic = next(s for s in sim.scenarios if s.label != "baseline")
    assert generic.sensitivity_label == "high"
    assert "assumption" in generic.sensitivity_note


def test_sensitivity_label_present_for_every_scenario(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk and speed", max_scenarios=4, max_steps=5)
    for s in sim.scenarios:
        assert s.sensitivity_label in ("low", "moderate", "high")
        assert s.sensitivity_note


# ---- Comparison / ranking ----


def test_compare_scenarios_ranks_fewer_risks_first():
    scenarios = [
        {
            "label": "risky", "strategy": "x", "assumptions": [], "steps": [{"step": 1, "description": "a"}],
            "predicted_outcomes": [], "dependencies": [], "costs": [], "risks": ["r1", "r2", "r3"],
            "failure_modes": [], "reversibility": "reversible", "evidence_quality": "medium",
            "confidence_band": "moderate", "uncertainty_notes": None, "steps_completed": 1, "steps_blocked": 0, "stopped_reason": None,
        },
        {
            "label": "safe", "strategy": "x", "assumptions": [], "steps": [{"step": 1, "description": "a"}],
            "predicted_outcomes": [], "dependencies": [], "costs": [], "risks": ["r1"],
            "failure_modes": [], "reversibility": "reversible", "evidence_quality": "medium",
            "confidence_band": "moderate", "uncertainty_notes": None, "steps_completed": 1, "steps_blocked": 0, "stopped_reason": None,
        },
    ]
    ranked, too_uncertain = se.compare_scenarios(scenarios)
    assert too_uncertain is False
    assert ranked[0]["label"] == "safe"
    assert ranked[0]["rank"] == 1


def test_too_uncertain_to_rank_when_all_non_baseline_low_evidence(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk", max_scenarios=2, max_steps=5)
    assert sim.too_uncertain_to_rank is True
    non_baseline = [s for s in sim.scenarios if s.label != "baseline"]
    assert all(s.rank is None for s in non_baseline)


def test_not_too_uncertain_when_system_model_grounds_a_scenario(db_session):
    model = st.create_system_model(db_session, name="Sys")
    hub = CognitiveConcept(name="Hub")
    db_session.add(hub)
    db_session.commit()
    db_session.refresh(hub)
    clients = []
    for i in range(4):
        c = CognitiveConcept(name=f"C{i}")
        db_session.add(c)
        clients.append(c)
    db_session.commit()
    st.add_node(db_session, model.id, concept_id=hub.id)
    for c in clients:
        db_session.refresh(c)
        st.add_node(db_session, model.id, concept_id=c.id)
        db_session.add(CognitiveRelationship(from_concept_id=c.id, to_concept_id=hub.id, relation_type="depends_on"))
    db_session.commit()

    sim = se.run_simulation(db_session, objective="Reduce risk", system_model_id=model.id, max_scenarios=2, max_steps=5)
    assert sim.too_uncertain_to_rank is False


# ---- Decision handoff ----


def test_decision_handoff_recommends_top_ranked_non_baseline(db_session):
    model = st.create_system_model(db_session, name="Sys")
    hub = CognitiveConcept(name="Hub")
    db_session.add(hub)
    db_session.commit()
    db_session.refresh(hub)
    clients = []
    for i in range(4):
        c = CognitiveConcept(name=f"C{i}")
        db_session.add(c)
        clients.append(c)
    db_session.commit()
    st.add_node(db_session, model.id, concept_id=hub.id)
    for c in clients:
        db_session.refresh(c)
        st.add_node(db_session, model.id, concept_id=c.id)
        db_session.add(CognitiveRelationship(from_concept_id=c.id, to_concept_id=hub.id, relation_type="depends_on"))
    db_session.commit()

    sim = se.run_simulation(db_session, objective="Reduce risk", system_model_id=model.id, max_scenarios=2, max_steps=5)
    handoff = se.build_decision_handoff(sim)
    assert handoff["recommended_scenario_id"] is not None
    assert handoff["too_uncertain_to_rank"] is False
    assert "forecast" in handoff["recommendation_summary"]


def test_decision_handoff_no_recommendation_when_too_uncertain(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk", max_scenarios=2, max_steps=5)
    handoff = se.build_decision_handoff(sim)
    assert handoff["recommended_scenario_id"] is None
    assert handoff["too_uncertain_to_rank"] is True


def test_decision_handoff_flags_missing_system_model(db_session):
    sim = se.run_simulation(db_session, objective="Reduce risk", max_scenarios=2, max_steps=5)
    handoff = se.build_decision_handoff(sim)
    assert any("No system model" in c for c in handoff["caveats"])


# ---- No side effects / no real execution ----


def test_simulation_engine_never_imports_action_system():
    """Simulated scenarios are forecasts, never real actions — this module
    must have zero coupling to action_system.py, the separate,
    permission-gated real-execution path. Checks actual import statements,
    not incidental mentions (this module's own docstring explains the
    boundary in prose)."""
    import_lines = [line.strip() for line in inspect.getsource(se).splitlines() if line.strip().startswith(("import ", "from "))]
    assert not any("action_system" in line for line in import_lines)


def test_run_simulation_status_always_completed_never_running(db_session):
    """Bounded rule-based execution is synchronous and deterministic —
    there is no real 'in progress' state to leak."""
    sim = se.run_simulation(db_session, objective="Test status", max_scenarios=1, max_steps=3)
    assert sim.status == "completed"


def test_get_and_list_simulations(db_session):
    sim = se.run_simulation(db_session, objective="Findable simulation", max_scenarios=1, max_steps=3)
    assert se.get_simulation(db_session, sim.id).id == sim.id
    all_sims = se.list_simulations(db_session)
    assert any(s.id == sim.id for s in all_sims)
