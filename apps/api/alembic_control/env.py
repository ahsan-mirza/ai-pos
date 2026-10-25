"""Migrations for the console registry. Tenant schemas live in ../alembic.

The console used to keep these tables in qios_control. Production now has one database, so this
history uses its own version table when it runs beside the store schema.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.tenancy.models import ControlBase  # noqa: E402
from app.tenancy.registry import control_url  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
url = config.attributes.get("database_url") or (control_url(settings) if settings.control_database_url else None)
if not url:
    raise RuntimeError("CONTROL_DATABASE_URL is not configured.")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = ControlBase.metadata


def _version_table() -> str:
    """Keep the console revision list away from the store list when both share one database."""
    other = make_url(settings.database_url)
    current = make_url(url)
    if current.database == other.database and (current.host or "") == (other.host or ""):
        return "control_alembic_version"
    return "alembic_version"


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        version_table=_version_table(),
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
            version_table=_version_table(),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
