"""Static figures for the field EDA (Agg backend, no interactivity)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .metrics import natural_key
from .stats import spearman_with_ci

STATE_COLORS = {
    "IL": "#0072B2",
    "IA": "#D55E00",
    "NE": "#009E73",
    "MN": "#CC79A7",
    "MO": "#E69F00",
}
FALLBACK_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]

CROP_COLORS = {
    "Corn": "#E69F00",
    "Soybeans": "#56B4E9",
    "Grass/Pasture": "#009E73",
    "Other": "#B0B0B0",
}
CROP_LABELS = {
    "Corn": "Corn",
    "Soybeans": "Soybeans",
    "Grass/Pasture": "Grass/Pasture",
    "Other": "Other / unclassified",
}
MISSING_COLOR = "#FFFFFF"
GRID_COLOR = "#DDDDDD"

SEED = 20261127


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "axes.edgecolor": "#444444",
            "axes.linewidth": 0.8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
        }
    )


def _save(figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def _grower_order(fields: pd.DataFrame) -> list[str]:
    return sorted(fields["grower_name"].dropna().unique())


def grower_colors(fields: pd.DataFrame) -> dict[str, str]:
    colors: dict[str, str] = {}
    for index, name in enumerate(_grower_order(fields)):
        rows = fields.loc[fields["grower_name"] == name, "state"]
        state = str(rows.iloc[0]) if len(rows) else ""
        colors[name] = STATE_COLORS.get(state, FALLBACK_COLORS[index % len(FALLBACK_COLORS)])
    return colors


def figure_area_by_grower(fields: pd.DataFrame, path: Path) -> Path:
    """F1: field area distribution per grower."""
    _style()
    order = _grower_order(fields)
    colors = grower_colors(fields)
    rng = np.random.default_rng(SEED)

    figure, axes = plt.subplots(figsize=(7.2, 4.4))
    for position, name in enumerate(order):
        values = fields.loc[fields["grower_name"] == name, "area_ha"].to_numpy()
        color = colors[name]
        x = position + rng.uniform(-0.11, 0.11, values.size)
        axes.scatter(
            x, values, s=28, color=color, edgecolor="white", linewidth=0.6,
            zorder=3, alpha=0.9,
        )
        box = axes.boxplot(
            [values], positions=[position], widths=0.42, showfliers=False,
            patch_artist=True, zorder=2,
        )
        box["boxes"][0].set(facecolor=color, alpha=0.18, edgecolor=color, linewidth=1.0)
        for median in box["medians"]:
            median.set(color=color, linewidth=1.8)
        for whisker in box["whiskers"] + box["caps"]:
            whisker.set(color=color, linewidth=0.9)
        axes.text(
            position,
            values.max() + 0.03 * (fields["area_ha"].max() - fields["area_ha"].min()),
            f"n={values.size}  median {np.median(values):.0f} ha",
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#333333",
        )

    axes.set_xticks(range(len(order)))
    axes.set_xticklabels(order)
    axes.set_ylabel("Field area (ha)")
    axes.set_title("Field size by grower sample")
    axes.grid(axis="y", color=GRID_COLOR, linewidth=0.6)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.text(
        0.01,
        -0.02,
        "Top-10-by-area selection inside each county; points are individual fields.",
        fontsize=7,
        color="#555555",
        ha="left",
    )
    return _save(figure, path)


def figure_shape_vs_area(fields: pd.DataFrame, path: Path) -> Path:
    """F2: does field size track shape complexity?"""
    _style()
    colors = grower_colors(fields)
    figure, axes = plt.subplots(figsize=(7.0, 4.6))

    for name in _grower_order(fields):
        group = fields[fields["grower_name"] == name]
        axes.scatter(
            group["area_ha"], group["compactness"], s=34, color=colors[name],
            edgecolor="white", linewidth=0.6, alpha=0.9, label=name, zorder=3,
        )

    result = spearman_with_ci(fields["area_ha"], fields["compactness"])
    axes.text(
        0.02, 0.98,
        f"Spearman rho = {result['rho']:.2f} (p = {result['p_value']:.3f}, n = {result['n']})",
        transform=axes.transAxes, ha="left", va="top", fontsize=8, color="#333333",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": GRID_COLOR},
    )

    lowest = fields.nsmallest(2, "compactness")
    for _, row in lowest.iterrows():
        axes.annotate(
            f"{row['field_id']} ({row['compactness']:.2f})",
            xy=(row["area_ha"], row["compactness"]),
            xytext=(10, 6),
            textcoords="offset points",
            fontsize=7,
            color="#444444",
        )

    axes.set_xlabel("Field area (ha)")
    axes.set_ylabel("Polsby-Popper compactness (4πA/P²)")
    axes.set_title("Field shape vs size")
    axes.grid(color=GRID_COLOR, linewidth=0.6)
    axes.set_axisbelow(True)
    axes.legend(title="Grower", loc="upper right")
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.text(
        0.01, -0.02,
        "1.0 = circle; lower values are more elongated or irregular. Areas and perimeters in EPSG:5070.",
        fontsize=7, color="#555555", ha="left",
    )
    return _save(figure, path)


def figure_rotation_heatmap(
    fields: pd.DataFrame, path: Path, years: list[int] | None = None
) -> Path:
    """F3: dominant crop per field per CDL year, grouped by grower.

    ``years`` is passed explicitly from the CDL tables. The boundary also carries
    a ``crop_2025`` attribute, but it is not CDL and would add a gap-year column
    (2024 missing) that reads as a rotation step.
    """
    _style()
    if years is None:
        years = sorted(
            int(column.split("_")[1])
            for column in fields.columns
            if column.startswith("crop_") and column.split("_")[1].isdigit()
        )
    years = sorted(years)
    ordered = fields.sort_values(
        ["grower_name", "field_id"],
        key=lambda series: series.map(
            lambda value: natural_key(value) if isinstance(value, str) else value
        ),
    ).reset_index(drop=True)

    codes = {"Corn": 3, "Soybeans": 2, "Grass/Pasture": 1}
    grid = np.zeros((len(ordered), len(years)))
    for row_index, record in ordered.iterrows():
        for column_index, year in enumerate(years):
            crop = record.get(f"crop_{year}")
            grid[row_index, column_index] = codes.get(str(crop), 0)

    colors = [MISSING_COLOR, CROP_COLORS["Other"], CROP_COLORS["Soybeans"], CROP_COLORS["Corn"]]
    from matplotlib.colors import ListedColormap

    figure, axes = plt.subplots(figsize=(6.4, 8.6))
    axes.imshow(
        grid, aspect="auto", cmap=ListedColormap(colors), vmin=-0.5, vmax=3.5,
        interpolation="nearest",
    )

    axes.set_xticks(range(len(years)))
    axes.set_xticklabels([str(year) for year in years])
    axes.set_yticks(range(len(ordered)))
    axes.set_yticklabels(
        [f"{row['state']}  {row['field_id']}" for _, row in ordered.iterrows()],
        fontsize=7,
    )

    axes.set_xticks(np.arange(-0.5, len(years), 1), minor=True)
    axes.set_yticks(np.arange(-0.5, len(ordered), 1), minor=True)
    axes.grid(which="minor", color="white", linewidth=1.2)
    axes.tick_params(which="minor", length=0)

    blocks = []
    start = 0
    names = ordered["grower_name"].tolist()
    for index in range(1, len(names) + 1):
        if index == len(names) or names[index] != names[start]:
            blocks.append((names[start], start, index - 1))
            start = index
    for name, first, last in blocks:
        axes.axhline(first - 0.5, color="#222222", linewidth=1.4)
        axes.text(
            len(years) - 0.35, (first + last) / 2, name,
            va="center", ha="left", fontsize=8.5, clip_on=False,
        )
    axes.axhline(len(ordered) - 0.5, color="#222222", linewidth=1.4)

    legend = [
        Patch(facecolor=CROP_COLORS["Corn"], label="Corn"),
        Patch(facecolor=CROP_COLORS["Soybeans"], label="Soybeans"),
        Patch(facecolor=CROP_COLORS["Other"], label=CROP_LABELS["Other"]),
        Patch(facecolor=MISSING_COLOR, edgecolor="#999999", label="No data"),
    ]
    axes.legend(
        handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.06),
        ncol=4,
    )
    axes.set_title("Dominant crop by field and year")
    for spine in axes.spines.values():
        spine.set_visible(False)
    return _save(figure, path)


def figure_composition(
    fields: pd.DataFrame, cdl: pd.DataFrame, path: Path
) -> Path:
    """F4: class composition of the latest CDL year per field."""
    _style()
    if cdl.empty:
        raise ValueError("composition figure needs the CDL long table")

    latest_year = int(cdl["year"].max())
    year = cdl[cdl["year"] == latest_year]
    pivot = (
        year.pivot_table(
            index="field_id", columns="crop_name", values="pct", aggfunc="sum"
        )
        .fillna(0.0)
    )
    pivot["Corn"] = pivot.get("Corn", 0.0)
    pivot["Soybeans"] = pivot.get("Soybeans", 0.0)
    pivot["Grass/Pasture"] = pivot.get("Grass/Pasture", 0.0)
    known = pivot[["Corn", "Soybeans", "Grass/Pasture"]].sum(axis=1)
    pivot["Other"] = (100.0 - known).clip(lower=0.0)

    ordered = fields.sort_values(
        ["grower_name", "field_id"],
        key=lambda series: series.map(
            lambda value: natural_key(value) if isinstance(value, str) else value
        ),
    ).reset_index(drop=True)
    pivot = pivot.reindex(ordered["field_id"])

    totals = pivot[["Corn", "Soybeans", "Grass/Pasture", "Other"]]
    dominant_share = totals[["Corn", "Soybeans"]].max(axis=1)

    figure, axes = plt.subplots(figsize=(7.6, 8.6))
    left = np.zeros(len(pivot))
    y_positions = np.arange(len(pivot))
    for crop in ["Corn", "Soybeans", "Grass/Pasture", "Other"]:
        values = totals[crop].to_numpy()
        axes.barh(
            y_positions, values, left=left, color=CROP_COLORS[crop],
            edgecolor="white", linewidth=0.4, height=0.78, label=CROP_LABELS[crop],
        )
        left += values

    axes.set_yticks(y_positions)
    axes.set_yticklabels(
        [f"{row['state']}  {row['field_id']}" for _, row in ordered.iterrows()],
        fontsize=7,
    )
    axes.invert_yaxis()
    for position, share in enumerate(dominant_share.to_numpy()):
        axes.text(
            101.5, position, f"{share:.0f}%",
            va="center", ha="left", fontsize=6.5, color="#333333",
        )

    axes.set_xlim(0, 108)
    axes.set_xlabel("Share of CDL pixels in the field (%)")
    axes.set_title(f"{latest_year} crop composition per field")
    axes.grid(axis="x", color=GRID_COLOR, linewidth=0.6)
    axes.set_axisbelow(True)
    axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=4)
    figure.text(
        0.01, -0.02,
        "CDL tables omit unclassified pixels, so the residual lands in the grey band.",
        fontsize=7, color="#555555", ha="left",
    )
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    return _save(figure, path)


def figure_climatology(
    fields: pd.DataFrame, weather: pd.DataFrame, path: Path
) -> Path:
    """F5: monthly temperature and precipitation by grower, 2021-2025 spread."""
    _style()
    monthly = _monthly_by_grower(fields, weather)
    if monthly.empty:
        raise ValueError("climatology figure needs raw daily weather rows")

    figure, (temperature_axis, precip_axis) = plt.subplots(
        2, 1, figsize=(7.4, 6.4), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    colors = grower_colors(fields)
    months = list(range(1, 13))

    for name in _grower_order(fields):
        group = monthly[monthly["grower_name"] == name]
        temp_mean = group.groupby("month")["temp_mean"].mean().reindex(months)
        temp_low = group.groupby("month")["temp_mean"].min().reindex(months)
        temp_high = group.groupby("month")["temp_mean"].max().reindex(months)
        temperature_axis.plot(months, temp_mean, color=colors[name], linewidth=2, label=name)
        temperature_axis.fill_between(
            months, temp_low, temp_high, color=colors[name], alpha=0.14, linewidth=0
        )

        precip_mean = group.groupby("month")["precip_total"].mean().reindex(months)
        precip_low = group.groupby("month")["precip_total"].min().reindex(months)
        precip_high = group.groupby("month")["precip_total"].max().reindex(months)
        precip_axis.plot(months, precip_mean, color=colors[name], linewidth=2)
        precip_axis.fill_between(
            months, precip_low, precip_high, color=colors[name], alpha=0.14, linewidth=0
        )

    for axis in (temperature_axis, precip_axis):
        axis.axvspan(3.5, 10.5, color="#F2F2F2", zorder=0)
        axis.grid(color=GRID_COLOR, linewidth=0.6)
        axis.set_axisbelow(True)
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
    temperature_axis.set_ylabel("Mean air temperature (°C)")
    precip_axis.set_ylabel("Monthly precipitation (mm)")
    precip_axis.set_xlabel("Month")
    precip_axis.set_xticks(months)
    precip_axis.set_xticklabels(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
    temperature_axis.set_title("Seasonal climate by grower, 2021-2025")
    temperature_axis.legend(title="Grower", loc="upper left")
    temperature_axis.text(
        0.985, 0.03, "shaded band = year-to-year min-max; grey = Apr-Oct growing season",
        transform=temperature_axis.transAxes, ha="right", fontsize=7, color="#555555",
    )
    return _save(figure, path)


def _monthly_by_grower(fields: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Monthly per-grower climate, averaging the 10 co-located fields.

    The 10 fields in a grower share one climate grid, so precipitation must be
    summed per field-month *first* and then averaged across fields. Summing
    straight across the grower would multiply monthly totals by the field count.
    """
    if weather.empty:
        return pd.DataFrame()
    weather = weather.copy()
    weather["date"] = pd.to_datetime(weather["date"])
    weather["year"] = weather["date"].dt.year
    weather["month"] = weather["date"].dt.month

    mapping = fields.set_index("field_id")["grower_name"]
    weather["grower_name"] = weather["field_id"].map(mapping)
    weather = weather.dropna(subset=["grower_name"])

    per_field = (
        weather.groupby(
            ["grower_name", "year", "month", "field_id"], as_index=False
        )
        .agg(
            temp_mean=("T2M", "mean"),
            precip_total=("PRECTOTCORR", "sum"),
        )
    )
    return (
        per_field.groupby(["grower_name", "year", "month"], as_index=False)
        .agg(temp_mean=("temp_mean", "mean"), precip_total=("precip_total", "mean"))
        .sort_values(["grower_name", "year", "month"])
        .reset_index(drop=True)
    )


