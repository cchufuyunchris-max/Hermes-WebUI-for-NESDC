"""Admin policy management helpers for Hermes WebUI deployments."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


SECRET_KEYS = {"api_key", "password", "token", "secret", "client_secret", "authorization"}
DATABASE_TYPES = {
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
CONNECTOR_TYPES = [
    "dify",
    "clickhouse",
    "postgres",
    "mysql",
    "mariadb",
    "sqlite",
    "duckdb",
    "mongo",
    "redis",
    "mcp",
    "knowledge_base",
    "other",
]


def admin_ui_enabled() -> bool:
    raw = os.environ.get("HERMES_ADMIN_UI_ENABLED", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return os.environ.get("APP_ENV", "local").strip().lower() in {"local", "dev", "development"}


def require_admin(handler) -> None:
    if not admin_ui_enabled():
        raise PermissionError("Admin UI is disabled. Set HERMES_ADMIN_UI_ENABLED=true to enable it.")
    token = os.environ.get("HERMES_ADMIN_API_TOKEN", "").strip()
    if token:
        provided = (
            handler.headers.get("X-Hermes-Admin-Token", "")
            or handler.headers.get("Authorization", "").replace("Bearer ", "", 1)
        ).strip()
        if provided != token:
            raise PermissionError("Admin token is required")


def policy_path() -> Path:
    explicit = os.environ.get("HERMES_ADMIN_POLICY_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = os.environ.get("HERMES_POLICY_ROOT", "").strip()
    if root:
        return (Path(root).expanduser() / "global.json").resolve()
    return (Path.cwd() / "configs" / "policies" / "global.json").resolve()


def policy_root() -> Path:
    return policy_path().parent


def user_policy_dir() -> Path:
    return policy_root() / "users"


def user_data_root() -> Path | None:
    raw = (
        os.environ.get("HERMES_ADMIN_USER_DATA_ROOT", "").strip()
        or os.environ.get("HERMES_HOST_USER_DATA_ROOT", "").strip()
        or os.environ.get("HERMES_USER_DATA_ROOT", "").strip()
    )
    return Path(raw).expanduser() if raw else None


def _safe_child_path(root: Path, name: str) -> Path:
    safe = _safe_user_id(name)
    resolved_root = root.expanduser().resolve()
    path = (resolved_root / safe).resolve()
    path.relative_to(resolved_root)
    return path


def _safe_user_id(user_id: str) -> str:
    raw = str(user_id or "").strip()
    if not raw or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", raw):
        raise ValueError("Invalid user id. Use letters, numbers, dot, underscore, or dash.")
    return raw


def _user_container_name(user_id: str) -> str:
    return "jupyter-" + _safe_user_id(user_id)


def _docker_socket_path() -> Path:
    return Path(os.environ.get("HERMES_ADMIN_DOCKER_SOCKET", "/var/run/docker.sock")).expanduser()


def _docker_request(method: str, path: str) -> tuple[int, dict[str, Any] | str]:
    socket_path = _docker_socket_path()
    if not socket_path.exists():
        raise RuntimeError(f"Docker socket is not available: {socket_path}")
    raw_request = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Connection: close\r\n"
        "Content-Length: 0\r\n"
        "\r\n"
    ).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15)
        client.connect(str(socket_path))
        client.sendall(raw_request)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    header, _, body = raw.partition(b"\r\n\r\n")
    status_line = header.splitlines()[0].decode("iso-8859-1", errors="replace") if header else ""
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    body_text = body.decode("utf-8", errors="replace")
    try:
        return status, json.loads(body_text) if body_text.strip() else {}
    except Exception:
        return status, body_text


def _docker_container_exists(container_name: str) -> bool:
    status, _ = _docker_request("GET", f"/containers/{quote(container_name, safe='')}/json")
    if status == 404:
        return False
    if status != 200:
        raise RuntimeError(f"Docker inspect failed for {container_name}: HTTP {status}")
    return True


def rebuild_user_runtime_payload(user_id: str) -> dict[str, Any]:
    safe = _safe_user_id(user_id)
    container_name = _user_container_name(safe)
    existed = _docker_container_exists(container_name)
    stopped = False
    removed = False
    if existed:
        encoded = quote(container_name, safe="")
        stop_status, _ = _docker_request("POST", f"/containers/{encoded}/stop?t=10")
        if stop_status in {204, 304, 404}:
            stopped = stop_status != 404
        else:
            raise RuntimeError(f"Docker stop failed for {container_name}: HTTP {stop_status}")
        delete_status, _ = _docker_request("DELETE", f"/containers/{encoded}?force=true")
        if delete_status in {204, 404}:
            removed = delete_status != 404
        elif delete_status == 409:
            for _ in range(6):
                time.sleep(0.5)
                if not _docker_container_exists(container_name):
                    removed = True
                    break
            if not removed:
                raise RuntimeError(f"Docker remove failed for {container_name}: HTTP {delete_status}")
        else:
            raise RuntimeError(f"Docker remove failed for {container_name}: HTTP {delete_status}")
    return {
        "ok": True,
        "user_id": safe,
        "container": container_name,
        "existed": existed,
        "stopped": stopped,
        "removed": removed,
        "data_preserved": True,
        "message": (
            "User runtime container removed. The next Launch/Spawn will recreate it with the latest policy."
            if removed else
            "No existing user runtime container was found. The next Launch/Spawn will use the latest policy."
        ),
    }


def rebuild_all_user_runtimes_payload() -> dict[str, Any]:
    users_payload = list_user_policy_payloads()
    results = []
    for user in users_payload.get("users", []):
        user_id = user.get("user_id")
        if not user_id:
            continue
        try:
            results.append(rebuild_user_runtime_payload(user_id))
        except Exception as exc:
            results.append({
                "ok": False,
                "user_id": user_id,
                "container": _user_container_name(user_id),
                "error": str(exc),
            })
    failed = [item for item in results if not item.get("ok")]
    return {
        "ok": not failed,
        "count": len(results),
        "failed_count": len(failed),
        "results": results,
    }


def user_policy_path(user_id: str) -> Path:
    safe = _safe_user_id(user_id)
    root = user_policy_dir().resolve()
    path = (root / f"{safe}.json").resolve()
    path.relative_to(root)
    return path


def user_data_path(user_id: str) -> Path | None:
    root = user_data_root()
    if not root:
        return None
    return _safe_child_path(root, user_id)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_policy()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Policy file must contain a JSON object")
    return data


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{int(time.time() * 1000)}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def default_policy() -> dict[str, Any]:
    return {
        "enabled": True,
        "resources": {
            "cpu_limit": 2,
            "memory_limit": "4g",
            "disk_quota_bytes": 21474836480,
        },
        "model_policy": {
            "allow_user_model_settings": True,
            "allow_user_online_model_api_key": True,
            "runtime_privacy_guard_enabled": True,
            "online_allowed_toolsets": ["web", "vision", "clarify", "todo", "image_gen"],
            "public_mcp_tool_prefixes": [],
            "allow_terminal_network": False,
            "allow_code_network": False,
            "mode": "privacy-router",
            "default_tier": "safe",
            "allowed_tiers": ["safe", "quality", "fast"],
            "gateway_provider": "openai-compatible",
            "local_model": {
                "provider": "openai-compatible",
                "base_url": "http://host.docker.internal:3001/v1",
                "api_key": "",
                "model": "local-private-default",
            },
            "tiers": {
                "safe": "local-private-default",
                "quality": "online-quality",
                "fast": "online-fast",
            },
        },
        "data_connectors": {
            "audit": {
                "enabled": True,
                "log_path": "/home/hermes/data/audit/data-tools.jsonl",
            },
            "enforce_managed_mcp_servers": True,
            "connectors": [],
        },
    }


def normalize_policy(policy: dict[str, Any]) -> dict[str, Any]:
    base = default_policy()
    merged = _deep_merge(base, policy or {})
    dc = merged.setdefault("data_connectors", {})
    if not isinstance(dc, dict):
        dc = {"connectors": []}
        merged["data_connectors"] = dc
    dc.setdefault("audit", {"enabled": True, "log_path": "/home/hermes/data/audit/data-tools.jsonl"})
    dc.setdefault("enforce_managed_mcp_servers", True)
    connectors = dc.get("connectors")
    dc["connectors"] = connectors if isinstance(connectors, list) else []
    return merged


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            stat = current.lstat()
        except OSError:
            continue
        if current.is_symlink():
            total += stat.st_size
            continue
        if current.is_dir():
            try:
                stack.extend(current.iterdir())
            except OSError:
                continue
            continue
        total += stat.st_size
    return total


def _effective_user_resources(user_policy: dict[str, Any] | None) -> dict[str, Any]:
    global_policy = normalize_policy(_read_json(policy_path()))
    resources = copy.deepcopy(global_policy.get("resources") or {})
    if isinstance(user_policy, dict) and isinstance(user_policy.get("resources"), dict):
        resources.update({k: v for k, v in user_policy["resources"].items() if v not in (None, "")})
    return resources


def _usage_status(usage_bytes: int, quota_bytes: int | None) -> tuple[str, float | None]:
    if not quota_bytes or quota_bytes <= 0:
        return "no-quota", None
    percent = round((usage_bytes / quota_bytes) * 100, 2)
    if percent >= 90:
        return "critical", percent
    if percent >= 80:
        return "warn", percent
    return "ok", percent


def _usage_payload(data_path: Path | None, resources: dict[str, Any]) -> dict[str, Any]:
    exists = bool(data_path and data_path.exists())
    usage = _dir_size_bytes(data_path) if exists and data_path else 0
    quota_raw = resources.get("disk_quota_bytes")
    try:
        quota = int(quota_raw) if quota_raw not in (None, "") else None
    except (TypeError, ValueError):
        quota = None
    status, percent = _usage_status(usage, quota)
    return {
        "data_path": str(data_path) if data_path else "",
        "has_data": exists,
        "usage_bytes": usage,
        "disk_quota_bytes": quota,
        "usage_percent": percent,
        "usage_status": status,
    }


def _redact_policy(policy: dict[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if str(key).lower() in SECRET_KEYS and item:
                    out[key] = "********"
                else:
                    out[key] = walk(item)
            return out
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(policy)


def _merge_secret_placeholders(next_policy: dict[str, Any], current_policy: dict[str, Any]) -> dict[str, Any]:
    def merge_walk(next_value: Any, current_value: Any) -> Any:
        if isinstance(next_value, dict) and isinstance(current_value, dict):
            for key, value in list(next_value.items()):
                if str(key).lower() in SECRET_KEYS and value == "********":
                    next_value[key] = current_value.get(key, "")
                else:
                    next_value[key] = merge_walk(value, current_value.get(key))
        elif isinstance(next_value, list) and isinstance(current_value, list):
            for index, item in enumerate(next_value):
                if index < len(current_value):
                    next_value[index] = merge_walk(item, current_value[index])
        return next_value

    next_policy = merge_walk(next_policy, current_policy)
    current_by_id = {
        str(conn.get("id") or ""): conn
        for conn in ((current_policy.get("data_connectors") or {}).get("connectors") or [])
        if isinstance(conn, dict)
    }
    for conn in ((next_policy.get("data_connectors") or {}).get("connectors") or []):
        if not isinstance(conn, dict):
            continue
        current = current_by_id.get(str(conn.get("id") or ""))
        if not current:
            continue
        for key in SECRET_KEYS:
            if conn.get(key) == "********":
                conn[key] = current.get(key, "")
        mcp = conn.get("mcp")
        current_mcp = current.get("mcp") if isinstance(current.get("mcp"), dict) else {}
        if isinstance(mcp, dict):
            env = mcp.get("env")
            current_env = current_mcp.get("env") if isinstance(current_mcp, dict) else {}
            if isinstance(env, dict) and isinstance(current_env, dict):
                for key, value in list(env.items()):
                    if value == "********":
                        env[key] = current_env.get(key, "")
    return next_policy


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(policy, dict):
        return ["Policy must be a JSON object"]
    connectors = ((policy.get("data_connectors") or {}).get("connectors") or [])
    seen = set()
    if not isinstance(connectors, list):
        return ["data_connectors.connectors must be a list"]
    for index, conn in enumerate(connectors):
        if not isinstance(conn, dict):
            errors.append(f"Connector #{index + 1} must be an object")
            continue
        cid = str(conn.get("id") or "").strip()
        ctype = str(conn.get("type") or "").strip().lower()
        if not cid:
            errors.append(f"Connector #{index + 1} requires id")
        elif cid in seen:
            errors.append(f"Duplicate connector id: {cid}")
        seen.add(cid)
        if not ctype:
            errors.append(f"Connector {cid or index + 1} requires type")
        mode = str(conn.get("access_mode") or "").strip().lower()
        if ctype in DATABASE_TYPES and mode not in {"read", "readonly", "read-only", "ro", "select-only"} and conn.get("readonly") is not True:
            errors.append(f"Database connector {cid or index + 1} must be read-only")
        mcp = conn.get("mcp")
        if isinstance(mcp, dict) and mcp.get("enabled") is True:
            if not str(mcp.get("server_name") or "").strip():
                errors.append(f"Connector {cid or index + 1} MCP requires server_name")
            if not str(mcp.get("command") or "").strip():
                errors.append(f"Connector {cid or index + 1} MCP requires command")
    return errors


def load_policy_payload(*, include_secrets: bool = False) -> dict[str, Any]:
    path = policy_path()
    policy = normalize_policy(_read_json(path))
    return {
        "ok": True,
        "path": str(path),
        "writable": os.access(path.parent if path.exists() else path.parent, os.W_OK),
        "admin_ui_enabled": admin_ui_enabled(),
        "token_required": bool(os.environ.get("HERMES_ADMIN_API_TOKEN", "").strip()),
        "connector_types": CONNECTOR_TYPES,
        "database_types": sorted(DATABASE_TYPES),
        "policy": policy if include_secrets else _redact_policy(policy),
    }


def save_policy_payload(policy: dict[str, Any]) -> dict[str, Any]:
    path = policy_path()
    current = normalize_policy(_read_json(path))
    next_policy = normalize_policy(_merge_secret_placeholders(copy.deepcopy(policy), current))
    errors = validate_policy(next_policy)
    if errors:
        raise ValueError("; ".join(errors))
    _atomic_write_json(path, next_policy)
    return load_policy_payload(include_secrets=False)


def list_user_policy_payloads() -> dict[str, Any]:
    root = user_policy_dir()
    by_user: dict[str, dict[str, Any]] = {}
    data_root = user_data_root()
    if data_root and data_root.exists():
        for path in sorted(item for item in data_root.iterdir() if item.is_dir()):
            try:
                user_id = _safe_user_id(path.name)
            except ValueError:
                continue
            by_user[user_id] = {
                "user_id": user_id,
                "enabled": True,
                "resources": {},
                "effective_resources": _effective_user_resources({}),
                "path": "",
                "has_override": False,
                "updated_at": int(path.stat().st_mtime),
            }
    if root.exists():
        for path in sorted(root.glob("*.json")):
            try:
                data = _read_json(path)
            except Exception:
                data = {}
            resources = data.get("resources") if isinstance(data.get("resources"), dict) else {}
            by_user[path.stem] = {
                **by_user.get(path.stem, {}),
                "user_id": path.stem,
                "enabled": data.get("enabled", True),
                "resources": resources or {},
                "effective_resources": _effective_user_resources(data),
                "path": str(path),
                "has_override": True,
                "updated_at": int(path.stat().st_mtime),
            }
    users = []
    for key in sorted(by_user):
        user = by_user[key]
        effective_resources = user.get("effective_resources") or _effective_user_resources(user)
        user["effective_resources"] = effective_resources
        data_path = user_data_path(user["user_id"]) if data_root else None
        user.update(_usage_payload(data_path, effective_resources))
        users.append(user)
    total_usage = sum(int(user.get("usage_bytes") or 0) for user in users)
    warn_count = sum(1 for user in users if user.get("usage_status") in {"warn", "critical"})
    return {
        "ok": True,
        "root": str(root),
        "user_data_root": str(data_root) if data_root else "",
        "count": len(users),
        "total_usage_bytes": total_usage,
        "warn_count": warn_count,
        "users": users,
    }


def load_user_policy_payload(user_id: str) -> dict[str, Any]:
    path = user_policy_path(user_id)
    data = _read_json(path) if path.exists() else {"enabled": True, "resources": {}}
    effective_resources = _effective_user_resources(data)
    data_path = user_data_path(user_id)
    return {
        "ok": True,
        "user_id": _safe_user_id(user_id),
        "exists": path.exists(),
        "path": str(path),
        "policy": _redact_policy(data),
        "effective_resources": effective_resources,
        "usage": _usage_payload(data_path, effective_resources),
    }


def save_user_policy_payload(user_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    safe = _safe_user_id(user_id)
    if not isinstance(policy, dict):
        raise ValueError("User policy must be an object")
    out: dict[str, Any] = {
        "enabled": policy.get("enabled", True) is not False,
        "resources": {},
    }
    resources = policy.get("resources") if isinstance(policy.get("resources"), dict) else {}
    cpu = resources.get("cpu_limit")
    memory = str(resources.get("memory_limit") or "").strip()
    disk = resources.get("disk_quota_bytes")
    if cpu not in (None, ""):
        out["resources"]["cpu_limit"] = float(cpu)
    if memory:
        out["resources"]["memory_limit"] = memory
    if disk not in (None, ""):
        out["resources"]["disk_quota_bytes"] = int(disk)
    _atomic_write_json(user_policy_path(safe), out)
    return load_user_policy_payload(safe)


def delete_user_policy_payload(user_id: str) -> dict[str, Any]:
    safe = _safe_user_id(user_id)
    path = user_policy_path(safe)
    existed = path.exists()
    if existed:
        path.unlink()
    return {"ok": True, "user_id": safe, "deleted": existed}


def delete_user_data_payload(user_id: str, confirm_user_id: str | None = None) -> dict[str, Any]:
    safe = _safe_user_id(user_id)
    if str(confirm_user_id or "").strip() != safe:
        raise ValueError("Type the exact user id to confirm deleting this user's data.")
    data_path = user_data_path(safe)
    if data_path is None:
        raise ValueError("User data root is not configured.")
    usage = _usage_payload(data_path, _effective_user_resources(None))
    data_existed = data_path.exists()
    if data_existed:
        shutil.rmtree(data_path)
    policy_result = delete_user_policy_payload(safe)
    return {
        "ok": True,
        "user_id": safe,
        "deleted_data": data_existed,
        "deleted_policy": policy_result.get("deleted", False),
        "data_path": str(data_path),
        "usage_bytes_before_delete": usage.get("usage_bytes", 0),
    }


def audit_tail(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    raw = os.environ.get("HERMES_DATA_AUDIT_LOG_PATH", "").strip()
    path = Path(raw).expanduser() if raw else Path(os.environ.get("HERMES_DATA_DIR", "/home/hermes/data")) / "audit" / "data-tools.jsonl"
    if not path.exists():
        return {"ok": True, "path": str(path), "events": []}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return {"ok": True, "path": str(path), "events": events}
