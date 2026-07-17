"""ECHO Layer 1 — memory_privacy.py: sensitivity classification, secret
rejection, do-not-remember/forget detection. Pure function tests, no DB."""

from app.services import memory_privacy


def test_ordinary_statement_is_ordinary_personal():
    assert memory_privacy.classify_sensitivity("I prefer tea over coffee") == "ordinary_personal"


def test_empty_content_is_ordinary_personal_not_a_crash():
    assert memory_privacy.classify_sensitivity("") == "ordinary_personal"
    assert memory_privacy.classify_sensitivity(None) == "ordinary_personal"


def test_api_key_shaped_string_is_secret():
    assert memory_privacy.is_secret("my key is sk-abcdefghijklmnopqrstuvwxyz123456")
    assert memory_privacy.classify_sensitivity("api_key: abcd1234efgh5678") == "secret"


def test_bearer_token_is_secret():
    assert memory_privacy.is_secret("Authorization: Bearer abcdefghijklmno1234567890")


def test_private_key_header_is_secret():
    assert memory_privacy.is_secret("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")


def test_password_assignment_is_secret():
    assert memory_privacy.is_secret("password=hunter22222")


def test_card_number_shaped_string_is_secret():
    assert memory_privacy.classify_sensitivity("card is 4111 1111 1111 1111") == "secret"


def test_medical_statement_is_highly_sensitive():
    assert memory_privacy.classify_sensitivity("I was diagnosed with depression last year") == "highly_sensitive"


def test_home_address_is_highly_sensitive():
    assert memory_privacy.classify_sensitivity("my home address is 42 Example Street") == "highly_sensitive"


def test_relationship_statement_is_private():
    assert memory_privacy.classify_sensitivity("my relationship has been difficult lately") == "private"


def test_secret_can_never_be_stored_even_explicit():
    allowed, reason = memory_privacy.can_store("secret", explicit_request=True)
    assert allowed is False
    assert reason


def test_highly_sensitive_blocked_without_explicit_request():
    allowed, _ = memory_privacy.can_store("highly_sensitive", explicit_request=False)
    assert allowed is False


def test_highly_sensitive_allowed_with_explicit_request():
    allowed, _ = memory_privacy.can_store("highly_sensitive", explicit_request=True)
    assert allowed is True


def test_ordinary_personal_always_storable():
    allowed, _ = memory_privacy.can_store("ordinary_personal", explicit_request=False)
    assert allowed is True


def test_secret_never_retrievable():
    assert memory_privacy.can_retrieve("secret", purpose="general") is False
    assert memory_privacy.can_retrieve("secret", purpose="specific") is False


def test_highly_sensitive_only_retrievable_for_specific_purpose():
    assert memory_privacy.can_retrieve("highly_sensitive", purpose="general") is False
    assert memory_privacy.can_retrieve("highly_sensitive", purpose="specific") is True


def test_secret_never_displayed():
    assert memory_privacy.can_display("secret", developer_mode=True) is False


def test_highly_sensitive_display_requires_developer_mode():
    assert memory_privacy.can_display("highly_sensitive", developer_mode=False) is False
    assert memory_privacy.can_display("highly_sensitive", developer_mode=True) is True


def test_export_excludes_secret_and_highly_sensitive():
    assert memory_privacy.can_export("secret") is False
    assert memory_privacy.can_export("highly_sensitive") is False
    assert memory_privacy.can_export("ordinary_personal") is True


def test_detect_do_not_remember():
    assert memory_privacy.detect_do_not_remember("do not remember the next thing I say")
    assert memory_privacy.detect_do_not_remember("don't save this")
    assert not memory_privacy.detect_do_not_remember("please remember that I like tea")


def test_detect_forget_request():
    assert memory_privacy.detect_forget_request("forget that")
    assert memory_privacy.detect_forget_request("delete this memory")
    assert not memory_privacy.detect_forget_request("I forgot my keys today")


def test_redact_for_log_scrubs_secret():
    redacted = memory_privacy.redact_for_log("api_key=abcd1234efgh5678")
    assert "abcd1234efgh5678" not in redacted


def test_classify_never_raises_on_weird_input():
    # Defensive: a non-string-like input shouldn't crash the pipeline.
    assert memory_privacy.classify_sensitivity(12345) == "highly_sensitive"  # degrades safe, not "public"
