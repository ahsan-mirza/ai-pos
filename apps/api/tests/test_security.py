from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_value,
    encrypt_value,
    hash_password,
    hash_pin,
    verify_password,
    verify_pin,
)
from app.services.identifiers import is_valid_imei


def test_password_round_trip() -> None:
    encoded = hash_password("cashier-secret")
    assert verify_password("cashier-secret", encoded)
    assert not verify_password("wrong-secret", encoded)
    assert not verify_password("cashier-secret", "not-a-hash")
    assert not verify_password("cashier-secret", None)


def test_pin_hash_uses_pepper() -> None:
    settings = get_settings()
    encoded = hash_pin("4321", settings)
    assert verify_pin("4321", encoded, settings)
    assert not verify_pin("4322", encoded, settings)
    assert not verify_password("4321", encoded)


def test_access_token_round_trip() -> None:
    settings = get_settings()
    token, expires_in = create_access_token(subject="user-1", scope="pos", token_version=3, settings=settings)
    payload = decode_access_token(token, settings=settings)
    assert payload["sub"] == "user-1"
    assert payload["scope"] == "pos"
    assert payload["ver"] == 3
    assert expires_in == settings.access_token_expire_minutes * 60


def test_identifier_encryption_round_trip() -> None:
    settings = get_settings()
    token = encrypt_value("490154203237518", settings)
    assert token != "490154203237518"
    assert decrypt_value(token, settings) == "490154203237518"


def test_known_imei_vectors() -> None:
    assert is_valid_imei("490154203237518")
    assert not is_valid_imei("490154203237519")
    assert not is_valid_imei("12345")
