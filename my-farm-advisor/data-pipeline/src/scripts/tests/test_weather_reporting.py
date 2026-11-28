"""Regression test for annual precipitation in weather variability summaries.

Bug: ``summarize_weather_variability`` reported ``annual_precip_mm`` as a flat
sum over every row of the table, so a 5-year extract produced the five-year
total labelled as an annual value (4,591 mm instead of 918 mm/yr on a real
Illinois field). It now sums per field-year and averages across years.

Written as plain asserts so it runs under pytest *and* directly:

    python data-pipeline/src/scripts/tests/test_weather_reporting.py

Convention: src/scripts/tests/ is the repo's pytest dir (see
test_ingest_user_boundaries.py). No network, no fixtures on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SKILL_SRC = Path(__file__).resolve().parents[4] / "weather" / "nasa-power-weather" / "src"
sys.path.insert(0, str(SKILL_SRC))

from weather_reporting import summarize_weather_variability  # noqa: E402

DAILY_MM = 2.0
DAYS = 365


def _weather(field_id: str, years: list[int], daily_mm: float = DAILY_MM) -> pd.DataFrame:
    rows = []
    for year in years:
        for doy in range(1, DAYS + 1):
            rows.append(
                {
                    "field_id": field_id,
                    "date": pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=doy - 1),
                    "T2M": 12.0,
                    "T2M_MAX": 20.0,
                    "T2M_MIN": 4.0,
                    "PRECTOTCORR": daily_mm,
                }
            )
    return pd.DataFrame(rows)


def test_annual_precip_is_mean_of_year_totals() -> None:
    weather = pd.concat(
        [_weather("a", [2021, 2022, 2023]), _weather("b", [2021, 2022, 2023])],
        ignore_index=True,
    )
    summary = summarize_weather_variability(weather).set_index("field_id")

    expected = DAILY_MM * DAYS  # 730 mm in every year
    for field_id in ("a", "b"):
        got = float(summary.loc[field_id, "annual_precip_mm"])
        assert abs(got - expected) < 1e-6, (
            f"{field_id}: annual_precip_mm={got} != {expected} "
            "(a flat sum over all rows would give %s)" % (expected * 3)
        )
        assert int(summary.loc[field_id, "years"]) == 3
        assert abs(float(summary.loc[field_id, "avg_precip_mm"]) - DAILY_MM) < 1e-6


def test_annual_precip_tracks_year_variation() -> None:
    # 2021 is dry (1 mm/day), 2022 is wet (3 mm/day) -> mean annual total is
    # (365 + 1095) / 2 = 730 mm, which equals the constant-rate case by design;
    # this guards the averaging path rather than a single year's value.
    weather = pd.concat(
        [_weather("a", [2021], daily_mm=1.0), _weather("a", [2022], daily_mm=3.0)],
        ignore_index=True,
    )
    summary = summarize_weather_variability(weather).set_index("field_id")
    got = float(summary.loc["a", "annual_precip_mm"])
    assert abs(got - 730.0) < 1e-6, f"annual_precip_mm={got}, expected 730.0"


if __name__ == "__main__":
    test_annual_precip_is_mean_of_year_totals()
    test_annual_precip_tracks_year_variation()
    print("PASS: annual precipitation is a mean of per-year totals")
