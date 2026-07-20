#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="$ROOT_DIR/configs/local.env"

cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required. Start OrbStack or Docker Desktop first." >&2
  exit 1
fi

echo "==> Validating runtime layout"
"$ROOT_DIR/scripts/validate-runtime-layout.sh"
"$ROOT_DIR/scripts/ensure-local-env.sh"
# shellcheck disable=SC1090
. "$ENV_FILE"

echo "==> Building local images"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build hermes-runtime-build jupyterhub

echo "==> Starting JupyterHub and Hermes Admin"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d jupyterhub hermes-admin

echo
echo "Hermes test environment is starting:"
echo "  JupyterHub:   ${JUPYTERHUB_URL:-http://127.0.0.1:8000}"
echo "  Admin:        ${HERMES_ADMIN_URL:-http://127.0.0.1:8001}/admin.html"
echo
echo "Run smoke tests with:"
echo "  scripts/smoke-test.sh"
