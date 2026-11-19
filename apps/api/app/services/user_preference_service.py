"""Read and write the signed-in cashier's catalogue view.

The user id always comes from the authenticated principal. A missing row is grid,
and it is not inserted until the cashier chooses a view. When two terminals save,
the later timestamp wins. An equal timestamp keeps the row already stored.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.base import utcnow
from app.models.user import User
from app.models.user_preference import CATALOGUE_VIEW_KEY, CATALOGUE_VIEWS, UserPreference
from app.schemas.user_preference import CatalogueViewOut

_FUTURE_SKEW = timedelta(minutes=5)


def read_catalogue_view(db: Session, user: User) -> CatalogueViewOut:
    row = _row(db, user.id)
    if row is None:
        return CatalogueViewOut(product_catalogue_view="grid", updated_at=None, revision=0)
    return _out(row)


def save_catalogue_view(
    db: Session,
    user: User,
    view: str,
    client_updated_at: datetime | None,
) -> CatalogueViewOut:
    if view not in CATALOGUE_VIEWS:
        raise ApiError(422, "invalid_preference", "Choose grid, list, or compact.")
    row = _row(db, user.id)
    if row is None:
        created = UserPreference(
            id=uuid.uuid4(),
            user_id=user.id,
            preference_key=CATALOGUE_VIEW_KEY,
            preference_value=view,
            revision=1,
        )
        db.add(created)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = _row(db, user.id)
            if row is None:
                raise
            return _apply(db, row, view, client_updated_at)
        db.refresh(created)
        return _out(created)
    return _apply(db, row, view, client_updated_at)


def _apply(db: Session, row: UserPreference, view: str, client_updated_at: datetime | None) -> CatalogueViewOut:
    incoming = _client_time(client_updated_at)
    stored = _aware(row.updated_at)
    if incoming is not None and stored is not None and incoming <= stored:
        return _out(row)
    row.preference_value = view
    row.revision = int(row.revision or 0) + 1
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


def _row(db: Session, user_id: uuid.UUID) -> UserPreference | None:
    return db.scalar(
        select(UserPreference).where(
            UserPreference.user_id == user_id,
            UserPreference.preference_key == CATALOGUE_VIEW_KEY,
        )
    )


def _out(row: UserPreference) -> CatalogueViewOut:
    view = row.preference_value if row.preference_value in CATALOGUE_VIEWS else "grid"
    return CatalogueViewOut(
        product_catalogue_view=view,  # type: ignore[arg-type]
        updated_at=_aware(row.updated_at),
        revision=int(row.revision or 0),
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _client_time(value: datetime | None) -> datetime | None:
    stamp = _aware(value)
    if stamp is None:
        return None
    latest = utcnow() + _FUTURE_SKEW
    return latest if stamp > latest else stamp
