"""Laundry catalog and price quotes. Orders and production are separate later routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, authorize_any
from app.core.permissions import Permission
from app.models.laundry import LaundryGarmentType, LaundryPriceList, LaundryService, LaundryServiceCategory
from app.schemas.laundry import (
    BranchCapacityIn,
    BranchCapacityOut,
    LaundrySettingsIn,
    LaundrySettingsOut,
    NamedIn,
    NamedOut,
    PriceListIn,
    PriceListOut,
    QuoteIn,
    QuoteOut,
    RateIn,
    ServiceIn,
    ServiceOut,
    ServicePatch,
)
from app.services import laundry_catalog

router = APIRouter()
Catalogue = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_CATALOGUE))]
Configure = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_CONFIGURE))]
Reader = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
RegisterCatalog = Annotated[
    Principal,
    Depends(
        authorize_any(
            Permission.PORTAL_ACCESS,
            Permission.LAUNDRY_ORDERS_VIEW,
            Permission.LAUNDRY_ORDERS_CREATE,
            scopes=("portal", "pos"),
        )
    ),
]


def _service_out(row: LaundryService) -> ServiceOut:
    return ServiceOut(
        id=row.id,
        category_id=row.category_id,
        code=row.code,
        name=row.name,
        pricing_unit=row.pricing_unit,
        base_rate_cents=row.base_rate_cents,
        min_charge_cents=row.min_charge_cents,
        min_quantity=row.min_quantity,
        weight_precision=row.weight_precision,
        express_surcharge_cents=row.express_surcharge_cents,
        tax_category=row.tax_category,
        is_active=row.is_active,
        workflow_code=row.workflow_code,
    )


@router.get("/settings", response_model=LaundrySettingsOut)
def read_settings(_: Reader, db: Annotated[Session, Depends(get_db)]) -> LaundrySettingsOut:
    row = laundry_catalog.settings_row(db)
    db.commit()
    return row


@router.put("/settings", response_model=LaundrySettingsOut)
def write_settings(
    payload: LaundrySettingsIn, principal: Configure, db: Annotated[Session, Depends(get_db)]
) -> LaundrySettingsOut:
    return laundry_catalog.update_settings(
        db,
        modes=payload.operating_modes,
        tracking_mode=payload.tracking_mode,
        weight_precision=payload.weight_precision,
        express_daily_capacity=payload.express_daily_capacity,
        actor=principal.user,
    )


@router.post("/templates/{code}")
def apply_template(code: str, principal: Configure, db: Annotated[Session, Depends(get_db)]) -> dict:
    return laundry_catalog.apply_template(db, code, principal.user)


@router.get("/categories", response_model=list[NamedOut])
def list_categories(_: Reader, db: Annotated[Session, Depends(get_db)]) -> list[LaundryServiceCategory]:
    return list(
        db.scalars(
            select(LaundryServiceCategory).order_by(LaundryServiceCategory.display_order, LaundryServiceCategory.name)
        )
    )


@router.post("/categories", response_model=NamedOut)
def add_category(
    payload: NamedIn, principal: Catalogue, db: Annotated[Session, Depends(get_db)]
) -> LaundryServiceCategory:
    return laundry_catalog.create_category(db, code=payload.code, name=payload.name, actor=principal.user)


@router.get("/garments", response_model=list[NamedOut])
def list_garments(_: Reader, db: Annotated[Session, Depends(get_db)]) -> list[LaundryGarmentType]:
    return list(db.scalars(select(LaundryGarmentType).order_by(LaundryGarmentType.name)))


@router.post("/garments", response_model=NamedOut)
def add_garment(payload: NamedIn, principal: Catalogue, db: Annotated[Session, Depends(get_db)]) -> LaundryGarmentType:
    return laundry_catalog.create_garment(db, code=payload.code, name=payload.name, actor=principal.user)


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    _: RegisterCatalog,
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query()] = "",
    active: Annotated[bool | None, Query()] = None,
) -> list[ServiceOut]:
    statement = select(LaundryService).order_by(LaundryService.name)
    if q.strip():
        statement = statement.where(LaundryService.name.ilike(f"%{q.strip()}%"))
    if active is not None:
        statement = statement.where(LaundryService.is_active.is_(active))
    return [_service_out(row) for row in db.scalars(statement)]


@router.post("/services", response_model=ServiceOut)
def add_service(payload: ServiceIn, principal: Catalogue, db: Annotated[Session, Depends(get_db)]) -> ServiceOut:
    return _service_out(laundry_catalog.create_service(db, payload.model_dump(), principal.user))


@router.patch("/services/{service_id}", response_model=ServiceOut)
def edit_service(
    service_id: uuid.UUID, payload: ServicePatch, principal: Catalogue, db: Annotated[Session, Depends(get_db)]
) -> ServiceOut:
    return _service_out(
        laundry_catalog.update_service(db, service_id, payload.model_dump(exclude_unset=True), principal.user)
    )


@router.put("/branches/{store_id}/express-capacity", response_model=BranchCapacityOut)
def put_branch_capacity(
    store_id: uuid.UUID,
    payload: BranchCapacityIn,
    principal: Configure,
    db: Annotated[Session, Depends(get_db)],
) -> BranchCapacityOut:
    row = laundry_catalog.set_branch_capacity(db, store_id, payload.express_daily_capacity, principal.user)
    return BranchCapacityOut(id=row.id, store_id=row.store_id, express_daily_capacity=row.express_daily_capacity)


@router.get("/price-lists", response_model=list[PriceListOut])
def list_price_lists(_: Reader, db: Annotated[Session, Depends(get_db)]) -> list[LaundryPriceList]:
    return list(db.scalars(select(LaundryPriceList).order_by(LaundryPriceList.name)))


@router.post("/price-lists", response_model=PriceListOut)
def add_price_list(
    payload: PriceListIn, principal: Catalogue, db: Annotated[Session, Depends(get_db)]
) -> LaundryPriceList:
    return laundry_catalog.create_price_list(db, payload.model_dump(), principal.user)


@router.put("/price-lists/{price_list_id}/rates")
def put_rate(
    price_list_id: uuid.UUID, payload: RateIn, principal: Catalogue, db: Annotated[Session, Depends(get_db)]
) -> dict:
    row = laundry_catalog.set_rate(db, price_list_id, payload.service_id, payload.unit_price_cents, principal.user)
    return {"id": row.id, "unit_price_cents": row.unit_price_cents}


@router.post("/quotes", response_model=QuoteOut)
def price_quote(payload: QuoteIn, principal: Reader, db: Annotated[Session, Depends(get_db)]) -> QuoteOut:
    priced, price_list_id = laundry_catalog.quote_service(
        db,
        payload.service_id,
        quantity=payload.quantity,
        on=payload.on,
        store_id=payload.store_id,
        customer_id=payload.customer_id,
        price_list_id=payload.price_list_id,
        extras_cents=payload.extras_cents,
        express=payload.express,
        same_day=payload.same_day,
        special=payload.special,
        discount_cents=payload.discount_cents,
        discount_authorized=principal.has(Permission.POS_DISCOUNT),
    )
    return QuoteOut(**priced.__dict__, price_list_id=price_list_id)
