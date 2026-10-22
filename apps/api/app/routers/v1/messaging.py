from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.jobs import catalog as _catalog  # noqa: F401  registers the jobs
from app.jobs.runner import JOBS, run_job
from app.models.scheduled_job import ScheduledJob
from app.schemas.messaging import (
    JobOut,
    MessagingSettingsOut,
    MessagingSettingsWrite,
    OutboundOut,
    TemplateOut,
    TemplateWrite,
    TestMessage,
)
from app.services import messaging_service

router = APIRouter()
jobs_router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanManage = Annotated[Principal, Depends(authorize(Permission.MESSAGING_MANAGE))]
CanSettings = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]


@router.get("/settings", response_model=MessagingSettingsOut)
def get_settings_(db: Db, _: CanManage) -> MessagingSettingsOut:
    return messaging_service.settings_out(db)


@router.put("/settings", response_model=MessagingSettingsOut)
def put_settings(payload: MessagingSettingsWrite, db: Db, _: CanManage) -> MessagingSettingsOut:
    return messaging_service.update_settings(db, payload)


@router.get("/templates", response_model=list[TemplateOut])
def templates(db: Db, _: CanManage) -> list[TemplateOut]:
    return messaging_service.list_templates(db)


@router.put("/templates/{key}", response_model=TemplateOut)
def put_template(key: str, payload: TemplateWrite, db: Db, _: CanManage) -> TemplateOut:
    return messaging_service.update_template(db, key, payload)


@router.get("/outbox", response_model=list[OutboundOut])
def outbox(
    db: Db,
    _: CanManage,
    status: Literal["QUEUED", "SENT", "FAILED", "SKIPPED"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OutboundOut]:
    return messaging_service.outbox(db, status=status, limit=limit)


@router.post("/test", response_model=OutboundOut)
def send_test(payload: TestMessage, db: Db, settings: Config, _: CanManage) -> OutboundOut:
    return messaging_service.send_test(db, settings, payload.channel, payload.to)


@jobs_router.get("", response_model=list[JobOut])
def list_jobs(db: Db, _: CanSettings) -> list[JobOut]:
    rows = {row.name: row for row in db.query(ScheduledJob).all()}
    out = []
    for job in JOBS.values():
        row = rows.get(job.name)
        out.append(
            JobOut(
                name=job.name,
                description=job.description,
                schedule=job.schedule,
                last_started_at=row.last_started_at if row else None,
                last_finished_at=row.last_finished_at if row else None,
                last_status=row.last_status if row else None,
                last_result=row.last_result if row else None,
                run_count=row.run_count if row else 0,
                running=bool(row and row.locked_until is not None),
            )
        )
    return out


@jobs_router.post("/{name}/run", response_model=JobOut)
def run_now(name: str, db: Db, settings: Config, principal: CanSettings) -> JobOut:
    if name not in JOBS:
        raise ApiError(404, "not_found", "Unknown job.")
    if run_job(db, settings, name) == "busy":
        raise ApiError(409, "busy", "This job is already running.")
    return next(job for job in list_jobs(db, principal) if job.name == name)
