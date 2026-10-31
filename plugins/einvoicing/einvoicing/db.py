"""Shared AxizPOS database. DATABASE_URL is the same variable the API already uses."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_session = None


def get_engine():
    global _engine, _session
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
        _engine = create_engine(url, future=True)
        _session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def SessionLocal():
    get_engine()
    return _session()
