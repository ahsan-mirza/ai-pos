"""Production demo tenants: provisioning, catalog, and the restricted portal user.

Passwords are generated, hashed, and discarded. Nothing in this module returns a credential.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import build_engine
from app.core.deps import Principal
from app.core.permissions import Permission
from app.core.security import hash_password
from app.models.batch import Supplier
from app.models.brand import Brand, ProductModel
from app.models.category import Category, SubCategory
from app.models.customer import Customer
from app.models.menu import ModifierGroup, ProductModifierGroup
from app.models.product import Product
from app.models.purchasing import PurchaseOrder
from app.models.recipe import Recipe
from app.models.restaurant import DiningArea, DiningTable, OpenOrder, OpenOrderItem
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.models.warranty import WarrantyPolicy
from app.schemas.auth import UserCreate
from app.schemas.batches import SupplierCreate
from app.schemas.inventory import (
    BrandWrite,
    CategoryWrite,
    ManualAdjustment,
    ProductCreate,
    ProductModelWrite,
    PurchaseOrderCreate,
    PurchaseOrderLineIn,
    ReceiveLineIn,
    ReceiveRequest,
    SerialInput,
)
from app.schemas.loyalty import LoyaltySettingsWrite
from app.schemas.menu import ModifierGroupIn, ModifierOptionIn, ProductGroupsIn
from app.schemas.orders import DiningAreaIn, DiningTableIn, OrderAction, OrderCreate, OrderItemIn
from app.schemas.payloads import ModifierChoice
from app.schemas.pharmacy import IngredientWrite, PharmacyWrite
from app.schemas.promotions import PromotionWrite
from app.schemas.recipes import RecipeIn, RecipeLineIn
from app.schemas.store_credit import GiftCardIssue
from app.schemas.variants import MatrixAxis, MatrixVariantDraft, MatrixWrite
from app.schemas.warranty import PolicyWrite
from app.schemas.wholesale import CustomerWrite
from app.services import (
    brand_service,
    category_service,
    customer_service,
    gift_card_service,
    inventory,
    loyalty_service,
    menu_service,
    order_service,
    promotion_service,
    rbac_service,
    recipe_service,
    variant_matrix_service,
    warranty_service,
)
from app.services.import_batch_service import create_supplier
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import provisioning, registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import Tenant

_SPEC = Path(__file__).resolve().parents[4] / "packages" / "catalog" / "production-demos.json"
_OPENING = "demo-opening"
_NAMESPACE = uuid.UUID("018f5a2e-7c3b-7a1e-9c4d-0b6e2f1a8d30")
EXPLORER_USERNAME = "explorer"


class DemoSeedError(RuntimeError):
    """A demo tenant could not be provisioned or its catalog could not be loaded."""


@cache
def load_spec() -> dict:
    return json.loads(_SPEC.read_text(encoding="utf-8"))


def demo_tenants() -> list[dict]:
    return list(load_spec()["tenants"])


def tenant_spec(code: str) -> dict:
    for spec in demo_tenants():
        if spec["code"] == code:
            return spec
    raise DemoSeedError(f"Unknown demo business code {code!r}.")


def _ref(tenant: Tenant, settings: Settings) -> TenantRef:
    return TenantRef(
        id=str(tenant.id),
        slug=tenant.slug,
        name=tenant.name,
        database_url=settings.database_url,
        data_plane="shared",
    )


def _session(settings: Settings, tenant: Tenant) -> Session:
    return sessionmaker(bind=build_engine(settings.database_url), expire_on_commit=False)()


def _principal(user: User) -> Principal:
    return Principal(kind="user", scope="portal", user=user, permissions=frozenset(user.permissions))


def _named(db: Session, model: type, name: str):
    return db.scalar(select(model).where(func.lower(model.name) == name.lower()))


def _category(db: Session, name: str) -> Category:
    found = _named(db, Category, name)
    if found is None:
        category_service.create_category(db, CategoryWrite(name=name, description=""))
        found = _named(db, Category, name)
    if found is None:
        raise DemoSeedError(f"Category {name!r} was not created.")
    return found


def _sub(db: Session, category: Category, name: str) -> SubCategory:
    found = db.scalar(
        select(SubCategory).where(
            SubCategory.category_id == category.id,
            func.lower(SubCategory.name) == name.lower(),
        )
    )
    if found is None:
        category_service.create_sub_category(db, category.id, CategoryWrite(name=name, description=""))
        found = db.scalar(
            select(SubCategory).where(
                SubCategory.category_id == category.id,
                func.lower(SubCategory.name) == name.lower(),
            )
        )
    if found is None:
        raise DemoSeedError(f"Sub-category {name!r} was not created.")
    return found


def _product(db: Session, sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.sku == sku))


def _owner(db: Session) -> User:
    user = db.scalar(select(User).join(Role).where(Role.name == "Super Admin", Role.is_system.is_(True)))
    if user is None:
        raise DemoSeedError("The demo Super Admin was not created.")
    return user


def _mark(settings: Settings, spec: dict) -> Tenant:
    with registry.control_session(settings) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if tenant is None:
            raise DemoSeedError(f"{spec['slug']} was not registered.")
        if not tenant.is_demo and tenant.demo_business_type not in (None, spec["code"]):
            raise DemoSeedError(f"{spec['slug']} is not a demo tenant.")
        if tenant.demo_status in {"disabled", "resetting", "reset_failed"}:
            raise DemoSeedError(f"{spec['slug']} is {tenant.demo_status}.")
        tenant.is_demo = True
        tenant.demo_business_type = spec["code"]
        tenant.demo_status = "active"
        tenant.demo_access_enabled = False
        tenant.practice_mode = False
        tenant.demo_seed_version = int(load_spec()["version"])
        db.commit()
        db.refresh(tenant)
        db.expunge(tenant)
        return tenant


def _provision(settings: Settings, spec: dict) -> Tenant:
    with registry.control_session(settings) as db:
        existing = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if existing is not None and not existing.is_demo:
            raise DemoSeedError(f"{spec['slug']} already belongs to a live store.")
    plain = secrets.token_urlsafe(18)
    job = provisioning.Job(
        request_id=uuid.uuid4(),
        settings=settings,
        slug=spec["slug"],
        store_name=spec["name"],
        profile=spec["profile"],
        sub_type=spec["sub_type"],
        currency=spec["currency"],
        trn=spec["trn"],
        email=f"owner@{spec['slug']}.example.com",
        full_name=f"{spec['name']} Owner",
        password_hash=hash_password(plain),
        tenant_id=None,
        owner_username=None,
        country=spec["country"],
        address="Demo District",
    )
    del plain
    provisioning.step_migrations(job)
    provisioning.step_register(job)
    tenant = _mark(settings, spec)
    ref = _ref(tenant, settings)
    engine = build_engine(settings.database_url)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        with use_tenant(ref):
            rbac_service.ensure_system_roles(db)
            db.commit()
    finally:
        db.close()
    provisioning.step_owner(job)
    provisioning.step_settings(job)
    clear_settings_cache()
    return tenant


def _explorer(db: Session, settings: Settings, spec: dict, actor: User) -> None:
    if db.scalar(select(User.id).where(User.username == EXPLORER_USERNAME)) is not None:
        return
    role = db.scalar(select(Role).where(Role.is_system.is_(True), Role.name == "Demo Explorer"))
    if role is None:
        raise DemoSeedError("Demo Explorer role is missing.")
    password = secrets.token_urlsafe(18)
    pin = f"{1000 + secrets.randbelow(9000)}"
    rbac_service.create_user(
        db,
        settings,
        _principal(actor),
        UserCreate(
            username=EXPLORER_USERNAME,
            email=f"explorer@{spec['slug']}.example.com",
            full_name=f"{spec['name']} Explorer",
            role_id=role.id,
            password=password,
            pin=pin,
            has_pos_access=True,
            has_portal_access=True,
        ),
    )
    del password, pin


def _customers(db: Session, spec: dict) -> None:
    for row in spec["customers"]:
        if _named(db, Customer, row["name"]) is not None:
            continue
        customer_service.create_customer(
            db,
            CustomerWrite(
                name=row["name"],
                customer_type=row["type"],
                credit_limit_cents=int(row.get("credit_limit_cents") or 0),
                payment_terms="NET_30" if row["type"] == "WHOLESALE" else "DUE_ON_RECEIPT",
            ),
        )


def _pharmacy(row: dict) -> PharmacyWrite | None:
    block = row.get("pharmacy")
    if not block:
        return None
    return PharmacyWrite(
        product_kind=block["product_kind"],
        dispensing_class=block["dispensing_class"],
        generic_name=block.get("generic_name") or "",
        manufacturer=block.get("manufacturer") or "",
        dosage_form=block.get("dosage_form") or "",
        route=block.get("route") or "",
        strength_amount=block.get("strength_amount"),
        strength_unit=block.get("strength_unit") or "",
        pack_size_label=block.get("pack_size_label") or "",
        units_per_pack=int(block.get("units_per_pack") or 1),
        gtin=row["barcode"],
        ingredients=[
            IngredientWrite(
                name=item["name"],
                strength_amount=item.get("strength_amount"),
                strength_unit=item.get("strength_unit") or "",
            )
            for item in block.get("ingredients") or []
        ],
    )


def _products(db: Session, spec: dict, actor: Principal) -> None:
    for row in spec["products"]:
        if _product(db, row["sku"]) is not None:
            continue
        category = _category(db, row["category"])
        inventory.create_product(
            db,
            actor,
            ProductCreate(
                sku=row["sku"],
                barcode=row["barcode"],
                name=row["name"],
                category_id=category.id,
                price_cents=int(row["price_cents"]),
                price_includes_tax=bool(row.get("includes_tax")),
                is_serialized=bool(row.get("serial")),
                sold_by_weight=bool(row.get("weighed")),
                plu_code=row.get("plu"),
                is_ingredient=bool(row.get("ingredient")),
                item_type="RAW_INGREDIENT" if row.get("ingredient") else "PRE_PACKAGED",
                pharmacy=_pharmacy(row),
            ),
            spec["currency"],
        )


def _matrix(db: Session, spec: dict, store: Store, user: User) -> None:
    block = spec.get("variants")
    if not block:
        return
    if _product(db, block["rows"][0]["sku"]) is not None:
        return
    category = _category(db, block["category"])
    sub = _sub(db, category, block["sub_category"])
    brand = _named(db, Brand, block["brand"])
    if brand is None:
        brand_service.create_brand(db, BrandWrite(name=block["brand"], description=""))
        brand = _named(db, Brand, block["brand"])
    if brand is None:
        raise DemoSeedError(f"Brand {block['brand']!r} was not created.")
    model = db.scalar(
        select(ProductModel).where(ProductModel.brand_id == brand.id, ProductModel.name == block["model"])
    )
    if model is None:
        brand_service.create_model(
            db,
            ProductModelWrite(brand_id=brand.id, sub_category_id=sub.id, name=block["model"]),
        )
        model = db.scalar(
            select(ProductModel).where(ProductModel.brand_id == brand.id, ProductModel.name == block["model"])
        )
    if model is None:
        raise DemoSeedError(f"Model {block['model']!r} was not created.")
    variant_matrix_service.generate(
        db,
        model.id,
        MatrixWrite(
            axes=[MatrixAxis(key=axis["key"], values=list(axis["values"])) for axis in block["axes"]],
            price_cents=min(int(row["price_cents"]) for row in block["rows"]),
            sku_prefix=block["rows"][0]["sku"].split("-")[0],
            opening_store_id=store.id,
            variants=[
                MatrixVariantDraft(
                    attributes={"size": row["size"], "color": row["color"]},
                    sku=row["sku"],
                    barcode=row["barcode"],
                    price_cents=int(row["price_cents"]),
                    cost_cents=int(row["price_cents"]) // 2,
                    opening_quantity=int(row["stock"]),
                )
                for row in block["rows"]
            ],
        ),
        spec["currency"],
        user_id=user.id,
    )


def _modifiers(db: Session, spec: dict) -> None:
    block = spec.get("modifier")
    if not block:
        return
    product = next((row for row in spec["products"] if row.get("modifier")), None)
    if product is None:
        return
    target = _product(db, product["sku"])
    if target is None:
        raise DemoSeedError("Modifier product is missing.")
    group = _named(db, ModifierGroup, block["group"])
    if group is None:
        menu_service.create_group(
            db,
            ModifierGroupIn(
                name=block["group"],
                min_select=0,
                max_select=1,
                options=[ModifierOptionIn(name=block["option"], price_delta_cents=int(block["delta_cents"]))],
            ),
        )
        group = _named(db, ModifierGroup, block["group"])
    if group is None:
        raise DemoSeedError("Modifier group was not created.")
    linked = db.scalar(
        select(ProductModifierGroup.group_id).where(
            ProductModifierGroup.product_id == target.id,
            ProductModifierGroup.group_id == group.id,
        )
    )
    if linked is None:
        menu_service.set_product_groups(db, target.id, ProductGroupsIn(group_ids=[group.id]))


def _tables(db: Session, spec: dict, store: Store, actor: Principal) -> None:
    labels = spec.get("tables") or []
    if not labels:
        return
    area = _named(db, DiningArea, "Dining room")
    if area is None:
        order_service.save_area(db, actor, None, DiningAreaIn(store_id=store.id, name="Dining room"))
        area = _named(db, DiningArea, "Dining room")
    if area is None:
        raise DemoSeedError("Dining room was not created.")
    for index, label in enumerate(labels):
        if db.scalar(select(DiningTable.id).where(DiningTable.label == label, DiningTable.area_id == area.id)):
            continue
        order_service.save_table(
            db,
            actor,
            None,
            DiningTableIn(area_id=area.id, label=label, seats=4, x=index * 3, y=0),
        )


def _recipe(db: Session, spec: dict, user: User) -> None:
    dish = next((row for row in spec["products"] if row.get("recipe")), None)
    ingredient = next((row for row in spec["products"] if row.get("ingredient")), None)
    if dish is None or ingredient is None:
        return
    made = _product(db, dish["sku"])
    raw = _product(db, ingredient["sku"])
    if made is None or raw is None:
        raise DemoSeedError("Recipe products are missing.")
    if db.scalar(select(Recipe.id).where(Recipe.product_id == made.id)) is not None:
        return
    recipe_service.save_recipe(
        db,
        made.id,
        RecipeIn(
            yield_quantity=1,
            notes="One espresso from the house beans.",
            lines=[RecipeLineIn(ingredient_id=raw.id, quantity=18)],
        ),
        user.id,
    )


def _loyalty(db: Session, spec: dict) -> None:
    if spec["profile"] not in {"grocery", "retail_fashion", "pharmacy"}:
        return
    loyalty_service.update_settings(
        db,
        LoyaltySettingsWrite(enabled=True, earn_per_unit=1, redeem_cents=10, min_redeem=50),
    )


def _promotion(db: Session, spec: dict) -> None:
    from app.models.promotion import Promotion

    name = f"{spec['name']} 10% off"
    if db.scalar(select(Promotion.id).where(Promotion.name == name)) is not None:
        return
    skus = [row["sku"] for row in spec["products"] if row.get("promo")]
    block = spec.get("variants") or {}
    skus.extend(row["sku"] for row in block.get("rows", []) if row.get("promo"))
    products = list(db.scalars(select(Product).where(Product.sku.in_(skus))).all()) if skus else []
    if not products:
        return
    promotion_service.create(
        db,
        PromotionWrite(
            name=name,
            description="Demo shelf promotion.",
            kind="PERCENT_OFF",
            percent_bps=1000,
            product_ids=[product.id for product in products],
        ),
        None,
    )


def _warranty(db: Session, spec: dict) -> None:
    row = next((item for item in spec["products"] if item.get("warranty_months")), None)
    if row is None:
        return
    product = _product(db, row["sku"])
    if product is None:
        return
    if db.scalar(select(WarrantyPolicy.id).where(WarrantyPolicy.product_id == product.id)) is not None:
        return
    warranty_service.save_policy(
        db,
        PolicyWrite(
            name=f"{product.name} cover",
            scope="PRODUCT",
            product_id=product.id,
            months=int(row["warranty_months"]),
        ),
    )


def _gift_card(db: Session, spec: dict, store: Store, user: User) -> None:
    amount = spec.get("gift_card_cents")
    if not amount:
        return
    from app.models.store_credit import StoreCredit

    note = "Demo welcome card"
    if db.scalar(select(StoreCredit.id).where(StoreCredit.note == note)) is not None:
        return
    gift_card_service.issue(db, user, GiftCardIssue(store_id=store.id, amount_cents=int(amount), note=note))


def _receipt_line(line, row: dict, serials: dict[str, list[str]], received) -> ReceiveLineIn:
    medicine = (row.get("pharmacy") or {}).get("product_kind") == "MEDICINE"
    return ReceiveLineIn(
        purchase_order_line_id=line.id,
        quantity=line.quantity_ordered,
        serials=[SerialInput(kind="serial", value=value) for value in serials.get(line.sku, [])],
        manufacturer_lot=f"{line.sku}-LOT" if medicine else None,
        manufactured_on=received - timedelta(days=30) if medicine else None,
        expiry_date=received + timedelta(days=400) if medicine else None,
    )


def _opening_stock(db: Session, settings: Settings, spec: dict, store: Store, actor: Principal) -> None:
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.notes == _OPENING)) is not None:
        _dated_lots(db, settings, spec, store, actor)
        _release_medicines(db, actor)
        return
    lines = []
    serials: dict[str, list[str]] = {}
    for row in spec["products"]:
        quantity = int(row.get("stock") or 0)
        if quantity < 1 or row.get("recipe"):
            continue
        product = _product(db, row["sku"])
        if product is None:
            raise DemoSeedError(f"Product {row['sku']} is missing.")
        lines.append(
            PurchaseOrderLineIn(
                product_id=product.id,
                quantity_ordered=quantity,
                unit_cost_cents=max(1, int(row["price_cents"]) // 2),
            )
        )
        if row.get("serial"):
            serials[row["sku"]] = [f"SN-{spec['code'][:2].upper()}-{index:04d}" for index in range(1, quantity + 1)]
    if not lines:
        return
    order = inventory.create_purchase_order(
        db,
        actor,
        PurchaseOrderCreate(
            supplier_name=spec["supplier"],
            destination_store_id=store.id,
            notes=_OPENING,
            lines=lines,
        ),
    )
    inventory.mark_ordered(db, actor, order.id)
    placed = inventory.get_purchase_order(db, actor, order.id)
    by_sku = {row["sku"]: row for row in spec["products"]}
    received = datetime.now(UTC).date()
    inventory.receive_purchase_order(
        db,
        settings,
        actor,
        order.id,
        ReceiveRequest(
            note="Demo opening receipt",
            lines=[
                _receipt_line(line, by_sku.get(line.sku) or {}, serials, received)
                for line in placed.lines
            ],
        ),
    )
    _dated_lots(db, settings, spec, store, actor)
    _release_medicines(db, actor)


def _release_medicines(db: Session, actor: Principal) -> None:
    from app.models.batch import BatchItem
    from app.services.pharmacy_lots import release_for_sale

    user_id = actor.user.id if actor.user is not None else None
    for item in db.scalars(select(BatchItem).where(BatchItem.lot_status == "UNRELEASED")).all():
        release_for_sale(db, item, user_id)


def _dated_lots(db: Session, settings: Settings, spec: dict, store: Store, actor: Principal) -> None:
    row = next((item for item in spec["products"] if item.get("batch")), None)
    if row is None:
        return
    product = _product(db, row["sku"])
    if product is None:
        return
    today = datetime.now(UTC).date()
    for label, days, quantity in (("SOON", 6, 20), ("LATER", 40, 30)):
        inventory.manual_adjust(
            db,
            settings,
            actor,
            ManualAdjustment(
                adjustment_id=uuid.uuid5(_NAMESPACE, f"{spec['code']}:{row['sku']}:{label}"),
                product_id=product.id,
                store_id=store.id,
                mode="add",
                quantity=quantity,
                reason_code="SUPPLIER_SAMPLE_IN",
                note=f"Dated {label.lower()} lot for the demo shelf.",
                unit_cost_cents=max(1, int(row["price_cents"]) // 2),
                lot_number=f"{row['sku']}-{label}",
                expiry_date=today + timedelta(days=days),
            ),
        )


def _orders(db: Session, spec: dict, store: Store, actor: Principal, user: User) -> None:
    if spec["code"] != "restaurant":
        return
    coffee = _product(db, "RST-COFFEE")
    wrap = _product(db, "RST-WRAP")
    if coffee is None or wrap is None:
        return
    tables = list(db.scalars(select(DiningTable).order_by(DiningTable.label)).all())
    if not tables:
        return
    group = _named(db, ModifierGroup, spec["modifier"]["group"])
    option = group.options[0] if group is not None and group.options else None
    plans = [
        ("dine-in", "DINE_IN", tables[0].id, coffee, option),
        ("takeaway", "TAKEAWAY", None, wrap, None),
        ("delivery", "DELIVERY", None, coffee, None),
    ]
    for key, service, table_id, product, choice in plans:
        order_id = uuid.uuid5(_NAMESPACE, f"{spec['slug']}-{key}")
        if db.get(OpenOrder, order_id) is not None:
            continue
        modifiers = []
        price = product.price_cents
        if choice is not None and group is not None:
            price += choice.price_delta_cents
            modifiers = [
                ModifierChoice(
                    group_id=group.id,
                    option_id=choice.id,
                    group=group.name,
                    option=choice.name,
                    price_delta_cents=choice.price_delta_cents,
                )
            ]
        created = order_service.create_order(
            db,
            actor,
            OrderCreate(
                id=order_id,
                store_id=store.id,
                service_type=service,
                table_id=table_id,
                covers=2 if service == "DINE_IN" else 0,
                name=key,
                user_id=user.id,
                items=[
                    OrderItemIn(
                        id=uuid.uuid5(order_id, "line"),
                        product_id=product.id,
                        quantity=1,
                        unit_price_cents=price,
                        modifiers=modifiers,
                    )
                ],
            ),
        )
        item = db.scalar(select(OpenOrderItem).where(OpenOrderItem.order_id == order_id))
        if item is not None and item.sent_at is None:
            order_service.send_order(db, actor, order_id, OrderAction(revision=created.revision, user_id=user.id))


def _supplier(db: Session, spec: dict) -> None:
    if _named(db, Supplier, spec["supplier"]) is not None:
        return
    create_supplier(db, SupplierCreate(name=spec["supplier"]))


def _leave_practice(db: Session) -> bool:
    """A demo is already a live store. Practice mode offers Go live, which deletes the shared catalog."""
    row = load_settings(db, lock=True)
    if row.live_at is not None:
        return False
    row.live_at = datetime.now(UTC)
    return True


def end_practice_for_demos(settings: Settings) -> list[str]:
    """Marks every existing demo store live. Returns the slugs that were still in practice."""
    with registry.control_session(settings) as control:
        rows = list(control.scalars(select(Tenant).where(Tenant.is_demo.is_(True))))
        for row in rows:
            control.expunge(row)
    changed: list[str] = []
    for tenant in rows:
        db = _session(settings, tenant)
        try:
            with use_tenant(_ref(tenant, settings)):
                if _leave_practice(db):
                    changed.append(tenant.slug)
                db.commit()
        finally:
            db.close()
    return changed


def seed_catalog(settings: Settings, spec: dict, tenant: Tenant) -> None:
    """Creates the tenant's catalog. A second run does not insert a second copy of any of it."""
    ref = _ref(tenant, settings)
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            clear_settings_cache()
            user = _owner(db)
            actor = _principal(user)
            _explorer(db, settings, spec, user)
            store = db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.code))
            if store is None:
                raise DemoSeedError(f"{spec['slug']} has no store.")
            _supplier(db, spec)
            _customers(db, spec)
            _products(db, spec, actor)
            _matrix(db, spec, store, user)
            _modifiers(db, spec)
            _tables(db, spec, store, actor)
            _recipe(db, spec, user)
            _loyalty(db, spec)
            _promotion(db, spec)
            _warranty(db, spec)
            _gift_card(db, spec, store, user)
            _opening_stock(db, settings, spec, store, actor)
            _orders(db, spec, store, actor, user)
            _leave_practice(db)
            db.commit()
    finally:
        db.close()


