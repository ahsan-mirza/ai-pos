from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # raw-sql: allowed (SQLite driver setting, no ORM equivalent)
            cursor.close()

        return engine

    return create_engine(database_url, pool_pre_ping=True)


def get_session_factory() -> sessionmaker[Session]:
    """Sessions for the tenant bound to this request/job, or DATABASE_URL when tenancy is off."""
    if get_settings().tenancy_enabled:
        from app.tenancy.context import current_tenant
        from app.tenancy.registry import session_factory_for

        tenant = current_tenant()
        if tenant is None:
            raise RuntimeError("No tenant is bound to this request or job.")
        return session_factory_for(tenant)
    global _engine, _session_factory
    if _session_factory is None:
        _engine = build_engine(get_settings().database_url)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


def create_database(server_url: str, name: str) -> bool:
    """Creates an empty Postgres database on the server of `server_url`. Returns False if it already exists."""
    if not name.replace("_", "").isalnum() or not name.islower():
        raise ValueError("Database names must be lowercase letters, digits, and underscores.")
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            cursor = connection.connection.cursor()
            exists = "SELECT 1 FROM pg_database WHERE datname = %s"
            cursor.execute(exists, (name,))  # raw-sql: allowed (catalog lookup before CREATE DATABASE)
            if cursor.fetchone() is not None:
                return False
            cursor.execute(f'CREATE DATABASE "{name}"')  # raw-sql: allowed (CREATE DATABASE has no ORM equivalent)
            return True
    finally:
        engine.dispose()


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
