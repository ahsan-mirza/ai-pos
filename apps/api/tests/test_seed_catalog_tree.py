import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.brand import Brand, ProductModel
from app.models.product import Product
from app.seed import catalog_path, seed_catalog_tree, seed_categories


def test_catalog_tree_seeds_brands_models_and_variants_once(session: Session) -> None:
    seed_categories(session)
    tree = json.loads(catalog_path().read_text(encoding="utf-8"))["catalog_tree"]
    first = seed_catalog_tree(session, "AED")
    assert first
    assert seed_catalog_tree(session, "AED") == []

    assert session.scalar(select(func.count()).select_from(Brand)) == len(tree)
    assert session.scalar(select(func.count()).select_from(ProductModel)) == sum(len(b["models"]) for b in tree)
    with_barcode = sum(1 for b in tree for m in b["models"] for v in m["variants"] if "barcode" in v)
    assert session.scalar(select(func.count()).select_from(Product)) == with_barcode

    variant = session.scalar(select(Product).where(Product.sku == "APL-IP16PM-256-DST"))
    assert variant is not None
    assert variant.name == "iPhone 16 Pro Max 256GB Desert Titanium"
    assert variant.brand == "Apple"
    assert variant.category == "Phones"
    assert variant.variant_attributes == {"storage": "256GB", "color": "Desert Titanium"}
    assert variant.product_model is not None and variant.product_model.name == "iPhone 16 Pro Max"
    assert variant.sub_category_ref is not None and variant.sub_category_ref.name == "Smartphones"
    apple = session.scalar(select(Brand).where(Brand.name == "Apple"))
    assert apple is not None
    assert {"Smartphones", "Laptops", "iPads", "Smartwatches", "Earbuds"} <= {s.name for s in apple.sub_categories}
