"""Tenant administration.

python -m app.tenancy.cli init                                  # create / upgrade the control database
python -m app.tenancy.cli create client1 --name "Client One"    # new database qios_client1, migrated + Super Admin
python -m app.tenancy.cli create cafe1 --name "Cafe" --profile cafe   # same, with the cafe module preset
python -m app.tenancy.cli adopt demo --name "Demo" --database ai_pos   # register an existing database
python -m app.tenancy.cli migrate-all                           # upgrade every tenant database
python -m app.tenancy.cli list
python -m app.tenancy.cli set-status client1 suspended
python -m app.tenancy.cli create-operator --email it@axizpos.com --name "IT Support" --role ADMIN   # console staff
python -m app.tenancy.cli collect-stats                         # refresh the console directory (run daily)
python -m app.tenancy.cli demo                                  # one demo store per business type, with registers
"""

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.capabilities import DEFAULT_PROFILE, PROFILES
from app.core.config import Settings, env_file_name, get_settings
from app.core.database import build_engine
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.tenancy import registry
from app.tenancy.context import TenantRef
from app.tenancy.models import TENANT_STATUSES, Tenant

API_ROOT = Path(__file__).resolve().parents[2]


def _alembic(script: str, ini: str, url: str) -> Config:
    config = Config(str(API_ROOT / ini))
    config.set_main_option("script_location", str(API_ROOT / script))
    config.attributes["database_url"] = url
    return config


def upgrade_control(settings: Settings) -> None:
    if not settings.control_database_url:
        sys.exit(f"Set CONTROL_DATABASE_URL in {env_file_name(settings.app_env)} at the repo root first.")
    url = registry.control_url(settings)
    if url != settings.control_database_url:
        missing = make_url(settings.control_database_url).database
        print(f"Control database {missing} does not exist. Using {make_url(url).database}.")
    command.upgrade(_alembic("alembic_control", "alembic_control.ini", url), "head")


def upgrade_tenant(url: str, tenant_id: str | None = None) -> None:
    previous = os.environ.get("ALEMBIC_TENANT_ID")
    if tenant_id:
        os.environ["ALEMBIC_TENANT_ID"] = str(tenant_id)
    else:
        os.environ.pop("ALEMBIC_TENANT_ID", None)
    try:
        command.upgrade(_alembic("alembic", "alembic.ini", url), "head")
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_TENANT_ID", None)
        else:
            os.environ["ALEMBIC_TENANT_ID"] = previous


def _seed_admin(tenant, settings: Settings) -> str:
    from app.seed import admin_spec
    from app.tenancy.context import use_tenant

    spec = admin_spec(settings)
    factory = sessionmaker(bind=build_engine(tenant.database_url), expire_on_commit=False)
    with use_tenant(tenant), factory() as session:
        ensure_system_roles(session)
        admin, created = ensure_super_admin(
            session,
            settings,
            username=spec.username,
            email=spec.email,
            full_name=spec.full_name,
            password=spec.password or "",
            pin=spec.pin,
        )
        session.commit()
        return f"Super Admin '{admin.username}' {'created' if created else 'already exists'}"


def _set_profile(tenant, profile: str) -> None:
    from app.services.settings_service import provision_profile
    from app.services.taxonomy_service import ensure_taxonomy
    from app.tenancy.context import use_tenant

    factory = sessionmaker(bind=build_engine(tenant.database_url), expire_on_commit=False)
    with use_tenant(tenant), factory() as session:
        provision_profile(session, profile)
        ensure_taxonomy(session, profile)
        session.commit()


def _register(
    slug: str,
    name: str,
    url: str,
    settings: Settings,
    profile: str = DEFAULT_PROFILE,
    data_plane: str = "legacy",
) -> None:
    with registry.control_session(settings) as db:
        if db.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
            sys.exit(f"Tenant '{slug}' already exists.")
        tenant = Tenant(
            slug=slug,
            name=name,
            status="active",
            profile=profile,
            data_plane=data_plane,
            database_url_encrypted=registry.encrypt_database_url(url, settings),
        )
        db.add(tenant)
        db.flush()
        from app.console.billing import start_trial

        start_trial(db, tenant)
        db.commit()
    registry.invalidate(slug)


def _check_slug(slug: str) -> str:
    slug = registry.normalize_store_code(slug)
    if not registry.valid_slug(slug):
        sys.exit("Subdomains are 1-32 lowercase letters, digits, or dashes, and not a reserved name (www, api, ...).")
    return slug


