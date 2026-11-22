from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://o82boot@127.0.0.1:55944/axizpos_o84act")
with engine.begin() as conn:
    deleted = conn.execute(text("DELETE FROM business_settings WHERE business_profile <> 'grocery'")).rowcount
    left = conn.execute(text("SELECT business_profile FROM business_settings")).scalars().all()
print("deleted", deleted)
print("left", ",".join(left))
