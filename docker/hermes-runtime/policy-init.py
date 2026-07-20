#!/usr/bin/env python3
"""Apply administrator-managed runtime policy inside a user Hermes container."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml


def env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def json_env(name: str, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        backup = path.with_suffix(path.suffix + ".invalid")
        try:
            path.replace(backup)
        except Exception:
            pass
        return {}


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def safe_user_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return slug or "user"


def load_json_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_runtime_policy() -> dict:
    policy_root_raw = os.environ.get("HERMES_POLICY_ROOT", "").strip()
    if not policy_root_raw:
        return {}
    policy_root = Path(policy_root_raw).expanduser()
    policy = load_json_policy(policy_root / "global.json")
    user_id = os.environ.get("HERMES_USER_ID", "").strip()
    user_slug = os.environ.get("HERMES_RUNTIME_POLICY_USER", "").strip() or safe_user_slug(user_id)
    for candidate in (user_id, user_slug):
        if candidate:
            policy = deep_merge(policy, load_json_policy(policy_root / "users" / f"{safe_user_slug(candidate)}.json"))
    return policy


def model_from_runtime_policy(policy: dict) -> dict[str, str]:
    model_policy = policy.get("model_policy") if isinstance(policy.get("model_policy"), dict) else {}
    local_model = model_policy.get("local_model") if isinstance(model_policy.get("local_model"), dict) else {}
    if not local_model:
        return {}
    return {
        "provider": str(local_model.get("provider") or "").strip(),
        "model": str(local_model.get("model") or local_model.get("default") or "").strip(),
        "base_url": str(local_model.get("base_url") or "").strip(),
        "api_key": str(local_model.get("api_key") or "").strip(),
    }


def provider_env_prefix(provider: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(provider or "").strip()).strip("_")
    return slug.upper()


def provider_env_vars(provider: str) -> tuple[str, str]:
    normalized = str(provider or "").strip().lower()
    if normalized in {"openai-compatible", "custom", "local", "openai"}:
        return "OPENAI_API_KEY", "OPENAI_BASE_URL"
    prefix = provider_env_prefix(normalized)
    return f"{prefix}_API_KEY", f"{prefix}_BASE_URL"


def quote_env_value(value: str) -> str:
    return json.dumps(str(value or ""))


def write_env_values(path: Path, values: dict[str, str]) -> bool:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = {key: str(value) for key, value in values.items() if str(value or "").strip()}
    if not pending:
        return False

    changed = False
    output: list[str] = []
    seen: set[str] = set()
    for line in existing:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not match:
            output.append(line)
            continue
        key = match.group(1)
        if key in pending:
            new_line = f"{key}={quote_env_value(pending[key])}"
            output.append(new_line)
            seen.add(key)
            changed = changed or new_line != line
        else:
            output.append(line)

    missing = [key for key in pending if key not in seen]
    if missing:
        if output and output[-1].strip():
            output.append("")
        output.append("# Managed by Hermes runtime policy.")
        for key in missing:
            output.append(f"{key}={quote_env_value(pending[key])}")
        changed = True

    if changed:
        path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return changed


def set_or_remove(mapping: dict, key: str, value: str | None) -> bool:
    if value is None or str(value).strip() == "":
        if key in mapping:
            mapping.pop(key, None)
            return True
        return False
    if mapping.get(key) != value:
        mapping[key] = value
        return True
    return False


def sync_admin_model_config(hermes_home: Path, cfg: dict) -> bool:
    policy_model = model_from_runtime_policy(load_runtime_policy())
    provider = policy_model.get("provider") or os.environ.get("MODEL_PROVIDER", "").strip()
    model = policy_model.get("model") or os.environ.get("MODEL_DEFAULT", "").strip()
    base_url = policy_model.get("base_url") or os.environ.get("MODEL_BASE_URL", "").strip()
    api_key = policy_model.get("api_key") or os.environ.get("MODEL_API_KEY", "").strip()
    if not provider or not model:
        return False

    normalized_provider = "custom" if provider.lower() in {"openai-compatible", "local"} else provider
    model_cfg = cfg.get("model")
    if not isinstance(model_cfg, dict):
        model_cfg = {}
        cfg["model"] = model_cfg

    changed = False
    desired_model = {
        "provider": normalized_provider,
        "default": model,
        "api_key": api_key,
    }
    if base_url:
        desired_model["base_url"] = base_url.rstrip("/")

    for key, value in desired_model.items():
        if set_or_remove(model_cfg, key, value):
            changed = True
    if not base_url and set_or_remove(model_cfg, "base_url", ""):
        changed = True

    cfg.setdefault("managed_runtime", {})
    if isinstance(cfg["managed_runtime"], dict):
        managed = cfg["managed_runtime"]
        managed_values = {
            "model_source": "admin_policy",
            "model_provider": normalized_provider,
            "model_id": model,
            "model_base_url": base_url.rstrip("/") if base_url else "",
        }
        for key, value in managed_values.items():
            if managed.get(key) != value:
                managed[key] = value
                changed = True

    api_key_var, base_url_var = provider_env_vars(provider)
    env_values = {
        "MODEL_PROVIDER": normalized_provider,
        "MODEL_DEFAULT": model,
        api_key_var: api_key,
        base_url_var: base_url.rstrip("/") if base_url else "",
    }
    if normalized_provider == "custom":
        env_values["OPENAI_API_KEY"] = api_key
        env_values["OPENAI_BASE_URL"] = base_url.rstrip("/") if base_url else ""
    if write_env_values(hermes_home / ".env", env_values):
        changed = True
    return changed


def main() -> None:
    hermes_home = Path(os.environ.get("HERMES_HOME", "/home/hermes/data/hermes")).expanduser()
    hermes_home.mkdir(parents=True, exist_ok=True)
    config_path = hermes_home / "config.yaml"
    cfg = load_yaml(config_path)
    changed = sync_admin_model_config(hermes_home, cfg)

    managed_mcp = json_env("HERMES_MANAGED_MCP_SERVERS_JSON", {})
    if isinstance(managed_mcp, dict) and managed_mcp and env_truthy("HERMES_ENFORCE_MANAGED_MCP_SERVERS", "true"):
        cfg["mcp_servers"] = managed_mcp
        changed = True
        cfg.setdefault("managed_runtime", {})
        if isinstance(cfg["managed_runtime"], dict):
            cfg["managed_runtime"]["mcp_servers_source"] = "admin_policy"

    connectors = json_env("HERMES_DATA_CONNECTORS_JSON", [])
    if isinstance(connectors, list) and connectors:
        cfg.setdefault("managed_runtime", {})
        if isinstance(cfg["managed_runtime"], dict):
            cfg["managed_runtime"]["data_connectors"] = [
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "privacy_level": item.get("privacy_level"),
                    "access_mode": item.get("access_mode") or ("read-only" if item.get("readonly") else None),
                }
                for item in connectors
                if isinstance(item, dict)
            ]
            changed = True

    if changed:
        config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
