#!/usr/bin/env python3
"""Grower-level interactive web map from the pipeline's own field boundaries.

One self-contained HTML file per grower: Leaflet from a CDN, Esri World Imagery
tiles underneath, and the real farm boundary GeoJSON embedded inline. No raster
bundles, no exported tiles, no new Python dependency.

Inputs (runtime, written by the pipeline):

    growers/<grower>/grower.json
    growers/<grower>/farms/<farm>/farm.json
    growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson
    growers/<grower>/farms/<farm>/fields/<field>/field.json   (display names)

Outputs:

    growers/<grower>/derived/dashboards/<grower>_grower_map.html
    growers/<grower>/manifests/grower_webmap.json

Usage (run from the runtime source copy per the data-pipeline contract):

    export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
    ./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py --grower il-grower
    ./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py --all-growers

Publishing a copy as a repository example fixture (one file, no manifest):

    ./.venv/bin/python src/scripts/webmap/generate_grower_webmap.py \
        --grower il-grower --public-fixture --out <repo>/examples/webmap/output/il-grower_grower_map.html

``--public-fixture`` drops the properties that tie a parcel to a real USDA
record (``csb_id``, ``source``, ``state_fips``, ``county_fips``). Runtime output
keeps them; only the published copy is minimized.

The basemap needs internet (it is fetched by the browser, not this script).
Field geometry plus its farm metadata is all that is embedded, so the HTML
stays in the tens of KB.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX_KB = 512
DEFAULT_PRECISION = 6  # ~0.1 m at the equator; invisible at field scale
ESRI_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery"
    "/MapServer/tile/{z}/{y}/{x}"
)
OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ATTRIBUTION = (
    "Imagery \u00a9 Esri, Maxar, Earthstar Geographics | "
    "Boundaries: USDA CSB via My Farm Advisor"
)
PALETTE = [
    "#2563eb", "#dc2626", "#059669", "#d97706",
    "#7c3aed", "#0891b2", "#be185d", "#4d7c0f",
]
# Parcel-identifying properties that stay in runtime output but never ship in a
# published fixture: ``csb_id`` resolves the same parcel in USDA's public
# browser, and the FIPS pair narrows it to a county. The map renders and reads
# identically without them; only the popup's source line loses detail.
PUBLIC_FIXTURE_DROP = ("csb_id", "source", "state_fips", "county_fips")

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root { --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --panel:#f8fafc; }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; }
  body { font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color:var(--ink); background:#e5e7eb; }
  #app { display:flex; height:100%; }
  #sidebar { width:320px; min-width:260px; height:100%; overflow-y:auto;
             background:#fff; border-right:1px solid var(--line); padding:16px; }
  #sidebar header h1 { margin:0 0 2px; font-size:17px; letter-spacing:-0.01em; }
  #sidebar header p { margin:0 0 14px; color:var(--muted); font-size:12px; }
  #fit-all { width:100%; padding:7px 10px; margin-bottom:14px; border:1px solid var(--line);
             border-radius:6px; background:var(--panel); color:var(--ink); font:inherit; cursor:pointer; }
  #fit-all:hover { background:#eef2f7; }
  .farm { margin-bottom:16px; }
  .farm h2 { margin:0 0 2px; font-size:13px; display:flex; align-items:center; gap:7px; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; flex:0 0 auto; }
  .farm-meta { margin:0 0 8px; color:var(--muted); font-size:11px; }
  .field-row { display:flex; justify-content:space-between; gap:8px; width:100%;
               padding:6px 8px; margin-bottom:3px; border:1px solid transparent; border-radius:5px;
               background:none; color:var(--ink); font:inherit; font-size:13px; text-align:left; cursor:pointer; }
  .field-row:hover { background:var(--panel); border-color:var(--line); }
  .field-row .acres { color:var(--muted); font-size:12px; white-space:nowrap; }
  #map { flex:1 1 auto; height:100%; }
  .pop h3 { margin:0 0 6px; font-size:15px; }
  .kv { display:flex; justify-content:space-between; gap:12px; padding:1px 0; font-size:12px; }
  .kv span:first-child { color:var(--muted); }
  .kv span:last-child { text-align:right; }
  .leaflet-control-attribution { font-size:10px; }
  @media (max-width:720px) {
    #app { flex-direction:column; }
    #sidebar { width:100%; height:44%; border-right:none; border-bottom:1px solid var(--line); }
    #map { height:56%; }
  }
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <header>
      <h1>{{GROWER_NAME}}</h1>
      <p>{{SUBTITLE}}</p>
    </header>
    <button id="fit-all" type="button">Zoom to all fields</button>
    <div id="field-list"></div>
    <p class="farm-meta" style="margin-top:18px">{{ATTRIBUTION}}</p>
  </aside>
  <main id="map" role="application" aria-label="Field map"></main>
</div>
<script type="application/json" id="map-data">{{DATA_JSON}}</script>
<script>
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("map-data").textContent);
  var map = L.map("map", { preferCanvas: true, zoomControl: true, minZoom: 3 });
  // Clicking a field is the primary interaction, so keep popups anchored.
  map.options.closePopupOnClick = true;

  var imagery = L.tileLayer("{{ESRI_TILES}}", {
    maxZoom: 19,
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics"
  }).addTo(map);

  var streets = L.tileLayer("{{OSM_TILES}}", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  });

  L.control.layers(
    { "Satellite (Esri World Imagery)": imagery, "Streets (OpenStreetMap)": streets },
    null,
    { collapsed: true }
  ).addTo(map);
  L.control.scale({ imperial: true, metric: true }).addTo(map);

  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(
      /[&<>"']/g,
      function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      }
    );
  }

  function row(label, value) {
    if (value === null || value === undefined || value === "") return "";
    return '<div class="kv"><span>' + esc(label) + "</span><span>" + esc(value) + "</span></div>";
  }

  function popupHtml(p) {
    var area = p.area_acres ? Math.round(p.area_acres) + " ac" : "";
    var county = p.county ? p.county + " County" : "";
    return (
      '<div class="pop"><h3>' + esc(p.field_name) + "</h3>" +
      row("Grower", p.grower_name) +
      row("Farm", p.farm_name) +
      row("Field ID", p.field_id) +
      row("Crop", p.crop) +
      row("Area", area) +
      row("County", county) +
      row("State", p.state) +
      row("Boundary", p.source) +
      "</div>"
    );
  }

  function styleFor(feature) {
    return {
      color: feature.properties.farm_color,
      weight: 2,
      opacity: 0.95,
      fillColor: feature.properties.farm_color,
      fillOpacity: 0.12
    };
  }

  var layersById = {};
  L.geoJSON(data.fields, {
    style: styleFor,
    onEachFeature: function (feature, layer) {
      layer.bindPopup(popupHtml(feature.properties), { maxWidth: 300 });
      layer.on("mouseover", function () { layer.setStyle({ weight: 3, fillOpacity: 0.26 }); });
      layer.on("mouseout", function () { layer.setStyle(styleFor(feature)); });
      layersById[feature.properties.field_id] = layer;
    }
  }).addTo(map);

  function focus(bounds, layer) {
    if (!bounds) return;
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
    if (layer && layer.openPopup) layer.openPopup();
  }

  var list = document.getElementById("field-list");
  data.farms.forEach(function (farm) {
    var group = document.createElement("section");
    group.className = "farm";

    var head = document.createElement("h2");
    var dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = farm.color;
    head.appendChild(dot);
    head.appendChild(document.createTextNode(farm.name));
    group.appendChild(head);

    var meta = document.createElement("p");
    meta.className = "farm-meta";
    meta.textContent =
      farm.fields.length + (farm.fields.length === 1 ? " field" : " fields") +
      (farm.state ? " \u00b7 " + farm.state : "") +
      (farm.county ? " \u00b7 " + farm.county + " County" : "");
    group.appendChild(meta);

    farm.fields.forEach(function (field) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "field-row";

      var name = document.createElement("span");
      name.className = "name";
      name.textContent = field.name;
      var acres = document.createElement("span");
      acres.className = "acres";
      acres.textContent = field.acres ? Math.round(field.acres) + " ac" : "";

      button.appendChild(name);
      button.appendChild(acres);
      button.addEventListener("click", function () {
        focus(field.bounds, layersById[field.field_id]);
      });
      group.appendChild(button);
    });

    list.appendChild(group);
  });

  document.getElementById("fit-all").addEventListener("click", function () {
    map.closePopup();
    focus(data.bounds, null);
  });

  focus(data.bounds, null);
})();
</script>
</body>
</html>
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round_coords(coords, ndigits: int):
    if isinstance(coords, (int, float)):
        return round(float(coords), ndigits)
    return [_round_coords(item, ndigits) for item in coords]


def _geometry_bounds(geometry: dict) -> list[list[float]] | None:
    """[[south, west], [north, east]] for a Polygon/MultiPolygon, else None."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(node):
        if isinstance(node, (int, float)):
            raise TypeError("unexpected scalar")
        if node and isinstance(node[0], (int, float)):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
            return
        for child in node:
            walk(child)

    try:
        walk(geometry.get("coordinates"))
    except (TypeError, IndexError):
        return None
    if not xs or not ys:
        return None
    return [[min(ys), min(xs)], [max(ys), max(xs)]]


