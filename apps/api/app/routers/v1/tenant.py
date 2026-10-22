from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.governance import ChangeRequestIn, ChangeRequestOut, TenantModulesOut
from app.services import settings_service
from app.tenancy import change_requests
from app.tenancy.context import current_tenant
from app.tenancy.registry import current_identity, tenant_public_url

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
SignedIn = Annotated[Principal, Depends(authorize(allow_device=True, scopes=("portal", "pos")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]


def tenant_name(db: Session, settings: Settings) -> str:
    identity = current_identity(settings)
    if current_tenant() is not None:
        return identity.name
    return settings_service.cached_settings(db).legal_name or identity.name


class TenantOut(BaseModel):
    slug: str
    name: str
    url: str
    multi_tenant: bool


class TenantProfileOut(BaseModel):
    """The industry this tenant registered as, and the modules that industry currently has switched on."""

    business_type: str
    enabled_modules: list[str]


@router.get("", response_model=TenantOut)
def tenant(settings: Annotated[Settings, Depends(get_settings)]) -> TenantOut:
    """Public: which store this subdomain belongs to (login and activation screens show its name)."""
    ref = current_tenant()
    if ref is None:
        return TenantOut(slug="default", name="AI POS", url=settings.public_base_url, multi_tenant=False)
    return TenantOut(slug=ref.slug, name=ref.name, url=tenant_public_url(ref.slug, settings), multi_tenant=True)


@router.get("/profile", response_model=TenantProfileOut)
def profile(db: Db, _: SignedIn, settings: Config) -> TenantProfileOut:
    modules = settings_service.tenant_modules(db, tenant_name(db, settings))
    return TenantProfileOut(business_type=modules.business_profile, enabled_modules=modules.enabled)


@router.get("/change-requests", response_model=list[ChangeRequestOut])
def list_change_requests(principal: CanManage, settings: Config) -> list[ChangeRequestOut]:
    return change_requests.list_for_tenant(settings)


@router.post("/change-requests", response_model=ChangeRequestOut, status_code=201)
def create_change_request(payload: ChangeRequestIn, db: Db, principal: CanManage, settings: Config) -> ChangeRequestOut:
    """Asks IT support for a business-type migration or a module outside this business type."""
    if principal.user is None or principal.user.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide admin can request this change.")
    return change_requests.create(db, settings, principal.user, payload)


@router.get("/modules", response_model=TenantModulesOut)
def modules(db: Db, principal: SignedIn, settings: Config) -> TenantModulesOut:
    """The business type (locked after onboarding) and the modules this store has on or can switch on."""
    return settings_service.tenant_modules(db, tenant_name(db, settings))
