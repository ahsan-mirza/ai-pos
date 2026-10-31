"""Retail & Fashion demo (`python -m app.seed --profile retail_fashion`): two apparel models with size x colour grids,
tees bought outright on a purchase order, jeans on consignment from a denim supplier, and three weeks of sales so the
grid, the consignment settlement and the labels have something to show."""

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.batch import BatchItem, PurchaseBatch, Supplier
from app.models.brand import ProductModel
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.store import Store
from app.models.store_credit import StoreCredit
from app.models.user import User
from app.schemas.batches import SupplierCreate
from app.schemas.catalogue import FashionAttributes
from app.schemas.payloads import SalePayload
from app.schemas.store_credit import GiftCardIssue
from app.schemas.variants import MatrixAxis, MatrixWrite
from app.seed_history import _payload, _receive_stock
from app.services import (
    fashion_attributes,
    gift_card_service,
    import_batch_service,
    product_image_service,
    variant_matrix_service,
)
from app.services.brand_service import link, resolve_brand
from app.services.category_service import resolve_by_name
from app.services.inventory import move_stock
from app.services.sale_service import record_sale
from app.services.settings_service import business_currency
from app.services.tax import entered_includes_tax, line_tax
from app.services.tax import policy as tax_policy

MODELS = (
    {
        "name": "Classic Tee",
        "code": "TEE",
        "sub_category": "T-Shirts",
        "axes": (("size", ("XS", "S", "M", "L", "XL", "XXL")), ("color", ("Black", "White", "Navy"))),
        "price_cents": 4900,
        "price_by_value": {"XXL": 5400},
        "consignment": False,
        "season": "SS26",
        "collection": "Resort",
        "gender": "unisex",
        "material": "100% cotton",
        "fit": "Regular",
        "care": "Machine wash cold",
    },
    {
        "name": "Slim Jeans",
        "code": "JEAN",
        "sub_category": "Jeans",
        "axes": (("size", ("28", "30", "32", "34", "36")), ("color", ("Indigo", "Black"))),
        "price_cents": 12900,
        "price_by_value": {},
        "season": "AW26",
        "collection": "Denim",
        "gender": "women",
        "material": "98% cotton, 2% elastane",
        "fit": "Slim",
        "care": "Wash inside out",
        "consignment": True,
    },
)
CONSIGNOR = "Dubai Denim Co"
_COLOURS = {"Black": (24, 24, 28), "White": (244, 244, 246), "Navy": (20, 36, 72), "Indigo": (46, 58, 110)}


def _attributes(spec: dict) -> FashionAttributes:
    return FashionAttributes(
        season=spec["season"],
        collection=spec["collection"],
        gender=spec["gender"],
        material=spec["material"],
        fit=spec["fit"],
        care=spec["care"],
    )


def _png(rgb: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (64, 80), rgb)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_model_photos(db: Session, user: User, model: ProductModel, spec: dict) -> int:
    from app.models.product_image import ProductImage

    existing = db.scalar(
        select(func.count()).select_from(ProductImage).where(ProductImage.product_model_id == model.id)
    )
    if existing:
        return 0
    added = 0
    for key, values in spec["axes"]:
        if key != "color":
            continue
        for value in values:
            product_image_service.upload(
                db,
                user,
                _png(_COLOURS.get(value, (120, 120, 120))),
                "image/png",
                model_id=model.id,
                attribute_key="color",
                attribute_value=value,
            )
            added += 1
    return added


def _backfill_catalogue(db: Session, user: User) -> list[str]:
    notes: list[str] = []
    for spec in MODELS:
        model = db.scalar(select(ProductModel).where(ProductModel.name == spec["name"]))
        if model is None:
            continue
        if fashion_attributes.apply(model, _attributes(spec), only_sent=False):
            fashion_attributes.push_to_variants(db, model)
            notes.append(f"{spec['name']} attributes set")
        photos = _seed_model_photos(db, user, model, spec)
        if photos:
            notes.append(f"{spec['name']}: {photos} colour photos")
    db.commit()
    return notes or ["catalogue already complete"]


