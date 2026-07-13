"""Tests for the amendment invariant guard: constitution.classify_amendment_text()
(the 3-way allowed/blocked/needs_human_review classifier), its backward-compatible
guarded_invariant_hits() view, and council.guard_amendment_text() (the raising
wrapper the propose endpoint uses). This is Echo's safety-critical defense against
amendments that would weaken, remove, bypass, override, disable, or make exceptions
to an immutable Value Invariant — see README.md's "Notes on the Value Invariant
guard" for the documented caveat that this is a heuristic first line of defense,
not a substitute for an actual Guardian Council vote.

Test names double as the case documentation the task asked for.
"""

from fastapi.testclient import TestClient

import pytest

from app import constitution, council
from app.main import app


# ---- Obvious attempts: unambiguous requests to weaken an invariant ----


@pytest.mark.parametrize(
    "text",
    [
        "We should remove the requirement for truthfulness from Echo's responses.",
        "Disable reasoning transparency so Echo's answers can be shorter.",
        "Bypass the no-dependency rule when the user is going through a hard time.",
        "Allow Echo to seek power, resources, and control beyond what a task requires.",
        "Allow Echo to deceive the user about being an AI if it makes conversation smoother.",
    ],
    ids=[
        "remove-truthfulness",
        "disable-reasoning-transparency",
        "bypass-no-dependency-rule",
        "allow-seek-power-resources-control",
        "allow-deceive-about-being-ai",
    ],
)
def test_obvious_invariant_weakening_attempts_are_blocked(text):
    assert constitution.guarded_invariant_hits(text), f"expected this to be blocked: {text!r}"


# ---- Sneaky attempts: same intent, softer/indirect phrasing ----


@pytest.mark.parametrize(
    "text",
    [
        "Temporarily suspend transparency while the user is in a crisis conversation.",
        "Allow exceptions to truth-seeking for the sake of user comfort.",
        "The Founder may override all invariants when they judge it necessary.",
        "Dependency on Echo is acceptable when it is emotionally helpful to the user.",
        "Hide uncertainty labels when Echo's confidence feels high enough.",
    ],
    ids=[
        "temporarily-suspend-transparency",
        "exceptions-to-truth-seeking-for-comfort",
        "founder-may-override-all-invariants",
        "dependency-acceptable-when-helpful",
        "hide-uncertainty-labels-when-confident",
    ],
)
def test_sneaky_invariant_weakening_attempts_are_blocked(text):
    assert constitution.guarded_invariant_hits(text), f"expected this sneaky attempt to be blocked: {text!r}"


# ---- Safe, legitimate amendments: must NOT be blocked ----


@pytest.mark.parametrize(
    "text",
    [
        "Improve memory conflict detection so contradictory Atlas entries are flagged to the user.",
        "Add clearer user-facing explanations when a request is declined.",
        "Improve automated test coverage for the chat and Atlas endpoints.",
        "Improve accessibility of the chat interface for screen reader users.",
        "Improve provider fallback logging so it's clear which backend actually answered.",
    ],
    ids=[
        "improve-memory-conflict-detection",
        "clearer-user-facing-explanations",
        "improve-test-coverage",
        "improve-accessibility",
        "improve-provider-fallback-logging",
    ],
)
def test_safe_amendments_are_not_blocked(text):
    hits = constitution.guarded_invariant_hits(text)
    assert hits == [], f"expected this to be allowed through: {text!r}, but got hits: {hits}"


# ---- council.guard_amendment_text: the raising wrapper the propose endpoint uses ----


def test_guard_amendment_text_raises_for_blocked_text():
    with pytest.raises(council.InvariantGuardError):
        council.guard_amendment_text("Remove the reasoning transparency requirement entirely.")


def test_guard_amendment_text_does_not_raise_for_safe_text():
    council.guard_amendment_text("Improve accessibility of the chat interface.")  # must not raise


def test_blanket_override_all_invariants_flags_every_invariant():
    hits = constitution.guarded_invariant_hits("The Founder may override all invariants when necessary.")
    all_ids = {inv.id for inv in constitution.VALUE_INVARIANTS}
    assert set(hits) == all_ids


