# Hermes WebUI

Engineering scaffold for running Hermes WebUI + Hermes Agent as a multi-user,
containerized service.

Current target:

1. Package a single-user `hermes-runtime` image.
2. Provision default project skills into each user's persistent data directory.
3. Run one isolated runtime container per user through JupyterHub + DockerSpawner.
4. Keep local, server, and platform integration differences in configuration.

See [docs/engineering-plan.md](docs/engineering-plan.md) for the implementation
plan.

See [docs/local-dev.md](docs/local-dev.md) for local build and startup steps.

See [docs/local-ops.md](docs/local-ops.md) for local test-environment
operations, smoke tests, logs, and single-user reset scripts.

See [docs/deployment-config.md](docs/deployment-config.md) for environment
configuration, server migration, and externalized settings.

See [docs/server-migration.md](docs/server-migration.md) for the complete
GitHub-to-server migration checklist, including Docker installation, first
startup, reverse proxy, model policy sync, and update flow.

See [docs/server-ops.md](docs/server-ops.md) for 24h server startup,
systemd-managed Docker Compose, logs, updates, and backup guidance.

## Layout

```text
apps/webui/                 # Hermes WebUI source
vendor/hermes-agent/        # Hermes Agent source vendored into runtime image
docker/hermes-runtime/      # Single-user runtime image and startup scripts
docker/jupyterhub/          # JupyterHub + DockerSpawner configuration
skills/                     # Recommended skill catalog source for admins
configs/                    # Environment templates
scripts/                    # Local validation and maintenance scripts
docker-compose.local.yml    # Local JupyterHub/Admin stack
docker-compose.server.yml   # Server stack with restart policy
```

## First Milestone

The first milestone is not full platform integration. It is a stable runtime:

```text
Hermes WebUI + Hermes Agent + default skills + persistent user data
```

Once this is stable, JupyterHub can safely start one copy per user.

The runtime image installs the vendored Hermes Agent in editable mode and points
the WebUI at `/home/hermes/agent` through `HERMES_WEBUI_AGENT_DIR`.
