from app.core.config import Settings

_REQUIRED = {
    "app_env": "test",
    "database_url": "sqlite://",
    "jwt_secret": "test-jwt-secret-must-be-32-chars!!",
    "pin_salt": "test-pin-pepper-16chars",
    "encryption_secret": "test-encryption-secret-32-chars!",
    "api_key": "test-api-key-value",
    "cors_origins": "http://localhost:5173",
}


def _settings(pin: str | None) -> Settings:
    return Settings(_env_file=None, admin_pin=pin, **_REQUIRED)


def test_four_digit_admin_pin_is_kept() -> None:
    assert _settings(" 1357 ").admin_pin == "1357"
    assert _settings('"2468"').admin_pin == "2468"


def test_blank_or_legacy_admin_pin_does_not_reject_settings() -> None:
    assert _settings(None).admin_pin is None
    assert _settings("").admin_pin is None
    assert _settings("   ").admin_pin is None
    # generate-secrets used to write 6 digits. That must not stop migrations.
    assert _settings("034906").admin_pin is None
