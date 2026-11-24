# Grower-Level Interactive Web Map

Build one lightweight, self-contained HTML map per grower from the field
boundaries the data pipeline already wrote. The page loads Leaflet from a CDN,
draws **Esri World Imagery** underneath the real polygons, and lists every
farm and field in a sidebar that zooms and opens the popup on click.

The generator is `../src/scripts/webmap/generate_grower_webmap.py`. It is
standalone: it is not a step in `run_farm_pipeline.py`, it never downloads
imagery, and it adds no Python dependency (stdlib only).

## Why this exists

The pipeline produces per-field posters, per-farm reports, and raster products,
but nothing that answers "show me every field this grower has, on a satellite
view, in one file I can open in a browser". This subskill is that view. It
embeds geometry only, so the artifact stays small enough to email or drop on a
shared drive while tiles stream from the internet.

## Inputs (runtime, written by the pipeline)

```
growers/<grower>/grower.json
growers/<grower>/farms/<farm>/farm.json
growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson   # required
growers/<grower>/farms/<farm>/fields/<field>/field.json           # display names
```

Any number of farms per grower and fields per farm is supported; farms with no
boundary GeoJSON are skipped with a message rather than failing the run.

## Outputs

```
growers/<grower>/derived/dashboards/<grower>_grower_map.html
growers/<grower>/manifests/grower_webmap.json
```

The manifest records the HTML path and size, field/farm counts, the basemap
URL templates, the coordinate precision, and a sha256 for every source file.
Paths use the repository `*_rel` convention, keyed against
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline`, so the manifest stays portable.

## Run it

Run from the runtime source copy, per the data-pipeline contract:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py --all-growers
```

Single grower, or an explicit destination:

```bash
./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py --grower il-grower
./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py \
  --grower il-grower --out /tmp/il.html --precision 5
```

| flag | default | purpose |
|---|---|---|
| `--grower <slug>` | `AG_GROWER_SLUG` | one grower |
| `--all-growers` | off | every grower with a farm boundary |
| `--out <path>` | contract path above | single-grower override |
| `--precision <n>` | `6` | coordinate decimals (~0.1 m) |
| `--max-kb <n>` | `512` | warn (do not truncate) above this size |
| `--data-root <path>` | `DATA_PIPELINE_DATA_ROOT` | runtime root; `…/data-pipeline` is appended when present |
| `--public-fixture` | off | drop parcel identifiers and skip the manifest, for a copy meant to be committed |

## What the page does

- **Satellite by default.** Esri World Imagery tiles, no key, same URL class as
  `src/scripts/lib/basemap.py`. A Streets (OpenStreetMap) layer is available
  from the layer control.
- **All fields, colored per farm.** Each farm gets one color from a fixed
  palette, reused cyclically past eight farms.
- **Click a field** for grower, farm, field name, field ID, crop, area, county,
  state, and boundary source. Values are HTML-escaped before insertion.
- **Sidebar list** grouped by farm with acreage; clicking a row fits the map to
  that field and opens its popup. "Zoom to all fields" resets the view.
- **Pan, zoom, scale bar** from Leaflet; the initial view is the union of all
  field bounds.

Custom raster overlays or improved geometry would require re-running the data
pipeline; this page deliberately shows the boundary file as written.

## Size and network expectations

Fields are embedded as JSON (6-decimal coordinates) inside
`<script type="application/json">`, alongside the grower, farm, and view-bounds
metadata the page reads, and parsed with `JSON.parse`, so there is no
JS-literal escaping to get wrong. A six-field grower lands in the tens of KB.
Tiles and the Leaflet 1.9.4 bundle are fetched by the browser at view time —
an offline viewer sees the sidebar and field outlines but gray basemap.

## Publishing a copy (example fixture)

A copy meant to be committed and served publicly is generated with
`--public-fixture`, which:

- removes `csb_id`, `source`, `state_fips`, and `county_fips` from every
  feature's properties — the identifiers that would let a reader resolve the
  parcel in USDA's own public browser. Geometry, crop, acreage, county/state
  name, and the farm and grower labels are unchanged, so the page renders and
  reads exactly the same;
- skips the runtime manifest, so the artifact is one self-contained file rather
  than a provenance record.

Repository policy permits generated output at exactly one location, so a
published copy belongs under `examples/webmap/output/`:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
for slug in il-grower ia-grower; do
  ./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py \
    --grower "$slug" --public-fixture \
    --out <repo>/my-farm-advisor/data-pipeline/examples/webmap/output/${slug}_grower_map.html
done
```

The runtime output at the contract path keeps every identifier; only the
published copy is minimized. Re-run this after any template change so the
fixture cannot drift from the generator.

## Verification

`../src/scripts/tests/test_grower_webmap.py` builds a throwaway runtime and
asserts the basemap and CDN URLs, the presence of every field ID, grower/farm/
field names, popup field labels, 6-decimal coordinates, the `< 300 KB`
ceiling, a correct `path_rel` in the manifest, and that no absolute runtime
path leaks into either file. It also executes the inline script under Node
against a stub Leaflet, and checks that a `--public-fixture` copy drops exactly
the four parcel identifiers while leaving geometry and displayed properties
untouched.

```bash
cd my-farm-advisor/data-pipeline
python3 -m pytest src/scripts/tests/test_grower_webmap.py -q
```

Structural checks cannot prove the map *looks* right. Open the generated HTML
in a browser after a run if the change touched the template, the palette, or
the popup content.
