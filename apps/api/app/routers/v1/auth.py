from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, current_user, renewable_session, require_device
from app.core.errors import ApiError
from app.core.rate_limit import check_identity
from app.models.user import User
from app.schemas.auth import (
    AccountPasswordChange,
    AccountProfileUpdate,
    CashierOption,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    PasswordLoginRequest,
    PinLoginRequest,
    RecoveredStoreOut,
    ResetPasswordRequest,
    StoreCodeVerifyResponse,
    TokenResponse,
    UnlockRequest,
    UserOut,
    VerifyResetCodeRequest,
)
from app.schemas.signup import HandoffRequest
from app.services import avatar_service, password_reset_service, rbac_service, store_code_recovery
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
    http: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ForgotPasswordResponse:
    """Emails a reset code when the address belongs to a portal user of this store. The reply does not say which."""
    check_identity(http, "password-reset", request.email, ip_limit=30, identity_limit=5, window_seconds=600)
    message = password_reset_service.request_code(db, settings, request.email)
    return ForgotPasswordResponse(message=message)


@router.post("/verify-reset-code", response_model=ForgotPasswordResponse)
def verify_reset_code(
    request: VerifyResetCodeRequest,
    http: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ForgotPasswordResponse:
    check_identity(http, "password-reset-check", request.email, ip_limit=40, identity_limit=12, window_seconds=600)
    password_reset_service.check_code(db, request.email, request.code)
    return ForgotPasswordResponse(message="Code accepted.")


@router.post("/reset-password", response_model=ForgotPasswordResponse)
def reset_password(
    request: ResetPasswordRequest,
    http: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ForgotPasswordResponse:
    """Sets a new password from a valid code. Does not sign the user in. Existing tokens stop working."""
    check_identity(http, "password-reset-confirm", request.email, ip_limit=20, identity_limit=8, window_seconds=600)
    password_reset_service.reset_password(db, settings, request.email, request.code, request.password)
    return ForgotPasswordResponse(message="Password updated. Sign in with the new password.")


@router.post("/recover-store-code", response_model=ForgotPasswordResponse)
def recover_store_code(
    request: ForgotPasswordRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ForgotPasswordResponse:
    """Emails a code when the address can sign in to a store. The reply does not say whether it can."""
    check_identity(http, "store-code", request.email, ip_limit=30, identity_limit=5, window_seconds=600)
    message = store_code_recovery.request_code(settings, request.email, http.client.host if http.client else None)
    return ForgotPasswordResponse(message=message)


@router.post("/recover-store-code/verify", response_model=StoreCodeVerifyResponse)
def recover_store_code_verify(
    request: VerifyResetCodeRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StoreCodeVerifyResponse:
    """Returns store codes only after the emailed code matches. A wrong code reveals nothing."""
    check_identity(http, "store-code-verify", request.email, ip_limit=40, identity_limit=12, window_seconds=600)
    stores, message = store_code_recovery.verify(
        settings, request.email, request.code, http.client.host if http.client else None
    )
    return StoreCodeVerifyResponse(
        message=message,
        stores=[RecoveredStoreOut(code=item.code, name=item.name, branch=item.branch) for item in stores],
    )


@router.get("/cashiers", response_model=list[CashierOption])
def cashiers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_device)],
) -> list[CashierOption]:
    """Profiles for the activated register. The branch comes from the device token, never from the query string."""
    return rbac_service.list_pos_cashiers(db, principal.store_id)


@router.post("/login-pin", response_model=TokenResponse)
def login_pin(
    request: PinLoginRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_device)],
) -> TokenResponse:
    return rbac_service.authenticate(
        db,
        settings,
        username=request.username,
        secret=request.pin,
        method="pin",
        store_id=principal.store_id,
    )


@router.post("/unlock", response_model=TokenResponse)
def unlock(
    request: UnlockRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_device)],
) -> TokenResponse:
    return rbac_service.unlock_cashier(db, settings, request.user_id, request.pin, principal.store_id)


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


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    session: Annotated[tuple[User, Literal["portal", "pos"]], Depends(renewable_session)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Reissues the same kind of access token while this one is still accepted.

    A token a couple of minutes past exp can still renew. Revoked and disabled sessions cannot.
    """
    user, scope = session
    return rbac_service.renew_session(db, settings, user, scope)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> UserOut:
    return rbac_service.user_out(user, db)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> UserOut:
    data = await file.read(avatar_service.MAX_BYTES + 1)
    return avatar_service.set_avatar(db, user, data, file.content_type)


@router.delete("/me/avatar", response_model=UserOut)
def delete_avatar(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    return avatar_service.clear_avatar(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(
    request: AccountProfileUpdate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    return rbac_service.update_own_profile(db, user, request.full_name)


@router.post("/me/password", response_model=TokenResponse)
def change_password(
    request: AccountPasswordChange,
    http: Request,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    check_identity(http, "password-change", user.email, ip_limit=20, identity_limit=8, window_seconds=600)
    return rbac_service.change_own_password(db, settings, user, request.current_password, request.password)
