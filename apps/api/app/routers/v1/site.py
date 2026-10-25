"""Public marketing-site contact. Listed in OPEN_PATHS so the landing page needs no tenant."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.console import site
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.schemas.site import SiteContactOut
from app.tenancy import registry

router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/contact", response_model=SiteContactOut)
def contact(settings: Config, response: Response) -> SiteContactOut:
    """Click-to-chat settings for the marketing site. Browsers revalidate; this process caches the row."""
    response.headers["Cache-Control"] = "no-cache"
    if not settings.tenancy_enabled:
        raise ApiError(
            404,
            "site_unavailable",
            "The marketing site contact is available when the server hosts more than one store.",
        )
    with registry.control_session(settings) as db:
        cached = site.lookup_contact(db)
        if cached is not None:
            return cached
        found = site.read_contact(db)
        db.commit()
        site.remember_contact(db, found)
        return found
