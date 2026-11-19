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
        ids = [f["properties"]["field_id"] for f in payload["features"]]
        assert sorted(ids) == sorted(BOXES), f"field IDs not all embedded: {ids}"

        props = payload["features"][0]["properties"]
        assert props["grower_name"] == "Test Grower"
        assert props["farm_name"] in {farm["display_name"] for farm in FARMS.values()}
        assert props["field_name"]

        # Coordinates are rounded, so the page stays small and diffable.
        for feature in payload["features"]:
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
    test_grower_without_boundaries_fails_loudly()
    print("ok: grower webmap regression checks passed")
