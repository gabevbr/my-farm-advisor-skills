# Field EDA Data Contract

What the subskill reads from the runtime, how it discovers it, what it writes, and
which conditions become warnings rather than failures.

## Runtime root

`resolve_data_root` accepts either form:

- a base directory that contains `data-pipeline/growers/`, or
- a directory that already contains `growers/` (that is, `.../data-pipeline`).

The value comes from `--data-root`, else `DATA_PIPELINE_DATA_ROOT`. If neither resolves
to a directory holding `growers/`, the run exits with code 2.

## Farm discovery

Every directory under `growers/` is a grower; every directory under
`growers/<grower>/farms/` is a farm. `--growers` filters by grower directory slug.
Grower and farm display names come from `grower.json` (`display_name`) and `farm.json`
(`display_name`, else `farm_name`), falling back to the directory name.

## Required inputs

### Boundary — required

`<farm>/boundary/field_boundaries.geojson`, CRS EPSG:4326.

Required columns:

| Column | Use |
| --- | --- |
| `field_id` | join key everywhere; cast to string |
| `area_ha_est` | declared area, compared with projected area |
| `crop` | boundary's current-crop attribute, exposed as `crop_2025` |
| `csb_id` | source polygon id; duplicate check |
| `county` | display |
| `state_fips`, `county_fips` | provenance display |
| `geometry` | projected to EPSG:5070 for metrics |

A non-EPSG:4326 boundary warns but still projects for metrics. Duplicate `field_id` or
`csb_id`, and inventory/boundary membership mismatches, warn.

### Weather — expected

Newest `derived/tables/*_weather_*.csv` by mtime. If several match, the newest is used
and the rest are named in a warning.

Required columns:

```text
field_id, date, T2M, T2M_MAX, T2M_MIN, PRECTOTCORR,
ALLSKY_SFC_SW_DWN, RH2M, WS10M
```

- `date` is parsed; unparseable rows are dropped with a warning.
- Fields in the boundary with no weather rows warn; weather rows for unknown fields warn.
- Fewer than five distinct years warns.
- A field with less than 95% of the expected daily rows for the available years warns.

Units are NASA POWER defaults: °C, mm/day, MJ/m²/day, %, m/s. They are not stored in
the runtime metadata; if that changes, update this file and the figure axis labels.

### CDL — expected

All `derived/tables/*_<year>_cdl.csv` files (long format). Required columns:

```text
field_id, year, crop_name, pct
```

Additional shipped columns (`crop_code`, `pixel_count`, `crop_source`) are preserved but
not required. Years are the inference unit; the subskill does not interpolate missing
years. A field missing a year that other fields have warns.

**Unclassified residual.** The per-year tables omit unclassified pixels, so `pct` sums
to slightly less than 100 (observed 96.9–99.96%). This is expected and is surfaced as
`latest_unclassified_pct` and drawn as the grey band in F4. It is not an error.

### Rotation context — optional

`derived/tables/*_crop_rotation.csv` is loaded if present and listed in the manifest
inputs, but the dominant sequence and diversity are recomputed from the CDL shares.

### Inventory — optional

`manifests/field-inventory.csv`, if present, is used only to cross-check field ids and is
listed as an input.

## Outputs

Default root: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/<run-id>/`.

### `tables/field-metrics.csv`

One row per field. Columns:

| Group | Columns |
| --- | --- |
| Identity | `grower_slug`, `grower_name`, `farm_slug`, `farm_name`, `state`, `county`, `field_id`, `csb_id`, `crop_2025` |
| Boundary | `area_ha`, `area_proj_ha`, `perimeter_m`, `compactness`, `vertices`, `multipart` |
| Rotation | `rotation_years`, `rotation_sequence`, `rotation_diversity`, `continuous_corn`, `latest_cdl_year`, `latest_crop`, `latest_purity_pct`, `latest_unclassified_pct`, `cdl_years_available` |
| Weather means | `season_precip_mm_mean`, `annual_precip_mm_mean`, `season_gdd_c_mean`, `season_mean_temp_c_mean`, `hot_days_mean`, `weather_years` |
| Sequence | `crop_<year>` for each CDL year (for example `crop_2019` … `crop_2023`) |

Notes:

- `area_ha` is the declared `area_ha_est`; `area_proj_ha` is measured in EPSG:5070.
  A >2% relative difference warns.
- `compactness` is `4πA/P²`, clipped to `[0, 1]`; square = `π/4`, circle = 1.
- `rotation_diversity` is Shannon over the dominant-crop sequence, `0` for a constant
  sequence.
- `crop_2025` is the boundary's current-crop attribute. In the Assignment 2 dataset it
  matches the 2023 CDL dominant crop on all 30 fields; it is not a CDL year and is
  deliberately excluded from the F3 heatmap.
- Weather means are computed over the field's available years (five in Assignment 2).

### `tables/stats-boundaries.csv`

Long result table with the shared schema:

```text
analysis, grouping, comparison, test, n, statistic, p_value, p_holm,
effect_size, effect_metric, median, q1, q3, min, max, significant, notes
```

Rows: per-grower area summaries (`analysis=describe`), a Kruskal–Wallis omnibus, and
pairwise Mann–Whitney contrasts with Holm-adjusted p-values.

### `tables/stats-cdl.csv`

Same schema. Rows: per-grower rotation-diversity summaries, continuous-corn counts and
shares, a Kruskal–Wallis omnibus, and pairwise Mann–Whitney contrasts.

### `tables/stats-weather.csv`

Same schema. Rows: pooled and per-grower Spearman correlations between season
precipitation and season GDD, plus between-grower variance shares for each variable on
farm-year means.

### `manifest.json`

- `run_id`, `generated_at`, `data_root`
- `growers[]`: slug, name, farm, field count, weather rows, CDL rows, CDL years
- `counts`: fields, growers, farms
- `outputs`: root, figure names, table names
- `warnings`: aggregated loader and analysis warnings, prefixed with the farm label
- `environment`: Python, platform, pandas, geopandas, matplotlib, scipy versions
- Input records per farm: relative path, bytes, UTC mtime, SHA-256

## Failure vs warning

Exit code 2 is reserved for an unusable runtime root, no matching farms, or a missing
required boundary/column. Everything else that is recoverable — a thin weather series, a
missing CDL year, an unclassified residual, an area mismatch — is written to the
manifest warnings and printed in the run summary so a reviewer can see it without
reading the code.
