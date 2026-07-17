"""ECHO Layer 2C — Decision Engine.

Recommends; never makes an irreversible choice for the user (the milestone's
own non-negotiable rule) — analyse() produces a recommendation the user must
still explicitly select via select_option(). Every number here is either an
explicit user input (a criterion weight, an option rating) or a plain count/
average over those inputs — nothing is inferred from free text and presented
as a fabricated precision. Deterministic, no model call, matching this
codebase's established convention (cognitive_core.py, task_understanding_v2.py,
systems_thinking.py, simulation_engine.py).
"""

from sqlalchemy.orm import Session

from app import schemas
from app.models import DecisionCase, DecisionCriterion, DecisionOption, Simulation

_EVIDENCE_TO_CONFIDENCE_BAND = {"high": "narrow", "medium": "moderate", "low": "wide"}
_REVERSIBILITY_RANK = {"reversible": 0, "hard_to_reverse": 1, "irreversible": 2}
_EVIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}
_SIM_CONFIDENCE_BAND_TO_CONFIDENCE = {"narrow": "high", "moderate": "medium", "wide": "low"}


# ============================================================================
# Phase 1 — CRUD
# ============================================================================


def create_decision_case(db: Session, payload: schemas.DecisionCaseCreate) -> DecisionCase:
    case = DecisionCase(
        question=payload.question,
        objective=payload.objective,
        constraints_json=payload.constraints,
        stakeholders_json=payload.stakeholders,
        evidence_json=payload.evidence,
        assumptions_json=payload.assumptions,
        uncertainty=payload.uncertainty,
        time_horizon=payload.time_horizon,
        reversibility=payload.reversibility,
        consequence_level=payload.consequence_level,
        simulation_id=payload.simulation_id,
        task_id=payload.task_id,
        project_id=payload.project_id,
    )
    db.add(case)
    db.flush()

    for c in payload.criteria:
        db.add(
            DecisionCriterion(
                decision_case_id=case.id,
                name=c.name,
                description=c.description,
                source=c.source,
                importance=c.importance,
                hard_or_soft=c.hard_or_soft,
            )
        )

    for o in payload.options:
        db.add(
            DecisionOption(
                decision_case_id=case.id,
                label=o.label,
                description=o.description,
                benefits_json=o.benefits,
                drawbacks_json=o.drawbacks,
                direct_cost=o.direct_cost,
                opportunity_cost=o.opportunity_cost,
                time_estimate=o.time_estimate,
                dependencies_json=o.dependencies,
                risks_json=o.risks,
                failure_modes_json=o.failure_modes,
                reversibility=o.reversibility,
                evidence_quality=o.evidence_quality,
                confidence=o.confidence,
                violates_criteria_json=o.violates_criteria,
            )
        )

    if payload.simulation_id and not payload.options:
        seed_options_from_simulation(db, case, payload.simulation_id)

    db.commit()
    db.refresh(case)
    return case


def seed_options_from_simulation(db: Session, case: DecisionCase, simulation_id: str) -> list[DecisionOption]:
    """Seeds DecisionOption rows from a completed Layer 2B simulation's
    scenarios — an optional interop point, never a requirement (a
    DecisionCase works fully standalone with user-typed options)."""
    simulation = db.get(Simulation, simulation_id)
    if simulation is None:
        return []
    created = []
    for scenario in simulation.scenarios:
        option = DecisionOption(
            decision_case_id=case.id,
            label=scenario.label,
            description=scenario.strategy,
            benefits_json=scenario.predicted_outcomes_json,
            drawbacks_json=scenario.failure_modes_json,
            direct_cost=", ".join(scenario.costs_json) if scenario.costs_json else None,
            dependencies_json=scenario.dependencies_json,
            risks_json=scenario.risks_json,
            failure_modes_json=scenario.failure_modes_json,
            reversibility=scenario.reversibility,
            evidence_quality=scenario.evidence_quality,
            confidence=_SIM_CONFIDENCE_BAND_TO_CONFIDENCE.get(scenario.confidence_band, "medium"),
            source_scenario_id=scenario.id,
        )
        db.add(option)
        created.append(option)
    db.flush()
    return created


def get_decision_case(db: Session, decision_case_id: str) -> DecisionCase | None:
    return db.get(DecisionCase, decision_case_id)


def list_decision_cases(db: Session, *, project_id: str | None = None) -> list[DecisionCase]:
    q = db.query(DecisionCase)
    if project_id:
        q = q.filter(DecisionCase.project_id == project_id)
    return q.order_by(DecisionCase.created_at.desc()).all()


def set_criterion_weight(db: Session, criterion_id: str, weight: float | None) -> DecisionCriterion | None:
    """The only way a criterion gets a weight — always an explicit user
    action, never silently inferred (Phase 2's non-negotiable rule)."""
    criterion = db.get(DecisionCriterion, criterion_id)
    if criterion is None:
        return None
    criterion.weight = weight
    db.commit()
    db.refresh(criterion)
    return criterion


