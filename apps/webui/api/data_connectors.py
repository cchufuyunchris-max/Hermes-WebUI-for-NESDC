"""Managed data connector policy and audit helpers for Hermes WebUI runtime."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_AUDIT_LOCK = threading.Lock()

SECRET_KEY_RE = re.compile(r"(password|passwd|pwd|token|secret|api[_-]?key|authorization|cookie)", re.I)
SENSITIVE_VALUE_KEYS = {
    "query",
    "sql",
    "statement",
    "command",
    "cmd",
    "script",
    "code",
    "source",
    "content",
    "body",
    "headers",
}
DATABASE_TOOL_RE = re.compile(
    r"(clickhouse|postgres|postgresql|psql|mysql|mariadb|sqlite|duckdb|mongo|redis|database|db)",
    re.I,
)
KNOWLEDGE_TOOL_RE = re.compile(r"(dify|knowledge|kb|retrieval|rag|vector)", re.I)
WRITE_INTENT_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|merge|upsert|grant|revoke|write|mutate|execute)\b",
    re.I,
)
READ_INTENT_RE = re.compile(r"\b(select|show|describe|desc|explain|search|query|retrieve|read|list|get)\b", re.I)


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


def _json_env(name: str, default: Any) -> Any:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _connector_list() -> list[dict[str, Any]]:
    data = _json_env("HERMES_DATA_CONNECTORS_JSON", [])
    if isinstance(data, dict):
        data = data.get("connectors", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def managed_connectors() -> list[dict[str, Any]]:
    """Return enabled administrator-managed data connectors."""
    connectors = [c for c in _connector_list() if c.get("enabled", True) is not False]
    if connectors:
        return connectors

    # Backward-compatible view for older policy files.
    legacy: list[dict[str, Any]] = []
    if os.environ.get("CLICKHOUSE_HOST"):
        legacy.append(
            {
                "id": "clickhouse-readonly",
                "type": "clickhouse",
                "enabled": True,
                "privacy_level": os.environ.get("CLICKHOUSE_PRIVACY_LEVEL", "private"),
                "access_mode": "read-only",
            }
        )
    if os.environ.get("DIFY_BASE_URL"):
        legacy.append(
            {
                "id": "dify-public",
                "type": "dify",
                "enabled": True,
                "privacy_level": os.environ.get("DIFY_PRIVACY_LEVEL", "public"),
                "access_mode": "read-only",
            }
        )
    if os.environ.get("DIFY_KNOWLEDGE_BASE_URL"):
        legacy.append(
            {
                "id": "dify-knowledge",
                "type": "knowledge_base",
                "enabled": True,
                "privacy_level": os.environ.get("DIFY_KNOWLEDGE_PRIVACY_LEVEL", "public"),
                "access_mode": os.environ.get("DIFY_KNOWLEDGE_ACCESS_MODE", "read-only"),
            }
        )
    return legacy


def _connector_id(connector: dict[str, Any]) -> str:
    return str(connector.get("id") or connector.get("name") or connector.get("type") or "").strip()


def _connector_type(connector: dict[str, Any]) -> str:
    return str(connector.get("type") or "").strip().lower()


def _is_readonly_connector(connector: dict[str, Any]) -> bool:
    mode = str(connector.get("access_mode") or connector.get("mode") or "").strip().lower()
    readonly = connector.get("readonly")
    return readonly is True or mode in {"read", "readonly", "read-only", "ro", "select-only"}


def _stringify_leaf_values(value: Any, *, max_items: int = 40) -> str:
    chunks: list[str] = []

    def walk(item: Any) -> None:
        if len(chunks) >= max_items:
            return
        if isinstance(item, dict):
            for key, val in item.items():
                if key in SENSITIVE_VALUE_KEYS:
                    chunks.append(str(val or "")[:500])
                else:
                    walk(val)
        elif isinstance(item, list):
            for val in item:
                walk(val)
        elif item is not None:
            chunks.append(str(item)[:200])

    walk(value)
    return "\n".join(chunks)


def query_text_from_args(args: dict[str, Any]) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("query", "sql", "statement", "command", "cmd", "script", "code", "source"):
        value = args.get(key)
        if value:
            return str(value)
    return _stringify_leaf_values(args)


def access_intent(tool_name: str, args: dict[str, Any]) -> str:
    text = f"{tool_name}\n{query_text_from_args(args)}"
    if WRITE_INTENT_RE.search(text):
        return "write"
    if READ_INTENT_RE.search(text):
        return "read"
    return "unknown"


def _match_connector_ids(tool_name: str, args: dict[str, Any]) -> list[str]:
    haystack = f"{tool_name}\n{_stringify_leaf_values(args)}".lower()
    matches: list[str] = []
    for connector in managed_connectors():
        cid = _connector_id(connector)
        ctype = _connector_type(connector)
        server_name = str((connector.get("mcp") or {}).get("server_name") or "").strip()
        candidates = [cid, ctype, server_name]
        if any(candidate and candidate.lower() in haystack for candidate in candidates):
            matches.append(cid or ctype)
    return sorted(set(matches))


def data_tool_profile(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Classify a tool call if it touches a managed data connector surface."""
    args = args if isinstance(args, dict) else {}
    name = str(tool_name or "").strip()
    text = f"{name}\n{query_text_from_args(args)}"
    connector_ids = _match_connector_ids(name, args)
    category = ""

    if DATABASE_TOOL_RE.search(text):
        category = "database"
    elif KNOWLEDGE_TOOL_RE.search(text):
        category = "knowledge_base"
    elif name.startswith("mcp_"):
        category = "mcp"
    elif connector_ids:
        category = "data_connector"

    if not category:
        return None

    privacy_levels = []
    access_modes = []
    for connector in managed_connectors():
        cid = _connector_id(connector) or _connector_type(connector)
        if not connector_ids or cid in connector_ids:
            privacy_levels.append(str(connector.get("privacy_level") or "private"))
            access_modes.append(str(connector.get("access_mode") or ("read-only" if _is_readonly_connector(connector) else "unknown")))

    return {
        "category": category,
        "connector_ids": connector_ids or _csv_env("HERMES_ALLOWED_DATA_CONNECTORS"),
        "privacy_levels": sorted(set(level for level in privacy_levels if level)),
        "access_modes": sorted(set(mode for mode in access_modes if mode)),
        "intent": access_intent(name, args),
    }


