"""Self-service signup (bare domain, no tenant). Every step after start carries the X-Signup-Token it returned."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request

from app.core.config import Settings, get_settings
from app.core.rate_limit import check
from app.schemas.signup import (
    AvailabilityResult,
    EmailLookup,
    PhoneLookup,
    SignupBusiness,
    SignupResume,
    SignupStart,
    SignupStarted,
    SignupState,
    SignupStore,
    SignupVerify,
    SlugCheck,
)
from app.services import availability
from app.tenancy import provisioning, signup_service

router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]
Token = Annotated[str | None, Header(alias="X-Signup-Token")]


def _limit(request: Request) -> None:
    check(
        request,
        "signup-availability",
        limit=availability.RATE_LIMIT,
        window_seconds=availability.RATE_WINDOW_SECONDS,
    )


@router.post("/start", response_model=SignupStarted, status_code=201)
def start(payload: SignupStart, settings: Config) -> SignupStarted:
    return signup_service.start(settings, payload)


@router.post("/resume", response_model=SignupStarted)
def resume(payload: SignupResume, settings: Config) -> SignupStarted:
    return signup_service.resume(settings, payload)


@router.get("/slug-check", response_model=SlugCheck)
def slug_check(
    request: Request, settings: Config, slug: Annotated[str, Query(min_length=1, max_length=40)]
) -> SlugCheck:
    _limit(request)
    return signup_service.check_slug(settings, slug)


@router.post("/availability/email", response_model=AvailabilityResult)
def email_availability(request: Request, payload: EmailLookup, settings: Config) -> AvailabilityResult:
    _limit(request)
    return availability.check_email(settings, payload.email)


@router.post("/availability/phone", response_model=AvailabilityResult)
def phone_availability(request: Request, payload: PhoneLookup, settings: Config) -> AvailabilityResult:
    _limit(request)
    return availability.check_phone(settings, payload.phone)


@router.get("/{request_id}", response_model=SignupState)
@router.get("/{request_id}/status", response_model=SignupState)
def status(request_id: uuid.UUID, settings: Config, token: Token = None) -> SignupState:
    return signup_service.current(settings, request_id, token)


@router.post("/{request_id}/resend", response_model=SignupStarted)
def resend(request_id: uuid.UUID, settings: Config, token: Token = None) -> SignupStarted:
    return signup_service.resend(settings, request_id, token)


@router.post("/{request_id}/verify", response_model=SignupState)
def verify(request_id: uuid.UUID, payload: SignupVerify, settings: Config, token: Token = None) -> SignupState:
    return signup_service.verify(settings, request_id, token, payload.code)


@router.post("/{request_id}/business", response_model=SignupState)
def business(request_id: uuid.UUID, payload: SignupBusiness, settings: Config, token: Token = None) -> SignupState:
    return signup_service.choose_business(settings, request_id, token, payload)


@router.post("/{request_id}/store", response_model=SignupState)
def store(
    request_id: uuid.UUID, payload: SignupStore, settings: Config, background: BackgroundTasks, token: Token = None
) -> SignupState:
    result = signup_service.choose_store(settings, request_id, token, payload)
    background.add_task(provisioning.provision, request_id, settings)
    return result


@router.post("/{request_id}/retry", response_model=SignupState)
def retry(request_id: uuid.UUID, settings: Config, background: BackgroundTasks, token: Token = None) -> SignupState:
    result = signup_service.retry(settings, request_id, token)
    background.add_task(provisioning.provision, request_id, settings)
    return result
