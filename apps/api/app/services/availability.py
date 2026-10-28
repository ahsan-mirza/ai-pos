"""Advisory checks for signup email, mobile, and store address.

PostgreSQL is the source of truth. The Bloom filter skips the existence query only when it is healthy
and reports the value absent. A hit, a stale filter, or a Redis failure always reads the database.
The filter never answers "taken" by itself.

Store display names are not unique, so they are not filtered and have no availability lookup.
The unique store key is the address (slug).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.signup import AvailabilityResult
from app.services import bloom_filter
from app.services.phone_numbers import normalize_phone, optional_email
from app.tenancy import registry
from app.tenancy.models import SignupRequest, SignupSlugHold, Tenant

log = logging.getLogger("ai_pos.availability")

RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60

stats = {"absent": 0, "db": 0, "rebuild": 0}


def reset_stats() -> None:
    for key in stats:
        stats[key] = 0


def check_email(settings: Settings, raw: str) -> AvailabilityResult:
    email = _email(raw)
    with registry.control_session(settings) as db:
        available = _is_available(db, "email", email, _emails, lambda: email_is_taken(db, email))
    return _result(available)


def check_phone(settings: Settings, raw: str) -> AvailabilityResult:
    phone = _phone(raw)
    with registry.control_session(settings) as db:
        available = _is_available(db, "phone", phone, _phones, lambda: phone_is_taken(db, phone))
    return _result(available)


def slug_needs_database(db: Session, slug: str) -> bool:
    """False when the filter proves this address has never been reserved since the last rebuild."""
    return not _skips_database(db, "slug", slug, _slugs)


def remember_account(db: Session, email: str, phone: str) -> None:
    _remember(db, "email", email, _emails)
    _remember(db, "phone", phone, _phones)


def remember_slug(db: Session, slug: str) -> None:
    _remember(db, "slug", slug, _slugs)


def note_slug_released() -> None:
    """A released address cannot be removed from the bitset, so the next check rebuilds from PostgreSQL."""
    bloom_filter.mark_stale("slug")


def email_is_taken(db: Session, email: str) -> bool:
    return db.scalar(select(SignupRequest.id).where(SignupRequest.email == email).limit(1)) is not None


def phone_is_taken(db: Session, phone: str) -> bool:
    return db.scalar(select(SignupRequest.id).where(SignupRequest.phone == phone).limit(1)) is not None


def _result(available: bool) -> AvailabilityResult:
    return AvailabilityResult(available=available, code="available" if available else "taken")


def _email(raw: str) -> str:
    try:
        cleaned = optional_email(raw)
    except ValueError as exc:
        raise ApiError(422, "invalid_request", "Enter a valid email address.") from exc
    if cleaned is None:
        raise ApiError(422, "invalid_request", "Enter an email address.")
    return cleaned


def _phone(raw: str) -> str:
    try:
        cleaned = normalize_phone(raw, required=True)
    except ValueError as exc:
        raise ApiError(422, "invalid_request", "Enter a valid phone number.") from exc
    if cleaned is None:
        raise ApiError(422, "invalid_request", "Enter a phone number.")
    return cleaned


def _emails(db: Session) -> list[str]:
    return list(db.scalars(select(SignupRequest.email)))


def _phones(db: Session) -> list[str]:
    return list(db.scalars(select(SignupRequest.phone)))


def _slugs(db: Session) -> list[str]:
    held = list(db.scalars(select(SignupSlugHold.slug)))
    live = list(db.scalars(select(Tenant.slug)))
    pending = list(
        db.scalars(
            select(SignupRequest.slug).where(
                SignupRequest.slug.is_not(None),
                SignupRequest.status.in_(("PROVISIONING", "READY")),
            )
        )
    )
    return [item for item in {*held, *live, *pending} if item]


def _is_available(
    db: Session,
    kind: str,
    value: str,
    loader: Callable[[Session], list[str]],
    taken: Callable[[], bool],
) -> bool:
    if _skips_database(db, kind, value, loader):
        return True
    stats["db"] += 1
    started = time.perf_counter()
    available = not taken()
    log.info(
        "signup availability kind=%s bloom=database db=1 available=%s ms=%s",
        kind,
        available,
        round((time.perf_counter() - started) * 1000, 2),
    )
    return available


def _skips_database(db: Session, kind: str, value: str, loader: Callable[[Session], list[str]]) -> bool:
    decision = bloom_filter.probe(kind, value)
    if decision == "unknown" and bloom_filter.should_rebuild(kind):
        if bloom_filter.rebuild(kind, loader(db)):
            stats["rebuild"] += 1
            decision = bloom_filter.probe(kind, value)
    if decision == "absent":
        stats["absent"] += 1
        log.info("signup availability kind=%s bloom=absent db=0", kind)
        return True
    return False


def _remember(db: Session, kind: str, value: str, loader: Callable[[Session], list[str]]) -> None:
    if not bloom_filter.is_ready(kind):
        bloom_filter.rebuild(kind, loader(db))
        return
    decision = bloom_filter.probe(kind, value)
    if decision == "possible":
        return
    if decision != "absent" or not bloom_filter.add(kind, value):
        bloom_filter.mark_stale(kind)
