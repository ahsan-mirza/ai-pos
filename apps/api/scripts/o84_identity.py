from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://ai_pos_app:o84-act-app-password@127.0.0.1:55944/axizpos_o84act")
with engine.connect() as conn:
    row = conn.execute(
        text(
            """
            SELECT current_user, current_database(), inet_server_port(),
                   (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
                   (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user),
                   (SELECT COUNT(*) FROM users),
                   (SELECT COUNT(*) FROM products),
                   (SELECT business_profile FROM business_settings LIMIT 1)
            """
        )
    ).one()
    conn.execute(text("SELECT set_config('app.tenant_id', '00000000-0000-4000-8000-0000000000a1', true)"))
    scoped = conn.execute(text("SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM devices), (SELECT business_profile FROM business_settings LIMIT 1)")).one()
    print("scoped_users", scoped[0])
    print("scoped_products", scoped[1])
    print("scoped_devices", scoped[2])
    print("scoped_profile", scoped[3])
    for item in conn.execute(text("SELECT business_profile FROM business_settings")).all():
        print("profile_row", item[0])
print("role", row[0])
print("database", row[1])
print("port", row[2])
print("super", row[3])
print("bypass", row[4])
print("users", row[5])
print("products", row[6])
print("profile", row[7])