def create(args: argparse.Namespace, settings: Settings) -> None:
    """Registers a store on the shared operational database. No new database is created."""
    slug = _check_slug(args.slug)
    url = settings.database_url
    upgrade_tenant(url)
    _register(slug, args.name, url, settings, args.profile, data_plane="shared")
    found = registry.lookup(slug, settings)
    if found.tenant is None:
        sys.exit(f"Tenant '{slug}' was not registered.")
    print(_seed_admin(found.tenant, settings))
    _set_profile(found.tenant, args.profile)
    print(f"Business profile {args.profile}; the first admin sign-in runs the onboarding wizard.")
    print(f"Tenant '{slug}' ready at {registry.tenant_public_url(slug, settings)}")


def adopt(args: argparse.Namespace, settings: Settings) -> None:
    slug = _check_slug(args.slug)
    url = args.url or registry.tenant_database_url(args.database, settings)
    # The id has to exist before the migration stamps existing rows.
    _register(slug, args.name, url, settings)
    found = registry.lookup(slug, settings)
    if found.tenant is None:
        sys.exit(f"Tenant '{slug}' was not registered.")
    upgrade_tenant(url, found.tenant.id)
    print(f"Adopted {make_url(url).database} as tenant '{slug}' ({registry.tenant_public_url(slug, settings)}).")


def _apply_taxonomy(tenant) -> int:
    """Fill a store's category tree from the profile already saved on its settings."""
    from app.models.business_settings import BusinessSettings
    from app.services.taxonomy_service import ensure_taxonomy
    from app.tenancy.context import use_tenant

    factory = sessionmaker(bind=build_engine(tenant.database_url), expire_on_commit=False)
    with factory() as session, use_tenant(tenant):
        row = session.scalar(select(BusinessSettings).limit(1))
        if row is None or not row.business_profile:
            return 0
        added = ensure_taxonomy(session, row.business_profile)
        session.commit()
        return added


def _database_name(url: str) -> str:
    return make_url(url).database or url


def migrate_all(_: argparse.Namespace, settings: Settings) -> None:
    """Upgrade every live store database, then the shared database.

    Existing stores are still `legacy` and keep their own databases. Those are the production
    databases. `DATABASE_URL` is the shared database for new stores; it may be empty, and a failure
    there must not skip the databases that are already serving sales.

    Shared stores are catalogued after that shared database is upgraded. Taxonomy reads
    business_settings, which fails when a new column such as purchased_capabilities is still missing.
    """
    with registry.control_session(settings) as db:
        slugs = [row.slug for row in db.scalars(select(Tenant).order_by(Tenant.slug)).all()]
    seen: set[str] = set()
    legacy = 0
    shared: list[tuple[str, TenantRef]] = []
    for slug in slugs:
        tenant = registry.lookup(slug, settings).tenant
        if tenant is None:
            continue
        if tenant.data_plane == "shared":
            shared.append((slug, tenant))
            continue
        if tenant.database_url in seen:
            continue
        seen.add(tenant.database_url)
        legacy += 1
        print(f"Migrating legacy {slug} ({_database_name(tenant.database_url)})...")
        upgrade_tenant(tenant.database_url, tenant.id)
        added = _apply_taxonomy(tenant)
        if added:
            print(f"  {slug}: {added} catalog rows added.")
    shared_name = _database_name(settings.database_url)
    if settings.database_url in seen:
        print(f"Shared database {shared_name} was migrated with its legacy tenant.")
    else:
        print(f"Migrating the shared operational database ({shared_name})...")
        upgrade_tenant(settings.database_url)
    for slug, tenant in shared:
        added = _apply_taxonomy(tenant)
        if added:
            print(f"  {slug}: {added} catalog rows added.")
    print(f"Migrations finished. {len(shared)} shared tenant(s), {legacy} legacy database(s).")


def list_tenants(_: argparse.Namespace, settings: Settings) -> None:
    with registry.control_session(settings) as db:
        for row in db.scalars(select(Tenant).order_by(Tenant.slug)):
            found = registry.lookup(row.slug, settings).tenant
            database = make_url(found.database_url).database if found is not None else "?"  # type: ignore[union-attr]
            plane = found.data_plane if found is not None else row.data_plane
            print(f"{row.slug:<20} {row.status:<10} {plane:<8} {database:<24} {row.name}")


