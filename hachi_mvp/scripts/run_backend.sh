#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
VENV_DIR="$BACKEND_DIR/.venv"

HOST="${HACHI_HOST:-0.0.0.0}"
PORT="${HACHI_PORT:-8008}"

echo
echo "Starting Hachi MVP backend on http://$HOST:$PORT"
cd "$BACKEND_DIR"

if [[ -f "$ENV_FILE" ]]; then
  MILVUS_MODE_FILE="$(awk -F= '$1=="MILVUS_MODE"{print $2}' "$ENV_FILE" | tail -n 1)"
  MILVUS_URI_FILE="$(awk -F= '$1=="MILVUS_URI"{print $2}' "$ENV_FILE" | tail -n 1)"
  if [[ "${MILVUS_MODE_FILE:-}" == "remote" ]]; then
    echo "Detected MILVUS_MODE=remote (URI=${MILVUS_URI_FILE:-unset})."
    echo "If Milvus is not started yet, run:"
    echo "  $ROOT_DIR/scripts/milvus_remote.sh start"
    echo
  fi
fi

exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
