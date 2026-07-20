# Local Development

## Prerequisites

- A Docker-compatible local runtime, such as OrbStack or Docker Desktop
- Docker Compose v2
- A local or reachable model service if you want to test real agent calls

## 1. Configure Environment

Start from the template:

```sh
scripts/ensure-local-env.sh
```

This creates `configs/local.env` with absolute host paths for your current
checkout. Keep `configs/local.env` out of version control.

Update model settings when you want to test real agent calls:

```env
MODEL_BASE_URL=...
MODEL_API_KEY=...
MODEL_DEFAULT=...
```

The compose file uses `configs/.env.example` for broad defaults and
`configs/local.env` for machine-specific overrides.

## 2. Build Runtime Image

```sh
docker build -f docker/hermes-runtime/Dockerfile -t hermes-runtime:local .
```

Expected behavior:

- The image contains the Hermes WebUI source from `apps/webui`.
- The image contains the Hermes Agent source from `vendor/hermes-agent`.
- The image contains `skills` as a recommended skill catalog source.
- User data is not stored in the image.

The runtime Dockerfile pins its Python base image by digest. This avoids
unexpected rebuilds caused by a moving `python:3.11-slim` tag.

## 3. Test Single-User Runtime

```sh
docker run --rm \
  -p 8080:8080 \
  -v "$PWD/.data/local-user:/home/hermes/data" \
  -e PUBLIC_BASE_PATH=/user/local/ \
  --env-file configs/local.env \
  hermes-runtime:local
```

Open:

```text
http://localhost:8080/user/local/
```

After first startup, verify the persistent user data root exists:

```text
.data/local-user/
```

## 4. Test JupyterHub

```sh
docker compose -f docker-compose.local.yml up --build
```

The local scripts call compose with the generated env file:

```sh
docker compose --env-file configs/local.env -f docker-compose.local.yml up --build
```

Open:

```text
http://localhost:8000
```

For the MVP, the JupyterHub config uses NativeAuthenticator with open signup.
Create two test users and confirm each user gets:

```text
.data/users/{safe-user-slug}/skills/
.data/users/{safe-user-slug}/skill-state.json
```

In local JupyterHub mode, `docker-compose.local.yml` also mounts the repository
`skills/` directory into each user container as a read-only recommended skill
catalog source. By default, recommended skills are not auto-installed into user
skill directories; users should install them from the future Skill Hub flow.

Local development should keep:

```env
JUPYTERHUB_AUTH_MODE=native
```

Server integration with the Java + Vue platform should switch to:

```env
JUPYTERHUB_AUTH_MODE=oauth
OAUTH_USERNAME_KEY=id
```

See [platform-oauth-integration.md](platform-oauth-integration.md).

For server deployment, start from:

```sh
cp configs/server.env.example configs/server.env
```

Then edit host paths, ports, OAuth values, admin token, and model gateway URL.

## 5. Agent Integration

The runtime currently starts `apps/webui/server.py` directly so the WebUI can run
as a stable foreground container process. Hermes Agent is installed from
`vendor/hermes-agent` and exposed to the WebUI with:

```env
HERMES_WEBUI_AGENT_DIR=/home/hermes/agent
```

Useful checks:

- Startup logs should show `agent dir : /home/hermes/agent [ok]`.
- `python3 -c "import run_agent, tools.terminal_tool"` should pass inside the
  runtime container.
- `/api/health/agent` should no longer report `ModuleNotFoundError`. Until the
  gateway/model layer is configured, `gateway_not_configured` is expected.
