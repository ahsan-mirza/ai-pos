import uuid

from sqlalchemy import select, update

from app.models.brand import Brand
from app.tenancy.context import TenantRef, use_tenant


def _ref(tenant_id: uuid.UUID) -> TenantRef:
    return TenantRef(id=str(tenant_id), slug="store", name="Store", database_url="sqlite://")


def test_two_tenants_see_only_their_own_brand(session):
    first, second = uuid.uuid4(), uuid.uuid4()
    with use_tenant(_ref(first)):
        session.add(Brand(name="HP", code="HP"))
        session.commit()
    with use_tenant(_ref(second)):
        session.add(Brand(name="HP", code="HP"))
        session.commit()

    with use_tenant(_ref(first)):
        rows = session.scalars(select(Brand).where(Brand.name == "HP")).all()
        assert [row.tenant_id for row in rows] == [first]
    with use_tenant(_ref(second)):
        rows = session.scalars(select(Brand).where(Brand.name == "HP")).all()
        assert [row.tenant_id for row in rows] == [second]


def test_scoped_session_cannot_update_another_tenants_brand(session):
    first, second = uuid.uuid4(), uuid.uuid4()
    with use_tenant(_ref(second)):
        brand = Brand(name="Dell", code="DELL", description="original")
        session.add(brand)
        session.commit()
        brand_id = brand.id

    with use_tenant(_ref(first)):
        result = session.execute(update(Brand).where(Brand.id == brand_id).values(name="Hacked"))
        session.commit()
        assert result.rowcount == 0
        session.expire_all()
        assert session.get(Brand, brand_id) is None

    with use_tenant(_ref(second)):
        loaded = session.get(Brand, brand_id)
        assert loaded is not None
        assert loaded.name == "Dell"
        loaded.description = "from-the-other-store"
    with use_tenant(_ref(first)):
        session.commit()
    with use_tenant(_ref(second)):
        session.expire_all()
        again = session.get(Brand, brand_id)
        assert again is not None
        assert again.description == "original"
