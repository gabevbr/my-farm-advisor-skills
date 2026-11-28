# Field EDA

Field-level exploratory analysis for a built My Farm Advisor runtime. This subskill
compares the three things every field already carries — its boundary, its Cropland
Data Layer (CDL) history, and its daily weather — and writes static Python figures plus
CSV statistics tables.

It is the analysis layer for the Assignment 2 field EDA. It is deliberately smaller
than a reporting product: no dashboard, no HTML, no PDF, no soil analysis. Those are
separate steps that consume these outputs.

## What it answers

| Category | Question | Figure | Table |
| --- | --- | --- | --- |
| Boundaries | Are field sizes different across growers, and how large is the effect? | F1 | `stats-boundaries.csv` |
| Boundaries | Does field size track shape complexity? | F2 | `stats-boundaries.csv` |
| CDL | What rotation is each field running? | F3 | `field-metrics.csv` |
| CDL | What is the latest crop composition, and how pure is each field? | F4 | `field-metrics.csv` |
| CDL | Is rotation diversity different across growers? | — | `stats-cdl.csv` |
| Weather | What does the seasonal cycle look like by grower? | F5 | `stats-weather.csv` |
| Weather | How do seasonal water and heat co-vary? | F6 | `stats-weather.csv` |
| Geospatial | Where are the sampled fields, and what crop is in each? | F7 | `field-metrics.csv` |

The full encoding and intended story for each figure is in
[references/figure-specs.md](references/figure-specs.md). Test choices and results are
in [references/statistics.md](references/statistics.md).

## Run

The tool reads a runtime root that contains `data-pipeline/growers/`. It accepts either
the base directory or the `data-pipeline` directory itself.

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"

# Validate inputs and print a summary without writing anything
python my-farm-advisor/eda/field-eda/run_field_eda.py --dry-run

# Full run: figures + tables + manifest
python my-farm-advisor/eda/field-eda/run_field_eda.py

# Limit to specific grower slugs
python my-farm-advisor/eda/field-eda/run_field_eda.py --growers il-grower ia-grower

# Tables and manifest only
python my-farm-advisor/eda/field-eda/run_field_eda.py --no-figures
```

Output defaults to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/<run-id>/`:

```text
<run-id>/
├── figures/
│   ├── F1-boundaries-area-by-grower.png
│   ├── F2-boundaries-shape-vs-area.png
│   ├── F3-cdl-rotation-heatmap.png
│   ├── F4-cdl-composition.png
│   ├── F5-weather-climatology.png
│   ├── F6-weather-precip-vs-gdd.png
│   └── F7-geospatial-field-map.png
├── tables/
│   ├── field-metrics.csv
│   ├── stats-boundaries.csv
│   ├── stats-cdl.csv
│   └── stats-weather.csv
└── manifest.json
```

Use `--run-id` to overwrite a reviewed run in place, or `--out` to write elsewhere.
Generated outputs stay in the runtime and are never committed from this repository.

## Inputs

The loaders discover tables by glob, because the same three families use different
prefixes per farm (`illinois_demo`, `iowa`, `nebraska_demo`). They read, per farm:

- `boundary/field_boundaries.geojson` (EPSG:4326)
- `derived/tables/*_weather_*.csv` (daily, one row per field-day)
- `derived/tables/*_<year>_cdl.csv` (long format, one row per field-year-class)
- `derived/tables/*_crop_rotation.csv` (optional context)
- `manifests/field-inventory.csv` (cross-check)

Exact columns, dtypes, and validation warnings are in
[references/data-contract.md](references/data-contract.md).

## Methods at a glance

- **Area and shape.** Boundaries are projected to EPSG:5070 (CONUS Albers) before any
  metric is computed. Polsby-Popper compactness is `4πA / P²`: a square scores `π/4`,
  a circle scores `1.0`. Both `area_ha_est` from the boundary attributes and the
  projected area are retained and compared; a >2% disagreement warns.
- **Rotation.** Dominant crop is the class with the largest CDL pixel share in each
  field-year. Diversity is the Shannon index of the five-year dominant-crop sequence
  (2019–2023), not of pixel areas. Continuous corn means the dominant crop was Corn in
  every available CDL year.
- **Composition.** The latest CDL year is stacked per field. Classes outside
  Corn/Soybeans/Grass–Pasture are grouped as "Other"; because the CDL tables omit
  unclassified pixels, the missing share is drawn as a grey residual band and also
  written as `latest_unclassified_pct`.
- **Weather.** Growing season is April 1–October 31. GDD uses base 10 °C with a 30 °C
  cap. Monthly precipitation is summed per field-month first and then averaged across
  the co-located fields, so a shared climate grid is not counted ten times.
- **Geospatial.** F7 draws one panel per farm on a local UTM metre frame, auto-rotated
  to the sampled-field cluster, with a true-north arrow and an Esri World Imagery
  basemap under the footprints. The fields are colored by latest dominant crop. Because
  the sample is county-wide (fields span tens of kilometres), per-field IDs would not be
  legible at README size; they stay in F3/F4 and `field-metrics.csv`.

## Statistical posture

Ten fields per grower and five weather years are small samples. Everything is rank
based: Kruskal–Wallis for the omnibus comparison, Mann–Whitney U with Holm correction
for pairwise contrasts, Spearman rho for association, and eta-squared for the share of
variance between growers. Effect sizes and confidence intervals are reported alongside
p-values; p-values are not treated as decision thresholds on their own.

The important caveat: the 10 fields in a grower share one climate grid, and the
fields are the top 10 by area in each county, not a random draw. Weather p-values use
field-years as rows but the effective sample is closer to 5 years per grower, and the
pooled precipitation–GDD correlation is a between-grower contrast that changes sign
within Illinois. See [references/statistics.md](references/statistics.md).

## Figure quality gate

Every figure is reviewed against the repository's five-point vision gate before it is
accepted: no empty panels, a correct field-map frame on F7 (local-metre axes,
auto-rotation, north arrow, basemap under), legible labels at README size, color
semantics matching the data type, and a title/annotation set that reads without the
surrounding prose. The current verdict for all seven figures, including the defects
found and fixed during review (F4 label overlap, F5 10× precipitation aggregation, F7
axis collapse and halo scaling), is recorded in
[references/figure-specs.md](references/figure-specs.md).

## Scope and non-goals

- No soil analysis, imagery indices, terrain derivatives, or in-season monitoring.
- No report prose and no dashboard; this is the reusable analysis layer.
- No upload of runtime bundles, generated figures, or downloaded assets.
- No assumption that the three demo growers are agronomically representative.
