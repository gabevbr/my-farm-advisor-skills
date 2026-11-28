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
    continuous_corn,
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


if __name__ == "__main__":
    test_compactness_of_square_is_one()
    test_shannon_diversity()
    test_continuous_corn()
    test_daily_gdd_caps()
    test_season_mask()
    test_dominant_crop_and_margin()
    test_natural_key_orders_numbers()
    print("ok")
