"""Reading the audit trail: filtered pages, today's summary, facets, exports, and desktop ingestion."""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.audit_log import SENSITIVE_ACTION_TYPES, AuditLog
from app.models.store import Store
from app.models.user import User
from app.schemas.audit import (
    REASON_REQUIRED,
    ActiveStaff,
    AuditFacets,
    AuditFacetUser,
    AuditLogDetail,
    AuditLogPage,
    AuditLogRow,
    AuditSummary,
    DesktopAuditBatch,
    DesktopAuditRejection,
    DesktopAuditResult,
)
from app.services import audit
from app.services.audit_pdf import render_audit_pdf

LOGIN_TYPES = ("LOGIN_PIN", "LOGIN_PASSWORD")
EXPORT_LIMIT = 5000


@dataclass(frozen=True)
class AuditFilters:
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    user_id: uuid.UUID | None = None
    store_id: uuid.UUID | None = None
    action_types: tuple[str, ...] = ()
    target_entity: str | None = None
    query: str | None = None
    sensitive_only: bool = False

    def describe(self) -> dict[str, object]:
        return {
            key: value
            for key, value in {
                "from": self.occurred_from,
                "to": self.occurred_to,
                "user_id": self.user_id,
                "store_id": self.store_id,
                "action_types": list(self.action_types) or None,
                "target_entity": self.target_entity,
                "q": self.query,
                "sensitive_only": self.sensitive_only or None,
            }.items()
            if value is not None
        }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    """Store-bound users read their own branch only."""
    if principal.store_id is None:
        return store_id
    if store_id is not None and store_id != principal.store_id:
        raise ApiError(403, "store_scope", "You can only view activity for your own store.")
    return principal.store_id


def _filtered(principal: Principal, filters: AuditFilters) -> Select[tuple[AuditLog]]:
    statement = select(AuditLog)
    store_id = _scope(principal, filters.store_id)
    if store_id is not None:
        statement = statement.where(AuditLog.store_id == store_id)
    if filters.occurred_from is not None:
        statement = statement.where(AuditLog.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        statement = statement.where(AuditLog.occurred_at < filters.occurred_to)
    if filters.user_id is not None:
        statement = statement.where(or_(AuditLog.user_id == filters.user_id, AuditLog.approver_id == filters.user_id))
    if filters.action_types:
        statement = statement.where(AuditLog.action_type.in_(filters.action_types))
    if filters.sensitive_only:
        statement = statement.where(AuditLog.action_type.in_(SENSITIVE_ACTION_TYPES))
    if filters.target_entity:
        statement = statement.where(AuditLog.target_entity == filters.target_entity)
    if filters.query:
        needle = f"%{filters.query.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(func.coalesce(AuditLog.user_name, "")).like(needle),
                func.lower(AuditLog.action).like(needle),
                func.lower(AuditLog.target_entity).like(needle),
                func.lower(func.coalesce(AuditLog.reason_notes, "")).like(needle),
            )
        )
    return statement


def _lookups(db: Session, logs: list[AuditLog]) -> tuple[dict[uuid.UUID, Store], dict[uuid.UUID, str]]:
    store_ids = {log.store_id for log in logs if log.store_id is not None}
    approver_ids = {log.approver_id for log in logs if log.approver_id is not None}
    stores = {store.id: store for store in db.scalars(select(Store).where(Store.id.in_(store_ids))).all()}
    approvers = {
        user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(approver_ids))).unique().all()
    }
    return stores, approvers


def _changed(log: AuditLog) -> list[str]:
    keys = set((log.old_values or {}).keys()) | set((log.new_values or {}).keys())
    return sorted(keys)


def _row_fields(log: AuditLog, stores: dict[uuid.UUID, Store], approvers: dict[uuid.UUID, str]) -> dict[str, object]:
    store = stores.get(log.store_id) if log.store_id is not None else None
    return {
        "id": log.id,
        "occurred_at": _aware(log.occurred_at),
        "created_at": _aware(log.created_at),
        "user_id": log.user_id,
        "user_name": log.user_name,
        "user_role": log.user_role,
        "approver_id": log.approver_id,
        "approver_name": approvers.get(log.approver_id) if log.approver_id is not None else None,
        "store_id": log.store_id,
        "store_code": store.code if store is not None else None,
        "store_name": store.name if store is not None else None,
        "action_type": log.action_type,
        "action": log.action,
        "target_entity": log.target_entity,
        "target_entity_id": log.target_entity_id,
        "reason_notes": log.reason_notes,
        "client_device": log.client_device,
        "ip_address": log.ip_address,
        "changed_fields": _changed(log),
        "sensitive": log.action_type in SENSITIVE_ACTION_TYPES,
    }


