"""Runtime privacy guardrails for managed Hermes WebUI deployments."""

from __future__ import annotations

import json
import os
import re
from typing import Iterable


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


ONLINE_TIERS = frozenset({"quality", "fast"})
SAFE_TIER = "safe"

DEFAULT_ONLINE_ALLOWED_TOOLSETS = "web,vision,clarify,todo,image_gen"
DEFAULT_PRIVATE_TOOL_NAMES = (
    "terminal,process,read_terminal,execute_code,"
    "read_file,write_file,patch,search_files,"
    "memory,session_search,skill_manage,cronjob,delegate_task,send_message,"
    "browser_navigate,browser_snapshot,browser_click,browser_type,browser_scroll,"
    "browser_back,browser_press,browser_get_images,browser_vision,browser_console,"
    "browser_cdp,browser_dialog,computer_use"
)

DB_CLIENT_RE = re.compile(
    r"\b(clickhouse-client|clickhouse\s+client|psql|mysql|mariadb|sqlite3|duckdb|mongo|mongosh|redis-cli)\b",
    re.IGNORECASE,
)
DB_WRITE_RE = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|replace|merge|upsert|grant|revoke|"
    r"copy\s+.*\s+from|copy\s+.*\s+to|attach|detach|optimize|kill|rename|vacuum|"
    r"system\s+(reload|restart|drop|flush|stop|start)"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
DB_READ_RE = re.compile(
    r"^\s*(with\b.*\bselect\b|select\b|show\b|describe\b|desc\b|explain\b)",
    re.IGNORECASE | re.DOTALL,
)
TERMINAL_NETWORK_RE = re.compile(
    r"\b(curl|wget|nc|netcat|ncat|ssh|scp|sftp|rsync|ftp|telnet|socat)\b",
    re.IGNORECASE,
)
CODE_DB_RE = re.compile(
    r"\b(clickhouse|psycopg|psycopg2|asyncpg|pymysql|mysql|sqlite3|duckdb|sqlalchemy|pymongo|redis)\b",
    re.IGNORECASE,
)
CODE_NETWORK_RE = re.compile(
    r"\b(requests|httpx|urllib|aiohttp|socket|paramiko|ftplib|smtplib)\b",
    re.IGNORECASE,
)


def privacy_guard_enabled() -> bool:
    return _env_truthy("HERMES_RUNTIME_PRIVACY_GUARD_ENABLED", "true")


def tier_for_model_selection(model_id: str | None, fallback_model_id: str | None = None) -> str:
    try:
        from api.config import admin_model_tier_for_model

        tier = admin_model_tier_for_model(model_id)
        if tier:
            return tier
        return admin_model_tier_for_model(fallback_model_id)
    except Exception:
        return ""


def filter_toolsets_for_model(
    toolsets: Iterable[str] | None,
    model_id: str | None,
    *,
    resolved_model_id: str | None = None,
) -> tuple[list[str] | None, dict]:
    """Return toolsets restricted by the current model privacy tier."""
    original = list(toolsets) if toolsets is not None else None
    tier = tier_for_model_selection(model_id, resolved_model_id)
    if not privacy_guard_enabled() or tier not in ONLINE_TIERS:
        return original, {"enabled": privacy_guard_enabled(), "tier": tier, "restricted": False}

    allowed = set(_csv("HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS", DEFAULT_ONLINE_ALLOWED_TOOLSETS))
    source = original if original is not None else sorted(allowed)
    filtered = [name for name in source if name in allowed]
    return filtered, {
        "enabled": True,
        "tier": tier,
        "restricted": True,
        "allowed_toolsets": sorted(allowed),
        "removed_toolsets": sorted(set(original or []) - set(filtered)),
    }


def _private_tool_names() -> set[str]:
    return set(_csv("HERMES_PRIVATE_TOOL_NAMES", DEFAULT_PRIVATE_TOOL_NAMES))


def _is_private_tool(tool_name: str) -> bool:
    name = str(tool_name or "").strip()
    if not name:
        return False
    if name.startswith("mcp_"):
        public_mcp = set(_csv("HERMES_PUBLIC_MCP_TOOL_PREFIXES", ""))
        return not any(name.startswith(prefix) for prefix in public_mcp if prefix)
    return name in _private_tool_names()


def _command_text(args: dict) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("command", "cmd", "script"):
        value = args.get(key)
        if value:
            return str(value)
    return ""


def _code_text(args: dict) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("code", "script", "source"):
        value = args.get(key)
        if value:
            return str(value)
    return ""


def _json_error(message: str, code: str = "webui_privacy_policy") -> str:
    return json.dumps({"error": message, "code": code, "blocked_by": "webui_runtime_privacy_guard"}, ensure_ascii=False)


def _db_command_block_message(command: str) -> str | None:
    if not command:
        return None
    if DB_CLIENT_RE.search(command):
        if DB_WRITE_RE.search(command):
            return (
                "Database write operations are blocked in Hermes Runtime. "
                "Use read-only SELECT/SHOW/DESCRIBE/EXPLAIN queries through the approved local-safe path."
            )
        if not DB_READ_RE.search(command) and "--query" not in command and "-q" not in command:
            return (
                "Interactive database clients are blocked. "
                "Use a bounded read-only query through the approved database tool or an explicit SELECT query."
            )
    return None


def tool_call_block_message(
    tool_name: str,
    args: dict,
    *,
    model: str | None = None,
    model_tier: str | None = None,
) -> str | None:
    """Return a synthetic block message for unsafe tool calls, or None."""
    if not privacy_guard_enabled():
        return None

    tier = str(model_tier or "").strip() or tier_for_model_selection(model)
    name = str(tool_name or "").strip()

    try:
        from api.data_connectors import readonly_violation_message

        connector_block = readonly_violation_message(name, args)
    except Exception:
        connector_block = None
    if connector_block:
        return _json_error(connector_block, "managed_data_connector_readonly_blocked")

    if tier in ONLINE_TIERS and _is_private_tool(name):
        return _json_error(
            "This tool can access private local data, so it is not available on High Quality/Fast online tiers. "
            "Switch to Local Safe for database, file, terminal, MCP, or private knowledge-base work.",
            "online_tier_private_tool_blocked",
        )

    if name in {"terminal", "process"}:
        command = _command_text(args)
        db_block = _db_command_block_message(command)
        if db_block:
            return _json_error(db_block, "database_write_or_interactive_client_blocked")
        if not _env_truthy("HERMES_ALLOW_TERMINAL_NETWORK", "false") and TERMINAL_NETWORK_RE.search(command):
            return _json_error(
                "Outbound network commands are blocked from the terminal in managed Hermes Runtime. "
                "Use approved Web/search tools or an administrator-managed connector.",
                "terminal_network_blocked",
            )

    if name == "execute_code":
        code = _code_text(args)
        if CODE_DB_RE.search(code) and DB_WRITE_RE.search(code):
            return _json_error(
                "Database write operations from execute_code are blocked. Use read-only database access only.",
                "code_database_write_blocked",
            )
        if not _env_truthy("HERMES_ALLOW_CODE_NETWORK", "false") and CODE_NETWORK_RE.search(code):
            return _json_error(
                "Network-capable code is blocked in managed Hermes Runtime. Use approved connectors instead.",
                "code_network_blocked",
            )

    return None
