#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="$ROOT_DIR/configs/local.env"

cd "$ROOT_DIR"
"$ROOT_DIR/scripts/ensure-local-env.sh"

echo "==> Stopping local Hermes test environment"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down

echo
echo "Stopped. Persistent data was kept under:"
echo "  $ROOT_DIR/.data"
echo
echo "To delete one test user's Hermes data, run:"
echo "  scripts/dev-reset-user.sh <user_id>"
