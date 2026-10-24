import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import capabilities as capability_catalog
from app.core.config import Settings, env_file_name, get_settings
from app.core.database import build_engine
from app.core.security import hash_password, hash_pin
from app.models.brand import ProductModel
from app.models.category import Category, SubCategory
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.schemas.auth import UserCreate
from app.schemas.inventory import variant_attributes
from app.schemas.payloads import ProductPayload, StorePayload, SyncEventIn, SyncPushRequest
from app.schemas.wholesale import CustomerWrite
from app.seed_fashion import seed_fashion
from app.seed_history import seed_history
from app.services import sample_data
from app.services.brand_service import link, resolve_brand
from app.services.category_service import resolve_by_name
from app.services.inventory import level_for, move_stock
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import business_currency, provision_profile
from app.services.sync_service import canonical_hash, push_batch
from app.tenancy.registry import resolve_cli_database_url
from app.tenancy.scoping import use_database_tenant


def catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "packages" / "catalog" / "seed.json"


def profile_arg(argv: list[str]) -> str | None:
    """`--profile cafe` or `--profile=cafe`."""
    for index, arg in enumerate(argv):
        if arg.startswith("--profile="):
            profile = arg.split("=", 1)[1]
        elif arg == "--profile":
            profile = argv[index + 1] if index + 1 < len(argv) else ""
        else:
            continue
        if profile not in capability_catalog.PROFILES:
            sys.exit(f"--profile must be one of: {', '.join(capability_catalog.PROFILES)}.")
        return profile
    return None


def catalog_events(currency: str, *, products: bool = True) -> list[SyncEventIn]:
    """The seed catalog is priced in whatever currency the business currently uses."""
    catalog = json.loads(catalog_path().read_text(encoding="utf-8"))
    stores = [
        StorePayload.model_validate({**item, "currency": currency})
        for item in [catalog["store"], *catalog.get("branches", [])]
    ]
    items = catalog["products"] if products else []
    products_out = [ProductPayload.model_validate({**item, "currency": currency}) for item in items]
    events: list[SyncEventIn] = []
    for entity_type, payload in (
        *(("store", store) for store in stores),
        *(("product", item) for item in products_out),
    ):
        body = payload.model_dump(mode="json")
        events.append(
            SyncEventIn(
                idempotency_key=f"seed:{entity_type}:{body['id']}:{canonical_hash(body)[:16]}",
                entity_type=entity_type,  # type: ignore[arg-type]
                operation="upsert",
                payload=body,
                occurred_at="2026-10-19T00:00:00Z",
            )
        )
    return events


def seed_categories(session: Session) -> list[str]:
    """Default category tree. Names match case-insensitively, so renamed or existing categories are kept as they are."""
    catalog = json.loads(catalog_path().read_text(encoding="utf-8"))
    report: list[str] = []
    for spec in catalog.get("categories", []):
        known = session.scalar(select(Category).where(func.lower(Category.name) == spec["name"].lower()))
        known_subs = (
            set(session.scalars(select(func.lower(SubCategory.name)).where(SubCategory.category_id == known.id)))
            if known
            else set()
        )
        category, _ = resolve_by_name(session, spec["name"], None)
        if not category.description:
            category.description = spec.get("description", "")
        added = [name for name in spec.get("sub_categories", []) if name.lower() not in known_subs]
        for name in added:
            resolve_by_name(session, category.name, name)
        if known is None:
            report.append(f"{category.name} ({len(added)} sub-categories)")
        elif added:
            report.append(f"{category.name}: added {', '.join(added)}")
    session.commit()
    return report


def seed_menu(session: Session, settings: Settings, profile: str) -> list[str]:
    """Demo menu for food & beverage profiles: the signup starter kit (menu, modifiers, meals, floor plan where the
    business seats guests, kitchen stations), loaded as real items rather than practice samples."""
    added = sample_data.load_food_kit(session, settings, profile=profile, sample=False)
    return [f"{added} menu items and meals, with modifiers, kitchen stations and the floor plan"] if added else []


