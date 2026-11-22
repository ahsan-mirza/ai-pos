"""Confirm the grocery tenant still cannot see laundry rows and its brands are intact."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")


def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    control = create_engine(settings.control_database_url)
    with control.connect() as conn:
        ids = dict(conn.execute(text("SELECT slug, id::text FROM tenants WHERE slug IN ('laundry-a', 'grocery-b')")).all())
    control.dispose()
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": ids["grocery-b"]})
        brands = conn.execute(text("SELECT count(*) FROM brands")).scalar()
        services = conn.execute(text("SELECT count(*) FROM laundry_services")).scalar()
    engine.dispose()
    print({"grocery_brands": brands, "grocery_laundry_services": services})
    if brands != 5 or services != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
