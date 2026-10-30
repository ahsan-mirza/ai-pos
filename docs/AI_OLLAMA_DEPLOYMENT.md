# Ollama deployment

The API process reads `OLLAMA_*` from the repo-root env file (`.env.production` in production). The model name is that setting. Application code does not choose a model of its own.

## Service

`docker-compose.yml` runs `ollama/ollama:0.40.13`. The model volume is `ai_pos_ollama`. Port `11434` is bound to `127.0.0.1` only, so it is not reachable from the public network. Other Compose services can use `http://ollama:11434`. This API runs on the host, so `.env.production` uses `http://127.0.0.1:11434`.

CPU is the default. A host with the NVIDIA container toolkit can add `gpus: all` under the `ollama` service. Do not require a laptop GPU.

## Commands

```bash
chmod +x scripts/deploy-ollama.sh scripts/update-ollama-model.sh
./scripts/deploy-ollama.sh
```

The script starts only the `ollama` service, waits until `ollama list` works, and pulls `OLLAMA_MODEL` when it is missing. `--pull` downloads it again.

To switch models on a smaller machine:

```bash
./scripts/update-ollama-model.sh qwen3:4b
```

Then set `OLLAMA_MODEL=qwen3:4b` and restart the API. Confirm the server has enough RAM for the chosen model and for the concurrent requests you expect before treating it as production.

## Health

`GET /api/v1/assistant/health` requires the reports permission. It returns the configured provider, the configured model name, whether Ollama answered its tag list, and whether the built-in fallback is on. It does not return the network address.

If Ollama does not answer and `ASSISTANT_FALLBACK_ENABLED=true`, questions use the built-in assistant and the same report tools.
