# Webmap Local Instructions

## Purpose

This folder owns the grower-level interactive web map: one self-contained HTML
file per grower, built from the runtime field boundaries.

## Safe edit scope

Edits stay in this folder and `../src/scripts/webmap/` (plus its test). Do not
wire the generator into `run_farm_pipeline.py`, and do not change parent
`SKILL.md`, sibling workflows, or root policy from a webmap task.

## Read nearby docs first

Read `GUIDE.md` first. For the runtime contract, provenance `*_rel` rule, and
install flow, read `../AGENTS.md`. For the repository's existing Leaflet and
figure conventions, read `../../admin/interactive-web-map/GUIDE.md` and
`../references/basemap.md`.

## Local delta from the parent contract

- The generator is **standalone**. It runs after the pipeline, never as a
  pipeline step, and must not download tiles or rasters: basemap tiles are
  fetched by the viewer's browser.
- Output goes to `growers/<grower>/derived/dashboards/<grower>_grower_map.html`
  with a sibling `growers/<grower>/manifests/grower_webmap.json`. Keep both out
  of Git; they are runtime artifacts. The single sanctioned exception is a
  `--public-fixture` copy under `examples/webmap/output/`, which carries no
  manifest and no parcel identifiers — see `GUIDE.md`.
- Provenance uses `path_rel` only (root-relative against
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`). Never write absolute runtime
  paths into the HTML or the manifest — the test asserts this.
- stdlib only. Do not add folium, jinja2, geopandas, or a tile cache to this
  path; the page embeds GeoJSON and lets Leaflet do the rest.
- The embedded GeoJSON is the pipeline's boundary file unchanged apart from
  coordinate rounding and the added display properties. Re-derive geometry by
  re-running the pipeline, not by editing the HTML.

## Working in the runtime

`install.sh` copies `src/scripts/**` into the runtime, so a generator edit is
only visible after an install (or a manual copy) into
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/webmap/`. Run the script
from that copy with the runtime venv:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
DATA_PIPELINE_DATA_ROOT="$DATA_PIPELINE_DATA_ROOT" ./scripts/install.sh \
  --non-interactive --force-refresh --no-install-deps --persist none
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py --all-growers
```

## Local validation

```bash
python3 -m pytest src/scripts/tests/test_grower_webmap.py -q
```

Then `./scripts/validate.sh` from the repository root for structural changes.
If the template, palette, or popup layout changed, open a generated HTML in a
browser — structural asserts do not cover appearance.
