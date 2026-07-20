# Report Style

Follow the Obsidian template `数据年报报告模版-气候要素`.

## Structure

Use this order:

```markdown
---
title: 森林生态系统气候要素数据年报
author: 国家生态科学数据中心
---

# 森林生态系统关键要素动态变化图

## 气候要素

气候要素概述...

###### 图4-1 CERN森林站气温年际动态变化

![图4-1 CERN森林站气温年际动态变化](path/to/panel.png)

...
```

Use `######` for figure titles to match the source template.

## Writing Rules

- Write in Chinese.
- Keep prose formal, concise, and evidence-bound.
- Do not claim significance unless trend statistics were computed.
- Use `2005—2024年` with an em-like Chinese range mark in prose if possible.
- Explain missing station/metric outputs in a short note instead of failing the report.

## Figure Layout

The template expects station charts arranged two per row. For generated reports,
each figure title should be followed by one stitched image panel. The panel
itself contains the two-column station layout.

For PAR sections, include:

```markdown
*PAR：photosynthetically active radiation，光合有效辐射*
```

## Overview Paragraphs

Overview should synthesize:
- temperature, precipitation, humidity, PAR spatial differences
- annual trend highlights
- seasonal dynamics
- threshold and dry/rainy-day indicators

If full synthesis is not available, use a factual placeholder:

`本报告基于当前已接入台站和年份范围生成气候要素图集；趋势和空间差异以各图组统计结果为准。`
