"""Seed two branches and two customers for the disposable laundry tenant."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")


def main() -> None:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.customer import Customer
    from app.models.store import Store
    from app.tenancy import registry
    from app.tenancy.context import use_tenant

    settings = get_settings()
    found = registry.lookup("laundry-a", settings)
    if found.tenant is None:
        raise SystemExit("Laundry tenant is not registered.")
    with use_tenant(found.tenant):
        db = registry.session_factory_for(found.tenant)()
        try:
            for code, name in (("A", "Branch A"), ("B", "Branch B")):
                if db.scalar(select(Store).where(Store.code == code)) is None:
                    db.add(Store(code=code, name=name, currency="AED"))
            for code, name in (("WALK", "Walk-in Customer"), ("HOTEL", "Hotel Account")):
                if db.scalar(select(Customer).where(Customer.code == code)) is None:
                    db.add(Customer(code=code, name=name))
            db.commit()
            stores = db.scalars(select(Store).order_by(Store.code)).all()
            customers = db.scalars(select(Customer).order_by(Customer.code)).all()
        finally:
            db.close()
    print("stores", [(row.code, row.name) for row in stores])
    print("customers", [(row.code, row.name) for row in customers])


if __name__ == "__main__":
    main()
