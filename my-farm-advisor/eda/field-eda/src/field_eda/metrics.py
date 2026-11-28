"""Field metrics for boundary, CDL, and weather comparisons.

Everything here is pure pandas/numpy: no I/O, no plotting, no runtime imports.
Callers pass frames loaded by ``field_eda.loaders`` and write the results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

PROJECTED_CRS = "EPSG:5070"

# Growing season and GDD defaults agreed for the Assignment 2 EDA:
# Apr 1 - Oct 31, base 10 C, cap 30 C.
SEASON_START_MD = "04-01"
SEASON_END_MD = "10-31"
GDD_BASE_C = 10.0
GDD_CAP_C = 30.0


def natural_key(value: str) -> tuple[tuple[int, object], ...]:
    """Sort ``il-r2`` before ``il-r10`` without hard-coding grower names."""
    parts = re.split(r"(\d+)", str(value))
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts
    )


def boundary_metrics(fields):
    """Add projected area, perimeter, compactness, and vertex counts.

    ``area_ha_est`` ships in the boundary properties. Polsby-Popper compactness
    (4*pi*A/P^2) is scale-free but must be computed in an equal-area projection,
    so the geometry is projected to EPSG:5070 first.
    """
    if fields.empty:
        return fields.copy()

    out = fields.copy()
    projected = out.to_crs(PROJECTED_CRS)
    out["area_proj_ha"] = projected.area / 10_000.0
    out["perimeter_m"] = projected.length
    with np.errstate(divide="ignore", invalid="ignore"):
        compactness = (4.0 * np.pi * projected.area) / (projected.length**2)
    out["compactness"] = compactness.clip(lower=0.0, upper=1.0)
    out["vertices"] = projected.geometry.apply(_vertex_count)
    out["multipart"] = projected.geometry.apply(lambda geom: geom.geom_type != "Polygon")
    return out


def _vertex_count(geometry) -> int:
    if geometry.geom_type == "Polygon":
        return len(geometry.exterior.coords)
    return sum(len(part.exterior.coords) for part in geometry.geoms)


def dominant_crop(cdl: pd.DataFrame):
    """Return one dominant crop row per field-year with a second-class margin."""
    if cdl.empty:
        return pd.DataFrame(
            columns=["field_id", "year", "crop_name", "pct", "pct_next", "margin_pct"]
        )

    ranked = cdl.sort_values(
        ["field_id", "year", "pct"], ascending=[True, True, False]
    ).copy()
    ranked["rank"] = ranked.groupby(["field_id", "year"]).cumcount()

    top = ranked[ranked["rank"] == 0].copy()
    runner_up = ranked[ranked["rank"] == 1][["field_id", "year", "pct"]].rename(
        columns={"pct": "pct_next"}
    )
    top = top.merge(runner_up, on=["field_id", "year"], how="left")
    top["pct_next"] = top["pct_next"].fillna(0.0)
    top["margin_pct"] = top["pct"] - top["pct_next"]
    return top[["field_id", "year", "crop_name", "pct", "pct_next", "margin_pct"]]


# Two share floors for the distinct-class count. 0 counts every class the CDL
# table lists; 1% drops edge slivers that are one or two pixels of a neighbouring
# field. Both are reported because the literal count is sensitive to those slivers.
DIVERSITY_FLOORS = (("distinct_classes", 0.0), ("distinct_classes_1pct", 1.0))


CROP_GROUPS = ("Corn", "Soybeans", "Grass/Pasture")


def crop_group(name) -> str:
    """Collapse the CDL long tail into the four classes the figures colour."""
    value = str(name)
    return value if value in CROP_GROUPS else "Other"


def class_share_by_grower_year(cdl: pd.DataFrame, fields: pd.DataFrame) -> pd.DataFrame:
    """Share of classified CDL pixels per grower, year, and crop group.

    Computed inside each grower-year, so a year with more field rows cannot
    dominate. ``pixel_count`` is the exclusive unit when the producer ships a
    complete column: every pixel is counted once, and the unclassified residual
    is simply absent from the denominator rather than being assigned to a class.
    A missing or partial ``pixel_count`` falls back to ``pct`` instead of
    silently summing blanks to zero shares.
    """
    columns = ["grower_name", "year", "crop_group", "pct", "unit"]
    if cdl.empty or fields.empty:
        return pd.DataFrame(columns=columns)

    mapping = fields.set_index("field_id")["grower_name"]
    frame = cdl.copy()
    frame["grower_name"] = frame["field_id"].map(mapping)
    frame = frame.dropna(subset=["grower_name"])
    unit = "pct"
    if "pixel_count" in frame.columns:
        counts = pd.to_numeric(frame["pixel_count"], errors="coerce")
        # An all-NaN (or partly blank) count column would sum to zero and the
        # grid fillna below would report 0% for every class. Use it only when
        # every kept row has a count.
        if not frame.empty and counts.notna().all():
            unit = "pixel_count"
    frame["crop_group"] = frame["crop_name"].map(crop_group)

    grouped = (
        frame.groupby(["grower_name", "year", "crop_group"])[unit]
        .sum()
        .rename("value")
        .reset_index()
    )
    totals = grouped.groupby(["grower_name", "year"])["value"].transform("sum")
    out = grouped.assign(pct=grouped["value"] / totals * 100.0, unit=unit)

    # Complete the grower-year x class grid: a class with no pixels in one year
    # is a zero share, not a missing year to be dropped from the mean.
    grid = pd.MultiIndex.from_product(
        [
            sorted(out["grower_name"].unique()),
            sorted(out["year"].unique()),
            list(CROP_GROUPS) + ["Other"],
        ],
        names=["grower_name", "year", "crop_group"],
    )
    out = out.set_index(["grower_name", "year", "crop_group"]).reindex(grid)
    out["pct"] = out["pct"].fillna(0.0)
    out["unit"] = out["unit"].fillna(unit)
    return out.reset_index()[columns].sort_values(
        ["grower_name", "year", "crop_group"]
    ).reset_index(drop=True)


def class_diversity_per_field_year(cdl: pd.DataFrame) -> pd.DataFrame:
    """Distinct CDL classes per field-year, at the 0% and 1% share floors.

    A "class" is one ``crop_name`` row in the per-year CDL table whose share of
    the field is above the floor. This counts classes present in a single year,
    which is a different quantity from ``sequence_diversity`` (variety across the
    dominant 5-year sequence).
    """
    columns = ["field_id", "year"] + [name for name, _ in DIVERSITY_FLOORS]
    if cdl.empty:
        return pd.DataFrame(columns=columns)

    out = cdl[["field_id", "year"]].drop_duplicates().reset_index(drop=True)
    for name, floor in DIVERSITY_FLOORS:
        counts = (
            cdl.loc[cdl["pct"] > floor]
            .groupby(["field_id", "year"])["crop_name"]
            .nunique()
            .rename(name)
        )
        out = out.merge(counts, on=["field_id", "year"], how="left")
        out[name] = out[name].fillna(0).astype(int)
    return out.sort_values(["field_id", "year"]).reset_index(drop=True)


def rotation_matrix(dominant: pd.DataFrame):
    """Field x year crop-name matrix, ready for the rotation heatmap."""
    if dominant.empty:
        return pd.DataFrame()
    matrix = dominant.pivot(index="field_id", columns="year", values="crop_name")
    return matrix.sort_index(axis=1)


def shannon_diversity(counts) -> float:
    """Shannon index over class counts; 0 for a single class."""
    values = np.asarray([float(value) for value in counts if value > 0], dtype=float)
    if values.size == 0:
        return 0.0
    shares = values / values.sum()
    return float(max(0.0, -(shares * np.log(shares)).sum()))


def sequence_diversity(sequence) -> float:
    """Shannon index treating each year's dominant crop as one observation."""
    return shannon_diversity(pd.Series(sequence).value_counts().to_numpy())


