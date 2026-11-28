"""Offline checks for the field EDA statistics helpers.

Run directly or under pytest:

    python my-farm-advisor/eda/field-eda/src/field_eda/tests/test_stats.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from field_eda.stats import (  # noqa: E402
    holm_adjust,
    kruskal_across_groups,
    pairwise_mannwhitney,
    spearman_with_ci,
    variance_share,
)


def _groups() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for name, center in (("A", 10.0), ("B", 12.0), ("C", 20.0)):
        for value in rng.normal(center, 1.0, 10):
            rows.append({"grower": name, "value": value})
    return pd.DataFrame(rows)


def test_holm_is_monotone_and_clipped() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert np.all(adjusted >= np.array([0.01, 0.04, 0.03]) - 1e-12)
    assert np.all(adjusted <= 1.0)
    assert adjusted[0] == np.min(adjusted)


def test_kruskal_detects_separated_groups() -> None:
    result = kruskal_across_groups(_groups(), "value", "grower")
    assert result["p_value"] < 0.01
    assert 0.0 <= result["effect_size"] <= 1.0
    assert result["n"] == 30


def test_pairwise_table_shape() -> None:
    table = pairwise_mannwhitney(_groups(), "value", "grower")
    assert len(table) == 3
    assert set(table.columns) >= {"p_holm", "rank_biserial", "significant_holm"}
    assert table["p_holm"].between(0, 1).all()


def test_spearman_ci_skipped_for_small_n() -> None:
    result = spearman_with_ci([1, 2, 3], [3, 2, 1])
    assert result["rho"] == -1.0
    assert np.isnan(result["ci_low"])


def test_spearman_ci_present_for_larger_n() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=30)
    y = x + rng.normal(scale=0.3, size=30)
    result = spearman_with_ci(x, y)
    assert result["rho"] > 0.8
    assert result["ci_low"] <= result["rho"] <= result["ci_high"]


def test_variance_share() -> None:
    frame = pd.DataFrame(
        {"group": ["A", "A", "B", "B"], "value": [1.0, 1.2, 10.0, 10.2]}
    )
    share = variance_share(frame, "value", "group")
    assert 0.99 <= share <= 1.0


if __name__ == "__main__":
    test_holm_is_monotone_and_clipped()
    test_kruskal_detects_separated_groups()
    test_pairwise_table_shape()
    test_spearman_ci_skipped_for_small_n()
    test_spearman_ci_present_for_larger_n()
    test_variance_share()
    print("ok")
