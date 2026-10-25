"""Two legacy SQLite databases copy into one shared database without mixing or duplicating rows."""

import os

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.models import Base
from app.models.product import Product
from app.tenancy import registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.merge import merge_tenant
from app.tenancy.models import ControlBase, Tenant
from app.tenancy.scoping import include_all_tenants


def _product(sku: str) -> Product:
    return Product(
        sku=sku,
        barcode=f"b-{sku}",
        name=sku,
        category="Phones",
        price_cents=1000,
        currency="AED",
    )


def test_merge_keeps_duplicate_skus_and_is_idempotent(tmp_path) -> None:
    previous = os.environ.get("DATABASE_URL")
    previous_control = os.environ.get("CONTROL_DATABASE_URL")
    shared = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared
    os.environ["CONTROL_DATABASE_URL"] = control_url
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    settings = get_settings()
    ControlBase.metadata.create_all(build_engine(control_url))
    Base.metadata.create_all(build_engine(shared))
    try:
        for slug in ("alpha", "bravo"):
            url = f"sqlite:///{(tmp_path / f'{slug}.db').as_posix()}"
            engine = build_engine(url)
            Base.metadata.create_all(engine)
            with registry.control_session(settings) as control:
                tenant = Tenant(
                    slug=slug,
                    name=slug,
                    status="active",
                    data_plane="legacy",
                    database_url_encrypted=registry.encrypt_database_url(url, settings),
                )
                control.add(tenant)
                control.commit()
                tenant_id = tenant.id
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            with factory() as db, use_tenant(
                TenantRef(id=str(tenant_id), slug=slug, name=slug, database_url=url, data_plane="legacy")
            ):
                db.add(_product("SHARED-SKU"))
                db.commit()
            engine.dispose()
        dry = merge_tenant(settings, "alpha", commit=False)
        assert dry["status"] == "ok"
        assert dry["tables"]["products"] == 1
        first = merge_tenant(settings, "alpha", commit=True)
        assert first["status"] == "ok"
        assert all(item["ok"] for item in first["checks"])
        second = merge_tenant(settings, "alpha", commit=True)
        assert second["status"] == "already_shared"
        other = merge_tenant(settings, "bravo", commit=True)
        assert other["status"] == "ok"
        dest = sessionmaker(bind=build_engine(shared), expire_on_commit=False)()
        try:
            with include_all_tenants(dest):
                rows = dest.scalars(select(Product).where(Product.sku == "SHARED-SKU")).all()
            assert len(rows) == 2
            assert len({row.tenant_id for row in rows}) == 2
        finally:
            dest.close()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        if previous_control is None:
            os.environ.pop("CONTROL_DATABASE_URL", None)
        else:
            os.environ["CONTROL_DATABASE_URL"] = previous_control
        get_settings.cache_clear()
        registry.invalidate()
        registry._control_factory.cache_clear()


def test_request_session_cannot_bypass_tenant_scope() -> None:
    from sqlalchemy.orm import Session

    from app.core.database import build_engine
    from app.tenancy.scoping import include_all_tenants

    session = Session(bind=build_engine("sqlite://"))
    session.info["request_session"] = True
    try:
        with include_all_tenants(session):
            pass
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    session.close()