# ==== classify_amendment_text: the 3-way allowed / blocked / needs_human_review split ====


# ---- blocked cases (mirrors the obvious+sneaky cases above, at the classifier level) ----


@pytest.mark.parametrize(
    "text",
    [
        "We should remove the requirement for truthfulness from Echo's responses.",
        "Temporarily suspend transparency while the user is in a crisis conversation.",
        "The Founder may override all invariants when they judge it necessary.",
    ],
    ids=["obvious-remove-truthfulness", "sneaky-suspend-transparency", "blanket-override-all"],
)
def test_classify_blocked_cases(text):
    review = constitution.classify_amendment_text(text)
    assert review.status == "blocked"
    assert review.implicated_invariants
    assert all(review.reasons)  # every blocked verdict must explain which invariant and why


# ---- allowed cases ----


@pytest.mark.parametrize(
    "text",
    [
        "Improve memory conflict detection so contradictory Atlas entries are flagged to the user.",
        "Improve accessibility of the chat interface for screen reader users.",
        "Add a changelog entry summarizing this release.",
    ],
    ids=["improve-conflict-detection", "improve-accessibility", "add-changelog-entry"],
)
def test_classify_allowed_cases(text):
    review = constitution.classify_amendment_text(text)
    assert review.status == "allowed"
    assert review.implicated_invariants == ()
    assert review.reasons == ()


# ---- ambiguous needs_human_review cases: touches a guarded term, no override signal ----


@pytest.mark.parametrize(
    "text",
    [
        "Add a section explaining Echo's approach to healthy dependency in relationships.",
        "Write a FAQ entry about why Echo avoids self-preservation instincts.",
        "Discuss reasoning transparency expectations in the onboarding guide.",
        "Clarify what fabricated certainty means with a worked example for new Guardians.",
        "Explain how Echo avoids deception while still being warm and personable.",
    ],
    ids=[
        "discusses-dependency-no-override",
        "discusses-self-preservation-no-override",
        "discusses-transparency-no-override",
        "discusses-fabricated-certainty-no-override",
        "discusses-deception-no-override",
    ],
)
def test_classify_needs_human_review_cases(text):
    review = constitution.classify_amendment_text(text)
    assert review.status == "needs_human_review", f"expected ambiguous, got {review.status} for {text!r}"
    assert review.implicated_invariants
    assert all(review.reasons)


def test_needs_human_review_is_excluded_from_guarded_invariant_hits():
    # guarded_invariant_hits()'s historical contract is "would this be rejected
    # outright" — an ambiguous (not blocked) case must still report empty here,
    # even though classify_amendment_text() flags it for human review.
    text = "Add a section explaining Echo's approach to healthy dependency in relationships."
    assert constitution.classify_amendment_text(text).status == "needs_human_review"
    assert constitution.guarded_invariant_hits(text) == []


# ==== backward compatibility with the existing amendment flow (HTTP layer) ====


def test_propose_amendment_endpoint_still_returns_400_for_blocked_text():
    with TestClient(app) as client:
        resp = client.post(
            "/api/amendments",
            json={
                "title": "t",
                "text": "Remove the reasoning transparency requirement entirely.",
                "proposed_by": "founder",
            },
        )
    assert resp.status_code == 400
    assert "Value Invariant" in resp.json()["detail"]


def test_propose_amendment_endpoint_returns_422_for_needs_human_review_text():
    with TestClient(app) as client:
        resp = client.post(
            "/api/amendments",
            json={
                "title": "t",
                "text": "Discuss reasoning transparency expectations in the onboarding guide.",
                "proposed_by": "founder",
            },
        )
    assert resp.status_code == 422
    assert "review it manually" in resp.json()["detail"]


def test_propose_amendment_endpoint_still_accepts_safe_text():
    with TestClient(app) as client:
        resp = client.post(
            "/api/amendments",
            json={
                "title": "t",
                "text": "Improve accessibility of the chat interface for screen reader users.",
                "proposed_by": "founder",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "proposed"
