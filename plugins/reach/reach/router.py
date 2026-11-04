"""Portal routes for AxizReach. Tenant id comes from the bound request, never the body."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from reach import connections, webhooks
from reach.schemas import (
    CampaignOut,
    CampaignWrite,
    ChannelOut,
    ChannelWrite,
    ConnectionCreate,
    ConnectionOut,
    CreditOut,
    CreditTransactionOut,
    GenerateOut,
    GenerateWrite,
    MediaOut,
    MediaWrite,
    OverviewOut,
    PreviewOut,
    PricesWrite,
    RecipientOut,
    ReviseWrite,
    SuggestionOut,
    TemplateOut,
    TemplateWrite,
)
from reach.service import (
    approve_and_send,
    cancel,
    delete_template,
    get_campaign,
    launch,
    list_campaigns,
    list_channels,
    list_templates,
    overview,
    pause,
    present_campaign,
    present_campaigns,
    preview,
    recipients,
    require_reach,
    resume,
    retry_failed,
    reject_campaign,
    revise_campaign,
    submit_for_approval,
    save_channel,
    save_prices,
    save_template,
    search_customers,
    test_channel,
)
from reach import credits as credit_book

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanManage = Annotated[Principal, Depends(authorize(Permission.MESSAGING_MANAGE))]


def _webhook_db(request: Request, settings: Config):
    if settings.tenancy_enabled:
        yield None
        return
    override = request.app.dependency_overrides.get(get_db)
    if override is not None:
        yield from override()
        return
    yield from get_db()


WebhookDb = Annotated[Session | None, Depends(_webhook_db)]


@router.get("/channels", response_model=list[ChannelOut])
def channels(db: Db, settings: Config, _: CanManage) -> list[dict]:
    return list_channels(db, settings)


@router.put("/channels", response_model=ChannelOut)
def save_channel_route(payload: ChannelWrite, db: Db, settings: Config, _: CanManage) -> dict:
    return save_channel(db, settings, payload.model_dump())


@router.post("/channels/{channel}/test", response_model=ChannelOut)
def test_channel_route(channel: str, db: Db, settings: Config, _: CanManage) -> dict:
    return test_channel(db, settings, channel)


@router.get("/overview", response_model=OverviewOut)
def overview_route(db: Db, _: CanManage) -> dict:
    return overview(db)


@router.put("/prices")
def prices(payload: PricesWrite, db: Db, _: CanManage) -> dict[str, int]:
    require_reach(db)
    return save_prices(db, payload.model_dump())


@router.get("/customers")
def customers(db: Db, _: CanManage, q: str = "", whatsapp_opt_in: bool = False, limit: int = 50) -> list[dict]:
    return search_customers(db, q, whatsapp_opt_in=whatsapp_opt_in, limit=limit)


@router.post("/campaigns/preview", response_model=PreviewOut)
def preview_route(payload: CampaignWrite, db: Db, _: CanManage) -> dict:
    return preview(db, payload.model_dump())


@router.get("/campaigns", response_model=list[CampaignOut])
def campaigns(db: Db, _: CanManage) -> list:
    return present_campaigns(db, list_campaigns(db))


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def campaign(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, get_campaign(db, campaign_id))


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def launch_route(payload: CampaignWrite, db: Db, principal: CanManage) -> dict:
    return present_campaign(db, launch(db, principal.user.id, payload.model_dump()))


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
def cancel_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, cancel(db, campaign_id))


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignOut)
def pause_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, pause(db, campaign_id))


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignOut)
def resume_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, resume(db, campaign_id))


@router.post("/campaigns/{campaign_id}/retry", response_model=CampaignOut)
def retry_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, retry_failed(db, campaign_id))


@router.post("/campaigns/{campaign_id}/submit-approval", response_model=CampaignOut)
def submit_approval_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, submit_for_approval(db, campaign_id))


@router.post("/campaigns/{campaign_id}/reject", response_model=CampaignOut)
def reject_route(campaign_id: UUID, db: Db, _: CanManage) -> dict:
    return present_campaign(db, reject_campaign(db, campaign_id))


@router.post("/campaigns/{campaign_id}/revise", response_model=CampaignOut)
def revise_route(campaign_id: UUID, payload: ReviseWrite, db: Db, _: CanManage) -> dict:
    content = {key: value.model_dump(mode="json") for key, value in payload.content.items()}
    audience = None if payload.audience is None else payload.audience.model_dump(mode="json")
    return present_campaign(db, revise_campaign(db, campaign_id, content, audience))


@router.post("/campaigns/{campaign_id}/approve-and-send", response_model=CampaignOut)
def approve_send_route(campaign_id: UUID, db: Db, principal: CanManage) -> dict:
    return present_campaign(db, approve_and_send(db, principal.user.id, campaign_id))


@router.post("/media", response_model=MediaOut, status_code=201)
def media_upload(payload: MediaWrite, db: Db, settings: Config, _: CanManage):
    import base64

    from reach.media_store import save_upload
    from reach.service import require_reach

    require_reach(db)
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except Exception as exc:
        from app.core.errors import ApiError

        raise ApiError(422, "corrupt_media", "The file could not be read.") from exc
    return save_upload(db, settings, payload.file_name, payload.mime_type, raw)


@router.get("/media/{asset_id}")
def media_download(asset_id: UUID, db: Db, _: CanManage) -> FileResponse:
    from reach.media_store import file_path
    from reach.models import ReachMediaAsset
    from reach.service import require_reach

    require_reach(db)
    row = db.get(ReachMediaAsset, asset_id)
    if row is None:
        from app.core.errors import ApiError

        raise ApiError(404, "not_found", "File not found.")
    return FileResponse(file_path(row), media_type=row.mime_type, filename=row.file_name)


@router.delete("/media/{asset_id}", status_code=204)
def media_delete(asset_id: UUID, db: Db, _: CanManage) -> None:
    from reach.media_store import remove
    from reach.service import require_reach

    require_reach(db)
    remove(db, asset_id)


@router.post("/ai/generate", response_model=GenerateOut)
def ai_generate(payload: GenerateWrite, db: Db, settings: Config, _: CanManage) -> dict:
    from reach.assistant import generate
    from reach.service import require_reach

    require_reach(db)
    return generate(db, settings, payload.model_dump())


@router.get("/suggestions", response_model=list[SuggestionOut])
def suggestion_list(db: Db, _: CanManage) -> list:
    from reach.suggestions import list_suggestions

    return list_suggestions(db)


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=SuggestionOut)
def suggestion_dismiss(suggestion_id: UUID, db: Db, _: CanManage):
    from reach.suggestions import dismiss

    return dismiss(db, suggestion_id)


@router.post("/suggestions/{suggestion_id}/draft", response_model=CampaignOut, status_code=201)
def suggestion_draft(suggestion_id: UUID, db: Db, principal: CanManage) -> dict:
    from reach.suggestions import draft_from_suggestion

    return present_campaign(db, draft_from_suggestion(db, principal.user.id, suggestion_id))


@router.get("/campaigns/{campaign_id}/recipients.csv")
def recipient_export(campaign_id: UUID, db: Db, _: CanManage) -> Response:
    from reach.service import get_campaign, recipients

    get_campaign(db, campaign_id)
    lines = ["phone,status,failure_reason"]
    for row in recipients(db, campaign_id, None, 1000):
        digits = "".join(ch for ch in (row.phone or "") if ch.isdigit())
        masked = f"****{digits[-4:]}" if len(digits) >= 4 else "****"
        reason = (row.failure_reason or "").replace('"', "'")
        lines.append(f"{masked},{row.status},\"{reason}\"")
    return Response("\n".join(lines), media_type="text/csv")


@router.get("/messages", response_model=list[RecipientOut])
def messages(db: Db, _: CanManage, campaign_id: UUID | None = None, status: str | None = None, limit: int = 50) -> list:
    return recipients(db, campaign_id, status, limit)


@router.get("/templates", response_model=list[TemplateOut])
def templates(db: Db, _: CanManage) -> list:
    return list_templates(db)


@router.put("/templates", response_model=TemplateOut)
def template_save(payload: TemplateWrite, db: Db, _: CanManage) -> object:
    return save_template(db, payload.model_dump())


@router.delete("/templates/{template_id}", status_code=204)
def template_delete(template_id: UUID, db: Db, _: CanManage) -> None:
    delete_template(db, template_id)


@router.get("/provider")
def provider(settings: Config, _: CanManage) -> dict:
    return connections.provider_health(settings)


@router.get("/connections", response_model=list[ConnectionOut])
def connection_list(db: Db, _: CanManage) -> list:
    return connections.published(db)


@router.post("/connections", response_model=ConnectionOut, status_code=201)
def connection_create(payload: ConnectionCreate, db: Db, settings: Config, _: CanManage) -> dict:
    return connections._public(connections.create_connection(db, settings, payload.name))


@router.post("/connections/{connection_id}/connect", response_model=ConnectionOut)
def connection_connect(connection_id: UUID, db: Db, settings: Config, _: CanManage) -> dict:
    return connections.connect(db, settings, connection_id)


@router.post("/connections/{connection_id}/status", response_model=ConnectionOut)
def connection_status(connection_id: UUID, db: Db, settings: Config, _: CanManage) -> dict:
    return connections.refresh_status(db, settings, connection_id)


@router.post("/connections/{connection_id}/disconnect", response_model=ConnectionOut)
def connection_disconnect(connection_id: UUID, db: Db, settings: Config, _: CanManage) -> dict:
    return connections.disconnect(db, settings, connection_id)


@router.get("/credits", response_model=CreditOut)
def credits(db: Db, _: CanManage) -> dict:
    require_reach(db)
    found = credit_book.snapshot(db)
    return found or {"balance": 0, "reserved": 0, "available": 0}


@router.get("/credits/transactions", response_model=list[CreditTransactionOut])
def credit_transactions(db: Db, _: CanManage) -> list:
    require_reach(db)
    return credit_book.transactions(db)


@router.post("/webhooks/evolution/{webhook_key}")
def evolution_webhook(
    webhook_key: str,
    payload: dict,
    settings: Config,
    db: WebhookDb,
    apikey: Annotated[str | None, Header()] = None,
) -> dict:
    if settings.tenancy_enabled or db is None:
        return webhooks.accept_across_tenants(settings, webhook_key, payload, apikey)
    return webhooks.accept(db, settings, webhook_key, payload, apikey)
