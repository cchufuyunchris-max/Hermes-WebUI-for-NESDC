import json
import os
import re
from copy import deepcopy
from pathlib import Path

from nativeauthenticator import NativeAuthenticator
from oauthenticator.generic import GenericOAuthenticator


c = get_config()  # noqa: F821

c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.base_url = os.environ.get("JUPYTERHUB_BASE_URL", "/")
c.JupyterHub.default_url = os.environ.get("JUPYTERHUB_DEFAULT_URL", "/hub/home")
c.JupyterHub.db_url = os.environ.get(
    "JUPYTERHUB_DB_URL",
    "sqlite:////srv/jupyterhub-data/jupyterhub.sqlite",
)


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"Invalid policy JSON: {path}: {exc}") from exc


def runtime_policy_for_user(username: str, slug: str) -> dict:
    policy_root = Path(os.environ.get("HERMES_POLICY_ROOT", "/srv/hermes/policies"))
    global_policy = read_json_file(policy_root / "global.json")
    user_policy = read_json_file(policy_root / "users" / f"{username}.json")
    if slug != username:
        user_policy = deep_merge(user_policy, read_json_file(policy_root / "users" / f"{slug}.json"))
    return deep_merge(global_policy, user_policy)


def policy_bool(value, default: bool = False) -> str:
    if value is None:
        return "true" if default else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"


def policy_env_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def policy_csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


READONLY_MODES = {"read", "readonly", "read-only", "ro", "select-only"}
DATABASE_CONNECTOR_TYPES = {
    "clickhouse",
    "postgres",
    "postgresql",
    "mysql",
    "mariadb",
    "sqlite",
    "duckdb",
    "mongo",
    "mongodb",
    "redis",
    "database",
}


def connector_id(connector: dict) -> str:
    return str(connector.get("id") or connector.get("name") or connector.get("type") or "").strip()


def connector_type(connector: dict) -> str:
    return str(connector.get("type") or "").strip().lower()


def connector_access_mode(connector: dict) -> str:
    mode = str(connector.get("access_mode") or connector.get("mode") or "").strip().lower()
    if connector.get("readonly") is True and not mode:
        return "read-only"
    return mode


def connector_is_readonly(connector: dict) -> bool:
    return connector.get("readonly") is True or connector_access_mode(connector) in READONLY_MODES


def normalize_data_connectors(policy: dict) -> dict:
    raw = policy.get("data_connectors")
    if isinstance(raw, dict):
        connectors = raw.get("connectors") or []
        audit = raw.get("audit") if isinstance(raw.get("audit"), dict) else {}
    elif isinstance(raw, list):
        connectors = raw
        audit = {}
    else:
        connectors = []
        audit = {}

    normalized = []
    for item in connectors:
        if isinstance(item, dict) and item.get("enabled", True) is not False:
            normalized.append(item)

    # Backward compatibility for the earlier flat policy fields.
    dify = policy.get("dify")
    if isinstance(dify, dict) and dify.get("enabled", True) is not False:
        normalized.append(
            {
                "id": "dify-public",
                "type": "dify",
                "enabled": True,
                "privacy_level": dify.get("privacy_level") or "public",
                "access_mode": "read-only",
                **dify,
            }
        )

    clickhouse = policy.get("clickhouse")
    if isinstance(clickhouse, dict) and clickhouse.get("enabled", True) is not False:
        normalized.append(
            {
                "id": "clickhouse-readonly",
                "type": "clickhouse",
                "enabled": True,
                "privacy_level": clickhouse.get("privacy_level") or "private",
                "access_mode": clickhouse.get("access_mode") or "read-only",
                "readonly": True,
                **clickhouse,
            }
        )

    seen = set()
    deduped = []
    for connector in normalized:
        cid = connector_id(connector)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        deduped.append(connector)

    enforce = True
    if isinstance(raw, dict) and raw.get("enforce_managed_mcp_servers") is not None:
        enforce = raw.get("enforce_managed_mcp_servers")
    return {"connectors": deduped, "audit": audit, "enforce_managed_mcp_servers": enforce}