def readonly_violation_message(tool_name: str, args: dict[str, Any] | None = None) -> str | None:
    """Return a block message when a managed data connector is used for writes."""
    profile = data_tool_profile(tool_name, args)
    if not profile:
        return None
    if profile.get("intent") != "write":
        return None

    connectors = managed_connectors()
    matched = set(profile.get("connector_ids") or [])
    relevant = [
        connector
        for connector in connectors
        if not matched or (_connector_id(connector) or _connector_type(connector)) in matched
    ]
    if any(_is_readonly_connector(connector) for connector in relevant) or profile.get("category") == "database":
        return (
            "Managed data connectors are read-only in Hermes Runtime. "
            "Use SELECT/SHOW/DESCRIBE/EXPLAIN or an administrator-approved read-only retrieval tool."
        )
    return None


def _safe_arg_shape(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "<depth-limit>"
    if isinstance(value, dict):
        shaped = {}
        for key, val in value.items():
            key_s = str(key)
            if SECRET_KEY_RE.search(key_s):
                shaped[key_s] = "<redacted>"
            elif key_s.lower() in SENSITIVE_VALUE_KEYS:
                shaped[key_s] = {
                    "sha256": hashlib.sha256(str(val or "").encode("utf-8", "replace")).hexdigest(),
                    "length": len(str(val or "")),
                }
            else:
                shaped[key_s] = _safe_arg_shape(val, depth + 1)
        return shaped
    if isinstance(value, list):
        return [_safe_arg_shape(item, depth + 1) for item in value[:20]]
    if isinstance(value, (str, bytes)):
        text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
        if len(text) > 120:
            return {"sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(), "length": len(text)}
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:120]


def _audit_log_path() -> Path:
    raw = os.environ.get("HERMES_DATA_AUDIT_LOG_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    data_dir = os.environ.get("HERMES_DATA_DIR", "/home/hermes/data")
    return Path(data_dir) / "audit" / "data-tools.jsonl"


def audit_data_tool_call(
    *,
    tool_name: str,
    args: dict[str, Any] | None,
    status: str,
    model: str | None = None,
    model_tier: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    tool_call_id: str | None = None,
    duration_ms: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> bool:
    """Append one sanitized JSONL audit event for managed data-tool calls."""
    if not _env_truthy("HERMES_DATA_AUDIT_ENABLED", "true"):
        return False
    profile = data_tool_profile(tool_name, args)
    if not profile:
        return False

    safe_args = _safe_arg_shape(args or {})
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": "data_tool_call",
        "user_id": user_id or os.environ.get("HERMES_USER_ID", ""),
        "session_id": session_id or "",
        "turn_id": turn_id or "",
        "tool_call_id": tool_call_id or "",
        "tool_name": tool_name,
        "status": status,
        "model": model or "",
        "model_tier": model_tier or "",
        "duration_ms": duration_ms,
        "error_type": error_type or "",
        "error_message_hash": hashlib.sha256(str(error_message or "").encode("utf-8", "replace")).hexdigest()
        if error_message
        else "",
        "data_profile": profile,
        "args_shape": safe_args,
    }

    path = _audit_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with _AUDIT_LOCK:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return True
    except Exception:
        return False
