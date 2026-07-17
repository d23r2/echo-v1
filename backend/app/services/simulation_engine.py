"""ECHO Layer 2B — Simulation Engine.

Bounded, deterministic, rule-based "what if" exploration. Every output here
is a forecast or an estimate, never a fact — nothing in this module invents
a numerical probability and presents it as calibrated certainty; ranking
uses an explicit, inspectable tie-break chain instead of a fabricated
composite score. Simulated steps are text descriptions only: nothing here
ever calls action_system.py or any other real-execution path — the separate,
permission-gated Action System is the only place real actions happen.

Bounded by construction: max_scenarios caps branch count, max_steps caps
per-scenario depth. This app has no wall-clock/dollar cost data attached to
CognitiveConcept/CausalNote, so there is no real "cost" to bound beyond
scenario/step counts — documented honestly rather than fabricating a cost
model.
"""

from sqlalchemy.orm import Session

from app.models import CognitiveConcept, Simulation, SimulationScenario
from app.services import systems_thinking as st

_REVERSIBILITY_RANK = {"reversible": 0, "hard_to_reverse": 1, "irreversible": 2}
_EVIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

_SPEED_RE_WORDS = ("faster", "speed", "quick", "accelerate", "sooner")
_COST_RE_WORDS = ("cost", "cheaper", "budget", "spend")
_RISK_RE_WORDS = ("risk", "safe", "safer", "secure", "avoid")


def _baseline_scenario(objective: str, baseline_state: str | None) -> dict:
    return {
        "label": "baseline",
        "strategy": "Take no action; the current state persists unchanged.",
        "assumptions": [],
        "steps": [{"step": 1, "description": baseline_state or f"Current state with respect to '{objective}' continues as-is."}],
        "predicted_outcomes": ["No change from the current state."],
        "dependencies": [],
        "costs": ["None — no action taken."],
        "risks": ["Whatever risk already exists in the current state continues unmitigated."],
        "failure_modes": [],
        "reversibility": "reversible",
        "evidence_quality": "high",
        "confidence_band": "narrow",
        "uncertainty_notes": None,
        "steps_completed": 1,
        "steps_blocked": 0,
        "stopped_reason": None,
    }


def _bottleneck_scenario(bottleneck: dict, max_steps: int) -> dict:
    name = bottleneck["concept_name"]
    steps = [
        {"step": 1, "description": f"Reduce direct load/coupling on '{name}' (currently in={bottleneck['in_degree']}, out={bottleneck['out_degree']})."},
        {"step": 2, "description": f"Re-verify dependents of '{name}' still function after the change."},
    ]
    steps = steps[:max_steps]
    return {
        "label": f"address_bottleneck_{name}",
        "strategy": f"Reduce '{name}''s structural load — {bottleneck['reason']}.",
        "assumptions": [f"'{name}' can be decoupled from at least one dependent without breaking it."],
        "steps": steps,
        "predicted_outcomes": [f"Failure/delay in '{name}' would ripple to fewer dependents than today."],
        "dependencies": [name],
        "costs": ["Engineering/planning time to decouple or add redundancy."],
        "risks": [f"Decoupling '{name}' incorrectly could break a dependent that wasn't fully accounted for."],
        "failure_modes": ["Dependents not identified in the current world-model graph are missed."],
        "reversibility": "hard_to_reverse",
        "evidence_quality": "medium",
        "confidence_band": "moderate",
        "uncertainty_notes": "Grounded in the existing dependency graph, not in real load/traffic data.",
        "steps_completed": len(steps),
        "steps_blocked": 0,
        "stopped_reason": None,
    }


