# Field EDA Examples

This subskill has one runnable example: the Assignment 2 field EDA over three demo
growers. The figures are generated into the runtime and are **not committed here**; the
repository asset policy keeps generated outputs out of Git until a release asks for a
reviewed gallery.

## Prerequisites

A built runtime at `~/my-farm-advisor-runtime` containing:

- `data-pipeline/growers/il-grower/farms/illinois-demo-farm/`
- `data-pipeline/growers/ia-grower/farms/iowa-demo-farm/`
- `data-pipeline/growers/ne-grower/farms/nebraska-demo-farm/`

Each farm needs boundaries, daily weather 2021–2025, and CDL 2019–2023. See
[`../../../data-pipeline/references/assignment-2-dataset-expansion.md`](../../../data-pipeline/references/assignment-2-dataset-expansion.md)
for the dataset runbook and the weather-cache caveat.

## Reproduce

```bash
cd /path/to/my-farm-advisor-skills
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"

P="$HOME/my-farm-advisor-runtime/data-pipeline/.venv/bin/python"
$P my-farm-advisor/eda/field-eda/run_field_eda.py --dry-run
$P my-farm-advisor/eda/field-eda/run_field_eda.py
```

## Expected dry-run output

```text
farms loaded: 3
grower         farm                     fields  weather rows  cdl years
il-grower      illinois-demo-farm           10         18260  2019-2023
ia-grower      iowa-demo-farm               10         18260  2019-2023
ne-grower      nebraska-demo-farm           10         18260  2019-2023
fields: 30 | field-years: 150 | out: (dry run)
```

Three expected warnings, one per farm, say the CDL tables omit unclassified pixels and
report the residual range. They are informational, not failures.

## Expected full-run output

`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/<run-id>/` with 7 figures,
4 tables, and `manifest.json`:

```text
figures/F1-boundaries-area-by-grower.png
figures/F2-boundaries-shape-vs-area.png
figures/F3-cdl-rotation-heatmap.png
figures/F4-cdl-composition.png
figures/F5-weather-climatology.png
figures/F6-weather-precip-vs-gdd.png
figures/F7-geospatial-field-map.png
tables/field-metrics.csv
tables/stats-boundaries.csv
tables/stats-cdl.csv
tables/stats-weather.csv
manifest.json
```

## Verify a run

```bash
run="$HOME/my-farm-advisor-runtime/data-pipeline/eda/field-eda/<run-id>"
$P - "$run" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text())
assert manifest["counts"] == {"fields": 30, "growers": 3, "farms": 3}
assert len(manifest["outputs"]["figures"]) == 7
assert len(manifest["outputs"]["tables"]) == 4
for name in manifest["outputs"]["figures"]:
    assert (root / "figures" / name).stat().st_size > 0, name
print("ok")
PY
```

The reviewed result snapshot lives in
[`../references/statistics.md`](../references/statistics.md); if a rerun changes those
numbers, update that file and say why.

## Figure review

Before publishing any of these figures, inspect them with vision against the five-point
gate and record the verdict in the commit message. The per-figure verdicts for this
example are in [`../references/figure-specs.md`](../references/figure-specs.md).
