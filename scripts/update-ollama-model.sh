#!/usr/bin/env bash
# Pulls a replacement model into the existing Ollama volume. The previous model stays until you remove it.
# Usage: ./scripts/update-ollama-model.sh qwen3:4b
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODEL="${1:-}"
[[ -n "$MODEL" ]] || { echo "Pass the model name, for example qwen3:4b." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker is not installed." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose is not available." >&2; exit 1; }

docker compose up -d --no-deps ollama
docker compose exec -T ollama ollama pull "$MODEL"
docker compose exec -T ollama ollama list | grep -q "^${MODEL}[[:space:]]" || {
  echo "$MODEL is not listed after the pull." >&2
  exit 1
}
echo "$MODEL is available. Set OLLAMA_MODEL=$MODEL and restart the API. The old model is still on disk."
