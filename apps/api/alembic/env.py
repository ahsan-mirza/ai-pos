import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_reach_root = Path(__file__).resolve().parents[3] / "plugins" / "reach"
if _reach_root.is_dir():
    sys.path.insert(0, str(_reach_root))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402
from app.tenancy.registry import resolve_cli_database_url  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Tenant databases: the tenant CLI passes the URL; `alembic -x tenant=<slug>` (or TENANT=<slug>) looks it up.
database_url = config.attributes.get("database_url") or resolve_cli_database_url(
    settings, context.get_x_argument(as_dictionary=True).get("tenant")
)
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata
_version_locations = [str(Path(__file__).resolve().parent / "versions")]
_reach_versions = _reach_root / "backend" / "migrations"
if _reach_versions.is_dir():
    _version_locations.append(str(_reach_versions))


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_locations=_version_locations,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_locations=_version_locations,
        )
        with context.begin_transaction():
            # Later revisions run after row-level security is forced on. A local bypass lets DDL
            # and data moves see every row; request sessions never set this.
            from app.core.database import bypass_session_tenant

            bypass_session_tenant(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