def _cycle_scenario(cycle_names: list[str], max_steps: int) -> dict:
    chain = " -> ".join([*cycle_names, cycle_names[0]])
    steps = [{"step": 1, "description": f"Break one edge in the dependency cycle: {chain}."}][:max_steps]
    return {
        "label": f"break_cycle_{cycle_names[0]}",
        "strategy": f"Remove or redirect one dependency in the cycle {chain} to eliminate the circularity.",
        "assumptions": ["At least one edge in the cycle is not strictly required."],
        "steps": steps,
        "predicted_outcomes": ["The cycle no longer exists; dependency order becomes well-defined."],
        "dependencies": cycle_names,
        "costs": ["Redesign time for whichever component's dependency is redirected."],
        "risks": ["The 'broken' edge turns out to be load-bearing and something regresses."],
        "failure_modes": ["No edge in the cycle can safely be removed without a larger redesign."],
        "reversibility": "hard_to_reverse",
        "evidence_quality": "medium",
        "confidence_band": "moderate",
        "uncertainty_notes": "Cycle is structural (graph-derived); which edge is safest to break is not verified here.",
        "steps_completed": len(steps),
        "steps_blocked": 0 if steps else 1,
        "stopped_reason": None if steps else "max_steps_reached_before_any_step",
    }


def _critical_path_scenario(critical_path: dict, max_steps: int) -> dict:
    names = critical_path["node_names"]
    steps = [{"step": 1, "description": f"Parallelize or shorten the dependency chain: {' -> '.join(names)}."}][:max_steps]
    return {
        "label": "shorten_critical_path",
        "strategy": f"Shorten or parallelize the longest dependency chain ({critical_path['length']} steps: {' -> '.join(names)}).",
        "assumptions": ["At least one link in the chain can run in parallel with another, or be removed."],
        "steps": steps,
        "predicted_outcomes": ["Overall completion no longer depends on the full length of this chain."],
        "dependencies": names,
        "costs": ["Coordination overhead to parallelize previously-sequential work."],
        "risks": ["Two 'parallelized' steps turn out to have an undocumented dependency after all."],
        "failure_modes": ["The chain is fully sequential by necessity and cannot be shortened."],
        "reversibility": "reversible",
        "evidence_quality": "medium",
        "confidence_band": "moderate",
        "uncertainty_notes": "Chain length is graph-derived; real-world parallelizability is not verified here.",
        "steps_completed": len(steps),
        "steps_blocked": 0,
        "stopped_reason": None,
    }


def _generic_scenario(label: str, objective: str, description: str, max_steps: int) -> dict:
    steps = [{"step": 1, "description": description}][:max_steps]
    return {
        "label": label,
        "strategy": description,
        "assumptions": [f"'{objective}' can be meaningfully addressed without a system model to ground it."],
        "steps": steps,
        "predicted_outcomes": ["Directionally plausible, but not grounded in structured dependency data."],
        "dependencies": [],
        "costs": ["Unknown — no structured cost data available."],
        "risks": ["No dependency graph to check for unintended side effects."],
        "failure_modes": ["The generic strategy doesn't fit the specific, ungrounded situation."],
        "reversibility": "reversible",
        "evidence_quality": "low",
        "confidence_band": "wide",
        "uncertainty_notes": "No system model was attached to this simulation — this scenario is a generic, keyword-derived guess, not evidence-grounded.",
        "steps_completed": len(steps),
        "steps_blocked": 0,
        "stopped_reason": None,
    }


