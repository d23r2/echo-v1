"""Tests for Goal 17: deterministic preference/learning-style memory capture —
the missing layer between "remember that..." (explicit, already worked) and
relying on the model to spontaneously emit a MEMORY: block (implicit, unreliable
for natural preference statements, which was the actual reported bug).
"""

from app.preference_detection import detect_preference_statement


# ---- detect_preference_statement() — pure function ----


def test_when_you_explain_statement_is_detected():
    result = detect_preference_statement(
        "When you explain technical things to me, lead with a concrete example before the theory."
    )
    assert result is not None
    assert result.source == "learning_style_detection"
    assert "learning_style" in result.tags
    assert "explanation_style" in result.tags
    assert "technical_explanations" in result.tags


def test_i_learn_better_statement_is_detected():
    result = detect_preference_statement("I learn better when you show me an example first.")
    assert result is not None
    assert result.source == "learning_style_detection"
    assert "learning_style" in result.tags


def test_i_prefer_statement_is_detected():
    result = detect_preference_statement("I prefer simple step-by-step explanations.")
    assert result is not None
    assert "learning_style" in result.tags  # mentions "step-by-step"/"explanations"


def test_general_preference_without_learning_keywords_still_detected():
    result = detect_preference_statement("I prefer tea over coffee.")
    assert result is not None
    assert result.source == "explicit_user_preference"
    assert "learning_style" not in result.tags


def test_from_now_on_statement_is_detected():
    result = detect_preference_statement("From now on, explain code with examples first.")
    assert result is not None
    assert result.source == "learning_style_detection"


def test_next_time_statement_is_detected():
    result = detect_preference_statement("Next time, give me the practical version before the theory.")
    assert result is not None


def test_dont_start_with_statement_is_detected():
    result = detect_preference_statement(
        "Don't start with abstract theory; show me what it looks like first."
    )
    assert result is not None


def test_casual_one_off_request_is_not_detected():
    # This is a request about *this* message, not a durable preference — should
    # not become a long-term memory just because it mentions "explain"/"example".
    assert detect_preference_statement("Can you explain this with an example?") is None


def test_unrelated_casual_message_is_not_detected():
    assert detect_preference_statement("What's the weather like today?") is None


def test_empty_message_is_not_detected():
    assert detect_preference_statement("") is None


def test_content_preserves_original_wording():
    msg = "When you explain technical things to me, lead with a concrete example before the theory."
    result = detect_preference_statement(msg)
    assert result.content == msg
