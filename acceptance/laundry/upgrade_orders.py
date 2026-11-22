"""Apply the laundry order migration to the disposable cluster only, then grant the application role."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.laundry-acceptance"


def _value(name: str) -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Missing {name}")


def main() -> None:
    from sqlalchemy.engine import make_url

    owner_url = _value("LAUNDRY_OWNER_URL")
    app_url = _value("DATABASE_URL")
    for label, raw in (("owner", owner_url), ("app", app_url)):
        parsed = make_url(raw)
        if parsed.host != "127.0.0.1" or parsed.port != 55821 or parsed.database != "axizpos_laundry_acceptance":
            raise SystemExit(f"Refusing {label} URL")
    if make_url(owner_url).username != "axizpos_laundry" or make_url(app_url).username != "ai_pos_app":
        raise SystemExit("Refusing unexpected database login")

    os.environ["DATABASE_URL"] = owner_url
    os.environ["APP_ENV"] = "laundry-acceptance"
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    os.chdir(ROOT / "apps" / "api")
    from app.tenancy.cli import upgrade_tenant

    upgrade_tenant(owner_url, destination="20261121_0123")

    from sqlalchemy import create_engine, text

    owner = create_engine(owner_url)
    with owner.begin() as conn:
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    owner.dispose()
    if head != "20261121_0123":
        raise SystemExit(f"Unexpected head {head}")

    os.environ["DATABASE_URL"] = app_url
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.permissions import SUPER_ADMIN_PERMISSIONS, SUPER_ADMIN_ROLE_ID
    from app.models.role import Role
    from app.tenancy import registry
    from app.tenancy.context import use_tenant

    settings = get_settings()
    found = registry.lookup("laundry-a", settings)
    if found.tenant is None:
        raise SystemExit("Laundry tenant is missing")
    with use_tenant(found.tenant):
        db = registry.session_factory_for(found.tenant)()
        role = db.get(Role, uuid.UUID(SUPER_ADMIN_ROLE_ID))
        if role is None:
            raise SystemExit("Super Admin role is missing")
        role.set_permissions(set(SUPER_ADMIN_PERMISSIONS))
        db.commit()
        db.close()
    print({"head": head, "role_updated": True})


if __name__ == "__main__":
    main()