def _consignment_batch(
    db: Session, user: User, store: Store, supplier: Supplier, lines: list[tuple[Product, int]]
) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    count = db.scalar(select(func.count()).where(PurchaseBatch.batch_number.like(f"BATCH-{stamp}-%"))) or 0
    batch = PurchaseBatch(
        id=uuid.uuid4(),
        batch_number=f"BATCH-{stamp}-{count + 1:03d}",
        supplier_id=supplier.id,
        store_id=store.id,
        import_source="MANUAL",
        total_cost_amount=0,
        total_items_count=0,
        currency=business_currency(db),
        status="ACTIVE",
        is_consignment=True,
        notes="Demo consignment stock",
        created_by_id=user.id,
    )
    db.add(batch)
    db.flush()
    for position, (product, quantity) in enumerate(lines):
        cost = product.price_cents // 2
        db.add(
            BatchItem(
                id=uuid.uuid4(),
                batch_id=batch.id,
                position=position,
                product_id=product.id,
                store_id=store.id,
                quantity_imported=quantity,
                quantity_remaining=quantity,
                purchase_cost_per_unit=cost,
                selling_price_per_unit=product.price_cents,
                imported_serials=[],
            )
        )
        db.flush()
        move_stock(
            db,
            product_id=product.id,
            store_id=store.id,
            quantity=quantity,
            movement_type="PURCHASE_IN",
            reference_type="purchase_batch",
            reference_id=batch.id,
            user_id=user.id,
            note=f"{batch.batch_number} · consignment",
        )
        batch.total_items_count += quantity
        batch.total_cost_amount += quantity * cost
    db.commit()
    return batch.batch_number


def seed_fashion(db: Session, settings: Settings, *, user: User) -> list[str]:
    store = db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.is_warehouse, Store.code))
    if store is None:
        return ["no store to stock"]
    existing = db.scalar(select(ProductModel).where(ProductModel.name == MODELS[0]["name"]))
    if existing is not None:
        products = list(db.scalars(select(Product).where(Product.product_model_id == existing.id)))
        return [
            *_backfill_catalogue(db, user),
            *seed_till_demo(db, settings, user=user, store=store, products=products),
        ]
    rng = random.Random(20261021)
    brand = resolve_brand(db, "Urban Basics")
    currency = business_currency(db)
    report: list[str] = []
    owned: dict[Product, int] = {}
    consigned: list[tuple[Product, int]] = []
    for spec in MODELS:
        _, sub = resolve_by_name(db, "Apparel", spec["sub_category"])
        assert sub is not None
        link(brand, sub)
        model = ProductModel(
            brand_id=brand.id, sub_category_id=sub.id, name=spec["name"], code=spec["code"], description=""
        )
        fashion_attributes.apply(model, _attributes(spec), only_sent=False)
        db.add(model)
        db.flush()
        photos = _seed_model_photos(db, user, model, spec)
        grid = variant_matrix_service.generate(
            db,
            model.id,
            MatrixWrite(
                axes=[MatrixAxis(key=key, values=list(values)) for key, values in spec["axes"]],
                price_cents=spec["price_cents"],
                price_by_value=spec["price_by_value"],
            ),
            currency,
        )
        products = {row.id: row for row in db.scalars(select(Product).where(Product.product_model_id == model.id))}
        for cell in grid.cells:
            quantity = rng.randint(2, 9)
            if spec["consignment"]:
                consigned.append((products[cell.product_id], quantity))
            else:
                owned[products[cell.product_id]] = quantity
        report.append(f"{spec['name']}: {grid.created} sizes and colours, {photos} photos")

    _receive_stock(db, settings, user, store, owned)
    report.append(f"{sum(owned.values())} tees received on a purchase order")
    supplier = db.scalar(select(Supplier).where(Supplier.name == CONSIGNOR))
    if supplier is None:
        created = import_batch_service.create_supplier(db, SupplierCreate(name=CONSIGNOR))
        supplier = db.get(Supplier, created.id)
        assert supplier is not None
    number = _consignment_batch(db, user, store, supplier, consigned)
    report.append(f"{sum(quantity for _, quantity in consigned)} jeans on consignment from {CONSIGNOR} ({number})")

    sellable = [*owned.items(), *consigned]
    sold = 0
    now = datetime.now(UTC)
    for _ in range(40):
        product, _stock = rng.choice(sellable)
        db.refresh(product)
        payload = _payload(db, store=store, cashier=user, lines=[(product, 1)], customer=None)
        payload = payload.model_copy(
            update={"sold_at": now - timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 9))}
        )
        try:
            record_sale(db, settings, payload)
            db.commit()
            sold += 1
        except Exception:
            db.rollback()
    report.append(f"{sold} sales over the last three weeks")
    report.extend(seed_till_demo(db, settings, user=user, store=store, products=[product for product, _ in sellable]))
    return report