def generate_scenarios(
    db: Session,
    *,
    objective: str,
    system_model_id: str | None,
    baseline_state: str | None,
    max_scenarios: int,
    max_steps: int,
) -> list[dict]:
    """Deterministic scenario generation, bounded to max_scenarios (baseline
    always included first). Uses systems_thinking's graph analysis when a
    system_model_id is given; falls back to keyword-derived generic
    scenarios otherwise — always honestly labelled low evidence_quality."""
    scenarios = [_baseline_scenario(objective, baseline_state)]
    remaining = max(max_scenarios - 1, 0)
    if remaining == 0:
        return scenarios

    if system_model_id:
        analysis = st.build_system_analysis(db, system_model_id)
        if analysis:
            for bottleneck in analysis["bottlenecks"]:
                if len(scenarios) - 1 >= remaining:
                    break
                scenarios.append(_bottleneck_scenario(bottleneck, max_steps))

            if len(scenarios) - 1 < remaining and analysis["cycles"]:
                concept_ids = analysis["cycles"][0]
                concepts = db.query(CognitiveConcept).filter(CognitiveConcept.id.in_(concept_ids)).all()
                names_by_id = {c.id: c.name for c in concepts}
                cycle_names = [names_by_id.get(cid, cid) for cid in concept_ids]
                scenarios.append(_cycle_scenario(cycle_names, max_steps))

            if len(scenarios) - 1 < remaining and analysis["critical_path"]:
                scenarios.append(_critical_path_scenario(analysis["critical_path"], max_steps))

    if len(scenarios) - 1 < remaining:
        objective_lower = objective.lower()
        fallback_candidates = []
        if any(w in objective_lower for w in _SPEED_RE_WORDS):
            fallback_candidates.append(("increase_speed", f"Identify and remove the single slowest step toward '{objective}'."))
        if any(w in objective_lower for w in _COST_RE_WORDS):
            fallback_candidates.append(("reduce_cost", f"Identify and cut the highest-cost element of '{objective}'."))
        if any(w in objective_lower for w in _RISK_RE_WORDS):
            fallback_candidates.append(("reduce_risk", f"Identify and mitigate the highest-risk element of '{objective}'."))
        if not fallback_candidates:
            fallback_candidates.append(("direct_approach", f"Take the most direct available action toward '{objective}'."))

        for label, description in fallback_candidates:
            if len(scenarios) - 1 >= remaining:
                break
            scenarios.append(_generic_scenario(label, objective, description, max_steps))

    return scenarios[: max_scenarios if max_scenarios > 0 else len(scenarios)]


def _assess_sensitivity(scenario: dict) -> tuple[str, str]:
    """How much this scenario's forecast rests on unverified assumptions
    rather than graph-derived evidence — a distinct question from
    evidence_quality/confidence_band (which describe the forecast itself).
    Deterministic, based on assumption count and evidence quality, never a
    fabricated probability."""
    n_assumptions = len(scenario["assumptions"])
    if scenario["label"] == "baseline":
        return "low", "Baseline makes no assumptions beyond the current state persisting."
    if scenario["evidence_quality"] == "low" or n_assumptions >= 2:
        return (
            "high",
            f"Rests on {n_assumptions} unverified assumption(s) with {scenario['evidence_quality']} evidence — small changes to those assumptions could invalidate this forecast.",
        )
    if n_assumptions == 1:
        return "moderate", "Rests on a single stated assumption — verifying it would meaningfully firm up this forecast."
    return "low", "Grounded in graph-derived evidence rather than a stated assumption."


def compare_scenarios(scenarios: list[dict]) -> tuple[list[dict], bool]:
    """Ranks by an explicit tie-break chain — never a fabricated composite
    score: fewer risks, better reversibility, fewer blocked steps, higher
    evidence quality, then fewer steps (simpler plan wins ties). Flags
    too_uncertain_to_rank when every non-baseline scenario is low-evidence/
    wide-confidence-band, since ranking those against each other would
    imply a confidence the data doesn't support."""
    non_baseline = [s for s in scenarios if s["label"] != "baseline"]
    too_uncertain = bool(non_baseline) and all(s["evidence_quality"] == "low" and s["confidence_band"] == "wide" for s in non_baseline)

    def sort_key(s: dict) -> tuple:
        return (
            len(s["risks"]),
            _REVERSIBILITY_RANK.get(s["reversibility"], 1),
            s["steps_blocked"],
            _EVIDENCE_RANK.get(s["evidence_quality"], 1),
            len(s["steps"]),
        )

    ranked = sorted(scenarios, key=sort_key)
    for i, s in enumerate(ranked):
        s["rank"] = i + 1
    return ranked, too_uncertain


