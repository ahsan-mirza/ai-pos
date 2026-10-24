import uuid

from sqlalchemy import select, update

from app.core.currency import BUSINESS_SETTINGS_ID
from app.core.permissions import SUPER_ADMIN_ROLE_ID
from app.models.brand import Brand
from app.models.business_settings import BusinessSettings
from app.models.role import Role
from app.services.rbac_service import ensure_system_roles
from app.services.settings_service import load_settings
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.scoping import DEFAULT_TENANT_ID


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


def test_first_store_claims_migrated_roles_and_the_next_store_gets_its_own(session):
    first, second = uuid.uuid4(), uuid.uuid4()
    super_admin = uuid.UUID(SUPER_ADMIN_ROLE_ID)

    with use_tenant(_ref(first)):
        ensure_system_roles(session)
        session.commit()
        session.expire_all()
        claimed = session.get(Role, super_admin)
        assert claimed is not None
        assert claimed.tenant_id == first
        assert claimed.permissions

    with use_tenant(_ref(second)):
        ensure_system_roles(session)
        session.commit()
        session.expire_all()
        assert session.get(Role, super_admin) is None
        own = session.scalar(select(Role).where(Role.is_system.is_(True), Role.name == "Super Admin"))
        assert own is not None
        assert own.id == uuid.uuid5(second, "Super Admin")
        assert own.tenant_id == second
        assert len(session.scalars(select(Role).where(Role.is_system.is_(True))).all()) == 4

    with use_tenant(_ref(first)):
        session.expire_all()
        ensure_system_roles(session)
        session.commit()
        assert session.get(Role, super_admin) is not None
        assert len(session.scalars(select(Role).where(Role.is_system.is_(True))).all()) == 4


def test_first_store_claims_migrated_settings_and_the_next_store_gets_its_own(session):
    session.add(BusinessSettings(id=BUSINESS_SETTINGS_ID, currency="AED", tenant_id=DEFAULT_TENANT_ID))
    session.commit()
    first, second = uuid.uuid4(), uuid.uuid4()

    with use_tenant(_ref(first)):
        claimed = load_settings(session)
        session.commit()
        session.expire_all()
        row = session.get(BusinessSettings, BUSINESS_SETTINGS_ID)
        assert row is not None
        assert claimed.id == BUSINESS_SETTINGS_ID
        assert row.tenant_id == first

    with use_tenant(_ref(second)):
        own = load_settings(session)
        session.commit()
        session.expire_all()
        assert own.id == uuid.uuid5(second, "business-settings")
        assert own.tenant_id == second
        assert session.get(BusinessSettings, BUSINESS_SETTINGS_ID) is None
