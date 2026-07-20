#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/configs/local.env"
USER_ID="${1:-}"
CONFIRM="${2:-}"

if [ -z "$USER_ID" ]; then
  echo "Usage: scripts/dev-reset-user.sh <user_id> [--yes]" >&2
  exit 2
fi

case "$USER_ID" in
  *[!A-Za-z0-9_.-]*|"")
    echo "Invalid user id. Use letters, numbers, dot, underscore, or dash." >&2
    exit 2
    ;;
esac

"$ROOT_DIR/scripts/ensure-local-env.sh" >/dev/null
# shellcheck disable=SC1090
. "$ENV_FILE"

USER_DATA_DIR="${HERMES_HOST_USER_DATA_ROOT:-$ROOT_DIR/.data/users}/$USER_ID"
USER_POLICY_FILE="${HERMES_HOST_POLICY_ROOT:-$ROOT_DIR/configs/policies}/users/$USER_ID.json"
CONTAINER_NAME="jupyter-$USER_ID"

if [ "$CONFIRM" != "--yes" ]; then
  echo "This will stop the test container and delete Hermes data for user:"
  echo "  $USER_ID"
  echo
  echo "Paths:"
  echo "  $USER_DATA_DIR"
  echo "  $USER_POLICY_FILE"
  echo
  printf "Type the exact user id to continue: "
  read typed
  if [ "$typed" != "$USER_ID" ]; then
    echo "Cancelled."
    exit 1
  fi
fi

cd "$ROOT_DIR"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "==> Removing container $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

if [ -d "$USER_DATA_DIR" ]; then
  echo "==> Removing $USER_DATA_DIR"
  rm -rf "$USER_DATA_DIR"
fi

if [ -f "$USER_POLICY_FILE" ]; then
  echo "==> Removing $USER_POLICY_FILE"
  rm -f "$USER_POLICY_FILE"
fi

echo "User reset complete: $USER_ID"
