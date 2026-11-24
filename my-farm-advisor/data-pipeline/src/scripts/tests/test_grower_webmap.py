"""Regression test for the grower-level interactive web map.

The generator embeds real field geometry into a single HTML file plus a
provenance manifest. Three things can silently break and are cheap to assert:

* the page loses the satellite basemap or the Leaflet CDN and renders as a
  blank rectangle;
* a field disappears from the page (or its popup metadata stops being emitted)
  because a boundary/field.json lookup changed shape;
* an absolute runtime path leaks into a committed-adjacent artifact, which
  breaks the repository's portable-provenance contract.

Bug history: field names live in ``fields/<slug>/field.json`` while the
boundary GeoJSON only carries ``field_id``; a naive join lost the display name,
so the popup showed the ID twice.

Written as plain asserts so it runs under pytest *and* directly:

    python my-farm-advisor/data-pipeline/src/scripts/tests/test_grower_webmap.py

No network, no fixtures on disk: the runtime is built in a temp directory.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "webmap"))

import generate_grower_webmap as webmap  # noqa: E402

GROWER = "test-grower"
FARMS = {
    "north-farm": {
        "display_name": "North Test Farm",
        "state": "IL",
        "fields": {
            "n-1": {"display_name": "North One", "crop": "Corn", "area_acres": 120.5},
            "n-2": {"display_name": "North Two", "crop": "Soybean", "area_acres": 80.25},
        },
    },
    "south-farm": {
        "display_name": "South Test Farm",
        "state": "IA",
        "fields": {
            # Multipolygon on purpose: exercises the bounds walk and the
            # round-coordinate path for nested rings.
            "s-1": {"display_name": "South One", "crop": "Corn", "area_acres": 200.0},
            "s-2": {"display_name": "South Two", "crop": "Alfalfa", "area_acres": 45.0},
        },
    },
}

# Field-local boxes around Iroquois County, IL. Values carry more than six
# decimals so the test can prove rounding actually happened.
BOXES = {
    "n-1": (-87.700123456789, 40.700987654321, -87.698012345678, 40.702),
    "n-2": (-87.695111111111, 40.700111111111, -87.693, 40.701999999999),
    "s-1": (-87.700123456789, 40.690987654321, -87.698, 40.692),
    "s-2": (-87.695111111111, 40.690111111111, -87.693, 40.691999999999),
}


def _polygon(box, multi: bool = False) -> dict:
    west, south, east, north = box
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    if multi:
        return {"type": "MultiPolygon", "coordinates": [[ring]]}
    return {"type": "Polygon", "coordinates": [ring]}


def _build_runtime(root: Path) -> Path:
    data_root = root / "data-pipeline"
    grower_root = data_root / "growers" / GROWER
    grower_root.mkdir(parents=True)
    (grower_root / "grower.json").write_text(
        json.dumps({"grower_slug": GROWER, "display_name": "Test Grower"}),
        encoding="utf-8",
    )

    for farm_slug, farm in FARMS.items():
        farm_root = grower_root / "farms" / farm_slug
        (farm_root / "boundary").mkdir(parents=True)
        (farm_root / "farm.json").write_text(
            json.dumps(
                {
                    "farm_slug": farm_slug,
                    "display_name": farm["display_name"],
                    "state": farm["state"],
                }
            ),
            encoding="utf-8",
        )

        features = []
        for field_id, meta in farm["fields"].items():
            geometry = _polygon(BOXES[field_id], multi=(field_id == "s-1"))
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "field_id": field_id,
                        "state": farm["state"],
                        "county": "Iroquois" if farm["state"] == "IL" else "Kossuth",
                        "crop": meta["crop"],
                        "area_acres": meta["area_acres"],
                        "source": "test_fixture",
                        # Parcel-identifying attributes: runtime output keeps
                        # them, a published fixture must not.
                        "csb_id": f"17{field_id}000000000",
                        "state_fips": "17",
                        "county_fips": "075",
                    },
                    "geometry": geometry,
                }
            )

            field_dir = farm_root / "fields" / field_id
            field_dir.mkdir(parents=True)
            (field_dir / "field.json").write_text(
                json.dumps(
                    {
                        "grower_slug": GROWER,
                        "farm_slug": farm_slug,
                        "field_slug": field_id,
                        "field_id": field_id,
                        "display_name": meta["display_name"],
                    }
                ),
                encoding="utf-8",
            )

        (farm_root / "boundary" / "field_boundaries.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8",
        )

    return data_root


def _inline_payload(document: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="map-data">(.*?)</script>',
        document,
        re.DOTALL,
    )
    assert match, "inline map-data JSON block is missing"
    return json.loads(match.group(1))


def _inline_script(document: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", document, re.DOTALL)
    assert scripts, "inline map script is missing"
    return scripts[-1]


def _decimals(value) -> int:
    text = repr(float(value))
    return len(text.split(".")[1].rstrip("0")) if "." in text else 0


def test_grower_map_renders_every_field_and_is_portable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_root = _build_runtime(Path(tmp))
        manifest = webmap.write_grower_map(data_root, GROWER)

        html_path = data_root / "growers" / GROWER / "derived" / "dashboards" / f"{GROWER}_grower_map.html"
        assert html_path.is_file(), "grower map HTML was not written to the contract path"
        document = html_path.read_text(encoding="utf-8")

        # Basemap and viewer must actually be there.
        assert webmap.ESRI_TILES in document, "Esri World Imagery template missing"
        assert "World_Imagery" in document
        assert webmap.OSM_TILES in document, "OSM streets fallback missing"
        assert "unpkg.com/leaflet@1.9.4/dist/leaflet.css" in document
        assert "unpkg.com/leaflet@1.9.4/dist/leaflet.js" in document
        assert "L.tileLayer" in document and "L.geoJSON" in document
        assert "L.control.layers" in document, "basemap toggle missing"

        # Required popup metadata: grower, farm, field name.
        for label in ("Grower", "Farm", "Field ID"):
            assert f'row("{label}"' in document, f"popup row missing: {label}"
        for farm in FARMS.values():
            assert farm["display_name"] in document, "farm display name missing from page"
            for meta in farm["fields"].values():
                assert meta["display_name"] in document, "field display name missing from page"

        payload = _inline_payload(document)
        # The page reads these four keys directly. Embedding only the
        # FeatureCollection (the original bug) leaves data.fields undefined,
        # so no polygon is drawn and data.farms.forEach throws — a blank map
        # with an empty sidebar.
        for key in ("grower", "farms", "fields", "bounds"):
            assert key in payload, f"inline payload is missing {key!r}; the page reads data.{key}"
        assert payload["fields"]["type"] == "FeatureCollection"
        assert payload["grower"]["name"] == "Test Grower"
        assert payload["bounds"] and len(payload["bounds"]) == 2

        # Contract sweep: every data.<key> the inline script touches must be
        # embedded, so a future template edit cannot outrun the payload.
        referenced = set(re.findall(r"\bdata\.([A-Za-z_]\w*)", _inline_script(document)))
        missing = sorted(referenced - set(payload))
        assert not missing, f"inline script reads keys the payload does not carry: {missing}"

        ids = [f["properties"]["field_id"] for f in payload["fields"]["features"]]
        assert sorted(ids) == sorted(BOXES), f"field IDs not all embedded: {ids}"

        props = payload["fields"]["features"][0]["properties"]
        assert props["grower_name"] == "Test Grower"
        assert props["farm_name"] in {farm["display_name"] for farm in FARMS.values()}
        assert props["field_name"]

        # Coordinates are rounded, so the page stays small and diffable.
        for feature in payload["fields"]["features"]:
            stack = [feature["geometry"]["coordinates"]]
            while stack:
                node = stack.pop()
                if isinstance(node, (int, float)):
                    assert _decimals(node) <= webmap.DEFAULT_PRECISION, (
                        "coordinate was not rounded to the configured precision"
                    )
                elif isinstance(node, list):
                    stack.extend(node)

        # Lightweight output: geometry only, no rasters or bundles.
        assert len(document.encode("utf-8")) < 300 * 1024, "grower map is too large to be lightweight"

        # Portability: no absolute runtime path in either artifact.
        assert str(data_root) not in document
        assert "/home/" not in document
        manifest_text = (
            data_root / "growers" / GROWER / "manifests" / "grower_webmap.json"
        ).read_text(encoding="utf-8")
        assert str(data_root) not in manifest_text
        assert "/home/" not in manifest_text

        on_disk = json.loads(manifest_text)
        assert on_disk["fields"] == len(BOXES)
        assert on_disk["farms"] == len(FARMS)
        assert on_disk["html"]["path_rel"] == f"growers/{GROWER}/derived/dashboards/{GROWER}_grower_map.html"
        assert on_disk["html"]["bytes"] == len(document.encode("utf-8"))
        assert on_disk["basemap"]["url_template"] == webmap.ESRI_TILES
        sources = {entry["path_rel"] for entry in on_disk["sources"]}
        assert f"growers/{GROWER}/grower.json" in sources
        for farm_slug in FARMS:
            assert f"growers/{GROWER}/farms/{farm_slug}/farm.json" in sources
            assert (
                f"growers/{GROWER}/farms/{farm_slug}/boundary/field_boundaries.geojson"
                in sources
            )
        assert all(len(entry["sha256"]) == 64 for entry in on_disk["sources"])

        # Same input, same manifest payload: reruns are deterministic apart
        # from the timestamp.
        first = on_disk["sources"]
        webmap.write_grower_map(data_root, GROWER)
        second = json.loads(manifest_text)["sources"]
        assert first == second
        assert manifest["grower_slug"] == GROWER


NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");

const jsonMatch = html.match(/<script type="application\/json" id="map-data">([\s\S]*?)<\/script>/);
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].pop()[1];
const payload = JSON.parse(jsonMatch[1]);

const result = {
  threw: null,
  keys: Object.keys(payload),
  geoType: null,
  featureCount: 0,
  buttons: 0,
  bounds: null,
};
const buttons = [];
let geoArg = null;

function element(tag) {
  const el = {
    tagName: tag,
    style: {},
    className: "",
    textContent: "",
    children: [],
    appendChild(child) { this.children.push(child); },
    addEventListener() {},
    type: "",
  };
  if (tag === "button") buttons.push(el);
  return el;
}

const map = {
  options: {},
  fitBounds(bounds) { result.bounds = bounds; },
  closePopup() {},
};
const chain = () => ({ addTo() { return this; } });

global.document = {
  getElementById(id) {
    return id === "map-data" ? { textContent: jsonMatch[1] } : element("div");
  },
  createElement: element,
  createTextNode(text) { return { nodeValue: text }; },
};

global.L = {
  map: () => map,
  tileLayer: () => chain(),
  control: { layers: () => chain(), scale: () => chain() },
  geoJSON: (arg) => { geoArg = arg; return chain(); },
};

try {
  vm.runInThisContext(script);
} catch (error) {
  result.threw = error.constructor.name + ": " + error.message;
}

result.geoType = geoArg && geoArg.type;
result.featureCount = geoArg && Array.isArray(geoArg.features) ? geoArg.features.length : 0;
result.buttons = buttons.length;
console.log(JSON.stringify(result));
"""


