#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command '$1' was not found on PATH." >&2
    exit 1
  fi
}

# Every app reads the repo-root .env on this machine (.env.dev / .env.production elsewhere).
# Succeeds only when the file was created from the template, so its secrets still need generating.
ensure_development_env() {
  local example=".env.example"
  local destination=".env"
  if [[ ! -f "$example" ]]; then
    echo "Missing env template: $example" >&2
    exit 1
  fi
  if [[ -f "$destination" ]]; then
    echo "Kept existing $destination"
    return 1
  fi
  cp "$example" "$destination"
  echo "Created $destination"
}

require_cmd node
require_cmd pnpm
require_cmd python3

echo "Installing workspace packages..."
pnpm install

ENV_CREATED=0
ensure_development_env && ENV_CREATED=1 || true
if [[ "$ENV_CREATED" == "1" ]]; then
  echo "Generating secrets for the new .env..."
  node "$ROOT/scripts/generate-secrets.mjs"
  echo "Set DATABASE_URL in .env before migrating."
fi

VENV_PYTHON="$ROOT/apps/api/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Creating API virtualenv..."
  python3 -m venv "$ROOT/apps/api/.venv"
fi

echo "Installing API dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$ROOT/apps/api/requirements.txt" -r "$ROOT/apps/api/requirements-dev.txt"

echo "Generating desktop icons..."
node "$ROOT/scripts/generate-icon.mjs"

cat <<'EOF'

Bootstrap complete.
Next:
  docker compose up -d   (skip if PostgreSQL already runs on 5432)
  pnpm --filter @ai-pos/api migrate
  pnpm --filter @ai-pos/api seed
  pnpm dev
EOF