def seed_production_demos(settings: Settings, codes: list[str] | None = None) -> list[dict]:
    """Provisions each requested demo, loads its catalog and history, and returns a validation report."""
    from app.services.demo_history import seed_history
    from app.services.demo_validate import validate_demo

    wanted = set(codes or [spec["code"] for spec in demo_tenants()])
    reports = []
    for spec in demo_tenants():
        if spec["code"] not in wanted:
            continue
        tenant = _provision(settings, spec)
        seed_catalog(settings, spec, tenant)
        seed_history(settings, spec, tenant)
        ref = _ref(tenant, settings)
        db = _session(settings, tenant)
        try:
            with use_tenant(ref):
                report = validate_demo(db, spec)
        finally:
            db.close()
        if not report["ok"]:
            failed = [check["name"] for check in report["checks"] if not check["ok"]]
            raise DemoSeedError(f"{spec['code']} failed validation: {', '.join(failed)}")
        reports.append(report)
    return reports


def _explorer_state(settings: Settings, tenant: Tenant) -> str:
    """Whether the public Demo Explorer can be signed in. missing, blocked, or ok."""
    ref = _ref(tenant, settings)
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            user = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            if user is None:
                return "missing"
            role = user.role
            permissions = set() if role is None else set(role.permissions)
            if (
                not user.is_active
                or role is None
                or not role.is_system
                or role.name != "Demo Explorer"
                or Permission.PORTAL_ACCESS.value not in permissions
                or Permission.USERS_CREATE.value in permissions
            ):
                return "blocked"
            return "ok"
    finally:
        db.close()