def validate_data_connectors(connectors: list[dict]) -> None:
    for connector in connectors:
        ctype = connector_type(connector)
        cid = connector_id(connector) or ctype
        if ctype in DATABASE_CONNECTOR_TYPES and not connector_is_readonly(connector):
            raise RuntimeError(
                f"Data connector '{cid}' is a database connector and must set access_mode=read-only or readonly=true"
            )


def managed_mcp_servers(connectors: list[dict]) -> dict:
    servers = {}
    for connector in connectors:
        mcp = connector.get("mcp")
        if not isinstance(mcp, dict) or mcp.get("enabled", True) is False:
            continue
        name = str(mcp.get("server_name") or connector_id(connector)).strip()
        command = str(mcp.get("command") or "").strip()
        if not name or not command:
            continue
        env = mcp.get("env") if isinstance(mcp.get("env"), dict) else {}
        expansion = {
            "CONNECTOR_ID": connector_id(connector),
            "CONNECTOR_TYPE": connector_type(connector),
            "CLICKHOUSE_HOST": connector.get("host", ""),
            "CLICKHOUSE_PORT": connector.get("port", ""),
            "CLICKHOUSE_DATABASE": connector.get("database", ""),
            "CLICKHOUSE_USER": connector.get("user", ""),
            "CLICKHOUSE_PASSWORD": connector.get("password", ""),
        }

        def expand_mcp_value(value):
            text = str(value)
            for key, replacement in expansion.items():
                text = text.replace("${" + key + "}", str(replacement))
            return text

        server = {
            "command": command,
            "args": mcp.get("args") if isinstance(mcp.get("args"), list) else [],
            "env": {str(k): expand_mcp_value(v) for k, v in env.items()},
            "enabled": True,
        }
        for optional in ("cwd", "transport", "url", "headers"):
            if optional in mcp:
                server[optional] = mcp[optional]
        servers[name] = server
    return servers


def connector_by_type(connectors: list[dict], ctype: str) -> dict:
    for connector in connectors:
        if connector_type(connector) == ctype:
            return connector
    return {}