def figure_precip_vs_gdd(field_years: pd.DataFrame, path: Path) -> Path:
    """F6: growing-season precipitation vs GDD, one point per field-year."""
    _style()
    colors = {
        name: color
        for name, color in zip(
            sorted(field_years["grower_name"].unique()), FALLBACK_COLORS
        )
    }
    # Prefer the state-derived palette when available.
    states = (
        field_years.groupby("grower_name")["state"].first()
        if "state" in field_years
        else pd.Series(dtype=str)
    )
    for name, state in states.items():
        if str(state) in STATE_COLORS:
            colors[name] = STATE_COLORS[str(state)]

    figure, axes = plt.subplots(figsize=(7.2, 4.8))
    for name in sorted(field_years["grower_name"].unique()):
        group = field_years[field_years["grower_name"] == name]
        axes.scatter(
            group["season_precip_mm"], group["season_gdd_c"],
            s=24, color=colors[name], alpha=0.75, edgecolor="white",
            linewidth=0.4, label=name, zorder=3,
        )

    result = spearman_with_ci(
        field_years["season_precip_mm"], field_years["season_gdd_c"]
    )
    lines = [
        f"pooled rho = {result['rho']:.2f} "
        f"(p {_format_p(result['p_value'])}, n = {result['n']})"
    ]
    for name in sorted(field_years["grower_name"].unique()):
        group = field_years[field_years["grower_name"] == name]
        per_grower = spearman_with_ci(group["season_precip_mm"], group["season_gdd_c"])
        lines.append(f"{name}: rho = {per_grower['rho']:.2f} (n = {per_grower['n']})")
    axes.text(
        0.02, 0.98, "\n".join(lines), transform=axes.transAxes, ha="left", va="top",
        fontsize=7.5, color="#333333",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": GRID_COLOR},
    )

    axes.set_xlabel("Growing-season precipitation (mm, Apr-Oct)")
    axes.set_ylabel("Growing-season GDD (°C, base 10)")
    axes.set_title("Water and heat across field-years")
    axes.grid(color=GRID_COLOR, linewidth=0.6)
    axes.set_axisbelow(True)
    axes.legend(title="Grower", loc="lower left")
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.text(
        0.01, -0.02,
        "Pooled rho is a between-grower contrast; within a grower the sign can flip. "
        "10 fields per grower share one climate grid, so the 5 years are the effective sample.",
        fontsize=7, color="#555555", ha="left",
    )
    return _save(figure, path)


def _format_p(value: float) -> str:
    if not np.isfinite(value):
        return "= n/a"
    if value < 0.001:
        return "< 0.001"
    return f"= {value:.3f}"