def test_inline_script_draws_fields_with_stub_leaflet() -> None:
    """Execute the page's own script so a data/template mismatch fails here.

    Structural asserts cannot see ``TypeError: ... reading 'forEach'`` — the
    original bug passed every string check while rendering nothing. This runs
    the inline script against a stub Leaflet/DOM: fields must reach
    ``L.geoJSON`` as a FeatureCollection and one sidebar button per field must
    be created.
    """
    if shutil.which("node") is None:
        print("    skip  node not available; inline-script execution check skipped")
        return

    with tempfile.TemporaryDirectory() as tmp:
        data_root = _build_runtime(Path(tmp))
        webmap.write_grower_map(data_root, GROWER)
        html_path = (
            data_root / "growers" / GROWER / "derived" / "dashboards"
            / f"{GROWER}_grower_map.html"
        )
        harness = Path(tmp) / "harness.js"
        harness.write_text(NODE_HARNESS, encoding="utf-8")

        proc = subprocess.run(
            ["node", str(harness), str(html_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"node harness failed: {proc.stderr.strip()}"
        result = json.loads(proc.stdout.strip().splitlines()[-1])

        assert result["threw"] is None, f"inline script threw at load: {result['threw']}"
        assert set(result["keys"]) >= {"grower", "farms", "fields", "bounds"}
        assert result["geoType"] == "FeatureCollection", (
            f"L.geoJSON received {result['geoType']!r}; the payload shape is wrong"
        )
        assert result["featureCount"] == len(BOXES), (
            f"only {result['featureCount']}/{len(BOXES)} fields reached the map layer"
        )
        assert result["buttons"] == len(BOXES), (
            f"sidebar built {result['buttons']}/{len(BOXES)} field buttons"
        )
        assert result["bounds"] and len(result["bounds"]) == 2, "map never fitted to the fields"


def test_public_fixture_drops_parcel_identifiers() -> None:
    """A published copy must not carry USDA parcel identifiers.

    ``csb_id`` resolves the same parcel in USDA's public browser, so shipping it
    in a committed fixture attributes the demo to a specific real field. Runtime
    output keeps every identifier for provenance; only the published copy is
    minimized, and it must stay visually identical — same geometry, same
    displayed properties.
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_root = _build_runtime(Path(tmp))
        webmap.write_grower_map(data_root, GROWER)
        runtime = _inline_payload(
            (
                data_root / "growers" / GROWER / "derived" / "dashboards"
                / f"{GROWER}_grower_map.html"
            ).read_text(encoding="utf-8")
        )

    with tempfile.TemporaryDirectory() as tmp:
        data_root = _build_runtime(Path(tmp))
        out = Path(tmp) / "published_grower_map.html"
        webmap.write_grower_map(data_root, GROWER, out_path=out, public_fixture=True)
        published = _inline_payload(out.read_text(encoding="utf-8"))

        # A fixture is one self-contained file, not a provenance record.
        manifest = data_root / "growers" / GROWER / "manifests" / "grower_webmap.json"
        assert not manifest.exists(), "a published fixture must not write a runtime manifest"

    assert webmap.PUBLIC_FIXTURE_DROP, "redaction list must not be empty"
    for key in webmap.PUBLIC_FIXTURE_DROP:
        assert key in runtime["fields"]["features"][0]["properties"], (
            f"test fixture lacks {key!r}; the redaction assertion would be vacuous"
        )
        assert key not in published["fields"]["features"][0]["properties"], (
            f"published fixture still carries {key!r}"
        )

    # Everything the page draws or prints survives the redaction.
    runtime_props = runtime["fields"]["features"][0]["properties"]
    published_props = published["fields"]["features"][0]["properties"]
    for key in ("field_id", "field_name", "farm_name", "farm_slug",
                "grower_name", "crop", "area_acres", "county", "state"):
        assert published_props.get(key) == runtime_props.get(key), (
            f"redaction changed {key!r}, which the map displays"
        )
    assert published["bounds"] == runtime["bounds"]
    assert published["farms"] == runtime["farms"]

    # Geometry and every other property are untouched: only the four keys go.
    assert len(published["fields"]["features"]) == len(runtime["fields"]["features"])
    for before, after in zip(runtime["fields"]["features"], published["fields"]["features"]):
        assert after["geometry"] == before["geometry"], "redaction altered geometry"
        dropped = set(before["properties"]) - set(after["properties"])
        assert dropped <= set(webmap.PUBLIC_FIXTURE_DROP), (
            f"redaction dropped unexpected properties: {sorted(dropped)}"
        )


def test_grower_without_boundaries_fails_loudly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp) / "data-pipeline"
        (data_root / "growers" / "empty-grower").mkdir(parents=True)
        try:
            webmap.write_grower_map(data_root, "empty-grower")
        except SystemExit as exc:
            assert "no field polygons" in str(exc)
        else:  # pragma: no cover - would mean a silent empty page
            raise AssertionError("empty grower should raise SystemExit, not write a blank map")


if __name__ == "__main__":
    test_grower_map_renders_every_field_and_is_portable()
    test_inline_script_draws_fields_with_stub_leaflet()
    test_public_fixture_drops_parcel_identifiers()
    test_grower_without_boundaries_fails_loudly()
    print("ok: grower webmap regression checks passed")
