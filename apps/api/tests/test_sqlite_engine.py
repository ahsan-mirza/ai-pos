"""File SQLite must not hand one connection to concurrent requests.

The portal loads the board, settings, and billing together. StaticPool shares one sqlite3
connection across those threads, and sqlite3 answers with InterfaceError or a torn row.
"""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.database import build_engine


def test_memory_sqlite_keeps_one_connection_for_the_suite() -> None:
    engine = build_engine("sqlite://")
    try:
        assert isinstance(engine.pool, StaticPool)
    finally:
        engine.dispose()


def test_file_sqlite_gives_each_checkout_its_own_connection(tmp_path) -> None:
    engine = build_engine(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    factory = sessionmaker(bind=engine)
    try:
        assert isinstance(engine.pool, NullPool)
        with factory() as session:
            connection = session.connection()
            connection.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, name TEXT)")
            connection.exec_driver_sql("INSERT INTO probe (id, name) VALUES (1, 'one')")
            session.commit()

        def read(_: int) -> None:
            with factory() as session:
                row = session.connection().exec_driver_sql("SELECT name FROM probe WHERE id = 1").fetchone()
                assert row is not None and row[0] == "one"

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(read, range(40)))
    finally:
        engine.dispose()
