#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="$ROOT_DIR/configs/local.env"
SERVICE="${1:-}"

cd "$ROOT_DIR"
"$ROOT_DIR/scripts/ensure-local-env.sh"

if [ -n "$SERVICE" ]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs -f --tail=200 "$SERVICE"
else
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs -f --tail=200
fi
