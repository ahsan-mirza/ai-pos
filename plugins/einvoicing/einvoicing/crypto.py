"""Credential sealing. The API never returns the stored value."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.environ.get("EINVOICING_CREDENTIAL_KEY", "")
    if not key:
        raise RuntimeError("EINVOICING_CREDENTIAL_KEY is required before provider secrets can be stored.")
    return Fernet(key.encode())


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def open_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