def list_logs(db: Session, principal: Principal, filters: AuditFilters, *, limit: int, offset: int) -> AuditLogPage:
    statement = _filtered(principal, filters)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    logs = list(
        db.scalars(
            statement.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
        ).all()
    )
    stores, approvers = _lookups(db, logs)
    return AuditLogPage(
        total=total,
        limit=limit,
        offset=offset,
        rows=[AuditLogRow(**_row_fields(log, stores, approvers)) for log in logs],  # type: ignore[arg-type]
    )


def get_log(db: Session, principal: Principal, log_id: uuid.UUID) -> AuditLogDetail:
    log = db.get(AuditLog, log_id)
    if log is None or (principal.store_id is not None and log.store_id != principal.store_id):
        raise ApiError(404, "not_found", "Audit entry was not found.")
    stores, approvers = _lookups(db, [log])
    return AuditLogDetail(
        **_row_fields(log, stores, approvers),  # type: ignore[arg-type]
        old_values=log.old_values,
        new_values=log.new_values,
        details=log.details or {},
        request_path=log.request_path,
        client_event_id=log.client_event_id,
    )


def summary(db: Session, settings: Settings, principal: Principal, *, since: datetime | None) -> AuditSummary:
    now = datetime.now(UTC)
    start = _aware(since) if since is not None else now.replace(hour=0, minute=0, second=0, microsecond=0)
    base = _filtered(principal, AuditFilters(occurred_from=start)).subquery()
    counts = {
        action_type: count
        for action_type, count in db.execute(
            select(base.c.action_type, func.count()).group_by(base.c.action_type)
        ).all()
    }
    window = settings.access_token_expire_minutes
    logins = _filtered(
        principal, AuditFilters(occurred_from=now - timedelta(minutes=window), action_types=LOGIN_TYPES)
    ).order_by(AuditLog.occurred_at.desc())
    latest: dict[uuid.UUID, AuditLog] = {}
    for log in db.scalars(logins).all():
        if log.user_id is not None and log.user_id not in latest:
            latest[log.user_id] = log
    stores, _ = _lookups(db, list(latest.values()))
    return AuditSummary(
        since=start,
        total_actions=sum(counts.values()),
        sensitive_overrides=sum(counts.get(action_type, 0) for action_type in SENSITIVE_ACTION_TYPES),
        active_staff_sessions=len(latest),
        session_window_minutes=window,
        active_staff=[
            ActiveStaff(
                user_id=user_id,
                user_name=log.user_name or "Unknown user",
                user_role=log.user_role,
                store_code=stores[log.store_id].code if log.store_id in stores else None,
                client_device=log.client_device,  # type: ignore[arg-type]
                last_login_at=_aware(log.occurred_at),
            )
            for user_id, log in latest.items()
        ][:12],
        by_action_type=dict(sorted(counts.items(), key=lambda item: -item[1])),
    )


def facets(db: Session, principal: Principal) -> AuditFacets:
    base = _filtered(principal, AuditFilters()).subquery()
    users = db.execute(
        select(base.c.user_id, func.max(base.c.user_name), func.max(base.c.user_role))
        .where(base.c.user_id.is_not(None))
        .group_by(base.c.user_id)
    ).all()
    entities = db.scalars(select(base.c.target_entity).distinct().order_by(base.c.target_entity)).all()
    action_types = db.scalars(select(base.c.action_type).distinct().order_by(base.c.action_type)).all()
    return AuditFacets(
        users=sorted(
            (AuditFacetUser(id=row[0], name=row[1] or "Unknown user", role=row[2]) for row in users),
            key=lambda item: item.name.lower(),
        ),
        entities=list(entities),
        action_types=list(action_types),
    )


