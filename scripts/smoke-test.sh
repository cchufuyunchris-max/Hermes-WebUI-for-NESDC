#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="$ROOT_DIR/configs/local.env"

cd "$ROOT_DIR"
"$ROOT_DIR/scripts/ensure-local-env.sh" >/dev/null
# shellcheck disable=SC1090
. "$ENV_FILE"
ADMIN_URL="${HERMES_ADMIN_URL:-http://127.0.0.1:8001}"
HUB_URL="${JUPYTERHUB_URL:-http://127.0.0.1:8000}"

PASS_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "ok  - $1"
}

fail() {
  echo "fail - $1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
  pass "$1 is available"
}

http_ok() {
  url="$1"
  label="$2"
  if curl -fsS --max-time 8 "$url" >/dev/null; then
    pass "$label"
  else
    fail "$label ($url)"
  fi
}

container_running() {
  name="$1"
  running="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)"
  [ "$running" = "true" ] || fail "container is not running: $name"
  pass "container is running: $name"
}

user_slug() {
  printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/-/g; s/^[.-]*//; s/[.-]*$//'
}

echo "==> Hermes local smoke test"

require_cmd docker
require_cmd curl

"$ROOT_DIR/scripts/validate-runtime-layout.sh" >/dev/null
pass "runtime layout"

docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable"
pass "Docker daemon"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
pass "docker compose config"

container_running hermes-jupyterhub
container_running hermes-admin

http_ok "$HUB_URL/hub/login" "JupyterHub login page"
http_ok "$ADMIN_URL/login?next=/admin.html" "Hermes Admin login page"

if [ -n "${JUPYTERHUB_ADMIN_API_TOKEN:-}" ]; then
  export HUB_URL
  export JUPYTERHUB_ADMIN_API_TOKEN
  export HERMES_SMOKE_USER="${HERMES_SMOKE_USER:-smoke}"
  python3 - <<'PY'
import json
import os
import subprocess
import time

hub_url = os.environ["HUB_URL"].rstrip("/")
token = os.environ["JUPYTERHUB_ADMIN_API_TOKEN"]
user = os.environ.get("HERMES_SMOKE_USER", "smoke")
api = f"{hub_url}/hub/api"
headers = {
    "Authorization": f"token {token}",
    "Content-Type": "application/json",
}

def request(method, path, body=None, ok=(200, 201, 202, 204, 400, 409)):
    last_error = None
    for attempt in range(1, 6):
        cmd = [
            "curl",
            "-sS",
            "--max-time",
            "30",
            "-X",
            method,
            "-H",
            f"Authorization: token {token}",
            "-H",
            "Content-Type: application/json",
            "-o",
            "-",
            "-w",
            "\n%{http_code}",
            api + path,
        ]
        if body is not None:
            cmd.extend(["--data", json.dumps(body)])
        try:
            proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"curl exited {proc.returncode}")
            raw = proc.stdout
            payload, _, status_text = raw.rpartition("\n")
            status = int(status_text.strip())
            parsed = json.loads(payload) if payload.strip() else {}
            if status in ok:
                return status, parsed
            raise RuntimeError(f"{method} {path} failed: HTTP {status}: {payload}")
        except Exception as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(attempt)
                continue
            raise RuntimeError(f"{method} {path} failed after retries: {exc}") from exc
    raise RuntimeError(f"{method} {path} failed after retries: {last_error}")

request("GET", "", ok=(200,))
status, _ = request("GET", f"/users/{user}", ok=(200, 404))
if status == 404:
    request("POST", f"/users/{user}", {}, ok=(201, 409))

request("POST", f"/users/{user}/server", {}, ok=(201, 202, 400, 409))

deadline = time.time() + 180
last = None
while time.time() < deadline:
    _, payload = request("GET", f"/users/{user}", ok=(200,))
    last = payload
    servers = payload.get("servers") or {}
    default_server = servers.get("") or {}
    if default_server.get("ready") is True or payload.get("server"):
        print(f"spawn_ready user={user}")
        break
    time.sleep(3)
