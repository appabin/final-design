#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/milvus_remote.sh start    # start etcd + minio + milvus
  ./scripts/milvus_remote.sh stop     # stop milvus stack
  ./scripts/milvus_remote.sh status   # show service status
  ./scripts/milvus_remote.sh logs     # tail milvus logs
USAGE
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required but not found in PATH."
    exit 1
  fi
}

wait_for_milvus() {
  echo "Waiting for Milvus health endpoint http://127.0.0.1:9091/healthz ..."
  for _ in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:9091/healthz" >/dev/null 2>&1; then
      echo "Milvus is healthy."
      return 0
    fi
    sleep 2
  done
  echo "Milvus health check timed out."
  exit 1
}

start_stack() {
  docker compose -f "$COMPOSE_FILE" up -d etcd minio milvus-standalone
  wait_for_milvus
  cat <<EOF
Done.

Use this in backend .env:
  MILVUS_MODE=remote
  MILVUS_URI=http://127.0.0.1:19530
EOF
}

stop_stack() {
  docker compose -f "$COMPOSE_FILE" stop milvus-standalone minio etcd
}

status_stack() {
  docker compose -f "$COMPOSE_FILE" ps etcd minio milvus-standalone
}

logs_stack() {
  docker compose -f "$COMPOSE_FILE" logs -f --tail=120 milvus-standalone
}

cmd="${1:-}"
require_docker

case "$cmd" in
  start) start_stack ;;
  stop) stop_stack ;;
  status) status_stack ;;
  logs) logs_stack ;;
  *) usage; exit 1 ;;
esac

