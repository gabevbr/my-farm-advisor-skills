"""Small-sample statistics for the field EDA.

The runtime has 10 fields per grower and 5 years of weather. That rules out
normal-theory tests: everything here is rank based, with effect sizes and Holm
correction, and the docs state the pseudoreplication caveat for weather.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def holm_adjust(p_values) -> np.ndarray:
    """Holm step-down adjustment, monotone and clipped to 1."""
    values = np.asarray(p_values, dtype=float)
    if values.size == 0:
        return values
    order = np.argsort(values)
    adjusted = np.empty_like(values)
    running = 0.0
    total = len(values)
    for position, index in enumerate(order):
        candidate = min(1.0, (total - position) * values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def kruskal_across_groups(frame: pd.DataFrame, value: str, group: str) -> dict:
    """Kruskal-Wallis omnibus test with epsilon-squared effect size."""
    groups = [
        sub[value].dropna().to_numpy()
        for _, sub in frame.groupby(group, sort=True)
        if sub[value].notna().any()
    ]
    if len(groups) < 2:
        return {"test": "kruskal-wallis", "statistic": float("nan"), "p_value": float("nan"),
                "effect_size": float("nan"), "n": int(sum(len(g) for g in groups)),
                "groups": len(groups)}
    statistic, p_value = scipy_stats.kruskal(*groups)
    n = sum(len(group) for group in groups)
    k = len(groups)
    epsilon_squared = (statistic - k + 1) / (n - k) if n > k else float("nan")
    return {
        "test": "kruskal-wallis",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "effect_size": float(min(1.0, max(0.0, epsilon_squared))),
        "effect_metric": "epsilon_squared",
        "n": int(n),
        "groups": int(k),
    }


def pairwise_mannwhitney(frame: pd.DataFrame, value: str, group: str) -> pd.DataFrame:
    """Pairwise Mann-Whitney U with Holm-adjusted p and rank-biserial effect."""
    names = sorted(frame[group].dropna().unique())
    records: list[dict] = []
    for first, second in combinations(names, 2):
        left = frame.loc[frame[group] == first, value].dropna().to_numpy()
        right = frame.loc[frame[group] == second, value].dropna().to_numpy()
        if len(left) < 2 or len(right) < 2:
            continue
        result = scipy_stats.mannwhitneyu(left, right, alternative="two-sided")
        rank_biserial = 1.0 - (2.0 * result.statistic) / (len(left) * len(right))
        records.append(
            {
                "group": group,
                "value": value,
                "group_a": first,
                "group_b": second,
                "n_a": len(left),
                "n_b": len(right),
                "u_statistic": float(result.statistic),
                "p_value": float(result.pvalue),
                "rank_biserial": float(rank_biserial),
            }
        )
    table = pd.DataFrame(records)
    if not table.empty:
        table["p_holm"] = holm_adjust(table["p_value"].to_numpy())
        table["significant_holm"] = table["p_holm"] < 0.05
    return table


def spearman_with_ci(x, y, *, seed: int = 20261127, iterations: int = 2000) -> dict:
    """Spearman rho with a seeded bootstrap CI (skipped when n < 10)."""
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)
    mask = np.isfinite(x_values) & np.isfinite(y_values)
    x_values, y_values = x_values[mask], y_values[mask]
    n = len(x_values)
    if n < 3:
        return {"rho": float("nan"), "p_value": float("nan"), "ci_low": float("nan"),
                "ci_high": float("nan"), "n": n}

    rho, p_value = scipy_stats.spearmanr(x_values, y_values)
    ci_low = ci_high = float("nan")
    if n >= 10:
        rng = np.random.default_rng(seed)
        draws: list[float] = []
        for _ in range(iterations):
            index = rng.integers(0, n, n)
            if len(np.unique(index)) < 3:
                continue
            draw = scipy_stats.spearmanr(x_values[index], y_values[index]).statistic
            if np.isfinite(draw):
                draws.append(float(draw))
        if draws:
            ci_low, ci_high = np.percentile(draws, [2.5, 97.5])
    return {
        "rho": float(rho),
        "p_value": float(p_value),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "n": int(n),
    }


def variance_share(frame: pd.DataFrame, value: str, group: str) -> float:
    """Share of total variance sitting between groups (eta squared)."""
    values = frame[value].dropna()
    if values.empty:
        return float("nan")
    grand_mean = values.mean()
    total = ((values - grand_mean) ** 2).sum()
    if total == 0:
        return float("nan")
    grouped = frame.dropna(subset=[value]).groupby(group)[value]
    between = (grouped.size() * (grouped.mean() - grand_mean) ** 2).sum()
    return float(between / total)


def describe_groups(frame: pd.DataFrame, value: str, group: str) -> pd.DataFrame:
    """Count, median, IQR, min, max per group."""
    rows = []
    for name, sub in frame.groupby(group, sort=True):
        series = sub[value].dropna()
        if series.empty:
            continue
        q1, median, q3 = np.percentile(series, [25, 50, 75])
        rows.append(
            {
                "group": name,
                "n": int(series.size),
                "median": float(median),
                "q1": float(q1),
                "q3": float(q3),
                "min": float(series.min()),
                "max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)
