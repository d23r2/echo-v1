"""Tests for app.council: Guardian Council amendment voting and ratification.

These call council.py's functions directly against an isolated SQLite database
(see conftest.py's db_session fixture) rather than through HTTP — this is
vote-tallying/state-transition logic, not endpoint behavior, and the app
architecture already separates the two (routers/amendments.py is a thin
wrapper around these same functions).
"""

import pytest

from app import council
from app.models import Amendment


def _make_amendment(db_session, title="Test amendment", text="Echo should say hello more often."):
    amendment = Amendment(title=title, text=text, proposed_by="founder")
    db_session.add(amendment)
    db_session.commit()
    db_session.refresh(amendment)
    return amendment


# 1. Founder can propose but cannot vote.
def test_founder_can_propose_but_cannot_vote(db_session):
    amendment = _make_amendment(db_session)
    assert amendment.status == "proposed"

    with pytest.raises(ValueError, match="does not vote"):
        council.cast_vote(db_session, amendment, "founder", "approve", None)


# 2. Guardian A/B/C can vote.
@pytest.mark.parametrize("role", council.GUARDIAN_ROLES)
def test_guardians_can_vote(db_session, role):
    amendment = _make_amendment(db_session, title=f"Amendment for {role}")
    updated = council.cast_vote(db_session, amendment, role, "approve", None)
    assert any(v.role == role and v.decision == "approve" for v in updated.votes)


# 3. Verifier can vote.
def test_verifier_can_vote(db_session):
    amendment = _make_amendment(db_session)
    updated = council.cast_vote(db_session, amendment, "verifier", "approve", None)
    assert any(v.role == "verifier" and v.decision == "approve" for v in updated.votes)


# 4. 2 Guardian approvals + Verifier approval = ratified.
def test_two_guardian_approvals_plus_verifier_approval_ratifies(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_b", "approve", None)
    updated = council.cast_vote(db_session, amendment, "verifier", "approve", None)

    assert updated.status == "ratified"
    assert updated.decided_at is not None


# 5. 3 Guardian approvals + Verifier approval = ratified.
def test_three_guardian_approvals_plus_verifier_approval_ratifies(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_b", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_c", "approve", None)
    updated = council.cast_vote(db_session, amendment, "verifier", "approve", None)

    assert updated.status == "ratified"


# 6. 2 Guardian approvals + Verifier rejection = rejected.
def test_two_guardian_approvals_plus_verifier_rejection_is_rejected(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_b", "approve", None)
    updated = council.cast_vote(db_session, amendment, "verifier", "reject", None)

    assert updated.status == "rejected"


# 7. 2 Guardian rejections = rejected (blocked before the Verifier even needs to weigh in).
def test_two_guardian_rejections_is_rejected(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "reject", None)
    updated = council.cast_vote(db_session, amendment, "guardian_b", "reject", None)

    assert updated.status == "rejected"


# 8. 1 approval + 1 rejection + 1 pending = still proposed.
def test_split_vote_with_one_guardian_still_pending_stays_proposed(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    updated = council.cast_vote(db_session, amendment, "guardian_b", "reject", None)
    # guardian_c hasn't voted: 1 approve / 1 reject is neither quorum nor a block.

    assert updated.status == "proposed"


# 9. Duplicate vote from the same role is handled correctly (overwrite, not duplicate).
def test_duplicate_vote_from_same_role_overwrites_not_duplicates(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "reject", "first thought")
    updated = council.cast_vote(db_session, amendment, "guardian_a", "approve", "changed my mind")

    guardian_a_votes = [v for v in updated.votes if v.role == "guardian_a"]
    assert len(guardian_a_votes) == 1
    assert guardian_a_votes[0].decision == "approve"
    assert guardian_a_votes[0].comment == "changed my mind"


# 10. Ratified amendment updates the constitution version and ratified amendment list.
def test_ratified_amendment_appears_in_constitution_view_and_bumps_version(db_session):
    amendment = _make_amendment(db_session, title="Add a weekly check-in")
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_b", "approve", None)
    council.cast_vote(db_session, amendment, "verifier", "approve", None)

    view = council.build_constitution_view(db_session)

    assert view["version"] == "1.1"
    assert any(a["id"] == amendment.id for a in view["amendment_log"])


# 11. Rejected amendment does not get appended to the constitution.
def test_rejected_amendment_is_not_in_constitution_view(db_session):
    amendment = _make_amendment(db_session, title="A bad idea")
    council.cast_vote(db_session, amendment, "guardian_a", "reject", None)
    council.cast_vote(db_session, amendment, "guardian_b", "reject", None)

    view = council.build_constitution_view(db_session)

    assert view["version"] == "1.0"
    assert not any(a["id"] == amendment.id for a in view["amendment_log"])


# Extra: voting is closed once an amendment has already been decided.
def test_voting_is_closed_after_ratification(db_session):
    amendment = _make_amendment(db_session)
    council.cast_vote(db_session, amendment, "guardian_a", "approve", None)
    council.cast_vote(db_session, amendment, "guardian_b", "approve", None)
    council.cast_vote(db_session, amendment, "verifier", "approve", None)
    assert amendment.status == "ratified"

    with pytest.raises(ValueError, match="already"):
        council.cast_vote(db_session, amendment, "guardian_c", "approve", None)
