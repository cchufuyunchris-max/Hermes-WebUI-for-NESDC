# Manifest Schema

Use a small JSON manifest to decouple chart generation from report writing.

```json
{
  "title": "森林生态系统气候要素数据年报",
  "author": "国家生态科学数据中心",
  "stations": ["GGF", "ALF", "BNF"],
  "period": "2005-2024",
  "overview": [
    "第一段概述。",
    "第二段概述。"
  ],
  "figures": [
    {
      "id": "fig4-1",
      "title": "图4-1 CERN森林站气温年际动态变化",
      "path": "assets/fig4-1_temperature_annual.png",
      "note": ""
    }
  ],
  "quality_notes": [
    "GGF 2004 年异常值未纳入本期统计。"
  ],
  "missing": [
    {
      "figure": "fig4-4",
      "station": "ALF",
      "reason": "D32NV1 日值缺失，已尝试 D33NV1 月值路径。"
    }
  ]
}
```

Paths may be absolute or relative to the Markdown output directory. Prefer
relative paths when possible.
