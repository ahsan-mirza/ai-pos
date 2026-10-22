import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.price_lists import (
    CsvImportIn,
    CsvImportResult,
    CustomerGroupIn,
    CustomerGroupOut,
    CustomerPricingOut,
    PriceChangeIn,
    PriceChangeOut,
    PriceListIn,
    PriceListItemsIn,
    PriceListOut,
    PriceListRow,
    PriceListScope,
)
from app.services import labels_service, price_list_service
from app.services.labels_service import Layout

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_PRICING_MANAGE))]
# Registers fetch an attached customer's own and group prices to cache for offline use.
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]


@router.get("", response_model=list[PriceListRow])
def list_price_lists(
    db: Db, _: CanRead, scope: PriceListScope | None = None, scope_id: uuid.UUID | None = None
) -> list[PriceListRow]:
    return price_list_service.list_price_lists(db, scope, scope_id)


@router.post("", response_model=PriceListOut, status_code=201)
def create_price_list(payload: PriceListIn, db: Db, principal: CanManage) -> PriceListOut:
    return price_list_service.save_price_list(db, principal, payload)


@router.get("/groups", response_model=list[CustomerGroupOut])
def list_groups(db: Db, _: CanRead) -> list[CustomerGroupOut]:
    return price_list_service.list_groups(db)


@router.post("/groups", response_model=CustomerGroupOut, status_code=201)
def create_group(payload: CustomerGroupIn, db: Db, principal: CanManage) -> CustomerGroupOut:
    return price_list_service.save_group(db, principal, payload)


@router.put("/groups/{group_id}", response_model=CustomerGroupOut)
def update_group(group_id: uuid.UUID, payload: CustomerGroupIn, db: Db, principal: CanManage) -> CustomerGroupOut:
    return price_list_service.save_group(db, principal, payload, group_id)


@router.get("/changes", response_model=list[PriceChangeOut])
def list_changes(db: Db, _: CanRead) -> list[PriceChangeOut]:
    return price_list_service.list_changes(db)


@router.post("/changes", response_model=PriceChangeOut, status_code=201)
def create_change(payload: PriceChangeIn, db: Db, principal: CanManage) -> PriceChangeOut:
    return price_list_service.create_change(db, principal, payload)


@router.get("/changes/{change_id}", response_model=PriceChangeOut)
def get_change(change_id: uuid.UUID, db: Db, _: CanRead) -> PriceChangeOut:
    return price_list_service.get_change(db, change_id)


@router.post("/changes/{change_id}/cancel", response_model=PriceChangeOut)
def cancel_change(change_id: uuid.UUID, db: Db, principal: CanManage) -> PriceChangeOut:
    return price_list_service.cancel_change(db, principal, change_id)


@router.post("/changes/{change_id}/apply", response_model=PriceChangeOut)
def apply_change(change_id: uuid.UUID, db: Db, principal: CanManage) -> PriceChangeOut:
    return price_list_service.apply_now(db, principal, change_id)


@router.get("/changes/{change_id}/labels.pdf", response_class=Response)
def change_labels(
    change_id: uuid.UUID, db: Db, _: CanRead, layout: Layout = "a4_3x8", show_price: bool = True
) -> Response:
    content = labels_service.for_products(
        db, price_list_service.label_items(db, change_id), layout=layout, show_price=show_price
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="price-change-labels.pdf"'},
    )


@router.get("/customers/{customer_id}", response_model=CustomerPricingOut)
def customer_pricing(customer_id: uuid.UUID, db: Db, _: AtRegister) -> CustomerPricingOut:
    return price_list_service.customer_pricing(db, customer_id)


@router.get("/{list_id}", response_model=PriceListOut)
def get_price_list(list_id: uuid.UUID, db: Db, _: CanRead) -> PriceListOut:
    return price_list_service.get_price_list(db, list_id)


@router.put("/{list_id}", response_model=PriceListOut)
def update_price_list(list_id: uuid.UUID, payload: PriceListIn, db: Db, principal: CanManage) -> PriceListOut:
    return price_list_service.save_price_list(db, principal, payload, list_id)


@router.delete("/{list_id}", status_code=204)
def delete_price_list(list_id: uuid.UUID, db: Db, principal: CanManage) -> Response:
    price_list_service.delete_price_list(db, principal, list_id)
    return Response(status_code=204)


@router.put("/{list_id}/items", response_model=PriceListOut)
def put_items(list_id: uuid.UUID, payload: PriceListItemsIn, db: Db, principal: CanManage) -> PriceListOut:
    return price_list_service.put_items(db, principal, list_id, payload.items)


@router.post("/{list_id}/import", response_model=CsvImportResult)
def import_csv(list_id: uuid.UUID, payload: CsvImportIn, db: Db, principal: CanManage) -> CsvImportResult:
    return price_list_service.import_csv(db, principal, list_id, payload)


@router.get("/{list_id}/export.csv", response_class=Response)
def export_csv(list_id: uuid.UUID, db: Db, _: CanRead, download: bool = Query(default=True)) -> Response:
    name, content = price_list_service.export_csv(db, list_id)
    safe = "".join(char if char.isalnum() else "-" for char in name).strip("-").lower() or "price-list"
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'{disposition}; filename="{safe}.csv"'},
    )
