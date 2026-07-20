#!/usr/bin/env python3
"""Build a climate annual-report Markdown file from a small manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


PAR_FIGURES = {"fig4-4", "fig4-8"}


def _relpath(path: str, base_dir: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        return path
    try:
        return os.path.relpath(p, base_dir)
    except ValueError:
        return str(p)


def build_markdown(manifest: dict, output: Path) -> str:
    title = manifest.get("title") or "森林生态系统气候要素数据年报"
    author = manifest.get("author") or "国家生态科学数据中心"
    period = manifest.get("period") or ""
    overview = manifest.get("overview") or [
        "本报告基于当前已接入台站和年份范围生成气候要素图集；趋势和空间差异以各图组统计结果为准。"
    ]

    lines: list[str] = [
        "---",
        f"title: {title}",
        f"author: {author}",
        "---",
        "",
        "# 森林生态系统关键要素动态变化图",
        "",
        "## 气候要素",
        "",
    ]
    if period:
        lines.extend([f"统计时段：{period}", ""])

    for paragraph in overview:
        if str(paragraph).strip():
            lines.extend([str(paragraph).strip(), ""])

    figures = manifest.get("figures") or []
    for fig in figures:
        fig_id = fig.get("id") or ""
        fig_title = fig.get("title") or fig_id
        fig_path = fig.get("path") or ""
        note = fig.get("note") or ""
        if not fig_path:
            continue
        rel = _relpath(fig_path, output.parent)
        lines.extend([
            f"###### {fig_title}",
            "",
            f"![{fig_title}]({rel})",
            "",
        ])
        if fig_id in PAR_FIGURES:
            lines.extend(["*PAR：photosynthetically active radiation，光合有效辐射*", ""])
        if note:
            lines.extend([str(note).strip(), ""])

    quality_notes = manifest.get("quality_notes") or []
    missing = manifest.get("missing") or []
    if quality_notes or missing:
        lines.extend(["## 数据与质量说明", ""])
        for item in quality_notes:
            lines.append(f"- {item}")
        for item in missing:
            figure = item.get("figure", "")
            station = item.get("station", "")
            reason = item.get("reason", "")
            lines.append(f"- {figure} {station}: {reason}".strip())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", "-o", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_markdown(manifest, args.output), encoding="utf-8")


if __name__ == "__main__":
    main()