def _merge_bounds(bounds_list):
    boxes = [b for b in bounds_list if b]
    if not boxes:
        return None
    return [
        [min(b[0][0] for b in boxes), min(b[0][1] for b in boxes)],
        [max(b[1][0] for b in boxes), max(b[1][1] for b in boxes)],
    ]


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _field_display_names(farm_root: Path) -> dict[str, str]:
    """field_id / field_slug -> human label, from each field.json."""
    names: dict[str, str] = {}
    fields_dir = farm_root / "fields"
    if not fields_dir.is_dir():
        return names
    for field_dir in sorted(p for p in fields_dir.iterdir() if p.is_dir()):
        meta = _read_json(field_dir / "field.json")
        label = str(meta.get("display_name") or field_dir.name)
        for key in (meta.get("field_id"), meta.get("field_slug"), field_dir.name):
            if key:
                names[str(key)] = label
    return names


def collect_grower(
    data_root: Path,
    grower_slug: str,
    precision: int = DEFAULT_PRECISION,
    public_fixture: bool = False,
) -> dict:
    """Build the map payload for every farm and field under one grower."""
    grower_root = data_root / "growers" / grower_slug
    if not grower_root.is_dir():
        raise SystemExit(f"grower not found under runtime: {grower_root}")

    grower_meta = _read_json(grower_root / "grower.json")
    grower_name = str(grower_meta.get("display_name") or grower_slug)

    features: list[dict] = []
    farms_meta: list[dict] = []
    sources: list[Path] = []
    if (grower_root / "grower.json").is_file():
        sources.append(grower_root / "grower.json")

    farm_dirs = sorted(p for p in (grower_root / "farms").glob("*") if p.is_dir())
    for index, farm_root in enumerate(farm_dirs):
        boundary = farm_root / "boundary" / "field_boundaries.geojson"
        if not boundary.is_file():
            print(f"  skip  {farm_root.name}: no boundary/field_boundaries.geojson")
            continue
        try:
            collection = json.loads(boundary.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"  skip  {farm_root.name}: unreadable boundary ({exc})")
            continue

        farm_meta = _read_json(farm_root / "farm.json")
        farm_name = str(farm_meta.get("display_name") or farm_root.name)
        farm_state = str(farm_meta.get("state") or "")
        color = PALETTE[index % len(PALETTE)]
        names = _field_display_names(farm_root)

        farm_fields: list[dict] = []
        sources.append(boundary)
        if (farm_root / "farm.json").is_file():
            sources.append(farm_root / "farm.json")

        for feature in collection.get("features", []):
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                continue
            props = dict(feature.get("properties") or {})
            field_id = str(props.get("field_id") or "").strip()
            if not field_id:
                continue

            geometry["coordinates"] = _round_coords(geometry["coordinates"], precision)
            bounds = _geometry_bounds(geometry)
            field_name = names.get(field_id) or str(
                props.get("field_slug") or props.get("name") or field_id
            )
            acreage = props.get("area_acres")

            props.update(
                {
                    "field_id": field_id,
                    "field_name": field_name,
                    "farm_slug": farm_root.name,
                    "farm_name": farm_name,
                    "farm_color": color,
                    "grower_slug": grower_slug,
                    "grower_name": grower_name,
                    "state": props.get("state") or farm_state,
                    "county": props.get("county") or props.get("county_name") or "",
                }
            )
            if public_fixture:
                for key in PUBLIC_FIXTURE_DROP:
                    props.pop(key, None)
            features.append({"type": "Feature", "properties": props, "geometry": geometry})
            farm_fields.append(
                {
                    "field_id": field_id,
                    "name": field_name,
                    "acres": acreage,
                    "bounds": bounds,
                }
            )

        if not farm_fields:
            print(f"  skip  {farm_root.name}: no polygon features in boundary")
            continue

        farms_meta.append(
            {
                "slug": farm_root.name,
                "name": farm_name,
                "state": farm_state,
                "county": str(
                    next(
                        (f["properties"].get("county") for f in features
                         if f["properties"].get("farm_slug") == farm_root.name
                         and f["properties"].get("county")),
                        "",
                    )
                ),
                "color": color,
                "fields": farm_fields,
            }
        )

    if not features:
        raise SystemExit(f"no field polygons found for grower {grower_slug!r}")

    all_bounds = _merge_bounds([f["bounds"] for farm in farms_meta for f in farm["fields"]])
    return {
        "grower": {"slug": grower_slug, "name": grower_name},
        "farms": farms_meta,
        "fields": {"type": "FeatureCollection", "features": features},
        "bounds": all_bounds,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [str(p) for p in sources],
    }