def apply_runtime_policy(spawner, policy: dict, slug: str) -> None:
    if not policy:
        return
    if policy.get("enabled") is False:
        raise RuntimeError("Hermes access is disabled for this user")

    resources = policy.get("resources") if isinstance(policy.get("resources"), dict) else policy
    memory_limit = resources.get("memory_limit")
    cpu_limit = resources.get("cpu_limit")
    if memory_limit:
        spawner.mem_limit = parse_bytes(str(memory_limit), spawner.mem_limit)
    if cpu_limit is not None:
        spawner.cpu_limit = float(cpu_limit)

    env_updates = {}
    disk_quota = resources.get("disk_quota_bytes")
    if disk_quota is not None:
        env_updates["HERMES_DISK_QUOTA_BYTES"] = str(disk_quota)

    model_policy = policy.get("model_policy")
    if isinstance(model_policy, dict):
        env_updates.update(
            {
                "HERMES_ALLOW_USER_MODEL_SETTINGS": policy_bool(
                    model_policy.get("allow_user_model_settings"),
                    False,
                ),
                "HERMES_ALLOW_USER_ONLINE_MODEL_API_KEY": policy_bool(
                    model_policy.get("allow_user_online_model_api_key"),
                    False,
                ),
                "HERMES_MODEL_POLICY_MODE": policy_env_value(
                    model_policy.get("mode") or os.environ.get("HERMES_MODEL_POLICY_MODE", "local-only")
                ),
                "HERMES_MODEL_GATEWAY_PROVIDER": policy_env_value(
                    model_policy.get("gateway_provider") or os.environ.get("HERMES_MODEL_GATEWAY_PROVIDER", "")
                ),
                "HERMES_RUNTIME_PRIVACY_GUARD_ENABLED": policy_bool(
                    model_policy.get("runtime_privacy_guard_enabled"),
                    env_bool("HERMES_RUNTIME_PRIVACY_GUARD_ENABLED", "true"),
                ),
                "HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS": policy_env_value(
                    policy_csv_value(model_policy.get("online_allowed_toolsets"))
                    or os.environ.get("HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS", "")
                ),
                "HERMES_PRIVATE_TOOL_NAMES": policy_env_value(
                    policy_csv_value(model_policy.get("private_tool_names"))
                    or os.environ.get("HERMES_PRIVATE_TOOL_NAMES", "")
                ),
                "HERMES_PUBLIC_MCP_TOOL_PREFIXES": policy_env_value(
                    policy_csv_value(model_policy.get("public_mcp_tool_prefixes"))
                    or os.environ.get("HERMES_PUBLIC_MCP_TOOL_PREFIXES", "")
                ),
                "HERMES_ALLOW_TERMINAL_NETWORK": policy_bool(
                    model_policy.get("allow_terminal_network"),
                    env_bool("HERMES_ALLOW_TERMINAL_NETWORK", "false"),
                ),
                "HERMES_ALLOW_CODE_NETWORK": policy_bool(
                    model_policy.get("allow_code_network"),
                    env_bool("HERMES_ALLOW_CODE_NETWORK", "false"),
                ),
            }
        )
        tiers = model_policy.get("tiers")
        if isinstance(tiers, dict):
            env_updates["HERMES_MODEL_TIER_SAFE_MODEL"] = policy_env_value(tiers.get("safe"))
            env_updates["HERMES_MODEL_TIER_QUALITY_MODEL"] = policy_env_value(tiers.get("quality"))
            env_updates["HERMES_MODEL_TIER_FAST_MODEL"] = policy_env_value(tiers.get("fast"))
        local_model = model_policy.get("local_model")
        if isinstance(local_model, dict):
            if local_model.get("provider"):
                env_updates["MODEL_PROVIDER"] = policy_env_value(local_model.get("provider"))
                env_updates["HERMES_MODEL_GATEWAY_PROVIDER"] = policy_env_value(local_model.get("provider"))
            if local_model.get("base_url"):
                env_updates["MODEL_BASE_URL"] = policy_env_value(local_model.get("base_url"))
            if local_model.get("api_key"):
                env_updates["MODEL_API_KEY"] = policy_env_value(local_model.get("api_key"))
            if local_model.get("model"):
                env_updates["MODEL_DEFAULT"] = policy_env_value(local_model.get("model"))
                env_updates["HERMES_PRIVATE_MODEL_ID"] = policy_env_value(local_model.get("model"))
                if env_updates.get("HERMES_MODEL_TIER_SAFE_MODEL") in {"", "local-private-default"}:
                    env_updates["HERMES_MODEL_TIER_SAFE_MODEL"] = policy_env_value(local_model.get("model"))
        if model_policy.get("default_tier"):
            env_updates["HERMES_DEFAULT_MODEL_TIER"] = policy_env_value(model_policy.get("default_tier"))
        if model_policy.get("allowed_tiers"):
            env_updates["HERMES_ALLOWED_MODEL_TIERS"] = policy_env_value(model_policy.get("allowed_tiers"))

    connector_policy = normalize_data_connectors(policy)
    connectors = connector_policy["connectors"]
    validate_data_connectors(connectors)
    audit_policy = connector_policy["audit"]
    if connectors:
        connector_ids = [connector_id(connector) for connector in connectors if connector_id(connector)]
        env_updates["HERMES_ALLOWED_DATA_CONNECTORS"] = policy_csv_value(connector_ids)
        env_updates["HERMES_ALLOWED_DATA_SOURCES"] = policy_csv_value(connector_ids)
        env_updates["HERMES_DATA_CONNECTORS_JSON"] = json.dumps(connectors, ensure_ascii=False)
        env_updates["HERMES_DATA_AUDIT_ENABLED"] = policy_bool(audit_policy.get("enabled"), True)
        env_updates["HERMES_DATA_AUDIT_LOG_PATH"] = policy_env_value(
            audit_policy.get("log_path") or "/home/hermes/data/audit/data-tools.jsonl"
        )
        mcp_servers = managed_mcp_servers(connectors)
        if mcp_servers:
            env_updates["HERMES_MANAGED_MCP_SERVERS_JSON"] = json.dumps(mcp_servers, ensure_ascii=False)
            env_updates["HERMES_ENFORCE_MANAGED_MCP_SERVERS"] = policy_bool(
                connector_policy.get("enforce_managed_mcp_servers"),
                True,
            )

    dify = connector_by_type(connectors, "dify")
    if dify:
        env_updates.update(
            {
                "DIFY_BASE_URL": policy_env_value(dify.get("base_url")),
                "DIFY_API_KEY": policy_env_value(dify.get("api_key")),
                "DIFY_APP_ID": policy_env_value(dify.get("app_id")),
                "DIFY_PRIVACY_LEVEL": policy_env_value(dify.get("privacy_level") or "public"),
            }
        )

    clickhouse = connector_by_type(connectors, "clickhouse")
    if clickhouse:
        env_updates.update(
            {
                "CLICKHOUSE_HOST": policy_env_value(clickhouse.get("host")),
                "CLICKHOUSE_PORT": policy_env_value(clickhouse.get("port")),
                "CLICKHOUSE_DATABASE": policy_env_value(clickhouse.get("database")),
                "CLICKHOUSE_USER": policy_env_value(clickhouse.get("user")),
                "CLICKHOUSE_PASSWORD": policy_env_value(clickhouse.get("password")),
                "CLICKHOUSE_PRIVACY_LEVEL": policy_env_value(clickhouse.get("privacy_level") or "private"),
                "CLICKHOUSE_ACCESS_MODE": "read-only",
                "CLICKHOUSE_READONLY": "1",
            }
        )

    recommended_skills_root = policy.get("recommended_skills_root")
    if recommended_skills_root:
        spawner.volumes[str(recommended_skills_root)] = {
            "bind": "/home/hermes/provisioned-skills",
            "mode": "ro",
        }

    env_updates["HERMES_RUNTIME_POLICY_USER"] = slug
    spawner.environment.update({k: v for k, v in env_updates.items() if v != ""})


