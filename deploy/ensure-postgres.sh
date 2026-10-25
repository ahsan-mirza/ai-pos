#!/usr/bin/env bash
# Let the API role create databases, and create tables in the shared and control databases.
# Does not create a role or a database. The password in the env file is never printed or written to disk.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

ENV_FILE="${APP_DIR:-/opt/ai-pos}/.env.production"
test -f "$ENV_FILE" || { echo "Missing $ENV_FILE"; exit 1; }

parsed=$(python3 - "$ENV_FILE" <<'PY'
import re
import sys
import urllib.parse
from pathlib import Path

values = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

def identifier(value, label):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise SystemExit(f"{label} is not a plain Postgres identifier")
    return value

def parts(key):
    raw = values.get(key, "")
    if not raw:
        raise SystemExit(f"{key} is not set")
    url = urllib.parse.urlparse(raw.replace("postgresql+psycopg://", "postgresql://", 1))
    user_name = identifier(urllib.parse.unquote(url.username or ""), f"{key} user")
    database = identifier(urllib.parse.unquote((url.path or "").lstrip("/")), f"{key} database")
    return user_name, database

user_name, database = parts("DATABASE_URL")
names = [database]
control = values.get("CONTROL_DATABASE_URL", "")
if control:
    control_user, control_database = parts("CONTROL_DATABASE_URL")
    if control_user != user_name:
        raise SystemExit("CONTROL_DATABASE_URL must use the same role as DATABASE_URL")
    if control_database not in names:
        names.append(control_database)
print(user_name)
for name in names:
    print(name)
PY
)

mapfile -t rows <<<"$parsed"
user="${rows[0]}"
printf 'ALTER ROLE "%s" CREATEDB;\n' "$user" | sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres >/dev/null
echo "Role ${user} can create databases."
for database in "${rows[@]:1}"; do
  printf 'GRANT USAGE, CREATE ON SCHEMA public TO "%s";\n' "$user" \
    | sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$database" >/dev/null
  echo "Role ${user} can create tables in ${database}."
done
