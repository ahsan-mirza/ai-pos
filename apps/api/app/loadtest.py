"""Catalog load test (`python -m app.loadtest --products 50000`).

Seeds N products, then times what a supermarket register leans on: paging the whole catalog the way a register
syncs it (GET /products?after=, 1000 per page) and product search (GET /products/search). Without --database-url it
builds a throwaway SQLite file; with one (a Postgres with migrations applied) it inserts LT- products and always
deletes them again, so real trigram indexes can be measured.
"""

import argparse
import random
import statistics
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import build_engine
from app.models import Base
from app.models.product import Product
from app.services.catalog_service import list_products
from app.services.product_search import search_products
from app.tenancy.scoping import active_tenant_id, use_database_tenant

PREFIX = "LT-"
PAGE = 1000
WORDS = (
    "apple banana carrot dates eggs flour garlic honey ice-cream juice kale lemon milk noodles olive pepper quinoa "
    "rice salt tomato vinegar water yogurt zucchini bread butter cheese coffee tea sugar"
).split()
BRANDS = ("Almarai", "Al Ain", "Nestle", "Barakat", "Lulu", "Kraft", "Heinz", None)
SIZES = ("250 G", "500 G", "1 KG", "1 L", "2 L", "6 PACK")


def seed(db: Session, count: int, currency: str) -> None:
    rng = random.Random(20261021)
    tenant_id = active_tenant_id()
    rows = []
    for index in range(count):
        word, other = rng.choice(WORDS), rng.choice(WORDS)
        size = rng.choice(SIZES)
        rows.append(
            {
                "id": uuid.uuid4(),
                "sku": f"{PREFIX}{index:06d}",
                "barcode": f"6{index:011d}",
                "name": f"{word.title()} {other} {size}",
                "model_number": f"{word[:3].upper()}-{index % 977:03d}" if index % 3 == 0 else None,
                "brand": rng.choice(BRANDS),
                "category": rng.choice(("Fresh", "Dairy", "Pantry", "Drinks", "Bakery", "Frozen")),
                "price_cents": rng.randint(100, 9_000),
                "currency": currency,
                "variant_attributes": {},
                "sellable_units": ["PIECE"],
                "tenant_id": tenant_id,
            }
        )
        if len(rows) == 5_000:
            db.execute(insert(Product), rows)
            rows = []
    if rows:
        db.execute(insert(Product), rows)
    db.commit()


def timed(work: Callable[[], object]) -> float:
    started = time.perf_counter()
    work()
    return (time.perf_counter() - started) * 1000


def page_through(db: Session) -> tuple[int, int, float]:
    pages = seen = 0
    after: uuid.UUID | None = None
    started = time.perf_counter()
    while True:
        rows = list_products(db, limit=PAGE, after=after)
        pages += 1
        seen += len(rows)
        if len(rows) < PAGE:
            break
        after = rows[-1].id
    return pages, seen, (time.perf_counter() - started) * 1000


def report(label: str, samples: list[float]) -> None:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    print(f"  {label:<28} p50 {statistics.median(ordered):7.1f} ms   p95 {p95:7.1f} ms   max {ordered[-1]:7.1f} ms")


def run(database_url: str, count: int, currency: str, fresh_schema: bool) -> None:
    engine = build_engine(database_url)
    if fresh_schema:
        Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with use_database_tenant(database_url), factory() as db:
        existing = db.scalar(select(func.count()).select_from(Product).where(Product.sku.startswith(PREFIX))) or 0
        if existing:
            raise SystemExit(f"{existing} {PREFIX} products already exist; delete them first.")
        print(f"Seeding {count:,} products on {engine.dialect.name}...")
        print(f"  seeded in {timed(lambda: seed(db, count, currency)) / 1000:.1f} s")
        try:
            total = db.scalar(select(func.count()).select_from(Product)) or 0
            pages, seen, elapsed = page_through(db)
            print(f"Register catalog sync: {seen:,} of {total:,} products in {pages} pages, {elapsed / 1000:.2f} s")
            queries = {
                "one word (milk)": "milk",
                "two words (rice 1 kg)": "rice 1",
                "brand + word": "almarai yogurt",
                "exact barcode": f"6{count // 2:011d}",
                "SKU without dash": f"lt{count // 3:06d}",
                "no match": "zzqx",
            }
            print("Search (50 hits, 30 runs each):")
            for label, query in queries.items():
                report(label, [timed(lambda q=query: search_products(db, q, limit=50)) for _ in range(30)])
        finally:
            if not fresh_schema:
                db.execute(delete(Product).where(Product.sku.startswith(PREFIX)))
                db.commit()
                print(f"Removed the {PREFIX} products.")
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--products", type=int, default=50_000)
    parser.add_argument("--database-url", help="Measure an existing database (migrated) instead of a temp SQLite.")
    parser.add_argument("--currency", default="AED")
    args = parser.parse_args()
    if args.database_url:
        run(args.database_url, args.products, args.currency, fresh_schema=False)
        return
    with tempfile.TemporaryDirectory() as folder:
        run(f"sqlite:///{Path(folder) / 'loadtest.db'}", args.products, args.currency, fresh_schema=True)


if __name__ == "__main__":
    main()
