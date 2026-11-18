"""Public hardware catalogue on the registry connection."""

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import create_engine, inspect, select, text  # noqa: TID251
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from tests.governance_support import OPERATOR_PASSWORD, platform  # noqa: F401

from app.console.public_catalog import component_value
from app.models.base import TenantScoped
from app.models.product import Product
from app.tenancy.context import CONTROL_SESSION
from app.tenancy.models import BillingPlan, ControlBase, HardwareItem, OperatorAuditLog
from app.tenancy.public_hardware import (
    PublicHardwareCategory,
    PublicHardwarePackage,
    PublicHardwareProduct,
)
from app.tenancy.registry import control_version_table

API = Path(__file__).resolve().parents[1]
REASON = "Catalogue update"


def test_catalogue_models_are_registry_records_without_tenant_id() -> None:
    for model in (PublicHardwareCategory, PublicHardwareProduct, PublicHardwarePackage):
        assert issubclass(model, ControlBase)
        assert not issubclass(model, TenantScoped)
        assert "tenant_id" not in model.__table__.columns
    assert "tenant_id" in Product.__table__.columns
    assert "tenant_id" not in HardwareItem.__table__.columns
    assert control_version_table("postgresql://localhost/ai_pos", "postgresql://localhost/ai_pos") == (
        "control_alembic_version"
    )


def test_component_value_hides_savings_when_prices_or_currencies_are_incomplete() -> None:
    assert component_value([(1, 1000, "AED", False), (1, 500, "AED", False)], "AED", 1200) == (1500, 300)
    assert component_value([(1, 1000, "AED", False)], "AED", 1000) == (1000, None)
    assert component_value([(1, None, "AED", False)], "AED", 1000) == (None, None)
    assert component_value([(1, 1000, "USD", False)], "AED", 500) == (None, None)
    assert component_value([(2, 1000, "AED", True)], "AED", 100) == (0, None)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "orange").save(buffer, "PNG")
    return buffer.getvalue()


