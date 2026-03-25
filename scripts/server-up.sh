#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/root/teamhome}"

cd "$ROOT_DIR"

echo "[1/4] pull latest code"
git pull origin main

echo "[2/4] build and start containers"
docker compose up -d --build

echo "[3/4] show container status"
docker compose ps

echo "[4/4] check api health"
curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null
echo "API is up: http://127.0.0.1:8000/openapi.json"