def render_html(payload: dict) -> str:
    grower = payload["grower"]
    farm_count = len(payload["farms"])
    field_count = len(payload["fields"]["features"])
    subtitle = (
        f"{field_count} fields \u00b7 {farm_count} farm" + ("" if farm_count == 1 else "s")
        + " \u00b7 click a field for details"
    )
    # Exactly the keys the template reads. ``sources`` stays out on purpose:
    # it holds absolute runtime paths, and the page must remain portable.
    client_payload = {
        "grower": payload["grower"],
        "farms": payload["farms"],
        "fields": payload["fields"],
        "bounds": payload["bounds"],
    }
    data_json = json.dumps(client_payload, separators=(",", ":"), ensure_ascii=True)
    # A literal </script> inside any string would close the JSON block early.
    data_json = data_json.replace("</", "<\\/")

    return (
        TEMPLATE.replace("{{TITLE}}", f"{html.escape(grower['name'])} \u2014 field map")
        .replace("{{GROWER_NAME}}", html.escape(grower["name"]))
        .replace("{{SUBTITLE}}", html.escape(subtitle))
        .replace("{{ATTRIBUTION}}", html.escape(ATTRIBUTION))
        .replace("{{ESRI_TILES}}", ESRI_TILES)
        .replace("{{OSM_TILES}}", OSM_TILES)
        .replace("{{DATA_JSON}}", data_json)
    )


