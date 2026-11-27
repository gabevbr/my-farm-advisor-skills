# Assignment 2 dataset expansion (2026-11)

Expands the Assignment 1 runtime from two 3-field farms to three 10-field farms:

| Grower | Farm | State | County (FIPS) | Fields |
| --- | --- | --- | --- | --- |
| `il-grower` | `illinois-demo-farm` | IL | Iroquois (17075) | 10 (`il-r1..il-r10`) |
| `ia-grower` | `iowa-demo-farm` | IA | Kossuth (19109) | 10 (`ia-r1..ia-r10`) |
| `ne-grower` | `nebraska-demo-farm` | NE | York (31185) | 10 (`ne-r1..ne-r10`) |

Boundaries are real USDA Crop Sequence Boundaries (CSB) via the FIBOA
`us-usda-cropland` GeoParquet; the boundary contract is in
[`field-boundary-sources.md`](field-boundary-sources.md).

## Why York County, Nebraska

York County is south-central Nebraska in the Upper Big Blue Natural Resources
District — the most heavily groundwater-irrigated district in the state, with
over 1,000,000 acres under center-pivot systems. The NASS 2022 Census county
profile lists **254,793 irrigated acres, 73 % of land in farms**, and the CSB
extract is dominated by Corn/Soybeans. The bbox holds 1,052 CSB fields
≥ 40 ha, so ten large fields are available without leaving the county.

Caveat: CSB boundaries are field blocks, not pivot circles; center-pivot is a
county characteristic, not a boundary shape. Alternatives if the profile needs
to change: Hamilton (235,849 irrigated acres, 79 %), Merrick, Adams, Clay.

## County and state guards (why they exist)

The CSB extractor filters by bbox only. County bboxes overlap neighbours, and
an unfiltered top-10 pulls in foreign fields that the seed step would then
mislabelled as the target county:

- IL top-10: one Ford County field at rank 8.
- IA top-10: one Humboldt County field at rank 10; 31 fields in the Kossuth
  bbox carry a non-Iowa state prefix (Faribault/Martin, MN).
- NE top-10: one Clay County field at rank 10.

`download_csb_fields.py` therefore takes `--county-name` (matches CSB
`administrative_area_level_2`, case-insensitive) and `--state-fips` (matches
the CSB id prefix). Both are recorded in the provenance manifest.

## Procedure

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
R="$DATA_PIPELINE_DATA_ROOT/data-pipeline"
ROOT="$DATA_PIPELINE_DATA_ROOT"

# 1. Stage boundaries only (sequential, minutes each). The seed helper
#    aborts if an existing field's csb_id would change.
"$R/.venv/bin/python" "$ROOT/tools/seed_farm_csb.py" \
  --state Illinois --grower il-grower --farm illinois-demo-farm \
  --farm-name "Illinois Demo Farm" --fields 10 \
  --county-fips 17075 --county-name Iroquois --state-fips 17 \
  --bbox 40.485568 -88.131935 41.010341 -87.525661 --boundaries-only

"$R/.venv/bin/python" "$ROOT/tools/seed_farm_csb.py" \
  --state Iowa --grower ia-grower --farm iowa-demo-farm \
  --farm-name "Iowa Demo Farm" --fields 10 \
  --county-fips 19109 --county-name Kossuth --state-fips 19 \
  --bbox 42.907762 -94.443289 43.500468 -93.970201 --boundaries-only

"$R/.venv/bin/python" "$ROOT/tools/seed_farm_csb.py" \
  --state Nebraska --grower ne-grower --farm nebraska-demo-farm \
  --farm-name "Nebraska Demo Farm" --fields 10 \
  --county-fips 31185 --county-name York --state-fips 31 \
  --bbox 40.6985 -97.8263 41.0470 -97.3681 --boundaries-only
```

```bash
# 2. Full pipeline per farm, farms in parallel, detached.
mkdir -p "$ROOT/logs/assignment-2"
cd "$R"
for farm in "il-grower illinois-demo-farm Illinois Demo Farm" \
            "ia-grower iowa-demo-farm Iowa Demo Farm" \
            "ne-grower nebraska-demo-farm Nebraska Demo Farm"; do
  read -r grower slug name <<< "$farm"
  setsid nohup "$R/.venv/bin/python" src/scripts/run_farm_pipeline.py \
    --boundaries "$R/growers/$grower/farms/$slug/boundary/field_boundaries.geojson" \
    --grower-slug "$grower" --farm-slug "$slug" --farm-name "$name" \
    --inventory-csv "$R/growers/$grower/farms/$slug/manifests/field-inventory.csv" \
    --skip-field-sampling \
    > "$ROOT/logs/assignment-2/$grower.log" 2>&1 &
done
wait
```

```bash
# 3. Verify EDA layers + webmaps.
"$R/.venv/bin/python" "$ROOT/tools/verify_runtime.py"
"$R/.venv/bin/python" "$R/src/scripts/webmap/generate_grower_webmap.py" --all-growers
```

## Scope and verification

Assignment 2 EDA focuses on **field boundaries, weather, and CDL/cropland**.
Soil outputs are produced by the standard pipeline but are **not analyzed**;
no SDA/gNATSGO fallback is chased. Acceptance checks:

- Boundaries: 10 inventory rows per farm; every feature in the target county;
  correct `state_fips`/`county_fips`; stable `csb_id` for the Assignment 1
  fields.
- Weather: 2021–2025 per field (`fields/<field>/weather/`, farm
  `derived/tables/<farm>_weather_*.csv`).
- CDL: 2019–2023 per field plus `*_crop_rotation.csv` and
  `*_cdl_*_full_composition.csv`; `shared/cdl/rasters/CDL_*_31.tif` cached for
  Nebraska.
- Grower webmaps for all three growers; `verify_runtime.py` clean.

## Durability

Boundaries, weather, CDL, and shared caches are written under
`${DATA_PIPELINE_DATA_ROOT}`; a session timeout loses only the in-flight step.
Boundary staging is idempotent (merge by `field_id`), imagery skips reusable
manifests, and posters are cached by input fingerprint. Re-run the interrupted
farm/step; use `AG_FORCE=1` only for code changes.
