"""Tenant administration.

python -m app.tenancy.cli init                                  # create / upgrade the control database
python -m app.tenancy.cli create client1 --name "Client One"    # new database qios_client1, migrated + Super Admin
python -m app.tenancy.cli create cafe1 --name "Cafe" --profile cafe   # same, with the cafe module preset
python -m app.tenancy.cli adopt demo --name "Demo" --database ai_pos   # register an existing database
python -m app.tenancy.cli migrate-all                           # upgrade every tenant database
python -m app.tenancy.cli list
python -m app.tenancy.cli set-status client1 suspended
python -m app.tenancy.cli create-operator --email it@qios.ae --name "IT Support" --role ADMIN   # console staff
python -m app.tenancy.cli collect-stats                         # refresh the console directory (run daily)
python -m app.tenancy.cli demo                                  # one demo store per business type, with registers
"""

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.capabilities import DEFAULT_PROFILE, PROFILES
from app.core.config import Settings, env_file_name, get_settings
from app.core.database import build_engine, create_database
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.tenancy import registry
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
    command.upgrade(_alembic("alembic_control", "alembic_control.ini", settings.control_database_url), "head")


def upgrade_tenant(url: str) -> None:
    command.upgrade(_alembic("alembic", "alembic.ini", url), "head")


def _seed_admin(url: str, settings: Settings) -> str:
    from app.seed import admin_spec

    spec = admin_spec(settings)
    factory = sessionmaker(bind=build_engine(url), expire_on_commit=False)
    with factory() as session:
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


def _set_profile(url: str, profile: str) -> None:
    from app.services.settings_service import provision_profile

    factory = sessionmaker(bind=build_engine(url), expire_on_commit=False)
    with factory() as session:
        provision_profile(session, profile)


def _register(slug: str, name: str, url: str, settings: Settings, profile: str = DEFAULT_PROFILE) -> None:
    with registry.control_session(settings) as db:
        if db.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
            sys.exit(f"Tenant '{slug}' already exists.")
        tenant = Tenant(
            slug=slug,
            name=name,
            status="active",
            profile=profile,
            database_url_encrypted=registry.encrypt_database_url(url, settings),
        )
        db.add(tenant)
        db.flush()
        from app.console.billing import start_trial

        start_trial(db, tenant)
        db.commit()
    registry.invalidate(slug)


def _check_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not registry.valid_slug(slug):
        sys.exit("Subdomains are 1-32 lowercase letters, digits, or dashes, and not a reserved name (www, api, ...).")
    return slug


def create(args: argparse.Namespace, settings: Settings) -> None:
    slug = _check_slug(args.slug)
    database = args.database or f"qios_{slug.replace('-', '_')}"
    url = registry.tenant_database_url(database, settings)
    if make_url(url).get_backend_name() == "postgresql":
        server = make_url(url).set(database="postgres").render_as_string(hide_password=False)
        made = create_database(server, database)
        print(f"Database {database} {'created' if made else 'already existed'}.")
    upgrade_tenant(url)
    _register(slug, args.name, url, settings, args.profile)
    print(_seed_admin(url, settings))
    _set_profile(url, args.profile)
    print(f"Business profile {args.profile}; the first admin sign-in runs the onboarding wizard.")
    print(f"Tenant '{slug}' ready at {registry.tenant_public_url(slug, settings)}")


def adopt(args: argparse.Namespace, settings: Settings) -> None:
    slug = _check_slug(args.slug)
    url = args.url or registry.tenant_database_url(args.database, settings)
    upgrade_tenant(url)
    _register(slug, args.name, url, settings)
    print(f"Adopted {make_url(url).database} as tenant '{slug}' ({registry.tenant_public_url(slug, settings)}).")


def migrate_all(_: argparse.Namespace, settings: Settings) -> None:
    with registry.control_session(settings) as db:
        rows = db.scalars(select(Tenant).order_by(Tenant.slug)).all()
        targets = [(row.slug, registry.lookup(row.slug, settings).tenant) for row in rows]
    for slug, tenant in targets:
        if tenant is None:
            continue
        print(f"Migrating {slug}...")
        upgrade_tenant(tenant.database_url)
    print(f"{len(targets)} tenant database(s) at head.")


def list_tenants(_: argparse.Namespace, settings: Settings) -> None:
    with registry.control_session(settings) as db:
        for row in db.scalars(select(Tenant).order_by(Tenant.slug)):
            database = make_url(registry.lookup(row.slug, settings).tenant.database_url).database  # type: ignore[union-attr]
            print(f"{row.slug:<20} {row.status:<10} {database:<24} {row.name}")


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
    demo = sub.add_parser("demo", help="create or refresh one demo store per business type, with POS registers")
    demo.add_argument("--only", nargs="*", help="subdomains to include (default: all in demo-businesses.json)")

    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "init":
        upgrade_control(settings)
        print("Control database is at head.")
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
        "demo": demo_stores,
    }[args.command](args, settings)


if __name__ == "__main__":
    main()
