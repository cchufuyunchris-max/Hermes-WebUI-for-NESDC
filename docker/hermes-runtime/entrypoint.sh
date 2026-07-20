#!/usr/bin/env sh
set -eu

: "${PORT:=8080}"
: "${HERMES_DATA_DIR:=/home/hermes/data}"
: "${HERMES_USER_SKILLS_DIR:=$HERMES_DATA_DIR/skills}"
: "${HERMES_PROVISIONED_SKILLS_DIR:=/home/hermes/provisioned-skills}"

python3 /home/hermes/runtime/policy-init.py
python3 /home/hermes/runtime/skill-init.py

if [ -f /home/hermes/app/server.py ]; then
  cd /home/hermes/app
  exec python3 /home/hermes/app/server.py
fi

if [ -x /home/hermes/app/start.sh ]; then
  exec /home/hermes/app/start.sh --foreground --no-browser
fi

echo "No /home/hermes/app/start.sh found. Starting placeholder static server on port ${PORT}."
exec python3 /home/hermes/runtime/placeholder-server.py
