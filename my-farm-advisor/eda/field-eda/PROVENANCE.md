# Field EDA Provenance

This file records where the subskill's data, defaults, and methods come from, and what
is intentionally not part of it. It documents a repo-local analysis package; it does
not vendor any external skill.

## Origin

- Created for the Assignment 2 field-level EDA inside the My Farm Advisor skill catalog.
- Subskill path: `my-farm-advisor/eda/field-eda/`; frontmatter name `field-eda`.
- The analysis consumes the Assignment 2 dataset already produced by the My Farm
  Advisor data pipeline. It does not download boundaries, weather, or CDL itself.

## Input provenance

All inputs are runtime artifacts owned by the data pipeline:

- **Field boundaries** — USDA Common Spatial Boundary (CSB) hosted polygons selected by
  county, as built by the Assignment 2 expansion. Boundary CRS is EPSG:4326; the
  `area_ha_est`, `crop`, `csb_id`, `county`, and FIPS fields ship as properties.
- **Weather** — NASA POWER daily point series per field (`T2M`, `T2M_MAX`, `T2M_MIN`,
  `PRECTOTCORR`, `ALLSKY_SFC_SW_DWN`, `RH2M`, `WS10M`). Units are the provider defaults
  and are not repeated in the runtime metadata; the analysis treats them as °C, mm/day,
  MJ/m²/day, %, and m/s respectively.
- **CDL** — USDA NASS Cropland Data Layer per-year class shares, produced by the data
  pipeline and stored as long tables with `crop_code`, `crop_name`, `pixel_count`,
  `pct`, and `crop_source`.
- **Crop rotation** — the pipeline's `*_crop_rotation.csv` is optional context; the
  subskill recomputes the dominant sequence from the CDL shares rather than trusting a
  pre-joined rotation label.

The run manifest records a SHA-256 hash, byte size, and UTC mtime for every input file
that was read, so a reviewed figure can be tied back to exact source tables.

## Method provenance

- **Growing season and GDD** — April 1–October 31, base 10 °C, cap 30 °C. This is the
  convention agreed for the Assignment 2 EDA; it is a project default, not a universal
  agronomic standard. Document any change in the same commit as the code.
- **Polsby-Popper compactness** — `4πA / P²`, computed in EPSG:5070. The square scores
  `π/4` and the circle scores `1.0`; the test suite pins the square case.
- **Shannon diversity** — applied to the five-year dominant-crop sequence, not to pixel
  areas. A constant sequence scores 0; a two-class even split scores `ln 2 ≈ 0.693`.
- **Statistics** — rank-based tests (`scipy.stats.kruskal`, `mannwhitneyu`,
  `spearmanr`) with Holm correction and seeded bootstrap CIs. Choices and caveats are in
  [references/statistics.md](references/statistics.md).
- **Palette** — Okabe–Ito colorblind-safe colors, aligned with the repository's
  colormap guidance. Corn, Soybeans, Grass/Pasture, and the unclassified residual use
  fixed, distinct colors; continuous variables are only used as positions, not ramps.
- **Geospatial map (F7)** — built on the shared `data-pipeline/src/scripts/lib`
  `field_frame.py` and `basemap.py` helpers (local UTM metre frame, auto-rotation,
  true-north arrow, Esri World Imagery underlay). Those shared modules are imported
  read-only; this package does not modify them. The map is county-scale because the
  sampled fields span tens of kilometres, so per-field IDs live in F3/F4 and the field
  table rather than on the map.

## Explicit non-sources

- No soil data, imagery indices, terrain derivatives, or in-season satellite products.
- No vendored or copied Superior Byte Works skill content.
- No third-party report template, dashboard framework, or plotting theme.
- No generated runtime tables, figures, or downloaded bundles are committed with this
  package.

## Change rules

- Keep defaults (`SEASON_START_MD`, `SEASON_END_MD`, `GDD_BASE_C`, `GDD_CAP_C`,
  `PROJECTED_CRS`) in one place in `metrics.py`.
- A change to a figure renderer re-triggers review of every figure it draws; record the
  verdict in the commit message.
- If an input column or unit assumption changes, update
  [references/data-contract.md](references/data-contract.md) in the same change.