def variant_name(model: ProductModel, attributes: dict[str, str]) -> str:
    return " ".join([model.name, *attributes.values()])[:200]


def seed_catalog_tree(session: Session, currency: str) -> list[str]:
    """Brands > models > variants. Matched by brand name, (brand, sub-category, model name), and variant SKU;
    existing products with that SKU are linked to their model instead of being changed."""
    catalog = json.loads(catalog_path().read_text(encoding="utf-8"))
    report: list[str] = []
    for brand_spec in catalog.get("catalog_tree", []):
        brand = resolve_brand(session, brand_spec["brand"])
        if not brand.description:
            brand.description = brand_spec.get("description", "")
        created = linked = 0
        for spec in brand_spec["models"]:
            category, sub = resolve_by_name(session, spec["category"], spec["sub_category"])
            if sub is None:
                sys.exit(f"Model {spec['name']} needs a sub-category.")
            link(brand, sub)
            model = session.scalar(
                select(ProductModel).where(
                    ProductModel.brand_id == brand.id,
                    ProductModel.sub_category_id == sub.id,
                    func.lower(ProductModel.name) == spec["name"].lower(),
                )
            )
            if model is None:
                model = ProductModel(
                    brand_id=brand.id,
                    sub_category_id=sub.id,
                    name=spec["name"],
                    code=spec.get("code"),
                    release_year=spec.get("release_year"),
                    description="",
                )
                session.add(model)
                session.flush()
            for variant in spec["variants"]:
                attributes = variant_attributes(variant.get("attributes"))
                product = session.scalar(select(Product).where(Product.sku == variant["sku"]))
                if product is not None:
                    if product.product_model_id is None:
                        product.product_model_id = model.id
                        product.brand_id = brand.id
                        product.brand = brand.name
                        product.category_id = category.id
                        product.category = category.name
                        product.sub_category_id = sub.id
                        product.variant_attributes = attributes
                        linked += 1
                    continue
                if "barcode" not in variant:
                    continue
                product = Product(
                    sku=variant["sku"],
                    barcode=variant["barcode"],
                    name=variant_name(model, attributes),
                    model_number=spec.get("code"),
                    brand=brand.name,
                    brand_id=brand.id,
                    category=category.name,
                    category_id=category.id,
                    sub_category_id=sub.id,
                    product_model_id=model.id,
                    variant_attributes=attributes,
                    price_cents=variant["price_cents"],
                    currency=currency,
                    is_serialized=spec.get("serialized", False),
                )
                session.add(product)
                session.flush()
                for store_code, quantity in variant.get("stock", {}).items():
                    store = session.scalar(select(Store).where(Store.code == store_code))
                    if store is None or not quantity or product.is_serialized:
                        continue
                    move_stock(
                        session,
                        product_id=product.id,
                        store_id=store.id,
                        quantity=quantity,
                        movement_type="AUDIT_ADJUSTMENT",
                        reference_type="opening_balance",
                        reference_id=product.id,
                        note="Seed opening stock",
                    )
                created += 1
        if created or linked:
            report.append(f"{brand.name}: {created} variants created, {linked} linked")
    session.commit()
    return report


