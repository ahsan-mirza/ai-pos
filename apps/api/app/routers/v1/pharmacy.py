"""Pharmacy catalogue. Tenant comes from the signed-in session, never from the request body."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize_any
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.inventory import ProductCreate, ProductUpdate
from app.schemas.payloads import ProductOut
from app.schemas.pharmacy import PharmacyProductOut
from app.services import inventory, pharmacy_catalog
from app.services.settings_service import business_currency

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanCatalogue = Annotated[
    Principal,
    Depends(authorize_any(Permission.PORTAL_INVENTORY_MANAGE, Permission.PHARMACY_CATALOGUE)),
]


@router.get("/products", response_model=list[PharmacyProductOut])
def list_products(
    db: Db,
    _: CanCatalogue,
    q: Annotated[str, Query(max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PharmacyProductOut]:
    return pharmacy_catalog.list_products(db, query=q, limit=limit)


@router.get("/products/{product_id}", response_model=PharmacyProductOut)
def get_product(product_id: uuid.UUID, db: Db, _: CanCatalogue) -> PharmacyProductOut:
    return pharmacy_catalog.get_product(db, product_id)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Db, principal: CanCatalogue) -> ProductOut:
    if payload.pharmacy is None:
        raise ApiError(422, "pharmacy_required", "A pharmacy product needs its medicine details.")
    return inventory.create_product(db, principal, payload, business_currency(db))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, payload: ProductUpdate, db: Db, principal: CanCatalogue) -> ProductOut:
    if payload.pharmacy is None:
        raise ApiError(422, "pharmacy_required", "Send the pharmacy details to update this product.")
    actor = None if principal.user is None else principal.user.id
    return inventory.update_product(db, product_id, payload, user_id=actor)
