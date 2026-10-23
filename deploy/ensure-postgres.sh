#!/usr/bin/env bash
# Let the API role create one database per store. Does not create a role or a database.
# The password in the env file is never printed or written to disk.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

ENV_FILE="${APP_DIR:-/opt/ai-pos}/.env.production"
test -f "$ENV_FILE" || { echo "Missing $ENV_FILE"; exit 1; }

user=$(python3 - "$ENV_FILE" <<'PY'
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

raw = values.get("DATABASE_URL", "")
if not raw:
    raise SystemExit("DATABASE_URL is not set")
url = urllib.parse.urlparse(raw.replace("postgresql+psycopg://", "postgresql://", 1))
name = urllib.parse.unquote(url.username or "")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
    raise SystemExit("DATABASE_URL user is not a plain Postgres identifier")
print(name)
PY
)

printf 'ALTER ROLE "%s" CREATEDB;\n' "$user" | sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres >/dev/null
echo "Role ${user} can create databases."
