#!/usr/bin/env bash
# Create the Postgres role and databases named in /opt/ai-pos/.env.production when they are missing.
# Reads the password on the server and does not print it.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

ENV_FILE="${APP_DIR:-/opt/ai-pos}/.env.production"
test -f "$ENV_FILE" || { echo "Missing $ENV_FILE"; exit 1; }
systemctl enable --now postgresql

SQL_FILE=$(mktemp)
chmod 600 "$SQL_FILE"
python3 - "$ENV_FILE" "$SQL_FILE" <<'PY'
import re
import sys
import urllib.parse
from pathlib import Path

env_path, sql_path = sys.argv[1:]
values: dict[str, str] = {}
for line in Path(env_path).read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

def parsed(key: str) -> tuple[str, str, str]:
    raw = values.get(key, "")
    if not raw:
        raise SystemExit(f"{key} is not set in {env_path}")
    url = urllib.parse.urlparse(raw.replace("postgresql+psycopg://", "postgresql://", 1))
    user = urllib.parse.unquote(url.username or "")
    password = urllib.parse.unquote(url.password or "")
    database = urllib.parse.unquote(url.path.lstrip("/").split("?", 1)[0])
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", user):
        raise SystemExit(f"{key} user is not a plain Postgres identifier")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise SystemExit(f"{key} database is not a plain Postgres identifier")
    return user, password, database

user, password, database = parsed("DATABASE_URL")
_, _, control = parsed("CONTROL_DATABASE_URL")
tag = "pwd"
while f"${tag}$" in password:
    tag += "x"
quoted = f"${tag}${password}${tag}$"
names = [database] if database == control else [database, control]
creates = "\n".join(
    "SELECT format('CREATE DATABASE %I OWNER %I', '{name}', '{user}')\n"
    "WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{name}')\\gexec".format(name=name, user=user)
    for name in names
)
Path(sql_path).write_text(
    f"""
DO $body$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{user}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %s CREATEDB', '{user}', {quoted});
  END IF;
END
$body$;
ALTER ROLE "{user}" CREATEDB;
{creates}
""",
    encoding="utf-8",
)
PY
sudo -u postgres psql -v ON_ERROR_STOP=1 -f "$SQL_FILE" >/dev/null
rm -f "$SQL_FILE"
echo "Postgres role and databases are present."
