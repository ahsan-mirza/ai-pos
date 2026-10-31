"""Separate Alembic history for the plugin. It uses DATABASE_URL and alembic_version_einvoicing."""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from einvoicing.models import Base

config = context.config
url = os.environ.get("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_einvoicing",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
