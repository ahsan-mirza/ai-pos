"""Public marketing-site contact. Listed in OPEN_PATHS so the landing page needs no tenant."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.console import site
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.schemas.site import SiteContactOut
from app.tenancy import registry

router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/contact", response_model=SiteContactOut)
def contact(settings: Config) -> SiteContactOut:
    if not settings.tenancy_enabled:
        raise ApiError(
            404,
            "site_unavailable",
            "The marketing site contact is available when the server hosts more than one store.",
        )
    with registry.control_session(settings) as db:
        found = site.read_contact(db)
        db.commit()
        return found
