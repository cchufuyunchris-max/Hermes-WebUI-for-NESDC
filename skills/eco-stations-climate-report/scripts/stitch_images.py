#!/usr/bin/env python3
"""Stitch station charts into a two-column report panel."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def stitch_grid(
    image_paths: list[Path],
    output: Path,
    *,
    title: str = "",
    columns: int = 2,
    pad_h: int = 18,
    pad_v: int = 18,
    margin: int = 24,
    title_height: int = 54,
) -> None:
    if not image_paths:
        raise SystemExit("No input images supplied.")
    if columns < 1:
        raise SystemExit("columns must be >= 1.")

    images = [Image.open(path).convert("RGB") for path in image_paths]
    cell_w = max(img.width for img in images)
    cell_h = max(img.height for img in images)
    rows = (len(images) + columns - 1) // columns
    title_block = title_height if title else 0
    width = margin * 2 + columns * cell_w + (columns - 1) * pad_h
    height = margin * 2 + title_block + rows * cell_h + (rows - 1) * pad_v

    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    y0 = margin
    if title:
        font = _load_font(24)
        draw.text((margin, y0), title, fill=(24, 24, 24), font=font)
        y0 += title_block

    for idx, img in enumerate(images):
        row, col = divmod(idx, columns)
        x = margin + col * (cell_w + pad_h) + (cell_w - img.width) // 2
        y = y0 + row * (cell_h + pad_v) + (cell_h - img.height) // 2
        canvas.paste(img, (x, y))

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", "-o", required=True, type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--columns", type=int, default=2)
    args = parser.parse_args()
    stitch_grid(args.images, args.output, title=args.title, columns=args.columns)


if __name__ == "__main__":
    main()