def write_grower_map(
    data_root: Path,
    grower_slug: str,
    *,
    out_path: Path | None = None,
    precision: int = DEFAULT_PRECISION,
    max_kb: int = DEFAULT_MAX_KB,
    public_fixture: bool = False,
) -> dict:
    payload = collect_grower(
        data_root, grower_slug, precision=precision, public_fixture=public_fixture
    )
    document = render_html(payload)
    size_bytes = len(document.encode("utf-8"))

    target = out_path or (
        data_root / "growers" / grower_slug / "derived" / "dashboards"
        / f"{grower_slug}_grower_map.html"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")

    field_count = len(payload["fields"]["features"])
    if size_bytes > max_kb * 1024:
        print(
            f"  warn  {target.name} is {size_bytes / 1024:.0f} KB "
            f"(soft limit {max_kb} KB); lower --precision to shrink it"
        )

    manifest = {
        "dataset": "grower_webmap",
        "grower_slug": grower_slug,
        "grower_name": payload["grower"]["name"],
        "role": "interactive grower-level view of pipeline field boundaries",
        "fields": field_count,
        "farms": len(payload["farms"]),
        "html": {
            "path_rel": _rel(target, data_root),
            "bytes": size_bytes,
        },
        "basemap": {
            "satellite": "Esri World Imagery",
            "url_template": ESRI_TILES,
            "streets": "OpenStreetMap",
            "streets_url_template": OSM_TILES,
            "network_required": True,
        },
        "attribution": ATTRIBUTION,
        "geometry_precision_decimals": precision,
        "sources": [
            {"path_rel": _rel(path, data_root), "sha256": _sha256(path)}
            for path in map(Path, payload["sources"])
            if path.is_file()
        ],
        "generated_at": payload["generated_at"],
    }
    manifest_path = data_root / "growers" / grower_slug / "manifests" / "grower_webmap.json"
    # A published fixture is one self-contained file, not a runtime provenance
    # record: the manifest describes local inputs by sha256 and has no business
    # traveling with a copy that is meant to be committed.
    if not public_fixture:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"  {grower_slug}: {field_count} fields / {len(payload['farms'])} farm(s) "
        f"-> {target} ({size_bytes / 1024:.0f} KB)"
    )
    return manifest


