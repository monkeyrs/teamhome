#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/root/teamhome}"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.prod.yml"

cd "${ROOT_DIR}"

docker compose -f "${COMPOSE_FILE}" run --rm -e DEMO_SEED_MODE=manual api python -m app.commands.seed_demo_data
