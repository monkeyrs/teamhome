#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.yml not found: ${COMPOSE_FILE}" >&2
  exit 1
fi

cd "${ROOT_DIR}"
docker compose up -d --build
docker compose ps api langgraph db
curl -sS http://127.0.0.1:8000/openapi.json >/dev/null && echo "API health: OK" || echo "API health: FAILED"
curl -sS http://127.0.0.1:22024/docs >/dev/null && echo "LangGraph health: OK" || echo "LangGraph health: FAILED"
docker compose logs --tail=120 api langgraph
