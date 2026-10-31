"""Polls einvoicing_outbox. Run as its own process: python -m einvoicing.worker"""

from __future__ import annotations

import time

from einvoicing.db import SessionLocal
from einvoicing.service import process_outbox


def main() -> None:
    while True:
        db = SessionLocal()
        try:
            process_outbox(db)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":
    main()