CSV_COLUMNS = (
    "occurred_at",
    "user_name",
    "user_role",
    "store_code",
    "action_type",
    "action",
    "target_entity",
    "target_entity_id",
    "reason_notes",
    "approver_name",
    "client_device",
    "ip_address",
    "changed_fields",
    "old_values",
    "new_values",
)


def export(
    db: Session, principal: Principal, filters: AuditFilters, *, file_format: str
) -> tuple[str | bytes, str, list[AuditLogDetail]]:
    """Returns (body, media type, rows). The export itself is recorded in the trail."""
    logs = list(
        db.scalars(_filtered(principal, filters).order_by(AuditLog.occurred_at.desc()).limit(EXPORT_LIMIT)).all()
    )
    stores, approvers = _lookups(db, logs)
    rows = [
        AuditLogDetail(
            **_row_fields(log, stores, approvers),  # type: ignore[arg-type]
            old_values=log.old_values,
            new_values=log.new_values,
            details=log.details or {},
            request_path=log.request_path,
            client_event_id=log.client_event_id,
        )
        for log in logs
    ]
    audit.log_export(db, dataset="audit_logs", row_count=len(rows), filters=filters.describe(), file_format=file_format)
    db.commit()
    if file_format == "json":
        return json.dumps([row.model_dump(mode="json") for row in rows]), "application/json", rows
    if file_format == "pdf":
        scoped = _scope(principal, filters.store_id)
        store = db.get(Store, scoped) if scoped is not None else None
        scope = f"{store.code} · {store.name}" if store is not None else "All branches"
        described = {key: str(value) for key, value in filters.describe().items()}
        return render_audit_pdf(rows, scope=scope, filters=described), "application/pdf", rows
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        data = row.model_dump(mode="json")
        writer.writerow(
            [
                _csv_safe(
                    json.dumps(data[column], sort_keys=True)
                    if column in {"old_values", "new_values"} and data[column] is not None
                    else ";".join(data[column])
                    if column == "changed_fields"
                    else data[column]
                )
                for column in CSV_COLUMNS
            ]
        )
    return buffer.getvalue(), "text/csv", rows


def _csv_safe(value: object) -> str:
    """Neutralises spreadsheet formula injection in user-supplied text."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


def ingest_desktop(db: Session, batch: DesktopAuditBatch) -> DesktopAuditResult:
    ids = [event.id for event in batch.events]
    known = set(db.scalars(select(AuditLog.client_event_id).where(AuditLog.client_event_id.in_(ids))).all())
    user_ids = {event.user_id for event in batch.events} | {e.approver_id for e in batch.events if e.approver_id}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).unique().all()}
    store_ids = {
        store_id for store_id in db.scalars(select(Store.id).where(Store.id.in_({e.store_id for e in batch.events})))
    }

    accepted: list[uuid.UUID] = []
    duplicates: list[uuid.UUID] = []
    rejected: list[DesktopAuditRejection] = []
    seen: set[uuid.UUID] = set()
    for event in batch.events:
        if event.id in known or event.id in seen:
            duplicates.append(event.id)
            continue
        user = users.get(event.user_id)
        problem = None
        if user is None:
            problem = "Unknown cashier."
        elif event.store_id not in store_ids:
            problem = "Unknown store."
        elif event.approver_id is not None and event.approver_id not in users:
            problem = "Unknown approver."
        elif event.action_type in REASON_REQUIRED and not event.reason_notes:
            problem = f"{event.action_type} needs a reason."
        if problem is not None:
            rejected.append(DesktopAuditRejection(id=event.id, reason=problem))
            continue
        assert user is not None
        audit.record(
            db,
            action_type=event.action_type,
            action=event.action,
            target_entity=event.target_entity,
            target_entity_id=event.target_entity_id,
            user=user,
            approver_id=event.approver_id,
            store_id=event.store_id,
            reason_notes=event.reason_notes,
            old_values=event.old_values,
            new_values=event.new_values,
            details={**event.details, "device_id": batch.device_id},
            client_device="desktop",
            occurred_at=_aware(event.occurred_at),
            client_event_id=event.id,
        )
        seen.add(event.id)
        accepted.append(event.id)
    db.commit()
    return DesktopAuditResult(accepted=accepted, duplicates=duplicates, rejected=rejected)