def seed_branch_stock(session: Session) -> list[str]:
    """Shelf locations, reorder levels, and opening stock for branches that have no stock row yet."""
    catalog = json.loads(catalog_path().read_text(encoding="utf-8"))
    report: list[str] = []
    for spec in catalog.get("branch_stock", []):
        store = session.scalar(select(Store).where(Store.code == spec["store_code"]))
        product = session.scalar(select(Product).where(Product.sku == spec["sku"]))
        if store is None or product is None:
            continue
        existing = session.scalar(
            select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store.id)
        )
        level = existing or level_for(session, product.id, store.id)
        if level.aisle_shelf_location is None:
            level.aisle_shelf_location = spec.get("location")
        if not level.min_reorder_level:
            level.min_reorder_level = spec.get("min_reorder_level", 0)
        if level.max_stock_level is None and spec.get("max_stock_level") is not None:
            level.max_stock_level = spec["max_stock_level"]
        quantity = spec.get("quantity", 0)
        if existing is None and quantity:
            move_stock(
                session,
                product_id=product.id,
                store_id=store.id,
                quantity=quantity,
                movement_type="AUDIT_ADJUSTMENT",
                reference_type="opening_balance",
                note="Seed opening stock",
            )
            report.append(f"{store.code}: {quantity} x {product.sku}")
    session.commit()
    return report


def seed_wholesale(session: Session) -> list[str]:
    """Tier prices for products that have none yet, and the demo B2B customers (matched by code)."""
    wholesale = json.loads(catalog_path().read_text(encoding="utf-8")).get("wholesale", {})
    report: list[str] = []
    for spec in wholesale.get("pricing", []):
        product = session.scalar(select(Product).where(Product.sku == spec["sku"]))
        if product is None or product.prices:
            continue
        product.sellable_units = spec.get("sellable_units", ["PIECE"])
        product.min_order_quantity = spec.get("min_order_quantity", 1)
        for tier in spec["tiers"]:
            product.prices.append(
                ProductPrice(
                    product_id=product.id,
                    price_tier=tier["price_tier"],
                    price_cents=tier["price_cents"],
                    min_order_quantity=tier.get("min_order_quantity", 1),
                    volume_discounts=tier.get("volume_discounts", []),
                )
            )
        report.append(f"{product.sku}: {len(spec['tiers'])} price tiers")
    for spec in wholesale.get("customers", []):
        if session.scalar(select(Customer).where(Customer.code == spec["code"])) is not None:
            continue
        data = CustomerWrite.model_validate({key: value for key, value in spec.items() if key not in {"id", "code"}})
        session.add(Customer(id=uuid.UUID(spec["id"]), code=spec["code"], current_balance_cents=0, **data.model_dump()))
        report.append(f"customer {spec['code']} ({data.customer_type.lower()})")
    session.commit()
    return report


def demo_path() -> Path:
    return catalog_path().with_name("demo-users.json")


def seed_demo(session: Session, settings: Settings) -> list[str]:
    demo = json.loads(demo_path().read_text(encoding="utf-8"))
    report: list[str] = []
    roles: dict[str, Role] = {}
    for spec in demo["roles"]:
        permissions = set(spec["permissions"])
        role = session.scalar(select(Role).where(Role.name == spec["name"]))
        if spec["system"]:
            if role is None:
                sys.exit(f"System role {spec['name']} is missing. Run the migration first.")
            if role.permissions != permissions:
                report.append(
                    f"warning: {role.name} permissions differ from demo-users.json; the login page list is stale."
                )
        elif role is None:
            role = Role(name=spec["name"], description=spec.get("description", ""), is_system=False)
            role.set_permissions(permissions)
            session.add(role)
            session.flush()
            report.append(f"role {role.name} created")
        roles[spec["name"]] = role

    for spec in demo["users"]:
        if session.scalar(select(User).where(User.username == spec["username"])) is not None:
            report.append(f"user {spec['username']} already exists (unchanged)")
            continue
        data = UserCreate.model_validate(
            {
                "username": spec["username"],
                "email": spec["email"],
                "full_name": spec["full_name"],
                "role_id": roles[spec["role"]].id,
                "store_id": spec["store_id"],
                "password": spec["password"],
                "pin": spec["pin"],
                "has_portal_access": spec["has_portal_access"],
                "has_pos_access": spec["has_pos_access"],
            }
        )
        session.add(
            User(
                username=data.username,
                email=data.email,
                full_name=data.full_name,
                hashed_password=hash_password(data.password) if data.password else None,
                hashed_pin=hash_pin(data.pin, settings) if data.pin else None,
                is_active=True,
                store_id=data.store_id,
                role_id=data.role_id,
                has_pos_access=data.has_pos_access,
                has_portal_access=data.has_portal_access,
                failed_login_attempts=0,
                token_version=0,
            )
        )
        report.append(f"user {data.username} created ({spec['role']})")
    session.commit()
    return report


