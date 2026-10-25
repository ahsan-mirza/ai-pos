"""Starter catalog: categories, brands, and models, and no products."""

import uuid

from sqlalchemy import func, select

from app.models.brand import Brand, ProductModel
from app.models.category import Category
from app.models.product import Product
from app.services.taxonomy_service import ensure_taxonomy
from app.tenancy.context import TenantRef, use_tenant


def _ref(tenant_id: uuid.UUID) -> TenantRef:
    return TenantRef(id=str(tenant_id), slug="store", name="Store", database_url="sqlite://")


def test_taxonomy_inserts_once_and_stays_inside_its_profile(session):
    added = ensure_taxonomy(session, "electronics_wholesale")
    session.commit()

    assert added > 0
    assert session.scalar(select(func.count()).select_from(Product)) == 0
    assert session.scalar(select(Category).where(Category.name == "Phones")) is not None
    assert session.scalar(select(Brand).where(Brand.name == "Apple")) is not None
    assert session.scalar(select(ProductModel).where(ProductModel.name == "iPhone 16 Pro")) is not None

    categories = session.scalar(select(func.count()).select_from(Category))
    brands = session.scalar(select(func.count()).select_from(Brand))
    models = session.scalar(select(func.count()).select_from(ProductModel))
    phones = session.scalar(select(Category).where(Category.name == "Phones"))
    phones.description = "Kept by the merchant"
    session.commit()

    assert ensure_taxonomy(session, "electronics_wholesale") == 0
    session.commit()
    assert session.scalar(select(func.count()).select_from(Category)) == categories
    assert session.scalar(select(func.count()).select_from(Brand)) == brands
    assert session.scalar(select(func.count()).select_from(ProductModel)) == models
    assert session.get(Category, phones.id).description == "Kept by the merchant"

    restaurant = uuid.uuid4()
    with use_tenant(_ref(restaurant)):
        ensure_taxonomy(session, "restaurant")
        session.commit()
        names = set(session.scalars(select(Category.name)).all())
        assert "Grill" in names
        assert "Phones" not in names
        assert session.scalar(select(func.count()).select_from(Product)) == 0
