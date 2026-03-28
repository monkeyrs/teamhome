#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/root/teamhome}"
ENV_FILE="${ROOT_DIR}/backend/.env"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.prod.yml"

cd "$ROOT_DIR"

read_env_value() {
  local key="$1"
  local default_value="${2:-}"
  local line
  if [[ ! -f "${ENV_FILE}" ]]; then
    printf '%s' "${default_value}"
    return
  fi
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "${ENV_FILE}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    printf '%s' "${default_value}"
    return
  fi
  line="${line#*=}"
  line="${line%$'\r'}"
  line="${line#\"}"
  line="${line%\"}"
  line="${line#\'}"
  line="${line%\'}"
  printf '%s' "${line}"
}

validate_backend_security_config() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "backend/.env not found: ${ENV_FILE}" >&2
    exit 1
  fi

  local environment
  environment="$(read_env_value ENVIRONMENT production)"
  environment="${environment,,}"
  if [[ "${environment}" != "production" ]]; then
    echo "Backend security preflight: ENVIRONMENT=${environment}"
    return
  fi

  local issues=()
  local database_url
  database_url="$(read_env_value DATABASE_URL)"
  if [[ "${database_url}" == *"://admin:admin@"* ]]; then
    issues+=("DATABASE_URL must not use default admin/admin credentials.")
  fi

  local postgres_user
  postgres_user="$(read_env_value POSTGRES_USER admin)"
  local postgres_password
  postgres_password="$(read_env_value POSTGRES_PASSWORD admin)"
  if [[ "${postgres_user}" == "admin" && "${postgres_password}" == "admin" ]]; then
    issues+=("POSTGRES_USER/POSTGRES_PASSWORD must not both remain admin/admin.")
  fi

  local jwt_secret
  jwt_secret="$(read_env_value JWT_SECRET)"
  if [[ -z "${jwt_secret}" || "${jwt_secret}" == "dev-secret-change-me" || ${#jwt_secret} -lt 32 ]]; then
    issues+=("JWT_SECRET must be a non-default value with at least 32 characters.")
  fi

  local cors_allow_origins
  cors_allow_origins="$(read_env_value CORS_ALLOW_ORIGINS '*')"
  if [[ "${cors_allow_origins}" == *"*"* ]]; then
    issues+=("CORS_ALLOW_ORIGINS must not contain '*'.")
  fi

  [[ -n "$(read_env_value WECHAT_APPID)" ]] || issues+=("WECHAT_APPID is required.")
  [[ -n "$(read_env_value WECHAT_SECRET)" ]] || issues+=("WECHAT_SECRET is required.")

  local allow_insecure_dev_auth
  allow_insecure_dev_auth="$(read_env_value ALLOW_INSECURE_DEV_AUTH false)"
  if [[ "${allow_insecure_dev_auth,,}" == "true" ]]; then
    issues+=("ALLOW_INSECURE_DEV_AUTH must be false.")
  fi

  local enable_debug_endpoints
  enable_debug_endpoints="$(read_env_value ENABLE_DEBUG_ENDPOINTS false)"
  if [[ "${enable_debug_endpoints,,}" == "true" ]]; then
    issues+=("ENABLE_DEBUG_ENDPOINTS must be false.")
  fi

  if (( ${#issues[@]} > 0 )); then
    printf 'Unsafe production backend config in backend/.env: %s\n' "${issues[*]}" >&2
    exit 1
  fi

  echo "Backend security preflight: production config OK"
}

export_compose_env() {
  export POSTGRES_DB
  export POSTGRES_USER
  export POSTGRES_PASSWORD
  export DATABASE_URL

  POSTGRES_DB="$(read_env_value POSTGRES_DB teamhome)"
  POSTGRES_USER="$(read_env_value POSTGRES_USER admin)"
  POSTGRES_PASSWORD="$(read_env_value POSTGRES_PASSWORD admin)"

  local default_database_url
  default_database_url="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  DATABASE_URL="$(read_env_value DATABASE_URL "${default_database_url}")"
}

read_demo_seed_mode() {
  local configured
  configured="$(read_env_value DEMO_SEED_MODE '')"
  configured="${configured,,}"
  if [[ -n "${configured}" ]]; then
    printf '%s' "${configured}"
    return
  fi
  printf '%s' "auto"
}

get_api_container_name() {
  local container_id
  container_id="$(docker compose -f "${COMPOSE_FILE}" ps -q api 2>/dev/null | head -n 1 || true)"
  if [[ -z "${container_id}" ]]; then
    return
  fi
  docker inspect --format '{{.Name}}' "${container_id}" 2>/dev/null | sed 's#^/##'
}

run_in_api_container() {
  local command="$1"
  local container_name
  container_name="$(get_api_container_name)"
  if [[ -n "${container_name}" ]]; then
    docker exec "${container_name}" sh -lc "${command}"
    return
  fi
  docker compose -f "${COMPOSE_FILE}" run --rm api sh -lc "${command}"
}

run_demo_seed_if_auto() {
  if [[ "$(read_demo_seed_mode)" != "auto" ]]; then
    echo "demo seed deploy step: skipped"
    return
  fi
  echo "demo seed deploy step: running"
  run_in_api_container "DEMO_SEED_MODE=manual python -m app.commands.seed_demo_data"
}

echo "[1/4] pull latest code"
git pull origin main

echo "[2/4] build and start containers"
validate_backend_security_config
export_compose_env
docker compose -f "${COMPOSE_FILE}" up -d db
docker compose -f "${COMPOSE_FILE}" build api langgraph
docker compose -f "${COMPOSE_FILE}" up -d api langgraph
run_in_api_container "alembic upgrade head"
run_demo_seed_if_auto
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate api langgraph

echo "[3/4] show container status"
docker compose -f "${COMPOSE_FILE}" ps
run_in_api_container "alembic current" && echo "Database migrations: current" || echo "Database migrations: FAILED"
echo "Demo seed mode: $(read_demo_seed_mode)"

echo "[4/4] check api health"
curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null
echo "API is up: http://127.0.0.1:8000/openapi.json"
