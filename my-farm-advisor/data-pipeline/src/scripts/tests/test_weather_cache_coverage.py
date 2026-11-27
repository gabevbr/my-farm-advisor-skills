"""Regression test for the farm weather cache coverage check.

Bug: ``download_weather.py`` reused an existing farm weather CSV whenever the
file existed, ignoring which fields it covered. When a farm grew (Assignment 1
3-field farms expanded to 10 fields in Assignment 2) the cached table was
re-staged, and the seven new fields ended up with header-only
``weather/daily_weather.csv`` files while the pipeline reported success.

``_missing_cache_fields`` is now part of the cache contract: a cached table is
reusable only when it covers every field in the farm boundary file.

Run directly or under pytest (no network, no fixtures on disk):

    python data-pipeline/src/scripts/tests/test_weather_cache_coverage.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "lib"))

# Importing the ingest module resolves canonical runtime paths, which only need
# an absolute root. Point it at a throwaway dir; the test touches no files.
os.environ.setdefault(
    "DATA_PIPELINE_DATA_ROOT", Path(tempfile.gettempdir(), "mfa-weather-cache-test").as_posix()
)

from ingest.download_weather import _missing_cache_fields  # noqa: E402


def _square(x: float) -> Polygon:
    return Polygon([(x, 40.0), (x + 0.01, 40.0), (x + 0.01, 40.01), (x, 40.01)])


def _fields(*field_ids: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"field_id": list(field_ids)},
        geometry=[_square(index * 0.02) for index in range(len(field_ids))],
        crs="EPSG:4326",
    )


def _weather(*field_ids: str) -> pd.DataFrame:
    rows = [
        {
            "field_id": field_id,
            "date": pd.Timestamp("2021-01-01"),
            "T2M": 1.0,
        }
        for field_id in field_ids
    ]
    return pd.DataFrame(rows)


def test_full_coverage_is_reusable() -> None:
    assert _missing_cache_fields(_weather("il-r1", "il-r2"), _fields("il-r1", "il-r2")) == []


def test_new_fields_invalidate_the_cache() -> None:
    missing = _missing_cache_fields(
        _weather("il-r1", "il-r2", "il-r3"),
        _fields("il-r1", "il-r2", "il-r3", "il-r4", "il-r5"),
    )
    assert missing == ["il-r4", "il-r5"]


def test_id_dtype_does_not_matter() -> None:
    weather = _weather("ia-r1")
    weather["field_id"] = weather["field_id"].astype("string")
    assert _missing_cache_fields(weather, _fields("ia-r1")) == []


def test_table_without_field_id_covers_nothing() -> None:
    empty = pd.DataFrame(columns=["date", "T2M"])
    assert _missing_cache_fields(empty, _fields("ne-r1", "ne-r2")) == ["ne-r1", "ne-r2"]


if __name__ == "__main__":
    test_full_coverage_is_reusable()
    test_new_fields_invalidate_the_cache()
    test_id_dtype_does_not_matter()
    test_table_without_field_id_covers_nothing()
    print("ok")