def set_option_ratings(db: Session, option_id: str, ratings: dict[str, float]) -> DecisionOption | None:
    option = db.get(DecisionOption, option_id)
    if option is None:
        return None
    option.criterion_ratings_json = {**option.criterion_ratings_json, **ratings}
    db.commit()
    db.refresh(option)
    return option


# ============================================================================
# Phase 2 — Decision analysis methods
# ============================================================================


def eliminate_hard_constraints(case: DecisionCase) -> None:
    """Rule-based elimination: an option is eliminated iff a hard
    criterion's name appears in that option's own violates_criteria_json —
    an explicit signal set at option-creation time, never a text-matching
    guess. Idempotent — re-running never un-eliminates an option."""
    hard_names = {c.name for c in case.criteria if c.hard_or_soft == "hard"}
    if not hard_names:
        return
    for option in case.options:
        if option.eliminated:
            continue
        violated = hard_names & set(option.violates_criteria_json)
        if violated:
            option.eliminated = True
            option.eliminated_reason = f"Violates hard constraint(s): {', '.join(sorted(violated))}."


def build_tradeoff_matrix(case: DecisionCase) -> list[dict]:
    """A plain structural listing, not a score — benefits/drawbacks/risks
    side by side for every remaining option."""
    return [
        {
            "option_id": o.id,
            "label": o.label,
            "benefits": o.benefits_json,
            "drawbacks": o.drawbacks_json,
            "risks": o.risks_json,
            "reversibility": o.reversibility,
            "evidence_quality": o.evidence_quality,
        }
        for o in case.options
        if not o.eliminated
    ]


def compute_weighted_scores(case: DecisionCase) -> bool:
    """Weighted average of explicit per-option-per-criterion ratings,
    weighted by explicit user-approved criterion weights. Returns False (and
    leaves every score as None) when no criterion has a user-approved
    weight — weighted scoring is opt-in, never silently applied."""
    weighted_criteria = [c for c in case.criteria if c.weight is not None]
    if not weighted_criteria:
        return False

    total_weight = sum(c.weight for c in weighted_criteria)
    if total_weight <= 0:
        return False

    for option in case.options:
        if option.eliminated:
            option.score = None
            continue
        rated = [(c.weight, option.criterion_ratings_json.get(c.id)) for c in weighted_criteria]
        rated = [(w, r) for w, r in rated if r is not None]
        if not rated:
            option.score = None
            continue
        rated_weight = sum(w for w, _ in rated)
        option.score = sum(w * r for w, r in rated) / rated_weight if rated_weight > 0 else None
    return True


def detect_pareto_dominated(case: DecisionCase) -> None:
    """An option is Pareto-dominated when another remaining option is at
    least as good on every structural dimension (more benefits, fewer
    risks, more reversible, higher evidence quality) and strictly better on
    at least one. Purely structural — no fabricated utility function."""
    remaining = [o for o in case.options if not o.eliminated]
    for o in remaining:
        o.pareto_dominated = False

    def dims(o: DecisionOption) -> tuple:
        return (
            len(o.benefits_json),
            -len(o.risks_json),
            -_REVERSIBILITY_RANK.get(o.reversibility, 1),
            _EVIDENCE_RANK.get(o.evidence_quality, 1),
        )

    for a in remaining:
        a_dims = dims(a)
        for b in remaining:
            if a.id == b.id:
                continue
            b_dims = dims(b)
            if all(bd >= ad for bd, ad in zip(b_dims, a_dims, strict=True)) and any(bd > ad for bd, ad in zip(b_dims, a_dims, strict=True)):
                a.pareto_dominated = True
                break


def analyse(db: Session, decision_case_id: str) -> DecisionCase | None:
    """Runs the full Phase 2 pipeline and produces the Phase 3 report.
    Never selects an option for the user — see select_option()."""
    case = db.get(DecisionCase, decision_case_id)
    if case is None:
        return None

    eliminate_hard_constraints(case)
    tradeoffs = build_tradeoff_matrix(case)
    used_weighted_scoring = compute_weighted_scores(case)
    detect_pareto_dominated(case)

    remaining = [o for o in case.options if not o.eliminated]
    non_dominated = [o for o in remaining if not o.pareto_dominated]

    recommended: DecisionOption | None = None
    no_clear_winner = False

    if not remaining:
        no_clear_winner = True
    elif len(remaining) == 1:
        recommended = remaining[0]
    elif used_weighted_scoring:
        scored = [o for o in remaining if o.score is not None]
        if scored:
            scored.sort(key=lambda o: o.score, reverse=True)
            top_score = scored[0].score
            tied = [o for o in scored if abs(o.score - top_score) < 1e-9]
            if len(tied) == 1:
                recommended = tied[0]
            else:
                no_clear_winner = True
        else:
            no_clear_winner = True
    elif len(non_dominated) == 1:
        recommended = non_dominated[0]
    else:
        no_clear_winner = True

    case.no_clear_winner = no_clear_winner
    case.recommended_option_id = recommended.id if recommended else None
    case.status = "analysed"
    case.report_json = _build_report(case, tradeoffs, recommended, remaining, used_weighted_scoring)
    db.commit()
    db.refresh(case)
    return case


