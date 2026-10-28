from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import current_user, require_api_key
from app.core.errors import ApiError
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    PasswordLoginRequest,
    PinLoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyResetCodeRequest,
)
from app.schemas.signup import HandoffRequest
from app.services import password_reset_service, rbac_service
from app.tenancy import signup_service
from app.tenancy.context import current_tenant

router = APIRouter()


@router.post("/login-password", response_model=TokenResponse)
def login_password(
    request: PasswordLoginRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return rbac_service.authenticate(
        db,
        settings,
        username=request.username,
        secret=request.password,
        method="password",
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ForgotPasswordResponse:
    message = password_reset_service.request_code(db, settings, request.email)
    return ForgotPasswordResponse(message=message)


@router.post("/verify-reset-code", response_model=ForgotPasswordResponse)
def verify_reset_code(
    request: VerifyResetCodeRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ForgotPasswordResponse:
    password_reset_service.check_code(db, request.email, request.code)
    return ForgotPasswordResponse(message="Code accepted.")


@router.post("/reset-password", response_model=ForgotPasswordResponse)
def reset_password(
    request: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ForgotPasswordResponse:
    password_reset_service.reset_password(db, request.email, request.code, request.password)
    return ForgotPasswordResponse(message="Password updated. Sign in with the new password.")


@router.post("/login-pin", response_model=TokenResponse)
def login_pin(
    request: PinLoginRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(require_api_key)],
) -> TokenResponse:
    return rbac_service.authenticate(db, settings, username=request.username, secret=request.pin, method="pin")


@router.post("/handoff", response_model=TokenResponse)
def handoff(
    request: HandoffRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Signs the owner of a newly provisioned store in with the one-time token from signup."""
    tenant = current_tenant()
    if tenant is None:
        raise ApiError(404, "not_found", "Sign-in links only work on a store's own address.")
    username = signup_service.redeem_handoff(settings, request.token, tenant.id)
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if user is None:
        raise ApiError(401, "invalid_handoff", "The store owner account was not found. Sign in with your password.")
    return rbac_service.issue_session(db, settings, user, "handoff")


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> UserOut:
    return rbac_service.user_out(user, db)
