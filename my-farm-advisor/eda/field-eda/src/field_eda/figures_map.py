"""F7: field footprints on a local-metre frame with a basemap underlay.

The frame, north arrow, rotation, and basemap warp come from the shared
``data-pipeline/src/scripts/lib`` helpers so this figure follows the same
field-map contract as the rest of the catalog. The helpers are imported
read-only; nothing in that shared library is modified here.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from .figures import CROP_COLORS, CROP_LABELS, _save, _style
from .metrics import natural_key

BASEMAP_RES_M = 30.0
PANEL_HEIGHT_IN = 4.0
PANEL_WIDTH_IN = 3.4


def scripts_lib_dir() -> Path:
    """Locate the shared ``scripts/lib`` directory from a checkout or install."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates = (
            parent / "my-farm-advisor" / "data-pipeline" / "src" / "scripts" / "lib",
            parent / "data-pipeline" / "src" / "scripts" / "lib",
            parent / "src" / "scripts" / "lib",
        )
        for candidate in candidates:
            if (candidate / "field_frame.py").is_file():
                return candidate
    raise FileNotFoundError("could not locate data-pipeline/src/scripts/lib")


def _frame_tools():
    lib = scripts_lib_dir()
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    from basemap import draw as draw_basemap
    from field_frame import crs_note, decorate, frame_for, view_extent

    return frame_for, decorate, view_extent, crs_note, draw_basemap


def _crop_lookup(fields) -> dict[str, str]:
    if fields.empty or "latest_crop" not in fields:
        return {}
    return {
        str(row["field_id"]): str(row["latest_crop"])
        for _, row in fields.iterrows()
        if isinstance(row.get("latest_crop"), str)
    }


def _state_lookup(fields) -> dict[str, str]:
    if fields.empty or "state" not in fields:
        return {}
    return {
        str(row["field_id"]): str(row["state"])
        for _, row in fields.iterrows()
        if isinstance(row.get("state"), str) and row.get("state")
    }


def _ordered_fields(fields):
    return fields.sort_values(
        "field_id",
        key=lambda series: series.map(
            lambda value: natural_key(value) if isinstance(value, str) else value
        ),
    ).reset_index(drop=True)


def figure_field_map(farms, fields, path: Path) -> Path:
    """F7: one panel per farm, footprints in local metres over a basemap."""
    _style()
    frame_for, decorate, view_extent, crs_note, draw_basemap = _frame_tools()
    crop_for = _crop_lookup(fields)
    state_for = _state_lookup(fields)

    panels = [farm for farm in farms if not farm.fields.empty]
    if not panels:
        raise ValueError("field map needs at least one farm with boundaries")

    figure, axes = plt.subplots(
        1,
        len(panels),
        figsize=(PANEL_WIDTH_IN * len(panels), PANEL_HEIGHT_IN + 0.9),
        squeeze=False,
    )
    axes = axes[0]

    for axis, farm in zip(axes, panels):
        source = _ordered_fields(farm.fields[["field_id", "geometry"]])
        frame = frame_for(
            source, panel_h_in=PANEL_HEIGHT_IN, panel_w_in=PANEL_WIDTH_IN
        )
        framed = frame.geometry.reset_index(drop=True)
        min_x, min_y, max_x, max_y = framed.total_bounds
        extent = view_extent(min_x, max_x, min_y, max_y, pad_frac=0.15)
        width = extent[1] - extent[0]
        height = extent[3] - extent[2]
        nx = 900
        ny = max(300, int(round(nx * height / width)))
        resolution = max(8.0, width / nx)

        axis.set_facecolor("#F2F0EA")
        axis.set_xlim(extent[0], extent[1])
        axis.set_ylim(extent[2], extent[3])
        axis.set_aspect("equal")
        draw_basemap(axis, frame, extent, ny, nx, target_res_m=resolution)

        # Halo: a thin white outline around each footprint keeps it legible
        # over busy imagery without swallowing the field itself.
        buffer_m = max(40.0, resolution * 1.5)
        halo = gpd.GeoSeries(
            [framed.geometry.buffer(buffer_m).union_all()],
            crs=frame.geometry.crs,
        )
        halo.plot(ax=axis, facecolor="none", edgecolor="white", linewidth=1.0,
                  alpha=0.9, zorder=1)

        colors = [
            CROP_COLORS.get(crop_for.get(str(field_id), "Other"), CROP_COLORS["Other"])
            for field_id in framed["field_id"]
        ]
        framed.plot(
            ax=axis,
            color=colors,
            edgecolor="white",
            linewidth=0.7,
            alpha=0.82,
            zorder=2,
        )

        crops = [
            crop_for.get(str(field_id), "Other") for field_id in framed["field_id"]
        ]
        counts = Counter(crops)
        counts_text = " · ".join(
            f"{label} {counts[key]}"
            for key, label in (
                ("Corn", "Corn"),
                ("Soybeans", "Soybeans"),
                ("Grass/Pasture", "Grass"),
            )
            if counts.get(key)
        )


        # The x-axis note already states the tilt, so skip the in-panel
        # rotation callout; over imagery it was hard to read and collided
        # with field labels.
        decorate(axis, frame, arrow_r=0.09, arrow_fs=10.0, callout=False)
        axis.set_xlabel(crs_note(frame), fontsize=6.0, color="#374151")
        tick_step = 10000 if max(width, height) > 15000 else 2000
        axis.set_xticks(range(0, int(extent[1]) + 1, tick_step))
        axis.set_yticks(range(0, int(extent[3]) + 1, tick_step))
        axis.tick_params(labelsize=6, colors="#4B5563")
        state = state_for.get(str(framed["field_id"].iloc[0]), "")
        if not state and "state" in farm.fields:
            state = str(farm.fields["state"].iloc[0])
        title = f"{state or farm.grower_name} · {farm.farm_name}"
        if counts_text:
            title = f"{title}\n{counts_text}"
        axis.set_title(title, fontsize=9.2, pad=6)
        for spine in axis.spines.values():
            spine.set_visible(False)

    legend = [
        Patch(facecolor=CROP_COLORS["Corn"], label=CROP_LABELS["Corn"]),
        Patch(facecolor=CROP_COLORS["Soybeans"], label=CROP_LABELS["Soybeans"]),
        Patch(facecolor=CROP_COLORS["Grass/Pasture"], label=CROP_LABELS["Grass/Pasture"]),
        Patch(facecolor=CROP_COLORS["Other"], label=CROP_LABELS["Other"]),
    ]
    figure.legend(
        handles=legend,
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, -0.005),
    )
    figure.suptitle(
        "Field footprints and 2023 dominant crop",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.01,
        -0.065,
        "Each panel uses a local UTM metre frame, auto-rotated to the field cluster; "
        "north is shown per panel. Basemap: Esri World Imagery. Fields are the top 10 by area per county; "
        "field IDs and per-field values are in F3/F4 and field-metrics.csv.",
        fontsize=6.6,
        color="#555555",
        ha="left",
    )
    return _save(figure, path)
