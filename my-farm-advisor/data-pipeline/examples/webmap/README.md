# Grower web map — published example

Static copies of the grower-level interactive field map produced by
`../../src/scripts/webmap/generate_grower_webmap.py`, published so the map can be
opened from a URL instead of only from the local runtime.

```
output/
├── index.html                      hand-maintained landing page
├── ia-grower_grower_map.html       generated fixture, 3 fields / 1 farm
└── il-grower_grower_map.html       generated fixture, 3 fields / 1 farm
```

## Why these files are in Git

Repository policy permits generated output at exactly one location: small,
deterministic demonstration fixtures under `examples/**/output/`. These two
files qualify — each is a single self-contained HTML document in the tens of
KB, produced from the demo Illinois and Iowa farms in the local runtime, and
free of timestamps or other run-varying content.

## Redaction

The fixtures are generated with `--public-fixture`, which removes the four
properties that would tie a parcel to a real USDA record:

| Dropped | Kept |
|---|---|
| `csb_id`, `source`, `state_fips`, `county_fips` | geometry, `crop`, `area_acres`, `area_ha_est`, `county`, `county_name`, `state`, `country`, `year`, grower/farm/field names and colors |

Geometry is byte-identical to the runtime output and nothing the page displays
is lost — only the popup's boundary-source line and the parcel lookup go away.
The runtime copies under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/dashboards/`
keep every identifier for provenance, and the generator never writes a
`grower_webmap.json` manifest for a public fixture.

`src/scripts/tests/test_grower_webmap.py::test_public_fixture_drops_parcel_identifiers`
enforces this: it fails if a published copy gains one of the four keys, if
redaction changes geometry, or if it drops a property the page displays.

## Regenerating

Run from the runtime source copy (see `../../webmap/GUIDE.md` for the install
step), after any change to the template:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
repo=/path/to/my-farm-advisor-skills
for slug in il-grower ia-grower; do
  ./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py \
    --grower "$slug" --public-fixture \
    --out "$repo/my-farm-advisor/data-pipeline/examples/webmap/output/${slug}_grower_map.html"
done
```

`index.html` is not generated; update it by hand if a grower is added or
removed.

## Serving

The folder is designed to be deployed as a static site: set the service root to
this `output/` directory and serve it on port 80. Everything under the root is
public, so the root must be this folder — not `examples/`, not
`data-pipeline/`, and not the repository root.

The page loads Leaflet from unpkg and basemap tiles from Esri/OSM at view time;
the container itself needs no outbound network and no build step.