def ready_production_demos(settings: Settings) -> list[dict]:
    """Seeds a missing production demo and opens the public door. Existing demo data is left in place.

    A demo that is disabled, resetting, expired, or not the catalog tenant stops the run before any
    door is opened. A broken explorer is not repaired, because that would change who can sign in.
    """
    from app.services.demo_access import _expired, set_demo_access

    planned: list[tuple[dict, str]] = []
    for spec in demo_tenants():
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
            present = row is not None
            if present:
                is_demo = bool(row.is_demo and row.demo_business_type == spec["code"])
                active = row.demo_status == "active" and row.status == "active" and not _expired(row.demo_expires_at)
            else:
                is_demo = False
                active = False
        if not present:
            planned.append((spec, "seeded"))
            continue
        if not is_demo:
            raise DemoSeedError(f"{spec['slug']} is not the {spec['code']} demo.")
        if not active:
            raise DemoSeedError(f"{spec['slug']} is not an active demo.")
        planned.append((spec, "opened"))

    reports = []
    for spec, action in planned:
        if action == "seeded":
            seed_production_demos(settings, [spec["code"]])
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
            if row is None:
                raise DemoSeedError(f"{spec['slug']} was not registered.")
            db.expunge(row)
        state = _explorer_state(settings, row)
        if state == "missing":
            seed_catalog(settings, spec, row)
            state = _explorer_state(settings, row)
            if action != "seeded":
                action = "explorer"
        if state != "ok":
            raise DemoSeedError(f"{spec['slug']} explorer cannot sign in.")
        set_demo_access(settings, spec["code"], enabled=True)
        reports.append({"code": spec["code"], "slug": spec["slug"], "action": action, "demo_access_enabled": True})
    return reports


def explorer_denied() -> frozenset[str]:
    """Permissions the public demo user must not hold."""
    return frozenset(
        {
            Permission.USERS_CREATE.value,
            Permission.SETTINGS_MANAGE.value,
            Permission.ACCOUNTING_MANAGE.value,
            Permission.DEVICES_MANAGE.value,
        }
    )