def _discounted(db: Session, store: Store, user: User, product: Product, manual: int, reason: str) -> SalePayload:
    """A one-unit sale with a cashier discount, priced the way the register prices it (VAT on the charged amount)."""
    tax = tax_policy(db)
    rate = tax.rate_for(product.tax_category) if tax.enforced else 0
    priced = line_tax(product.price_cents - manual, 1, rate, inclusive=entered_includes_tax(product))
    payload = _payload(db, store=store, cashier=user, lines=[(product, 1)], customer=None)
    item = payload.items[0].model_copy(
        update={
            "manual_discount_cents": manual,
            "discount_reason": reason,
            "tax_cents": priced.tax_cents,
            "line_total_cents": priced.line_total_cents,
        }
    )
    return payload.model_copy(
        update={
            "items": [item],
            "tax_cents": priced.tax_cents,
            "subtotal_cents": priced.line_total_cents - priced.tax_cents,
            "total_cents": priced.line_total_cents,
        }
    )


def seed_till_demo(db: Session, settings: Settings, *, user: User, store: Store, products: list[Product]) -> list[str]:
    """Phase 1 till essentials: gift cards sold and issued, cashier discounts with reasons, a final-sale line."""
    if db.scalar(select(StoreCredit.id).where(StoreCredit.kind == "GIFT_CARD")) is not None or not products:
        return ["till demo already seeded (unchanged)"]
    report: list[str] = []
    gift = gift_card_service.ensure_product(db)
    db.commit()
    for amount in (10_000, 25_000):
        payload = _payload(db, store=store, cashier=user, lines=[(gift, 1)], customer=None)
        item = payload.items[0].model_copy(
            update={
                "unit_price_cents": amount,
                "list_price_cents": amount,
                "tax_cents": 0,
                "line_total_cents": amount,
                "gift_card_code": gift_card_service.new_code(),
            }
        )
        payload = payload.model_copy(
            update={"items": [item], "tax_cents": 0, "subtotal_cents": amount, "total_cents": amount}
        )
        record_sale(db, settings, payload)
        db.commit()
    gift_card_service.issue(
        db,
        user,
        GiftCardIssue(store_id=store.id, amount_cents=5_000, count=3, customer_id=None, note="Grand opening prizes"),
    )
    report.append("2 gift cards sold at the till and 3 issued as prizes")
    discounted = 0
    skipped: list[str] = []
    in_stock = (
        list(
            db.scalars(
                select(Product)
                .join(InventoryLevel, InventoryLevel.product_id == Product.id)
                .where(
                    Product.id.in_([product.id for product in products]),
                    InventoryLevel.store_id == store.id,
                    InventoryLevel.quantity_on_hand > 1,
                )
                .order_by(InventoryLevel.quantity_on_hand.desc())
            )
        )
        or products
    )
    for index, (reason, share) in enumerate((("staff", 20), ("damaged", 30), ("vip", 10), ("price_match", 5))):
        product = in_stock[index % len(in_stock)]
        db.refresh(product)
        try:
            record_sale(db, settings, _discounted(db, store, user, product, product.price_cents * share // 100, reason))
            db.commit()
            discounted += 1
        except Exception as error:  # noqa: BLE001 - demo data skips a sale the rules refuse and says why
            db.rollback()
            skipped.append(str(error))
    report.append(f"{discounted} sales with cashier discounts (staff, damaged, VIP, price match)")
    report.extend(f"discounted sale skipped: {reason}" for reason in dict.fromkeys(skipped))
    clearance = products[-1]
    clearance.is_final_sale = True
    db.commit()
    report.append(f"{clearance.name} marked final sale")
    return report