auth_mode = os.environ.get("JUPYTERHUB_AUTH_MODE", "native").strip().lower()
if auth_mode == "oauth":
    required_oauth_env = [
        "OAUTH_CLIENT_ID",
        "OAUTH_CLIENT_SECRET",
        "OAUTH_AUTHORIZE_URL",
        "OAUTH_TOKEN_URL",
        "OAUTH_USERDATA_URL",
    ]
    missing = [name for name in required_oauth_env if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "JUPYTERHUB_AUTH_MODE=oauth requires: " + ", ".join(missing)
        )

    c.JupyterHub.authenticator_class = GenericOAuthenticator
    c.GenericOAuthenticator.client_id = os.environ["OAUTH_CLIENT_ID"]
    c.GenericOAuthenticator.client_secret = os.environ["OAUTH_CLIENT_SECRET"]
    c.GenericOAuthenticator.authorize_url = os.environ["OAUTH_AUTHORIZE_URL"]
    c.GenericOAuthenticator.token_url = os.environ["OAUTH_TOKEN_URL"]
    c.GenericOAuthenticator.userdata_url = os.environ["OAUTH_USERDATA_URL"]
    c.GenericOAuthenticator.userdata_method = os.environ.get("OAUTH_USERDATA_METHOD", "GET")
    c.GenericOAuthenticator.username_key = os.environ.get("OAUTH_USERNAME_KEY", "id")
    c.GenericOAuthenticator.login_service = os.environ.get("OAUTH_LOGIN_SERVICE", "Platform")
    c.GenericOAuthenticator.scope = env_list("OAUTH_SCOPE", "openid,profile")
    oauth_callback_url = os.environ.get("OAUTH_CALLBACK_URL", "").strip()
    if oauth_callback_url:
        c.GenericOAuthenticator.oauth_callback_url = oauth_callback_url
else:
    c.JupyterHub.authenticator_class = NativeAuthenticator
    c.NativeAuthenticator.open_signup = env_bool("JUPYTERHUB_OPEN_SIGNUP", "true")

c.Authenticator.allow_all = os.environ.get("JUPYTERHUB_ALLOW_ALL", "true").lower() == "true"
c.Authenticator.admin_users = set(
    user.strip()
    for user in os.environ.get("JUPYTERHUB_ADMIN_USERS", "admin").split(",")
    if user.strip()
)