def run_simulation(
    db: Session,
    *,
    objective: str,
    task_id: str | None = None,
    system_model_id: str | None = None,
    baseline_state: str | None = None,
    constraints: list[str] | None = None,
    assumptions: list[str] | None = None,
    max_scenarios: int = 4,
    max_steps: int = 12,
    time_horizon: str | None = None,
    evaluation_criteria: list[str] | None = None,
    risk_tolerance: str = "medium",
) -> Simulation:
    max_scenarios = max(1, min(max_scenarios, 8))
    max_steps = max(1, min(max_steps, 25))

    scenario_dicts = generate_scenarios(
        db, objective=objective, system_model_id=system_model_id, baseline_state=baseline_state, max_scenarios=max_scenarios, max_steps=max_steps
    )
    ranked, too_uncertain = compare_scenarios(scenario_dicts)

    simulation = Simulation(
        task_id=task_id,
        system_model_id=system_model_id,
        objective=objective,
        baseline_state=baseline_state,
        constraints_json=constraints or [],
        assumptions_json=assumptions or [],
        max_scenarios=max_scenarios,
        max_steps=max_steps,
        time_horizon=time_horizon,
        evaluation_criteria_json=evaluation_criteria or [],
        risk_tolerance=risk_tolerance,
        status="completed",
        too_uncertain_to_rank=too_uncertain,
    )
    db.add(simulation)
    db.flush()

    for s in ranked:
        sensitivity_label, sensitivity_note = _assess_sensitivity(s)
        db.add(
            SimulationScenario(
                simulation_id=simulation.id,
                label=s["label"],
                strategy=s["strategy"],
                assumptions_json=s["assumptions"],
                steps_json=s["steps"],
                predicted_outcomes_json=s["predicted_outcomes"],
                dependencies_json=s["dependencies"],
                costs_json=s["costs"],
                risks_json=s["risks"],
                failure_modes_json=s["failure_modes"],
                reversibility=s["reversibility"],
                evidence_quality=s["evidence_quality"],
                confidence_band=s["confidence_band"],
                uncertainty_notes=s["uncertainty_notes"],
                sensitivity_label=sensitivity_label,
                sensitivity_note=sensitivity_note,
                steps_completed=s["steps_completed"],
                steps_blocked=s["steps_blocked"],
                stopped_reason=s["stopped_reason"],
                rank=None if too_uncertain else s["rank"],
            )
        )
    db.commit()
    db.refresh(simulation)
    return simulation


def get_simulation(db: Session, simulation_id: str) -> Simulation | None:
    return db.get(Simulation, simulation_id)


def list_simulations(db: Session, *, task_id: str | None = None, system_model_id: str | None = None) -> list[Simulation]:
    q = db.query(Simulation)
    if task_id:
        q = q.filter(Simulation.task_id == task_id)
    if system_model_id:
        q = q.filter(Simulation.system_model_id == system_model_id)
    return q.order_by(Simulation.created_at.desc()).all()


def build_decision_handoff(simulation: Simulation) -> dict:
    """Never executes anything — a plain summary object for a downstream
    decision/planning step (Layer 2C) to consume. Real execution always
    stays behind the separate, permission-gated Action System."""
    scenarios = sorted(simulation.scenarios, key=lambda s: (s.rank is None, s.rank if s.rank is not None else 0))
    caveats = []
    if simulation.system_model_id is None:
        caveats.append("No system model was attached — scenarios are generic and not grounded in dependency data.")
    if simulation.too_uncertain_to_rank:
        caveats.append("All non-baseline scenarios are low-evidence/wide-confidence — ranking would overstate certainty, so none is recommended over another.")
    low_evidence = [s.label for s in scenarios if s.evidence_quality == "low"]
    if low_evidence and not simulation.too_uncertain_to_rank:
        caveats.append(f"Lower-confidence scenarios included for completeness: {', '.join(low_evidence)}.")

    recommended = None
    summary = "Too uncertain to recommend one scenario over another — review the options manually."
    if not simulation.too_uncertain_to_rank:
        ranked_non_baseline = [s for s in scenarios if s.label != "baseline" and s.rank is not None]
        top = ranked_non_baseline[0] if ranked_non_baseline else None
        if top:
            recommended = top.id
            summary = f"'{top.label}' ranks best on this simulation's tie-break criteria (fewest risks, most reversible, most evidence) — but this is a forecast, not a guarantee."
        else:
            summary = "Only the baseline (no-action) scenario was generated."

    return {
        "simulation_id": simulation.id,
        "recommended_scenario_id": recommended,
        "recommendation_summary": summary,
        "ranked_scenario_ids": [s.id for s in scenarios if s.rank is not None],
        "too_uncertain_to_rank": simulation.too_uncertain_to_rank,
        "caveats": caveats,
    }