def set_status(args: argparse.Namespace, settings: Settings) -> None:
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == args.slug))
        if row is None:
            sys.exit(f"Tenant '{args.slug}' does not exist.")
        row.status = args.status
        db.commit()
    registry.invalidate(args.slug)
    print(f"{args.slug} is now {args.status}.")


def create_operator(args: argparse.Namespace, settings: Settings) -> None:
    """Console staff account. The password is typed (never an argument, so it stays out of shell history)."""
    import getpass

    from app.console.auth import create_operator as make_operator

    password = getpass.getpass(
        "Password (8+ characters, with an uppercase letter, a number and a special character): "
    )
    if password != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match.")
    try:
        operator, _secret = make_operator(
            settings, email=args.email, full_name=args.name, role=args.role, password=password
        )
    except ValueError as error:
        sys.exit(str(error))
    print(f"Operator {operator.email} ({operator.role}) created.")


def collect_stats(_: argparse.Namespace, settings: Settings) -> None:
    from app.console.stats import collect_all

    done, failed = collect_all(settings)
    print(f"Measured {done} tenant(s); {failed} could not be reached.")


def merge_shared(args: argparse.Namespace, settings: Settings) -> None:
    import json

    from app.tenancy.merge import merge_tenant

    report = merge_tenant(settings, args.tenant, commit=args.commit)
    print(json.dumps(report, indent=2, default=str))
    if report["status"] not in {"ok", "already_shared"}:
        sys.exit(1)


def demo_stores(args: argparse.Namespace, settings: Settings) -> None:
    from app.tenancy.demo import provision_all, report

    report(provision_all(settings, set(args.only) if args.only else None))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.tenancy.cli", description="Manage tenants.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create or upgrade the control database")
    made = sub.add_parser("create", help="provision a new tenant database")
    made.add_argument("slug")
    made.add_argument("--name", required=True)
    made.add_argument("--database", help="database name (default qios_<slug>)")
    made.add_argument("--profile", choices=tuple(PROFILES), default=DEFAULT_PROFILE, help="business profile preset")
    adopted = sub.add_parser("adopt", help="register an existing database as a tenant")
    adopted.add_argument("slug")
    adopted.add_argument("--name", required=True)
    group = adopted.add_mutually_exclusive_group(required=True)
    group.add_argument("--database", help="existing database name on the DATABASE_URL server")
    group.add_argument("--url", help="full SQLAlchemy URL of the existing database")
    sub.add_parser("migrate-all", help="upgrade every tenant database to head")
    sub.add_parser("list", help="list tenants")
    status = sub.add_parser("set-status", help="activate or suspend a tenant")
    status.add_argument("slug")
    status.add_argument("status", choices=TENANT_STATUSES)
    operator = sub.add_parser("create-operator", help="add a POS-company console operator")
    operator.add_argument("--email", required=True)
    operator.add_argument("--name", required=True)
    operator.add_argument("--role", choices=("SUPPORT", "ADMIN"), default="SUPPORT")
    sub.add_parser("collect-stats", help="refresh the console's size and activity snapshot of every tenant")
    merge = sub.add_parser("merge-shared", help="copy one legacy tenant database into the shared database")
    merge.add_argument("--tenant", required=True)
    merge.add_argument("--commit", action="store_true", help="write rows and switch the tenant when checks pass")
    demo = sub.add_parser("demo", help="create or refresh one demo store per business type, with POS registers")
    demo.add_argument("--only", nargs="*", help="subdomains to include (default: all in demo-businesses.json)")

    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "init":
        upgrade_control(settings)
        from app.console.auth import ensure_console_admin

        try:
            admin = ensure_console_admin(settings)
        except ValueError as error:
            sys.exit(str(error))
        print("Control database is at head.")
        if admin is not None:
            print(f"Console admin {admin.email} is ready.")
        return
    if not settings.tenancy_enabled:
        file_name = env_file_name(settings.app_env)
        sys.exit(f"Set CONTROL_DATABASE_URL in {file_name} at the repo root and run `init` first.")
    {
        "create": create,
        "adopt": adopt,
        "migrate-all": migrate_all,
        "list": list_tenants,
        "set-status": set_status,
        "create-operator": create_operator,
        "collect-stats": collect_stats,
        "merge-shared": merge_shared,
        "demo": demo_stores,
    }[args.command](args, settings)


if __name__ == "__main__":
    main()
