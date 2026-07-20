#!/usr/bin/env python3
"""Provision default project skills into a user's persistent Hermes data dir."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(os.environ.get("HERMES_DATA_DIR", "/home/hermes/data"))
USER_SKILLS_DIR = Path(os.environ.get("HERMES_USER_SKILLS_DIR", DATA_DIR / "skills"))
STATE_FILE = Path(os.environ.get("HERMES_SKILL_STATE_FILE", DATA_DIR / "skill-state.json"))
PROVISIONED_SKILLS_DIR = Path(
    os.environ.get("HERMES_PROVISIONED_SKILLS_DIR", "/home/hermes/provisioned-skills")
)
UPDATE_POLICY = os.environ.get("PROJECT_SKILLS_UPDATE_POLICY", "manual").lower()
AUTO_INSTALL_RECOMMENDED_SKILLS = (
    os.environ.get("HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"skills": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = STATE_FILE.with_suffix(f".invalid-{int(datetime.now().timestamp())}.json")
        shutil.copy2(STATE_FILE, backup)
        return {"skills": {}}


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def skill_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = item.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def skill_version(path: Path) -> str:
    manifest = path / "skill-version.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            version = data.get("version")
            if version:
                return str(version)
        except json.JSONDecodeError:
            pass
    return skill_fingerprint(path)[:12]


def copy_skill(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))


def ensure_data_dirs() -> None:
    for path in [
        DATA_DIR,
        USER_SKILLS_DIR,
        Path(os.environ.get("HERMES_WORKSPACE_DIR", DATA_DIR / "workspace")),
        Path(os.environ.get("HERMES_MEMORY_DIR", DATA_DIR / "memory")),
        Path(os.environ.get("HERMES_SESSION_DIR", DATA_DIR / "sessions")),
        Path(os.environ.get("HERMES_ARTIFACT_DIR", DATA_DIR / "artifacts")),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ensure_data_dirs()
    state = read_state()
    skills_state = state.setdefault("skills", {})

    if not AUTO_INSTALL_RECOMMENDED_SKILLS:
        write_state(state)
        return

    if not PROVISIONED_SKILLS_DIR.exists():
        write_state(state)
        return

    for src in sorted(p for p in PROVISIONED_SKILLS_DIR.iterdir() if p.is_dir()):
        name = src.name
        dest = USER_SKILLS_DIR / name
        available_version = skill_version(src)
        source_fingerprint = skill_fingerprint(src)
        current = skills_state.get(name)

        if current is None or not dest.exists():
            copy_skill(src, dest)
            skills_state[name] = {
                "source": "provisioned",
                "installed_version": available_version,
                "available_version": available_version,
                "installed_at": utc_now(),
                "updated_at": utc_now(),
                "source_fingerprint": source_fingerprint,
                "installed_fingerprint": skill_fingerprint(dest),
                "user_modified": False,
                "update_policy": UPDATE_POLICY,
            }
            continue

        installed_fingerprint = skill_fingerprint(dest)
        user_modified = installed_fingerprint != current.get("installed_fingerprint")
        current["available_version"] = available_version
        current["user_modified"] = user_modified
        current["update_policy"] = UPDATE_POLICY

        has_update = available_version != current.get("installed_version")
        if has_update and UPDATE_POLICY == "safe" and not user_modified:
            copy_skill(src, dest)
            current["installed_version"] = available_version
            current["updated_at"] = utc_now()
            current["source_fingerprint"] = source_fingerprint
            current["installed_fingerprint"] = skill_fingerprint(dest)
            current["user_modified"] = False
            current.pop("pending_update", None)
        elif has_update:
            current["pending_update"] = {
                "available_version": available_version,
                "detected_at": utc_now(),
                "reason": "manual_update_required" if user_modified else "manual_policy",
            }
        else:
            current.pop("pending_update", None)

    write_state(state)


if __name__ == "__main__":
    main()
