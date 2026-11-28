"""Offline checks for the run manifest.

Run directly or under pytest:

    python my-farm-advisor/eda/field-eda/src/field_eda/tests/test_manifest.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from field_eda.manifest import build_manifest  # noqa: E402


def _farm(weather_dates: list[str], cdl_years: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        grower_slug="stub-grower",
        grower_name="Stub Grower",
        farm_slug="stub-farm",
        fields=pd.DataFrame({"field_id": ["a", "b"]}),
        weather=pd.DataFrame({"date": pd.to_datetime(weather_dates)}),
        cdl=pd.DataFrame({"year": cdl_years}),
        inputs=[],
    )


def _manifest(farm: SimpleNamespace) -> dict:
    return build_manifest(
        run_id="test-run",
        data_root=Path("/tmp/data-root"),
        farms=[farm],
        field_table=pd.DataFrame(
            {"grower_slug": ["stub-grower", "stub-grower"], "farm_slug": ["stub-farm"] * 2}
        ),
        warnings=[],
        figures=[],
        tables=[],
        out_root=Path("/tmp/out"),
    )


def test_manifest_records_year_spans_from_the_loaded_frames() -> None:
    # CDL and weather cover different windows, so a consumer must be able to
    # read both from the manifest rather than assume they match.
    farm = _farm(
        ["2021-04-01", "2023-07-15", "2025-10-31"],
        [2019, 2020, 2023],
    )
    grower = _manifest(farm)["growers"][0]
    assert grower["cdl_years"] == [2019, 2020, 2023]
    assert grower["weather_years"] == [2021, 2023, 2025]


def test_manifest_year_lists_are_empty_without_rows() -> None:
    farm = _farm([], [])
    grower = _manifest(farm)["growers"][0]
    assert grower["cdl_years"] == []
    assert grower["weather_years"] == []


if __name__ == "__main__":
    test_manifest_records_year_spans_from_the_loaded_frames()
    test_manifest_year_lists_are_empty_without_rows()
    print("ok")