def _rel(path: Path, data_root: Path) -> str:
    """Root-relative path for provenance (portable across clones)."""
    try:
        return path.resolve().relative_to(data_root.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _resolve_data_root(raw: str | None) -> Path:
    value = raw or os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not value:
        raise SystemExit(
            "DATA_PIPELINE_DATA_ROOT is required (or pass --data-root); "
            "it must be an absolute path to the runtime outside the checkout."
        )
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise SystemExit(f"DATA_PIPELINE_DATA_ROOT must be absolute, got: {value}")
    # The contract's data root holds the data-pipeline tree as a child.
    root = root.resolve()
    return root / "data-pipeline" if (root / "data-pipeline").is_dir() else root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--grower", default=os.environ.get("AG_GROWER_SLUG"),
                        help="Grower slug (default: AG_GROWER_SLUG)")
    parser.add_argument("--all-growers", action="store_true",
                        help="Render every grower that has a farm boundary")
    parser.add_argument("--data-root", default=None,
                        help="Runtime root (default: DATA_PIPELINE_DATA_ROOT)")
    parser.add_argument("--out", default=None, help="Override the HTML output path")
    parser.add_argument("--precision", type=int, default=DEFAULT_PRECISION,
                        help="Coordinate decimals to keep (default 6, ~0.1 m)")
    parser.add_argument("--max-kb", type=int, default=DEFAULT_MAX_KB,
                        help="Warn when the HTML exceeds this size (default 512)")
    parser.add_argument("--public-fixture", action="store_true",
                        help="Drop parcel identifiers (" + ", ".join(PUBLIC_FIXTURE_DROP)
                             + ") and skip the manifest, for a copy meant to be "
                               "committed and served publicly")
    args = parser.parse_args()

    data_root = _resolve_data_root(args.data_root)

    if args.all_growers:
        growers = sorted(
            p.name for p in (data_root / "growers").glob("*")
            if p.is_dir() and any((p / "farms").glob("*/boundary/field_boundaries.geojson"))
        )
        if not growers:
            raise SystemExit(f"no growers with field boundaries under {data_root / 'growers'}")
    elif args.grower:
        growers = [args.grower]
    else:
        parser.error("one of --grower or --all-growers is required")

    if args.out and len(growers) > 1:
        parser.error("--out can only be used with a single grower")

    for slug in growers:
        out_path = Path(args.out).expanduser() if args.out else None
        write_grower_map(
            data_root,
            slug,
            out_path=out_path,
            precision=args.precision,
            max_kb=args.max_kb,
            public_fixture=args.public_fixture,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
