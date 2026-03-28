#!/usr/bin/env bash
set -euo pipefail
export PYTHONUTF8=1
export PYTHONIOENCODING=UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
ENV_FILE="${ROOT_DIR}/backend/.env"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.yml not found: ${COMPOSE_FILE}" >&2
  exit 1
fi

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
  environment="$(read_env_value ENVIRONMENT development)"
  environment="${environment,,}"
  if [[ "${environment}" != "production" ]]; then
    echo "Backend security preflight: ENVIRONMENT=${environment}"
    return
  fi

  local issues=()
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

cd "${ROOT_DIR}"
validate_backend_security_config
docker compose up -d db
docker compose build api langgraph
docker compose run --rm api alembic upgrade head
docker compose up -d --force-recreate api langgraph
docker compose ps api langgraph db
docker compose run --rm api alembic current && echo "Database migrations: current" || echo "Database migrations: FAILED"
curl -sS http://127.0.0.1:8000/openapi.json >/dev/null && echo "API health: OK" || echo "API health: FAILED"
curl -sS http://127.0.0.1:8000/openapi.json | grep -q '"/timeline"' && echo "Timeline route: OK" || echo "Timeline route: MISSING"
curl -sS http://127.0.0.1:22024/docs >/dev/null && echo "LangGraph health: OK" || echo "LangGraph health: FAILED"
docker compose logs --tail=120 api langgraph
