"""Postgres row-level security. Skipped unless TEST_DATABASE_URL points at a disposable database."""

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.database import build_engine, set_session_tenant
from app.models.brand import Brand

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not set")


def test_missing_tenant_context_hides_rows_and_a_foreign_tenant_cannot_write() -> None:
    engine = build_engine(os.environ["TEST_DATABASE_URL"])
    Brand.__table__.create(engine, checkfirst=True)
    statements = (
        "ALTER TABLE brands ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE brands FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS tenant_isolation ON brands",
        "CREATE POLICY tenant_isolation ON brands "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
        "OR current_setting('app.bypass_rls', true) = 'on') "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
        "OR current_setting('app.bypass_rls', true) = 'on')",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    alpha = uuid.uuid4()
    bravo = uuid.uuid4()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        connection = db.connection()
        set_session_tenant(connection, str(alpha))
        db.add(Brand(name="Alpha", code="ALP", tenant_id=alpha))
        db.commit()
    with factory() as db:
        rows = db.scalars(select(Brand)).all()
        assert rows == []
        set_session_tenant(db.connection(), str(bravo))
        db.add(Brand(name="Alpha", code="ALP", tenant_id=alpha))
        with pytest.raises(SQLAlchemyError):
            db.commit()
    engine.dispose()