admin_api_token = os.environ.get("JUPYTERHUB_ADMIN_API_TOKEN", "").strip()
if admin_api_token:
    c.JupyterHub.services = [
        {
            "name": "hermes-smoke-admin",
            "api_token": admin_api_token,
        }
    ]
    c.JupyterHub.load_roles = [
        {
            "name": "hermes-smoke-admin-role",
            "services": ["hermes-smoke-admin"],
            "scopes": [
                "admin:users",
                "admin:servers",
                "read:users",
                "read:servers",
            ],
        }
    ]


def parse_bytes(value: str, default: int) -> int:
    raw = str(value or "").strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmgt]?i?b?|)", raw)
    if not match:
        return default
    number = float(match.group(1))
    unit = match.group(2)
    multipliers = {
        "": 1,
        "b": 1,
        "k": 1000,
        "kb": 1000,
        "m": 1000**2,
        "mb": 1000**2,
        "g": 1000**3,
        "gb": 1000**3,
        "t": 1000**4,
        "tb": 1000**4,
        "ki": 1024,
        "kib": 1024,
        "mi": 1024**2,
        "mib": 1024**2,
        "gi": 1024**3,
        "gib": 1024**3,
        "ti": 1024**4,
        "tib": 1024**4,
    }
    return int(number * multipliers.get(unit, 1))

c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"
c.DockerSpawner.image = os.environ.get("HERMES_RUNTIME_IMAGE", "hermes-runtime:local")
c.DockerSpawner.network_name = os.environ.get("DOCKER_NETWORK_NAME", "hermes-net")
c.DockerSpawner.remove = env_bool("HERMES_REMOVE_STOPPED_USER_CONTAINERS", "true")
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.debug = os.environ.get("DOCKERSPAWNER_DEBUG", "false").lower() == "true"
c.DockerSpawner.port = int(os.environ.get("HERMES_RUNTIME_PORT", "8080"))

c.Spawner.default_url = "/"
c.Spawner.http_timeout = int(os.environ.get("HERMES_SPAWN_HTTP_TIMEOUT", "120"))
c.Spawner.start_timeout = int(os.environ.get("HERMES_SPAWN_START_TIMEOUT", "120"))
c.Spawner.mem_limit = parse_bytes(
    os.environ.get("HERMES_CONTAINER_MEMORY_LIMIT", "4g"),
    4 * 1024**3,
)
c.Spawner.cpu_limit = float(os.environ.get("HERMES_CONTAINER_CPU_LIMIT", "2"))

def user_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip(".-")
    return slug or "user"


def pre_spawn_hook(spawner):
    username = spawner.user.name
    slug = user_slug(username)
    policy = runtime_policy_for_user(username, slug)
    user_data_root = os.environ.get(
        "HERMES_HOST_USER_DATA_ROOT",
        os.environ.get("HERMES_USER_DATA_ROOT", "/srv/hermes/users"),
    )
    user_data_dir = Path(user_data_root) / slug
    runtime_uid = int(os.environ.get("HERMES_RUNTIME_UID", "1000"))
    runtime_gid = int(os.environ.get("HERMES_RUNTIME_GID", "1000"))
    user_data_dir.mkdir(parents=True, exist_ok=True)
    os.chown(user_data_dir, runtime_uid, runtime_gid)
    os.chmod(user_data_dir, 0o700)
    spawner.volumes = {
        f"{user_data_root}/{slug}": "/home/hermes/data",
    }
    policy_root = os.environ.get("HERMES_HOST_POLICY_ROOT", "").strip()
    if policy_root:
        spawner.volumes[policy_root] = {
            "bind": "/srv/hermes/policies",
            "mode": "ro",
        }
    provisioned_skills_root = os.environ.get("HERMES_HOST_PROVISIONED_SKILLS_ROOT", "").strip()
    if provisioned_skills_root:
        spawner.volumes[provisioned_skills_root] = {
            "bind": "/home/hermes/provisioned-skills",
            "mode": "ro",
        }
    spawner.environment.update(
        {
            "PUBLIC_BASE_PATH": f"/user/{username}/",
            "HERMES_USER_ID": username,
            "HERMES_USER_NAME": username,
            "HERMES_WEBUI_STATE_DIR": "/home/hermes/data/webui",
            "HERMES_WEBUI_DEFAULT_WORKSPACE": "/home/hermes/data/workspace",
            "HERMES_WEBUI_AGENT_DIR": "/home/hermes/agent",
            "HERMES_WEBUI_ONBOARDING_OPEN": "1",
            "HERMES_WEBUI_DEFAULT_THEME": "light",
            "HERMES_WEBUI_DEFAULT_LANGUAGE": "zh",
            "HERMES_DISABLE_SERVICE_WORKER": "true",
            "HERMES_HOME": "/home/hermes/data/hermes",
            "HERMES_POLICY_ROOT": "/srv/hermes/policies",
        }
    )
    apply_runtime_policy(spawner, policy, slug)


