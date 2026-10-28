"""Signup tax identifiers follow the selected country and stay optional."""

import pytest
from pydantic import ValidationError

from app.schemas.signup import SignupStore
from app.tenancy.countries import COUNTRY_CURRENCIES
from app.tenancy.tax_ids import normalize_tax_id


def _store(country: str, trn: str | None) -> SignupStore:
    return SignupStore(
        store_name="Al Noor",
        slug="alnoor",
        currency="USD",
        country=country,
        trn=trn,
    )


def test_blank_tax_id_is_allowed_for_every_signup_country():
    assert COUNTRY_CURRENCIES
    for country in COUNTRY_CURRENCIES:
        assert normalize_tax_id(country, None) is None
        assert normalize_tax_id(country, "  ") is None
        assert _store(country, None).trn is None
        assert _store(country, "").trn is None


def test_known_formats_and_a_generic_country():
    assert _store("AE", "100123456700003").trn == "100123456700003"
    assert _store("SA", "300000000000003").trn == "300000000000003"
    assert _store("GB", "123456789").trn == "GB123456789"
    assert _store("US", "12-3456789").trn == "12-3456789"
    assert _store("FR", "FR12345678901").trn == "FR12345678901"
    assert _store("PK", "1234567").trn == "1234567"


def test_a_uae_rule_does_not_reject_another_country():
    assert _store("DE", "DE123456789").trn == "DE123456789"
    with pytest.raises(ValidationError):
        _store("AE", "DE123456789")
    with pytest.raises(ValidationError):
        _store("US", "12-345")
    with pytest.raises(ValidationError):
        _store("SA", "100123456700003")


def test_changing_country_keeps_the_number_for_the_server_to_judge():
    entered = "GB123456789"
    with pytest.raises(ValidationError):
        _store("AE", entered)
    assert _store("GB", entered).trn == entered