else:
    raise RuntimeError(f"JupyterHub user server did not become ready: {last}")
PY
  pass "JupyterHub smoke user spawned"

  smoke_user="${HERMES_SMOKE_USER:-smoke}"
  smoke_slug="$(user_slug "$smoke_user")"
  [ -n "$smoke_slug" ] || smoke_slug="user"
  smoke_container="jupyter-$smoke_slug"
  container_running "$smoke_container"

  if curl -fsS --max-time 15 -H "Authorization: token ${JUPYTERHUB_ADMIN_API_TOKEN}" "$HUB_URL/user/$smoke_user/" >/dev/null; then
    pass "smoke user WebUI page"
  else
    fail "smoke user WebUI page ($HUB_URL/user/$smoke_user/)"
  fi

  docker exec -i "$smoke_container" python3 - <<'PY'
import os
from pathlib import Path

expected = {
    "HERMES_WEBUI_DEFAULT_THEME": "light",
    "HERMES_WEBUI_DEFAULT_LANGUAGE": "zh",
    "HERMES_DISABLE_SERVICE_WORKER": "true",
    "HERMES_PROVISIONED_SKILLS_DIR": "/home/hermes/provisioned-skills",
    "HERMES_POLICY_ROOT": "/srv/hermes/policies",
}
for key, value in expected.items():
    actual = os.environ.get(key)
    assert actual == value, f"{key}={actual!r}, expected {value!r}"
assert Path("/home/hermes/provisioned-skills").exists(), "recommended skills dir missing"
assert Path("/srv/hermes/policies/global.json").exists(), "admin policy dir missing"
assert Path("/home/hermes/data").exists(), "user data dir missing"
assert Path("/home/hermes/data/workspace").exists(), "workspace dir missing"
print("user_runtime_env_ok")
PY
  pass "smoke user runtime environment"
else
  echo "skip - JUPYTERHUB_ADMIN_API_TOKEN is not set; user spawn smoke test skipped"
fi

docker exec -i hermes-admin python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/app")

from api.admin_policy import load_policy_payload, list_user_policy_payloads

policy_payload = load_policy_payload()
policy = policy_payload["policy"]
assert policy.get("enabled") is not False, "global policy disabled"
assert "model_policy" in policy, "missing model_policy"
assert "data_connectors" in policy, "missing data_connectors"

users_payload = list_user_policy_payloads()
assert isinstance(users_payload.get("users"), list), "users payload is not a list"

skills_root = Path("/home/hermes/provisioned-skills")
assert skills_root.exists(), "recommended skills root missing"
skill_files = list(skills_root.glob("*/SKILL.md"))
assert skill_files, "no recommended skills found"

print(
    "admin_policy_ok users=%s skills=%s"
    % (users_payload.get("count", len(users_payload.get("users", []))), len(skill_files))
)
PY
pass "admin policy, users, and recommended skills"

if command -v node >/dev/null 2>&1; then
  node --check apps/webui/static/admin.js >/dev/null
  node --check apps/webui/static/ui.js >/dev/null
  pass "admin/user static JavaScript syntax"
else
  echo "skip - node is not installed; JavaScript syntax check skipped"
fi

python3 -m py_compile apps/webui/api/admin_policy.py apps/webui/api/routes.py
python3 -m py_compile docker/hermes-runtime/policy-init.py
pass "admin Python syntax"

tmp_policy_dir="$(mktemp -d /tmp/hermes-policy-init-smoke.XXXXXX)"
MODEL_PROVIDER=deepseek \
MODEL_BASE_URL=https://api.deepseek.com \
MODEL_API_KEY=smoke-secret \
MODEL_DEFAULT=deepseek-chat \
HERMES_HOME="$tmp_policy_dir/hermes" \
python3 docker/hermes-runtime/policy-init.py
python3 - "$tmp_policy_dir/hermes" <<'PY'
import sys
from pathlib import Path

