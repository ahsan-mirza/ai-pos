import os
import sys

sys.path.insert(0, r"D:\Work\ai-pos\apps\api")
os.environ["APP_ENV"] = "acceptance"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("CONTROL_DATABASE_URL", None)

from sqlalchemy import create_engine, text

from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    names = connection.execute(
        text("SELECT tgname FROM pg_trigger WHERE tgname = 'batch_item_events_append_only' AND NOT tgisinternal")
    ).scalars().all()
    role = connection.execute(text("SELECT current_user")).scalar_one()
print("role", role)
print("trigger", ",".join(names) or "missing")