def continuous_corn(sequence) -> bool:
    values = [str(value) for value in sequence if isinstance(value, str)]
    return bool(values) and all(value == "Corn" for value in values)


def daily_gdd(tmax: pd.Series, tmin: pd.Series) -> pd.Series:
    """Daily growing degree days, base 10 C, capped at 30 C."""
    tmax_capped = tmax.clip(upper=GDD_CAP_C)
    tmin_capped = tmin.clip(upper=GDD_CAP_C)
    return ((tmax_capped + tmin_capped) / 2.0 - GDD_BASE_C).clip(lower=0.0)


def is_growing_season(dates: pd.Series) -> pd.Series:
    month_day = dates.dt.strftime("%m-%d")
    return (month_day >= SEASON_START_MD) & (month_day <= SEASON_END_MD)


def weather_season_stats(weather: pd.DataFrame) -> pd.DataFrame:
    """Per field-year season and annual weather aggregates."""
    if weather.empty:
        return pd.DataFrame()

    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["in_season"] = is_growing_season(frame["date"])
    frame["gdd"] = daily_gdd(frame["T2M_MAX"], frame["T2M_MIN"])

    rows: list[dict] = []
    for (field_id, year), group in frame.groupby(["field_id", "year"], sort=True):
        season = group[group["in_season"]]
        rows.append(
            {
                "field_id": field_id,
                "year": int(year),
                "annual_precip_mm": float(group["PRECTOTCORR"].sum()),
                "season_precip_mm": float(season["PRECTOTCORR"].sum()),
                "season_gdd_c": float(season["gdd"].sum()),
                "season_mean_temp_c": float(season["T2M"].mean()),
                "season_hot_days": int((season["T2M_MAX"] > 30.0).sum()),
                "days_observed": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def monthly_climatology(weather: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly mean temperature and monthly precipitation totals by field-year."""
    if weather.empty:
        return pd.DataFrame(), pd.DataFrame()

    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month

    temperature = (
        frame.groupby(["field_id", "year", "month"], as_index=False)["T2M"].mean()
    )
    precipitation = (
        frame.groupby(["field_id", "year", "month"], as_index=False)["PRECTOTCORR"].sum()
    )
    return temperature, precipitation