import yaml

home = Path(sys.argv[1])
cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
model = cfg.get("model") or {}
managed = cfg.get("managed_runtime") or {}
assert model.get("provider") == "deepseek", model
assert model.get("default") == "deepseek-chat", model
assert model.get("base_url") == "https://api.deepseek.com", model
assert model.get("api_key") == "smoke-secret", model
assert managed.get("model_source") == "admin_policy", managed
env_text = (home / ".env").read_text(encoding="utf-8")
assert "DEEPSEEK_API_KEY=" in env_text, env_text
assert "DEEPSEEK_BASE_URL=" in env_text, env_text
assert "MODEL_DEFAULT=" in env_text, env_text
PY
rm -rf "$tmp_policy_dir"
pass "admin local model policy init"

tmp_policy_dir="$(mktemp -d /tmp/hermes-policy-file-smoke.XXXXXX)"
mkdir -p "$tmp_policy_dir/policies/users"
cat >"$tmp_policy_dir/policies/global.json" <<'JSON'
{
  "model_policy": {
    "local_model": {
      "provider": "deepseek",
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "policy-secret",
      "model": "deepseek-v4-flash"
    }
  }
}
JSON
MODEL_PROVIDER=openai-compatible \
MODEL_BASE_URL=http://stale.example.invalid/v1 \
MODEL_API_KEY=stale-secret \
MODEL_DEFAULT=stale-model \
HERMES_POLICY_ROOT="$tmp_policy_dir/policies" \
HERMES_HOME="$tmp_policy_dir/hermes" \
python3 docker/hermes-runtime/policy-init.py
python3 - "$tmp_policy_dir/hermes" <<'PY'
import sys
from pathlib import Path

import yaml

home = Path(sys.argv[1])
cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
model = cfg.get("model") or {}
assert model.get("provider") == "deepseek", model
assert model.get("default") == "deepseek-v4-flash", model
assert model.get("base_url") == "https://api.deepseek.com/v1", model
assert model.get("api_key") == "policy-secret", model
PY
rm -rf "$tmp_policy_dir"
pass "admin policy file overrides model env"

tmp_import_dir="$(mktemp -d /tmp/hermes-skill-import-smoke.XXXXXX)"
mkdir -p "$tmp_import_dir/workspace" "$tmp_import_dir/data"
if ! PYTHONPATH=apps/webui \
HERMES_DATA_DIR="$tmp_import_dir/data" \
HERMES_WEBUI_DEFAULT_WORKSPACE="$tmp_import_dir/workspace" \
HERMES_PROVISIONED_SKILLS_DIR="$tmp_import_dir/recommended" \
python3 - <<'PY' >/dev/null 2>"$tmp_import_dir/import.err"
import shutil
import tempfile
import zipfile
from pathlib import Path

from api import routes

root = Path(tempfile.mkdtemp(prefix="skill-zip-src."))
repo = root / "nature-skills-main"
skill = repo / "climate-report"
skill.mkdir(parents=True)
(skill / "SKILL.md").write_text(
    "---\nname: climate-report\ndescription: Test climate skill\n---\n\n# Climate\n",
    encoding="utf-8",
)
zip_path = root / "repo.zip"
with zipfile.ZipFile(zip_path, "w") as zf:
    for path in repo.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(root).as_posix())

extract = root / "extract"
extract.mkdir()
routes._safe_extract_zip(zip_path, extract)
found = routes._find_importable_skill_dirs(extract)
assert len(found) == 1, found
dest = routes._admin_skill_path("climate-report")
dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(found[0], dest)
summary = routes._recommended_skill_summary(dest, set())
assert summary["name"] == "climate-report", summary
PY
then
  cat "$tmp_import_dir/import.err" >&2
  rm -rf "$tmp_import_dir"
  fail "GitHub Skill import core"
fi
rm -rf "$tmp_import_dir"
pass "GitHub Skill import core"

echo
echo "Smoke test passed ($PASS_COUNT checks)."
