---
name: eco-stations-climate-report
description: Generate complete NESDC eco_stations climate annual reports from PostgreSQL MCP data, including all 12 climate figure groups, two-column stitched chart panels, Markdown output, and PDF export. Use when the user asks for 数据年报, 气候要素报告, 森林站气候报告, GGF/ALF/BNF climate annual report, Markdown/PDF report generation, or complete climate indicator output.
---

# Eco Stations Climate Report

Generate a complete climate-element annual report for the local `eco_stations`
database. The report must follow the Obsidian climate template: 12 figure
groups, each rendered as one stitched image panel with two charts per row, then
assembled into Markdown and exported to PDF.

## Stability Rules

This is a stable workflow. Do not modify this skill during report execution.
If an improvement is needed, write a short proposal outside this skill and ask
the user before applying it.

Hard limits:
- Do not use heredoc to create Python/R/JS scripts.
- Do not create one comprehensive script in the terminal.
- Do not load or expand all 27 cross-domain indicators; this skill is climate only.
- Do not put base64 images in Markdown.
- Do not insert dozens of individual station images into the report. Use stitched panels.
- Do not run `SELECT *` against observation tables.
- Do not return raw large query results to the chat. Return summaries and artifact paths.

## Data Access

Primary path: PostgreSQL MCP connected to `eco_stations`.

Before generating a report, verify:

```sql
SELECT current_database();
```

It must return `eco_stations`. If it does not, stop and tell the user to fix the
MCP `DATABASE_URL`. Do not fall back silently.

Use read-only aggregate queries. Use `sss000` for station filtering. Do not use
`sscode` as the station code.

Fallback path: only if MCP is unavailable and the user explicitly approves,
use `psql -d eco_stations` for short aggregate queries. Heredoc is allowed only
for short SQL execution, never for writing scripts.

## Supported Scope

Default stations: `GGF`, `ALF`, `BNF`.

Default period: use the requested years; if absent, use the maximum common
period available in queried tables, usually `2005-2024`.

Output:
- Markdown report
- PDF report
- PNG chart panels
- JSON manifest of generated panels

## Required Figure Groups

Read `references/climate-indicators.md` for SQL and calculation details.

Generate all 12 figure groups unless the user explicitly narrows the scope:

1. 图4-1 气温年际动态变化
2. 图4-2 降水量年际动态变化
3. 图4-3 空气湿度年际动态变化
4. 图4-4 光合有效辐射年际动态变化
5. 图4-5 气温季节动态变化
6. 图4-6 降水量季节动态变化
7. 图4-7 空气湿度季节动态变化
8. 图4-8 光合有效辐射季节动态变化
9. 图4-9 气温暖日阈值年际动态变化
10. 图4-10 气温冷夜阈值年际动态变化
11. 图4-11 连续干旱最大天数年际动态变化
12. 图4-12 有雨日降水强度年际动态变化

## Workflow

1. Confirm `current_database() = eco_stations`.
2. Read `references/climate-indicators.md`.
3. For each figure group, query only the aggregate series needed for that group.
4. Generate one station chart per available station and metric.
5. Stitch station charts into one panel per figure group:
   `python3 scripts/stitch_images.py --title "图4-1 ..." --output panel.png chart1.png chart2.png ...`
6. Write `manifest.json` containing report metadata and panel paths. See
   `references/manifest-schema.md`.
7. Build Markdown:
   `python3 scripts/build_markdown_report.py --manifest manifest.json --output report.md`
8. Export PDF using the available PDF tool. Prefer existing any2pdf/md2pdf if
   configured. If PDF export fails, keep the Markdown and clearly report the
   failure.

## Report Style

Read `references/report-style.md` before writing report prose.

The report should contain:
- title and metadata
- climate overview paragraphs
- 12 figure sections in template order
- one stitched PNG per figure section
- short notes, including PAR explanation where relevant
- a compact data/quality note if important exclusions were applied

The prose must be evidence-bound. Do not invent significant trends. If a trend
or comparison was not calculated, say it is not determined.

## Chart Assembly

Each figure group should produce one stitched image panel, not many separate
Markdown images. Panels use two columns. If there are an odd number of station
charts, leave the final cell blank.

Use `scripts/stitch_images.py`; do not rewrite a stitcher during execution.

## Failure Handling

If any metric lacks data for a station:
- skip that station chart for that metric,
- record it in the manifest `missing` list,
- keep generating the rest of the report.

If fewer than two valid annual points are available, do not compute a trend.

If a write or stream stalls, stop. Do not retry by writing a larger chunk. Resume
from the last completed artifact path and process one figure group at a time.
