#!/usr/bin/env sh
set -eu

required_paths="
apps/webui
docker/hermes-runtime/Dockerfile
docker/hermes-runtime/entrypoint.sh
docker/hermes-runtime/skill-init.py
docker/hermes-runtime/placeholder-server.py
docker/jupyterhub/Dockerfile
docker/jupyterhub/jupyterhub_config.py
skills/eco-stations-climate-report/SKILL.md
configs/.env.example
configs/local.env.example
configs/server.env.example
docker-compose.local.yml
docker-compose.server.yml
docs/engineering-plan.md
docs/local-ops.md
docs/server-ops.md
scripts/ensure-local-env.sh
scripts/smoke-test.sh
"

for path in $required_paths; do
  if [ ! -e "$path" ]; then
    echo "Missing required path: $path" >&2
    exit 1
  fi
done

echo "Runtime layout is valid."
