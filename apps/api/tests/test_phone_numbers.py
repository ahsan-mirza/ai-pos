import pytest

from app.core.errors import field_error_map
from app.services.phone_numbers import normalize_phone, search_terms


def test_uae_national_leading_zero_becomes_e164() -> None:
    assert normalize_phone("0501234567") == "+971501234567"


def test_uae_national_without_trunk_zero() -> None:
    assert normalize_phone("501234567") == "+971501234567"


def test_international_and_00_prefix() -> None:
    assert normalize_phone("+971501234567") == "+971501234567"
    assert normalize_phone("00971501234567") == "+971501234567"
    assert normalize_phone("+971 50 123 4567") == "+971501234567"


def test_country_code_is_not_applied_twice() -> None:
    assert normalize_phone("+971501234567") == "+971501234567"


def test_optional_blank_stays_blank_and_invalid_is_rejected() -> None:
    assert normalize_phone(None) is None
    assert normalize_phone("  ") is None
    with pytest.raises(ValueError, match="valid phone number"):
        normalize_phone("123")
    with pytest.raises(ValueError, match="phone number"):
        normalize_phone("", required=True)


def test_legacy_spaced_number_normalizes_and_search_still_matches() -> None:
    stored = normalize_phone("050 123 4567")
    assert stored == "+971501234567"
    assert "+971501234567" in search_terms("0501234567")
    assert "501234567" in search_terms("0501234567")


def test_validation_errors_keep_a_field_map() -> None:
    mapped = field_error_map(
        [{"loc": ["body", "phone"], "msg": "Enter a valid phone number.", "type": "value_error"}]
    )
    assert mapped == {"phone": "Enter a valid phone number."}
