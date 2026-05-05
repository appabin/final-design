#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
VENV_DIR="${HACHI_VENV_DIR:-$PROJECT_DIR/venv311}"
PYTHON_BIN="$VENV_DIR/bin/python"

HOST="${HACHI_HOST:-127.0.0.1}"
PORT="${HACHI_PORT:-8008}"

echo
echo "Starting Hachi MVP backend on http://$HOST:$PORT"
echo "Using Python environment: $VENV_DIR"
cd "$BACKEND_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python interpreter: $PYTHON_BIN"
  echo "Create or activate /Users/appa/Hachi_Assistant/venv311 first."
  exit 1
fi

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

exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
