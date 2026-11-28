"""Checks for the field EDA figure helpers that aggregate weather.

Run directly or under pytest:

    python my-farm-advisor/eda/field-eda/src/field_eda/tests/test_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from field_eda.figures import _monthly_by_grower  # noqa: E402
from field_eda.figures_map import scripts_lib_dir  # noqa: E402


def test_monthly_precip_averages_fields_not_sums() -> None:
    """Fields share one grid, so their identical rain must not add up 10x."""
    dates = pd.date_range("2023-07-01", periods=2, freq="D")
    rows = []
    for field_id in ("f1", "f2"):
        for date, precip in zip(dates, (10.0, 5.0)):
            rows.append(
                {
                    "field_id": field_id,
                    "date": date,
                    "T2M": 20.0,
                    "PRECTOTCORR": precip,
                }
            )
    weather = pd.DataFrame(rows)
    fields = pd.DataFrame({"field_id": ["f1", "f2"], "grower_name": ["G", "G"]})

    monthly = _monthly_by_grower(fields, weather)
    july = monthly[(monthly["month"] == 7)].iloc[0]
    assert abs(july["precip_total"] - 15.0) < 1e-9
    assert abs(july["temp_mean"] - 20.0) < 1e-9


def test_scripts_lib_dir_exists() -> None:
    lib = scripts_lib_dir()
    assert (lib / "field_frame.py").is_file()
    assert (lib / "basemap.py").is_file()


if __name__ == "__main__":
    test_monthly_precip_averages_fields_not_sums()
    test_scripts_lib_dir_exists()
    print("ok")
