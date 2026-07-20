# Climate Indicators

Use PostgreSQL MCP read-only queries against `eco_stations`. Observation table
names are uppercase and must be quoted. Filter stations with `sss000`.

Default stations: `GGF`, `ALF`, `BNF`.

Trend metrics use linear regression over annual series:
- `slope > 0`: increasing; `slope < 0`: decreasing
- `p < 0.01`: extremely significant
- `p < 0.05`: significant
- otherwise not significant

When `scipy` is unavailable, compute slope/intercept with least squares and
Pearson `r` if available; leave `p` empty rather than inventing it.

## Figure Groups

### 图4-1 气温年际动态变化

Metric: annual mean temperature.

Source: `meteorological."T3NV1"`, field `t302`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       AVG(t302)::double precision AS value
FROM meteorological."T3NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND t302 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `℃`.

### 图4-2 降水量年际动态变化

Metric: annual precipitation.

Source: `meteorological."R3NV1"`, field `sum000`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       SUM(sum000)::double precision AS value
FROM meteorological."R3NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND sum000 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `mm`.

### 图4-3 空气湿度年际动态变化

Metric: annual mean relative humidity.

Source: `meteorological."RH3NV1"`, field `rh302`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       AVG(rh302)::double precision AS value
FROM meteorological."RH3NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND rh302 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `%`.

### 图4-4 光合有效辐射年际动态变化

Metric: annual mean PAR.

Preferred source: `meteorological."D32NV1"`, field `d3210` daily total.
Fallback source: `meteorological."D33NV1"`, field `d3310` monthly total.

Daily aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       (SUM(d3210) / NULLIF(COUNT(d3210), 0))::double precision AS value
FROM meteorological."D32NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND d3210 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Monthly fallback:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       (SUM(d3310) / NULLIF(COUNT(d3310), 0))::double precision AS value
FROM meteorological."D33NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND d3310 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `mol/m²`.

### 图4-5 气温季节动态变化

Metric: monthly mean temperature.

Source: `meteorological."T3NV1"`, field `t302`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, mm0000::int AS month,
       AVG(t302)::double precision AS value,
       STDDEV_SAMP(t302)::double precision AS std_value,
       COUNT(t302)::int AS n
FROM meteorological."T3NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND t302 IS NOT NULL
GROUP BY sss000, sscode, ssname, mm0000
ORDER BY sss000, sscode, mm0000;
```

Unit: `℃`.

### 图4-6 降水量季节动态变化

Metric: monthly precipitation.

Source: `meteorological."R3NV1"`, field `sum000`.

Use the same monthly aggregate pattern as 图4-5, replacing `t302` with `sum000`.
Unit: `mm`.

### 图4-7 空气湿度季节动态变化

Metric: monthly mean relative humidity.

Source: `meteorological."RH3NV1"`, field `rh302`.

Use the same monthly aggregate pattern as 图4-5, replacing `t302` with `rh302`.
Unit: `%`.

### 图4-8 光合有效辐射季节动态变化

Metric: monthly PAR.

Source: `meteorological."D33NV1"`, field `d3310`.

Use the same monthly aggregate pattern as 图4-5, replacing `t302` with `d3310`.
Unit: `mol/m²`.

### 图4-9 气温暖日阈值年际动态变化

Metric: warm day threshold, 90th percentile of daily maximum temperature.

Source: `meteorological."T2NV1"`, field `max000`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY max000)::double precision AS value,
       COUNT(max000)::int AS n
FROM meteorological."T2NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND max000 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `℃`.

### 图4-10 气温冷夜阈值年际动态变化

Metric: cold night threshold. Use the 10th percentile of daily minimum
temperature if `min000` exists; otherwise use the 10th percentile of `max000`
only if the user confirms that legacy template wording should be followed.

Preferred source: `meteorological."T2NV1"`, field `min000`.

Aggregate: same as 图4-9, using `percentile_cont(0.1)` and `min000`.

Unit: `℃`.

### 图4-11 连续干旱最大天数年际动态变化

Metric: maximum consecutive dry days.

Source: `meteorological."R2NV1"`, field `sum000`.

Rule: `sum000 = 0` is a dry day; missing values break the sequence.

Query daily precipitation by station/facility/year/month/day only for requested
stations and years, then compute streaks outside SQL. Do not return unnecessary
columns.

### 图4-12 有雨日降水强度年际动态变化

Metric: precipitation intensity on rainy days.

Source: `meteorological."R2NV1"`, field `sum000`.

Aggregate:

```sql
SELECT sss000 AS station_code, sscode, ssname, yyyy00::int AS year,
       (SUM(sum000) FILTER (WHERE sum000 > 0)
        / NULLIF(COUNT(sum000) FILTER (WHERE sum000 > 0), 0))::double precision AS value,
       COUNT(sum000) FILTER (WHERE sum000 > 0)::int AS rainy_days
FROM meteorological."R2NV1"
WHERE sss000 = ANY($stations)
  AND yyyy00 BETWEEN $start_year AND $end_year
  AND sum000 IS NOT NULL
GROUP BY sss000, sscode, ssname, yyyy00
ORDER BY sss000, sscode, yyyy00;
```

Unit: `mm/d`.

## Data Quality Notes

Apply known exclusions only when verified by the queried data or user request.
Known caution: GGF 2004 annual temperature can be anomalously low in older
workflows. If the selected period includes 2004, check and document whether it
was excluded.