def _category(admin, client, name="POS Terminals") -> dict:
    response = client.post(
        "/api/v1/super-admin/hardware-catalog/categories",
        headers=admin,
        json={"name": name, "description": "Counters", "display_order": 1, "is_active": True, "reason": REASON},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product(admin, client, category_id: str, **extra) -> dict:
    body = {
        "category_id": category_id,
        "name": "Counter Terminal",
        "sku": "POS-15",
        "brand": "Axiz",
        "model_number": "T15",
        "short_description": "15 inch terminal",
        "full_description": "A counter terminal for the shop floor.",
        "display_price_fils": 189900,
        "purchase_price_fils": 120000,
        "warranty_months": 12,
        "stock_status": "in_stock",
        "specifications": [{"label": "RAM", "value": "8 GB"}],
        "compatibility": "Works with the AxizPOS register.",
        "reason": REASON,
    }
    body.update(extra)
    response = client.post("/api/v1/super-admin/hardware-catalog/products", headers=admin, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_support_cannot_change_the_catalogue_and_admins_can(platform) -> None:  # noqa: F811
    with platform.control() as db:
        assert db.info.get(CONTROL_SESSION) is True
    support = platform.operator("support-hw@axizpos.com", "SUPPORT")
    admin = platform.operator("admin-hw@axizpos.com", "ADMIN")
    assert platform.client.get("/api/v1/super-admin/hardware-catalog/overview").status_code == 401
    denied = platform.client.post(
        "/api/v1/super-admin/hardware-catalog/categories",
        headers=support,
        json={"name": "Scanners", "reason": REASON},
    )
    assert denied.status_code == 403
    created = _category(admin, platform.client)
    assert created["slug"] == "pos-terminals"
    overview = platform.client.get("/api/v1/super-admin/hardware-catalog/overview", headers=support)
    assert overview.status_code == 200
    assert overview.json()["categories"] == 1
    again = platform.client.post(
        "/api/v1/super-admin/hardware-catalog/categories",
        headers=admin,
        json={"name": "POS Terminals", "reason": REASON},
    )
    assert again.status_code == 201
    assert again.json()["slug"] != created["slug"]


def test_product_publish_image_package_and_public_visibility(platform) -> None:  # noqa: F811
    admin = platform.operator("catalog-admin@axizpos.com", "ADMIN")
    category = _category(admin, platform.client, "Receipt Printers")
    draft = _product(admin, platform.client, category["id"], sku="PRN-80", name="80mm Printer")
    assert draft["purchase_price_fils"] == 120000
    assert draft["is_published"] is False
    hidden = platform.client.get("/api/v1/public/hardware/products")
    assert hidden.status_code == 200
    assert hidden.json() == []
    missing = platform.client.get(f"/api/v1/public/hardware/products/{draft['slug']}")
    assert missing.status_code == 404
    uploaded = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/images",
        headers=admin,
        files={"file": ("printer.png", _png(), "image/png")},
        data={"alt": "Front of the printer", "reason": REASON},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["images"][0]["is_primary"] is True
    assert uploaded.json()["images"][0]["url"].endswith(".webp")
    rejected = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/images",
        headers=admin,
        files={"file": ("note.exe", b"MZ-not-an-image", "image/png")},
        data={"reason": REASON},
    )
    assert rejected.status_code == 415
    conflict = platform.client.post(
        "/api/v1/super-admin/hardware-catalog/products",
        headers=admin,
        json={"category_id": category["id"], "name": "Other", "sku": "PRN-80", "reason": REASON},
    )
    assert conflict.status_code == 409
    published = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    assert published.status_code == 200, published.text
    public = platform.client.get(f"/api/v1/public/hardware/products/{draft['slug']}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["display_price_fils"] == 189900
    assert "purchase_price" not in public.text
    assert body["specifications"] == [{"label": "RAM", "value": "8 GB"}]
    assert body["images"][0]["alt"] == "Front of the printer"
    drawer = _product(
        admin,
        platform.client,
        category["id"],
        sku="DRW-1",
        name="Cash Drawer",
        display_price_fils=9900,
        purchase_price_fils=4000,
    )
    platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{drawer['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    plan_id = None
    with platform.control() as db:
        plan = BillingPlan(code="HW-STANDARD", name="Standard", monthly_fils=9900, included_registers=1, active=True)
        db.add(plan)
        db.commit()
        plan_id = str(plan.id)
    package = platform.client.post(
        "/api/v1/super-admin/hardware-catalog/packages",
        headers=admin,
        json={
            "name": "Retail Counter",
            "package_type": "hardware_software",
            "billing_plan_id": plan_id,
            "display_price_fils": 150000,
            "is_featured": True,
            "items": [
                {"product_id": draft["id"], "quantity": 1, "is_optional": False},
                {"product_id": drawer["id"], "quantity": 1, "is_optional": False},
            ],
            "reason": REASON,
        },
    )
    assert package.status_code == 201, package.text
    assert package.json()["component_value_fils"] == 189900 + 9900
    assert package.json()["savings_fils"] == 189900 + 9900 - 150000
    assert package.json()["plan"]["monthly_fils"] == 9900
    blocked = platform.client.post(
        "/api/v1/super-admin/hardware-catalog/packages",
        headers=admin,
        json={
            "name": "Incomplete",
            "items": [{"product_id": draft["id"], "quantity": 1}],
            "reason": REASON,
        },
    )
    assert blocked.status_code == 201, blocked.text
    refused = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/unpublish",
        headers=admin,
        json={"reason": REASON},
    )
    assert refused.status_code == 200
    unpublished = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/packages/{blocked.json()['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    assert unpublished.status_code == 409
    platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    published_package = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/packages/{package.json()['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    assert published_package.status_code == 200, published_package.text
    listed = platform.client.get("/api/v1/public/hardware/packages")
    assert listed.json()[0]["slug"] == "retail-counter"
    detail = platform.client.get("/api/v1/public/hardware/packages/retail-counter")
    assert detail.status_code == 200
    assert detail.json()["plan"]["code"] == "HW-STANDARD"
    assert "purchase_price" not in detail.text
    kept = platform.client.delete(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}",
        headers=admin,
        params={"reason": REASON},
    )
    assert kept.status_code == 409
    archived = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{draft['id']}/archive",
        headers=admin,
        json={"reason": REASON},
    )
    assert archived.status_code == 200
    assert platform.client.get(f"/api/v1/public/hardware/products/{draft['slug']}").status_code == 404
    with platform.control() as db:
        actions = {row.action for row in db.scalars(select(OperatorAuditLog))}
    assert "public_hardware.product_publish" in actions
    assert "public_hardware.package_create" in actions
    assert "hardware.item.create" not in actions


def test_enquiries_are_rate_limited_private_and_status_audited(platform) -> None:  # noqa: F811
    admin = platform.operator("enquiry-admin@axizpos.com", "ADMIN")
    support = platform.operator("enquiry-support@axizpos.com", "SUPPORT")
    category = _category(admin, platform.client, "Barcode Scanners")
    product = _product(admin, platform.client, category["id"], sku="SCN-1", name="Scanner", display_price_fils=4900)
    platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/products/{product['id']}/publish",
        headers=admin,
        json={"reason": REASON},
    )
    payload = {
        "customer_name": "Noor Ali",
        "business_name": "Noor Grocery",
        "email": "noor@example.com",
        "phone": "+971501112233",
        "country": "United Arab Emirates",
        "business_type": "supermarket",
        "enquiry_type": "product",
        "product_slug": product["slug"],
        "quantity": 2,
        "message": "Please quote two scanners for the grocery checkout.",
        "source": "/hardware/barcode-scanners",
    }
    created = platform.client.post("/api/v1/public/hardware/enquiries", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["reference"].startswith("PHW-")
    assert "id" not in created.json()
    duplicate = platform.client.post("/api/v1/public/hardware/enquiries", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["reference"] == created.json()["reference"]
    draft = platform.client.post(
        "/api/v1/public/hardware/enquiries",
        json={**payload, "product_slug": "missing-sku", "message": "A different note about hardware."},
    )
    assert draft.status_code == 422
    bad = platform.client.post(
        "/api/v1/public/hardware/enquiries",
        json={**payload, "email": "not-an-email", "message": "Another hardware question."},
    )
    assert bad.status_code == 422
    rows = platform.client.get("/api/v1/super-admin/hardware-catalog/enquiries", headers=support)
    assert rows.status_code == 200
    assert rows.headers["x-total-count"] == "1"
    found = rows.json()[0]
    assert found["email"] == "noor@example.com"
    updated = platform.client.put(
        f"/api/v1/super-admin/hardware-catalog/enquiries/{found['id']}",
        headers=support,
        json={"status": "contacted", "reason": "Called the shop"},
    )
    assert updated.status_code == 200
    noted = platform.client.post(
        f"/api/v1/super-admin/hardware-catalog/enquiries/{found['id']}/notes",
        headers=support,
        json={"body": "Asked for a site visit.", "reason": "Internal follow-up"},
    )
    assert noted.json()["notes"][0]["body"] == "Asked for a site visit."
    public_again = platform.client.get("/api/v1/public/hardware/products")
    assert "site visit" not in public_again.text
    for index in range(6):
        platform.client.post(
            "/api/v1/public/hardware/enquiries",
            json={**payload, "email": f"shop{index}@example.com", "message": f"Quote request number {index} please."},
        )
    limited = platform.client.post(
        "/api/v1/public/hardware/enquiries",
        json={**payload, "email": "last@example.com", "message": "One more quote for the same counter."},
    )
    assert limited.status_code == 429
    with platform.control() as db:
        assert (
            db.scalar(select(OperatorAuditLog).where(OperatorAuditLog.action == "public_hardware.enquiry_status"))
            is not None
        )


def test_existing_hardware_catalogue_route_still_answers(platform) -> None:  # noqa: F811
    admin = platform.operator("legacy-hw@axizpos.com", "ADMIN")
    response = platform.client.get("/api/v1/super-admin/hardware/items", headers=admin)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_public_hardware_migration_upgrades_and_downgrades(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    engine = create_engine(url)
    ControlBase.metadata.create_all(engine)
    with engine.begin() as connection:
        for name in (
            "public_hardware_enquiry_notes",
            "public_hardware_enquiries",
            "public_hardware_product_images",
            "public_hardware_package_items",
            "public_hardware_packages",
            "public_hardware_products",
            "public_hardware_categories",
        ):
            connection.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    engine.dispose()
    config = Config(str(API / "alembic_control.ini"))
    config.set_main_option("script_location", str(API / "alembic_control"))
    config.attributes["database_url"] = url
    command.stamp(config, "control_0039")
    command.upgrade(config, "head")
    names = set(inspect(create_engine(url)).get_table_names())
    assert "public_hardware_products" in names
    assert "hardware_items" in names
    command.downgrade(config, "control_0039")
    names = set(inspect(create_engine(url)).get_table_names())
    assert "public_hardware_products" not in names
    assert "public_hardware_enquiries" not in names
    assert "hardware_items" in names
    assert "billing_plans" in names
    command.upgrade(config, "head")
    engine.dispose()


def test_duplicate_sku_is_rejected_by_the_database(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'sku.db').as_posix()}"
    engine = create_engine(url)
    ControlBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        category = PublicHardwareCategory(name="Drawers", slug="drawers")
        db.add(category)
        db.flush()
        db.add(PublicHardwareProduct(category_id=category.id, name="One", slug="one", sku="DR-1", specifications=[]))
        db.commit()
        db.add(PublicHardwareProduct(category_id=category.id, name="Two", slug="two", sku="DR-1", specifications=[]))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(PublicHardwareProduct).where(PublicHardwareProduct.sku == "DR-1")).name == "One"
    engine.dispose()
