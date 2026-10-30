#!/usr/bin/env bash
# Starts the pinned Ollama service, pulls qwen3:8b only when it is missing, and checks the host can reach it.
# Safe to run again. Does not restart Postgres, Redis, or the API.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="ollama/ollama:0.40.13"
SERVICE="ollama"
PULL=0
if [[ "${1:-}" == "--pull" ]]; then
  PULL=1
fi

ENV_FILE=""
for candidate in .env.production .env; do
  if [[ -f "$candidate" ]]; then
    ENV_FILE="$candidate"
    break
  fi
done

fail() {
  echo "deploy-ollama: $*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
docker compose version >/dev/null 2>&1 || fail "Docker Compose is not available."
[[ -n "$ENV_FILE" ]] || fail "No .env.production or .env file was found."

read_env() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  printf "%s" "${line#*=}"
}

PROVIDER="$(read_env ASSISTANT_PROVIDER)"
MODEL="$(read_env OLLAMA_MODEL)"
BASE_URL="$(read_env OLLAMA_BASE_URL)"
[[ "$PROVIDER" == "ollama" ]] || fail "$ENV_FILE must set ASSISTANT_PROVIDER=ollama (it is '${PROVIDER:-unset}')."
[[ -n "$MODEL" ]] || fail "$ENV_FILE must set OLLAMA_MODEL."
[[ -n "$BASE_URL" ]] || fail "$ENV_FILE must set OLLAMA_BASE_URL."

echo "Image: $IMAGE"
echo "Environment: $ENV_FILE"
echo "Provider: $PROVIDER"
echo "Model: $MODEL"

docker compose up -d --no-deps "$SERVICE"

ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T "$SERVICE" ollama list >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" == "1" ]] || fail "Ollama did not become ready."

if [[ "$PULL" == "1" ]] || ! docker compose exec -T "$SERVICE" ollama list | grep -q "^${MODEL}[[:space:]]"; then
  echo "Pulling $MODEL"
  docker compose exec -T "$SERVICE" ollama pull "$MODEL"
else
  echo "$MODEL is already present."
fi

docker compose exec -T "$SERVICE" ollama list | grep -q "^${MODEL}[[:space:]]" || fail "$MODEL is not available after pull."

PROBE="http://127.0.0.1:11434"
curl -fsS "$PROBE/api/tags" >/dev/null || fail "The host cannot reach Ollama at $PROBE."

GENERATE="$(curl -fsS "$PROBE/api/generate" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Say ok\",\"stream\":false,\"think\":false,\"options\":{\"num_predict\":8}}")"
printf "%s" "$GENERATE" | grep -q '"response"' || fail "Ollama did not return a generation."

echo "Ollama is reachable from the host at $PROBE."
echo "Configured OLLAMA_BASE_URL=$BASE_URL"
if [[ "$BASE_URL" == http://ollama:* || "$BASE_URL" == http://ollama/* ]]; then
  echo "That hostname works for a container on the Compose network. This host API should use $PROBE."
fi
echo "Deployment finished. Postgres and Redis were not restarted."
