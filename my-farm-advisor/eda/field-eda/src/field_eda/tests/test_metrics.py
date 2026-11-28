"""Offline checks for the field EDA metric helpers.

Run directly or under pytest:

    python my-farm-advisor/eda/field-eda/src/field_eda/tests/test_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from field_eda.metrics import (  # noqa: E402
    SEASON_END_MD,
    SEASON_START_MD,
    boundary_metrics,
    class_diversity_per_field_year,
    class_share_by_grower_year,
    continuous_corn,
    crop_group,
    daily_gdd,
    dominant_crop,
    is_growing_season,
    natural_key,
    sequence_diversity,
    shannon_diversity,
)


def _square(size_m: float) -> Polygon:
    return Polygon(
        [(0, 0), (size_m, 0), (size_m, size_m), (0, size_m)]
    )


def test_compactness_of_square_is_one() -> None:
    frame = gpd.GeoDataFrame(
        {"field_id": ["a"], "area_ha_est": [100.0]},
        geometry=[_square(1000.0)],
        crs="EPSG:5070",
    )
    metrics = boundary_metrics(frame)
    # Polsby-Popper: a square scores pi/4; only a circle reaches 1.0.
    assert abs(metrics["compactness"].iloc[0] - np.pi / 4.0) < 1e-6
    assert abs(metrics["area_proj_ha"].iloc[0] - 100.0) < 1e-3
    assert abs(metrics["perimeter_m"].iloc[0] - 4000.0) < 1e-3


def test_shannon_diversity() -> None:
    assert shannon_diversity([5]) == 0.0
    assert abs(shannon_diversity([1, 1]) - np.log(2)) < 1e-12
    assert sequence_diversity(["Corn", "Corn", "Soybeans", "Soybeans"]) > 0.6


def test_continuous_corn() -> None:
    assert continuous_corn(["Corn"] * 5)
    assert not continuous_corn(["Corn", "Soybeans", "Corn"])
    assert not continuous_corn([])


def test_daily_gdd_caps() -> None:
    tmax = pd.Series([35.0, 5.0])
    tmin = pd.Series([15.0, -5.0])
    result = daily_gdd(tmax, tmin)
    assert abs(result.iloc[0] - 12.5) < 1e-9  # max capped at 30: (30+15)/2 - 10
    assert result.iloc[1] == 0.0


def test_season_mask() -> None:
    dates = pd.Series(pd.to_datetime(["2023-03-31", "2023-04-01", "2023-10-31", "2023-11-01"]))
    mask = is_growing_season(dates).tolist()
    assert mask == [False, True, True, False]
    assert SEASON_START_MD < SEASON_END_MD


def test_dominant_crop_and_margin() -> None:
    cdl = pd.DataFrame(
        {
            "field_id": ["a", "a", "a", "b", "b"],
            "year": [2023, 2023, 2023, 2023, 2023],
            "crop_name": ["Corn", "Soybeans", "Grass/Pasture", "Soybeans", "Corn"],
            "pct": [91.0, 6.0, 3.0, 55.0, 45.0],
        }
    )
    top = dominant_crop(cdl)
    first = top[top["field_id"] == "a"].iloc[0]
    assert first["crop_name"] == "Corn"
    assert abs(first["margin_pct"] - 85.0) < 1e-9
    second = top[top["field_id"] == "b"].iloc[0]
    assert second["crop_name"] == "Soybeans"
    assert abs(second["margin_pct"] - 10.0) < 1e-9


def test_natural_key_orders_numbers() -> None:
    ids = ["il-r10", "il-r2", "il-r1"]
    assert sorted(ids, key=natural_key) == ["il-r1", "il-r2", "il-r10"]


def test_class_diversity_counts_distinct_classes_per_field_year() -> None:
    cdl = pd.DataFrame(
        {
            "field_id": ["a", "a", "a", "b", "b"],
            "year": [2023, 2023, 2023, 2023, 2023],
            "crop_name": ["Corn", "Soybeans", "Forest", "Corn", "Fallow/Idle"],
            "pct": [91.0, 6.0, 3.0, 99.4, 0.6],
        }
    )
    diversity = class_diversity_per_field_year(cdl)
    first = diversity[diversity["field_id"] == "a"].iloc[0]
    assert first["distinct_classes"] == 3
    assert first["distinct_classes_1pct"] == 3  # Forest is 3%, so it clears the floor

    second = diversity[diversity["field_id"] == "b"].iloc[0]
    assert second["distinct_classes"] == 2
    # A 0.6% sliver is excluded by the 1% floor, which is the whole point of it.
    assert second["distinct_classes_1pct"] == 1


def test_class_diversity_keeps_empty_field_years() -> None:
    cdl = pd.DataFrame(
        {
            "field_id": ["a", "a"],
            "year": [2023, 2023],
            "crop_name": ["Corn", "Soybeans"],
            "pct": [np.nan, np.nan],
        }
    )
    diversity = class_diversity_per_field_year(cdl)
    # No class clears any floor, but the field-year must still be reported.
    assert list(diversity["field_id"]) == ["a"]
    assert int(diversity["distinct_classes"].iloc[0]) == 0


def test_crop_group_collapses_long_tail() -> None:
    assert crop_group("Corn") == "Corn"
    assert crop_group("Grass/Pasture") == "Grass/Pasture"
    assert crop_group("Forest") == "Other"
    assert crop_group("Winter Wheat") == "Other"


def test_class_share_by_grower_year_is_exclusive() -> None:
    cdl = pd.DataFrame(
        {
            "field_id": ["a", "a", "a", "b", "b"],
            "year": [2023, 2023, 2023, 2023, 2023],
            "crop_name": ["Corn", "Soybeans", "Forest", "Corn", "Forest"],
            "pct": [70.0, 20.0, 10.0, 60.0, 40.0],
            "pixel_count": [70, 20, 10, 60, 40],
        }
    )
    fields = pd.DataFrame({"field_id": ["a", "b"], "grower_name": ["G", "G"]})
    shares = class_share_by_grower_year(cdl, fields)

    total = shares[shares["year"] == 2023]["pct"].sum()
    assert abs(total - 100.0) < 1e-9
    corn = shares[(shares["year"] == 2023) & (shares["crop_group"] == "Corn")]
    assert abs(float(corn["pct"].iloc[0]) - 65.0) < 1e-9
    assert set(shares["unit"]) == {"pixel_count"}


if __name__ == "__main__":
    test_compactness_of_square_is_one()
    test_shannon_diversity()
    test_continuous_corn()
    test_daily_gdd_caps()
    test_season_mask()
    test_dominant_crop_and_margin()
    test_natural_key_orders_numbers()
    test_class_diversity_counts_distinct_classes_per_field_year()
    test_class_diversity_keeps_empty_field_years()
    test_crop_group_collapses_long_tail()
    test_class_share_by_grower_year_is_exclusive()
    print("ok")
