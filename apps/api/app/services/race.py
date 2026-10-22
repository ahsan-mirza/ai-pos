"""Rows created lazily on first read (default templates, the chart of accounts, the settings row) can be created by
two requests at once: the portal loads several panels in parallel. Insert them in a savepoint and treat a unique
clash as "the other request won" instead of failing the page."""

from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def add_if_absent(db: Session, rows: Iterable[object]) -> bool:
    """Adds and flushes `rows`; False (and nothing added) when a concurrent request inserted them first."""
    pending = list(rows)
    if not pending:
        return True
    try:
        with db.begin_nested():
            db.add_all(pending)
            db.flush()
    except IntegrityError:
        return False
    return True