c.Spawner.pre_spawn_hook = pre_spawn_hook

c.DockerSpawner.environment = {
    "APP_ENV": os.environ.get("APP_ENV", "local"),
    "PUBLIC_BASE_PATH": "/",
    "PORT": "8080",
    "HERMES_WEBUI_HOST": "0.0.0.0",
    "HERMES_WEBUI_PORT": "8080",
    "HERMES_WEBUI_STATE_DIR": "/home/hermes/data/webui",
    "HERMES_WEBUI_DEFAULT_WORKSPACE": "/home/hermes/data/workspace",
    "HERMES_WEBUI_AGENT_DIR": "/home/hermes/agent",
    "HERMES_WEBUI_ONBOARDING_OPEN": "1",
    "HERMES_WEBUI_DEFAULT_THEME": "light",
    "HERMES_WEBUI_DEFAULT_LANGUAGE": "zh",
    "HERMES_DISABLE_SERVICE_WORKER": "true",
    "HERMES_HOME": "/home/hermes/data/hermes",
    "HERMES_USER_ID": "",
    "HERMES_USER_NAME": "",
    "HERMES_DATA_DIR": "/home/hermes/data",
    "HERMES_WORKSPACE_DIR": "/home/hermes/data/workspace",
    "HERMES_MEMORY_DIR": "/home/hermes/data/memory",
    "HERMES_SESSION_DIR": "/home/hermes/data/sessions",
    "HERMES_ARTIFACT_DIR": "/home/hermes/data/artifacts",
    "HERMES_USER_SKILLS_DIR": "/home/hermes/data/skills",
    "HERMES_SKILL_STATE_FILE": "/home/hermes/data/skill-state.json",
    "HERMES_PROVISIONED_SKILLS_DIR": "/home/hermes/provisioned-skills",
    "HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS": os.environ.get(
        "HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS",
        "false",
    ),
    "PROJECT_SKILLS_UPDATE_POLICY": os.environ.get("PROJECT_SKILLS_UPDATE_POLICY", "manual"),
    "MODEL_PROVIDER": os.environ.get("MODEL_PROVIDER", "openai-compatible"),
    "MODEL_BASE_URL": os.environ.get("MODEL_BASE_URL", ""),
    "MODEL_API_KEY": os.environ.get("MODEL_API_KEY", ""),
    "MODEL_DEFAULT": os.environ.get("MODEL_DEFAULT", ""),
    "HERMES_MODEL_POLICY_MODE": os.environ.get("HERMES_MODEL_POLICY_MODE", "local-only"),
    "HERMES_PRIVATE_MODEL_ID": os.environ.get("HERMES_PRIVATE_MODEL_ID", ""),
    "HERMES_PUBLIC_MODEL_ID": os.environ.get("HERMES_PUBLIC_MODEL_ID", ""),
    "HERMES_MODEL_TIER_SAFE_MODEL": os.environ.get("HERMES_MODEL_TIER_SAFE_MODEL", ""),
    "HERMES_MODEL_TIER_QUALITY_MODEL": os.environ.get("HERMES_MODEL_TIER_QUALITY_MODEL", ""),
    "HERMES_MODEL_TIER_FAST_MODEL": os.environ.get("HERMES_MODEL_TIER_FAST_MODEL", ""),
    "HERMES_MODEL_GATEWAY_PROVIDER": os.environ.get("HERMES_MODEL_GATEWAY_PROVIDER", ""),
    "HERMES_PRIVACY_TOOL_NAMES": os.environ.get(
        "HERMES_PRIVACY_TOOL_NAMES",
        "clickhouse,postgres,sqlite,database,mcp_clickhouse",
    ),
    "HERMES_RUNTIME_PRIVACY_GUARD_ENABLED": os.environ.get(
        "HERMES_RUNTIME_PRIVACY_GUARD_ENABLED",
        "true",
    ),
    "HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS": os.environ.get(
        "HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS",
        "web,vision,clarify,todo,image_gen",
    ),
    "HERMES_PRIVATE_TOOL_NAMES": os.environ.get(
        "HERMES_PRIVATE_TOOL_NAMES",
        "terminal,process,read_terminal,execute_code,read_file,write_file,patch,search_files,memory,session_search,skill_manage,cronjob,delegate_task,send_message,browser_navigate,browser_snapshot,browser_click,browser_type,browser_scroll,browser_back,browser_press,browser_get_images,browser_vision,browser_console,browser_cdp,browser_dialog,computer_use",
    ),
    "HERMES_PUBLIC_MCP_TOOL_PREFIXES": os.environ.get("HERMES_PUBLIC_MCP_TOOL_PREFIXES", ""),
    "HERMES_ALLOW_TERMINAL_NETWORK": os.environ.get("HERMES_ALLOW_TERMINAL_NETWORK", "false"),
    "HERMES_ALLOW_CODE_NETWORK": os.environ.get("HERMES_ALLOW_CODE_NETWORK", "false"),
    "HERMES_ALLOWED_DATA_CONNECTORS": os.environ.get("HERMES_ALLOWED_DATA_CONNECTORS", ""),
    "HERMES_DATA_CONNECTORS_JSON": os.environ.get("HERMES_DATA_CONNECTORS_JSON", ""),
    "HERMES_DATA_AUDIT_ENABLED": os.environ.get("HERMES_DATA_AUDIT_ENABLED", "true"),
    "HERMES_DATA_AUDIT_LOG_PATH": os.environ.get(
        "HERMES_DATA_AUDIT_LOG_PATH",
        "/home/hermes/data/audit/data-tools.jsonl",
    ),
    "HERMES_MANAGED_MCP_SERVERS_JSON": os.environ.get("HERMES_MANAGED_MCP_SERVERS_JSON", ""),
    "HERMES_ENFORCE_MANAGED_MCP_SERVERS": os.environ.get("HERMES_ENFORCE_MANAGED_MCP_SERVERS", "true"),
    "HERMES_ALLOW_USER_MODEL_SETTINGS": os.environ.get(
        "HERMES_ALLOW_USER_MODEL_SETTINGS",
        "false",
    ),
    "DIFY_BASE_URL": os.environ.get("DIFY_BASE_URL", ""),
    "DIFY_API_KEY": os.environ.get("DIFY_API_KEY", ""),
    "DIFY_APP_ID": os.environ.get("DIFY_APP_ID", ""),
    "DIFY_PRIVACY_LEVEL": os.environ.get("DIFY_PRIVACY_LEVEL", "public"),
    "CLICKHOUSE_HOST": os.environ.get("CLICKHOUSE_HOST", ""),
    "CLICKHOUSE_PORT": os.environ.get("CLICKHOUSE_PORT", ""),
    "CLICKHOUSE_DATABASE": os.environ.get("CLICKHOUSE_DATABASE", ""),
    "CLICKHOUSE_USER": os.environ.get("CLICKHOUSE_USER", ""),
    "CLICKHOUSE_PASSWORD": os.environ.get("CLICKHOUSE_PASSWORD", ""),
    "CLICKHOUSE_PRIVACY_LEVEL": os.environ.get("CLICKHOUSE_PRIVACY_LEVEL", "private"),
    "ENABLE_SANDBOX": os.environ.get("ENABLE_SANDBOX", "false"),
    "SANDBOX_API_URL": os.environ.get("SANDBOX_API_URL", ""),
}

c.JupyterHub.cookie_secret_file = os.environ.get(
    "JUPYTERHUB_COOKIE_SECRET_FILE",
    "/srv/jupyterhub-data/jupyterhub_cookie_secret",
)
