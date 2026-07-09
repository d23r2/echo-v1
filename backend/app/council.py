"""Guardian Council: simulated governance for constitutional amendments.

Single-user app -> there are no real separate accounts for Founder / Guardian
A-C / Verifier. The frontend RoleSwitcher lets the one user act "as" any of
these roles, clearly labeled as simulated. This module still enforces the
*process* for real: a proposal must clear the Value Invariant guard before it
can even be voted on, and ratification requires real quorum math over
whatever votes have actually been cast.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import constitution, models

GUARDIAN_ROLES = ("guardian_a", "guardian_b", "guardian_c")
ALL_ROLES = ("founder",) + GUARDIAN_ROLES + ("verifier",)
GUARDIAN_APPROVALS_REQUIRED = 2


class InvariantGuardError(Exception):
    def __init__(self, invariant_ids: list[str]):
        self.invariant_ids = invariant_ids
        names = ", ".join(invariant_ids)
        super().__init__(
            f"Proposed text appears to weaken protected Value Invariant(s): {names}. "
            "Value Invariants cannot be amended and this proposal was blocked before voting."
        )


def guard_amendment_text(text: str) -> None:
    hits = constitution.guarded_invariant_hits(text)
    if hits:
        raise InvariantGuardError(hits)


def tally(amendment: models.Amendment) -> dict:
    guardian_votes = {v.role: v.decision for v in amendment.votes if v.role in GUARDIAN_ROLES}
    verifier_vote = next((v.decision for v in amendment.votes if v.role == "verifier"), None)

    approvals = sum(1 for d in guardian_votes.values() if d == "approve")
    rejections = sum(1 for d in guardian_votes.values() if d == "reject")

    guardian_quorum_met = approvals >= GUARDIAN_APPROVALS_REQUIRED
    guardian_blocked = rejections > (len(GUARDIAN_ROLES) - GUARDIAN_APPROVALS_REQUIRED)

    return {
        "guardian_approvals": approvals,
        "guardian_rejections": rejections,
        "guardian_quorum_met": guardian_quorum_met,
        "guardian_blocked": guardian_blocked,
        "verifier_decision": verifier_vote,
        "ready_to_ratify": guardian_quorum_met and verifier_vote == "approve",
        "ready_to_reject": guardian_blocked or verifier_vote == "reject",
    }


def recompute_status(db: Session, amendment: models.Amendment) -> models.Amendment:
    if amendment.status != "proposed":
        return amendment
    t = tally(amendment)
    if t["ready_to_ratify"]:
        amendment.status = "ratified"
        amendment.decided_at = datetime.now(timezone.utc)
    elif t["ready_to_reject"]:
        amendment.status = "rejected"
        amendment.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(amendment)
    return amendment


def cast_vote(db: Session, amendment: models.Amendment, role: str, decision: str, comment: str | None) -> models.Amendment:
    if amendment.status != "proposed":
        raise ValueError(f"Amendment is already '{amendment.status}'; voting is closed.")
    if role == "founder":
        raise ValueError("The Founder proposes amendments but does not vote on them.")

    existing = next((v for v in amendment.votes if v.role == role), None)
    if existing:
        existing.decision = decision
        existing.comment = comment
    else:
        db.add(models.Vote(amendment_id=amendment.id, role=role, decision=decision, comment=comment))
    db.commit()
    db.refresh(amendment)
    return recompute_status(db, amendment)


def build_constitution_view(db: Session) -> dict:
    ratified = (
        db.query(models.Amendment)
        .filter(models.Amendment.status == "ratified")
        .order_by(models.Amendment.decided_at)
        .all()
    )

    version = f"{constitution.BASE_VERSION_MAJOR}.{len(ratified)}"

    full_text = constitution.base_full_text()
    if ratified:
        full_text += "\n\nRATIFIED AMENDMENTS\n"
        for a in ratified:
            full_text += f"- [{a.id}] {a.title}: {a.text}\n"

    return {
        "version": version,
        "codename": constitution.CODENAME,
        "philosophy": constitution.PHILOSOPHY,
        "core_values": [
            {"rank": v.rank, "name": v.name, "description": v.description} for v in constitution.CORE_VALUES
        ],
        "value_invariants": [{"id": i.id, "text": i.text} for i in constitution.VALUE_INVARIANTS],
        "edge_case_protocols": [
            {"id": p.id, "scenario": p.scenario, "resolution": p.resolution}
            for p in constitution.EDGE_CASE_PROTOCOLS
        ],
        "amendment_log": [
            {"id": a.id, "title": a.title, "text": a.text, "ratified_at": a.decided_at} for a in ratified
        ],
        "full_text": full_text,
    }
