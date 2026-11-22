from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _sqlite_memory(database_url: str) -> bool:
    """True when a new connection would open a different empty database.

    `sqlite://` and `sqlite:///:memory:` are per connection. A file URL (`sqlite:///path`) is not.
    """
    if ":memory:" in database_url:
        return True
    return database_url.rstrip("/") in {"sqlite:", "sqlite://"}


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        # Requests run on worker threads, so sqlite's same-thread check has to be off.
        # StaticPool is one connection for every thread. sqlite3 then raises InterfaceError
        # ("bad parameter or other API misuse") or returns torn rows when the portal fires
        # parallel requests. In-memory databases cannot be shared any other way, and the test
        # suite uses them one request at a time. A file database gets its own connection per
        # checkout, which is what a server needs.
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if _sqlite_memory(database_url) else NullPool,
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


def set_session_tenant(connection, tenant_id: str) -> None:
    """Tell Postgres which tenant this transaction may see. Ignored on SQLite."""
    set_session_scope(connection, tenant_id, None, None)


def set_session_scope(connection, tenant_id: str, store_id: str | None, device_id: str | None) -> None:
    """Bind tenant, store, and device for this transaction. Empty store or device fails closed.

    Ignored on SQLite. These settings are not an authorization bypass. Policies do not
    treat app.bypass_rls as permission to read another tenant.
    """
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(  # raw-sql: allowed (RLS)
        "SELECT set_config('app.tenant_id', %s, true), "
        "set_config('app.store_id', %s, true), "
        "set_config('app.device_id', %s, true)",
        (tenant_id, store_id or "", device_id or ""),
    )


def bypass_session_tenant(connection) -> None:
    """Retained for migration callers. Row policies no longer open because this flag is set.

    A superuser or a role with BYPASSRLS still bypasses FORCE ROW LEVEL SECURITY.
    The application login must have neither. Ignored on SQLite.
    """
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql("SELECT set_config('app.bypass_rls', 'off', true)")  # raw-sql: allowed (RLS)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    # HTTP sessions cannot turn on include_all_tenants. Migrations and the merge command can.
    session.info["request_session"] = True
    try:
        yield session
    finally:
        from app.tenancy.context import clear_scope

        clear_scope()
        session.close()


def _install_tenant_scope() -> None:
    from app.tenancy.scoping import install

    install()


_install_tenant_scope()