def admin_spec(settings: Settings) -> UserCreate:
    missing = [
        name
        for name, value in (
            ("ADMIN_USERNAME", settings.admin_username),
            ("ADMIN_EMAIL", settings.admin_email),
            ("ADMIN_PASSWORD", settings.admin_password),
        )
        if not value
    ]
    if missing:
        file_name = env_file_name(settings.app_env)
        sys.exit(f"Seed needs {', '.join(missing)} in {file_name} at the repo root to create the Super Admin.")
    return UserCreate.model_validate(
        {
            "username": settings.admin_username,
            "email": settings.admin_email,
            "full_name": settings.admin_full_name,
            "role_id": "00000000-0000-4000-8000-0000000000a1",
            "password": settings.admin_password,
            "pin": settings.admin_pin,
            "has_portal_access": True,
            "has_pos_access": settings.admin_pin is not None,
        }
    )


def main() -> None:
    settings = get_settings()
    profile = profile_arg(sys.argv[1:])
    food = profile in capability_catalog.FOOD_AND_BEVERAGE
    fashion = profile == "retail_fashion"
    spec = admin_spec(settings)
    if spec.password is None:
        sys.exit("ADMIN_PASSWORD is required.")
    url = resolve_cli_database_url(settings)
    engine = build_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with use_database_tenant(url), factory() as session:
        ensure_system_roles(session)
        admin, created = ensure_super_admin(
            session,
            settings,
            username=spec.username,
            email=spec.email,
            full_name=spec.full_name,
            password=spec.password,
            pin=spec.pin,
        )
        session.commit()
        if profile is not None:
            provision_profile(session, profile)
        currency = business_currency(session)
        session.commit()
        electronics = not food and not fashion
        category_report = seed_categories(session) if electronics else []
        events = catalog_events(currency, products=electronics)
        result = push_batch(session, SyncPushRequest(device_id="seed", events=events), settings, source="portal")
        menu_report = seed_menu(session, settings, profile) if food and profile else []
        tree_report = seed_catalog_tree(session, currency) if electronics else []
        stock_report = seed_branch_stock(session) if electronics else []
        wholesale_report = seed_wholesale(session) if electronics else []
        fashion_report = seed_fashion(session, settings, user=admin) if fashion else []
        demo_report = seed_demo(session, settings) if "--demo" in sys.argv[1:] else []
        history_report = (
            seed_history(session, settings, cashier=admin) if "--history" in sys.argv[1:] and electronics else []
        )
    applied = sum(1 for item in result.results if item.status == "applied")
    duplicates = sum(1 for item in result.results if item.status == "duplicate")
    admin_state = "created" if created else "already exists (credentials unchanged)"
    print(f"Super Admin '{admin.username}' {admin_state}.")
    if profile is not None:
        print(f"Business profile: {profile} (the first admin finishes onboarding in the portal)")
    for line in menu_report:
        print(f"Menu: {line}")
    for line in fashion_report:
        print(f"Fashion: {line}")
    for line in category_report:
        print(f"Category: {line}")
    print(f"Catalog seed complete. applied={applied} duplicates={duplicates}")
    for line in tree_report:
        print(f"Catalog: {line}")
    for line in stock_report:
        print(f"Opening stock: {line}")
    for line in wholesale_report:
        print(f"Wholesale: {line}")
    for line in demo_report:
        print(f"Demo: {line}")
    for line in history_report:
        print(f"History: {line}")


if __name__ == "__main__":
    main()