def select_option(db: Session, decision_case_id: str, option_id: str) -> DecisionCase | None:
    """The user's explicit, final choice — may differ from the
    recommendation. This is the only function that marks a decision
    'selected'; analyse() only ever recommends."""
    case = db.get(DecisionCase, decision_case_id)
    if case is None:
        return None
    option = db.get(DecisionOption, option_id)
    if option is None or option.decision_case_id != case.id:
        raise ValueError("That option does not belong to this decision case.")
    case.recommended_option_id = option_id
    case.status = "selected"
    db.commit()
    db.refresh(case)
    return case


# ============================================================================
# Phase 3 — DecisionReport
# ============================================================================


def _build_report(
    case: DecisionCase, tradeoffs: list[dict], recommended: DecisionOption | None, remaining: list[DecisionOption], used_weighted_scoring: bool
) -> dict:
    hard_names = sorted({c.name for c in case.criteria if c.hard_or_soft == "hard"})
    eliminated = [o for o in case.options if o.eliminated]

    if not case.options:
        decision_summary = f"No options have been added yet for '{case.objective}'."
    elif not remaining:
        decision_summary = f"All {len(case.options)} option(s) for '{case.objective}' were eliminated by hard constraints."
    else:
        decision_summary = f"For '{case.objective}', {len(remaining)} of {len(case.options)} option(s) remain after hard-constraint elimination."

    why_this_option = None
    if recommended:
        if used_weighted_scoring and recommended.score is not None:
            why_this_option = f"'{recommended.label}' scored highest ({recommended.score:.2f}) against your weighted criteria."
        elif len(remaining) == 1:
            why_this_option = f"'{recommended.label}' is the only option remaining after hard-constraint elimination."
        else:
            why_this_option = f"'{recommended.label}' is not dominated by any other remaining option on benefits, risk, reversibility, or evidence quality."

    key_tradeoffs = []
    for t in tradeoffs:
        if t["benefits"] or t["drawbacks"]:
            key_tradeoffs.append(f"{t['label']}: {', '.join(t['benefits']) or 'no stated benefits'} vs. {', '.join(t['drawbacks']) or 'no stated drawbacks'}.")

    alternatives = [o.label for o in remaining if recommended is None or o.id != recommended.id]

    risks_and_mitigations = []
    if recommended:
        risks_and_mitigations = [f"{r} (no recorded mitigation)" for r in recommended.risks_json]

    evidence_quality = recommended.evidence_quality if recommended else "low"
    confidence_band = _EVIDENCE_TO_CONFIDENCE_BAND.get(evidence_quality, "wide") if not case.no_clear_winner else "wide"

    next_information: list[str] = []
    if case.no_clear_winner:
        if not remaining:
            next_information.append("Add an option that doesn't violate the stated hard constraints, or relax a constraint.")
        elif not used_weighted_scoring:
            next_information.append("Set user-approved weights on your criteria and rate each option to enable weighted scoring.")
        else:
            next_information.append("Ratings produced a tie — provide a tiebreaking criterion or additional evidence.")
    elif evidence_quality == "low":
        next_information.append(f"Gather stronger evidence for '{recommended.label}' before treating this as settled.")

    user_confirmation_needed = case.consequence_level in ("high", "critical") or case.reversibility in ("hard_to_reverse", "irreversible")

    return {
        "decision_summary": decision_summary,
        "recommended_option_label": recommended.label if recommended else None,
        "no_clear_winner": case.no_clear_winner,
        "why_this_option": why_this_option,
        "key_tradeoffs": key_tradeoffs,
        "hard_constraints_checked": hard_names,
        "major_assumptions": case.assumptions_json,
        "major_uncertainties": ([case.uncertainty] if case.uncertainty else []) + [f"'{o.label}' eliminated: {o.eliminated_reason}" for o in eliminated],
        "risks_and_mitigations": risks_and_mitigations,
        "alternatives": alternatives,
        "reversibility": recommended.reversibility if recommended else case.reversibility,
        "evidence_quality": evidence_quality,
        "confidence_band": confidence_band,
        "next_information_to_collect": next_information,
        "user_confirmation_needed": user_confirmation_needed,
    }
