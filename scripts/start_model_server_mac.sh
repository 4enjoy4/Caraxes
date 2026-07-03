#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_PATH="${CARAXES_MODEL_PATH:-"$ROOT/models/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-GGUF/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-Q4_K.gguf"}"
HOST="${CARAXES_MODEL_HOST:-0.0.0.0}"
PORT="${CARAXES_MODEL_PORT:-9901}"
CONTEXT="${CARAXES_N_CTX:-32768}"
REASONING="${CARAXES_REASONING:-off}"
REASONING_BUDGET="${CARAXES_REASONING_BUDGET:-0}"

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model file not found: $MODEL_PATH"
  echo "Set CARAXES_MODEL_PATH=/path/to/model.gguf or copy the model into the Caraxes models folder."
  exit 1
fi

if ! command -v llama-server >/dev/null 2>&1; then
  echo "llama-server not found."
  echo "Install llama.cpp on macOS, for example: brew install llama.cpp"
  exit 1
fi

echo "Starting llama.cpp server on http://$HOST:$PORT/v1"
echo "Model: $MODEL_PATH"
echo "Context: $CONTEXT"

exec llama-server \
  -m "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  -c "$CONTEXT" \
  --reasoning "$REASONING" \
  --reasoning-budget "$REASONING_BUDGET"
