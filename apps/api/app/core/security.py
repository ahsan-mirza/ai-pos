import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from cryptography.fernet import Fernet

from app.core.config import Settings

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
TokenScope = Literal["portal", "pos"]

_DUMMY_HASH = "scrypt$" + "00" * 16 + "$" + "00" * 32


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt_bytes = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${salt_bytes.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-work check. A missing hash still runs scrypt so timing does not reveal unknown users."""
    target = encoded if encoded is not None else _DUMMY_HASH
    parts = target.split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        parts = _DUMMY_HASH.split("$")
    _, salt_hex, digest_hex = parts
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        salt = bytes(16)
    candidate = hash_password(password, salt=salt)
    matches = secrets_equal(candidate, f"scrypt${salt_hex}${digest_hex}")
    return matches and encoded is not None


def _peppered_pin(pin: str, settings: Settings) -> str:
    return hmac.new(settings.pin_salt.encode("utf-8"), pin.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_pin(pin: str, settings: Settings) -> str:
    return hash_password(_peppered_pin(pin, settings))


def verify_pin(pin: str, encoded: str | None, settings: Settings) -> bool:
    return verify_password(_peppered_pin(pin, settings), encoded)


def create_access_token(
    *,
    subject: str,
    scope: TokenScope,
    token_version: int,
    settings: Settings,
    expires_in: timedelta | None = None,
    tenant_id: str | None = None,
) -> tuple[str, int]:
    lifetime = expires_in if expires_in is not None else timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": subject,
        "scope": scope,
        "ver": token_version,
        "iat": now,
        "exp": now + lifetime,
    }
    if tenant_id is not None:
        # Every tenant signs with the same secret; the claim keeps a token from opening another store.
        claims["tid"] = tenant_id
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, *, settings: Settings, leeway_seconds: int = 0) -> dict[str, object]:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        leeway=leeway_seconds,
        options={"require": ["sub", "exp", "scope", "ver"]},
    )
    if not isinstance(payload, dict):
        raise jwt.InvalidTokenError("Token payload is invalid.")
    return payload


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(settings.encryption_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(value: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str, settings: Settings) -> str:
    return _fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")
