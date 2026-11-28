"""Assemble per-field metrics and the three category statistics tables."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .loaders import FarmData
from .metrics import (
    boundary_metrics,
    continuous_corn,
    dominant_crop,
    natural_key,
    sequence_diversity,
    weather_season_stats,
)
from .stats import (
    describe_groups,
    kruskal_across_groups,
    pairwise_mannwhitney,
    spearman_with_ci,
    variance_share,
)

STATS_COLUMNS = [
    "analysis",
    "grouping",
    "comparison",
    "test",
    "n",
    "statistic",
    "p_value",
    "p_holm",
    "effect_size",
    "effect_metric",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "significant",
    "notes",
]


@dataclass
class Dataset:
    fields: pd.DataFrame
    field_years: pd.DataFrame
    warnings: list[str]


def assemble(farms: list[FarmData]) -> Dataset:
    """Build one field table and one field-year weather table across farms."""
    field_rows: list[dict] = []
    field_year_frames: list[pd.DataFrame] = []
    warnings: list[str] = []

    for farm in farms:
        warnings.extend(f"{farm.label}: {message}" for message in farm.warnings)

        with_metrics = boundary_metrics(farm.fields)
        if not with_metrics.empty:
            mismatch = (
                (with_metrics["area_proj_ha"] - with_metrics["area_ha_est"]).abs()
                / with_metrics["area_ha_est"]
            )
            bad = with_metrics.loc[mismatch > 0.02, "field_id"].tolist()
            if bad:
                warnings.append(
                    f"{farm.label}: projected area differs >2% from area_ha_est for {bad}"
                )

        dominant = dominant_crop(farm.cdl)
        all_years = sorted(dominant["year"].unique().tolist()) if not dominant.empty else []

        season = weather_season_stats(farm.weather)
        if not season.empty:
            season = season.assign(
                grower_slug=farm.grower_slug,
                grower_name=farm.grower_name,
                farm_slug=farm.farm_slug,
                state=farm.fields["state"].iloc[0] if "state" in farm.fields else "",
            )
            field_year_frames.append(season)

        for record in with_metrics.to_dict("records"):
            field_id = str(record["field_id"])
            history = (
                dominant[dominant["field_id"] == field_id].sort_values("year")
                if not dominant.empty
                else dominant
            )
            sequence = history["crop_name"].astype(str).tolist()
            latest_year = int(history["year"].max()) if not history.empty else None
            latest = history[history["year"] == latest_year] if latest_year else history
            purity = float(latest["pct"].iloc[0]) if not latest.empty else np.nan
            unclassified = (
                float(100.0 - history[history["year"] == latest_year]["pct"].sum())
                if latest_year
                else np.nan
            )

            field_season = season[season["field_id"] == field_id] if not season.empty else season
            means = {
                "season_precip_mm_mean": field_season["season_precip_mm"].mean(),
                "annual_precip_mm_mean": field_season["annual_precip_mm"].mean(),
                "season_gdd_c_mean": field_season["season_gdd_c"].mean(),
                "season_mean_temp_c_mean": field_season["season_mean_temp_c"].mean(),
                "hot_days_mean": field_season["season_hot_days"].mean(),
                "weather_years": field_season["year"].nunique(),
            }

            row = {
                "grower_slug": farm.grower_slug,
                "grower_name": farm.grower_name,
                "farm_slug": farm.farm_slug,
                "farm_name": farm.farm_name,
                "state": record.get("state", ""),
                "county": record.get("county", ""),
                "field_id": field_id,
                "csb_id": str(record.get("csb_id", "")),
                "crop_2025": record.get("crop", ""),
                "area_ha": float(record.get("area_ha_est", np.nan)),
                "area_proj_ha": float(record.get("area_proj_ha", np.nan)),
                "perimeter_m": float(record.get("perimeter_m", np.nan)),
                "compactness": float(record.get("compactness", np.nan)),
                "vertices": int(record.get("vertices", 0)),
                "multipart": bool(record.get("multipart", False)),
                "rotation_years": int(len(sequence)),
                "rotation_sequence": " -> ".join(sequence),
                "rotation_diversity": sequence_diversity(sequence),
                "continuous_corn": continuous_corn(sequence),
                "latest_cdl_year": latest_year,
                "latest_crop": latest["crop_name"].iloc[0] if not latest.empty else None,
                "latest_purity_pct": purity,
                "latest_unclassified_pct": unclassified,
                "cdl_years_available": int(history["year"].nunique()) if not history.empty else 0,
                **means,
            }
            for year in all_years:
                match = history[history["year"] == year]
                row[f"crop_{year}"] = match["crop_name"].iloc[0] if not match.empty else None
            field_rows.append(row)

    fields = pd.DataFrame(field_rows)
    if not fields.empty:
        fields = fields.sort_values(
            ["grower_name", "field_id"],
            key=lambda series: series.map(
                lambda value: natural_key(value) if isinstance(value, str) else value
            ),
        ).reset_index(drop=True)

    field_years = (
        pd.concat(field_year_frames, ignore_index=True)
        if field_year_frames
        else pd.DataFrame()
    )
    return Dataset(fields=fields, field_years=field_years, warnings=warnings)


def _blank_row(**values) -> dict:
    row = {column: np.nan for column in STATS_COLUMNS}
    row.update(values)
    return row


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in STATS_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame[STATS_COLUMNS]


def boundary_stats(fields: pd.DataFrame) -> pd.DataFrame:
    """A1: is field area different across growers, and how big is the effect?"""
    rows: list[dict] = []
    if fields.empty:
        return _frame(rows)

    for summary in describe_groups(fields, "area_ha", "grower_name").to_dict("records"):
        rows.append(_blank_row(
            analysis="describe",
            grouping="grower_name",
            comparison=summary["group"],
            test="summary",
            n=summary["n"],
            median=summary["median"],
            q1=summary["q1"],
            q3=summary["q3"],
            min=summary["min"],
            max=summary["max"],
            notes="area_ha_est from the boundary file",
        ))

    omnibus = kruskal_across_groups(fields, "area_ha", "grower_name")
    rows.append(_blank_row(
        analysis="omnibus",
        grouping="grower_name",
        comparison="all growers",
        test=omnibus["test"],
        n=omnibus["n"],
        statistic=omnibus["statistic"],
        p_value=omnibus["p_value"],
        effect_size=omnibus["effect_size"],
        effect_metric=omnibus.get("effect_metric", ""),
        significant=bool(omnibus["p_value"] < 0.05) if np.isfinite(omnibus["p_value"]) else None,
        notes="n=10 fields per grower; nonparametric because of small groups",
    ))

    pairwise = pairwise_mannwhitney(fields, "area_ha", "grower_name")
    for pair in pairwise.to_dict("records"):
        rows.append(_blank_row(
            analysis="pairwise",
            grouping="grower_name",
            comparison=f"{pair['group_a']} vs {pair['group_b']}",
            test="mann-whitney-u",
            n=int(pair["n_a"] + pair["n_b"]),
            statistic=pair["u_statistic"],
            p_value=pair["p_value"],
            p_holm=pair["p_holm"],
            effect_size=pair["rank_biserial"],
            effect_metric="rank_biserial",
            significant=bool(pair["significant_holm"]),
            notes="Holm-adjusted; effect sign is group_a relative to group_b",
        ))
    return _frame(rows)


def cdl_stats(fields: pd.DataFrame) -> pd.DataFrame:
    """A2: rotation diversity across growers plus continuous-corn counts."""
    rows: list[dict] = []
    if fields.empty:
        return _frame(rows)

    for summary in describe_groups(
        fields, "rotation_diversity", "grower_name"
    ).to_dict("records"):
        rows.append(_blank_row(
            analysis="describe",
            grouping="grower_name",
            comparison=summary["group"],
            test="summary",
            n=summary["n"],
            median=summary["median"],
            q1=summary["q1"],
            q3=summary["q3"],
            min=summary["min"],
            max=summary["max"],
            notes="Shannon diversity of the dominant crop sequence (2019-2023)",
        ))

    for grower, group in fields.groupby("grower_name", sort=True):
        rows.append(_blank_row(
            analysis="continuous-corn",
            grouping="grower_name",
            comparison=grower,
            test="count",
            n=int(len(group)),
            statistic=int(group["continuous_corn"].sum()),
            effect_size=float(group["continuous_corn"].mean()),
            effect_metric="share_of_fields",
            notes="fields whose dominant crop was Corn in every available year",
        ))

    omnibus = kruskal_across_groups(fields, "rotation_diversity", "grower_name")
    rows.append(_blank_row(
        analysis="omnibus",
        grouping="grower_name",
        comparison="all growers",
        test=omnibus["test"],
        n=omnibus["n"],
        statistic=omnibus["statistic"],
        p_value=omnibus["p_value"],
        effect_size=omnibus["effect_size"],
        effect_metric=omnibus.get("effect_metric", ""),
        significant=bool(omnibus["p_value"] < 0.05) if np.isfinite(omnibus["p_value"]) else None,
        notes="n=10 fields per grower; effective history is 5 years per field",
    ))

    pairwise = pairwise_mannwhitney(fields, "rotation_diversity", "grower_name")
    for pair in pairwise.to_dict("records"):
        rows.append(_blank_row(
            analysis="pairwise",
            grouping="grower_name",
            comparison=f"{pair['group_a']} vs {pair['group_b']}",
            test="mann-whitney-u",
            n=int(pair["n_a"] + pair["n_b"]),
            statistic=pair["u_statistic"],
            p_value=pair["p_value"],
            p_holm=pair["p_holm"],
            effect_size=pair["rank_biserial"],
            effect_metric="rank_biserial",
            significant=bool(pair["significant_holm"]),
            notes="Holm-adjusted; diversity computed from the dominant sequence",
        ))
    return _frame(rows)


def weather_stats(field_years: pd.DataFrame, fields: pd.DataFrame) -> pd.DataFrame:
    """A3: precipitation-GDD correlation and the within/between variance split."""
    rows: list[dict] = []
    if field_years.empty:
        return _frame(rows)

    pooled = spearman_with_ci(
        field_years["season_precip_mm"], field_years["season_gdd_c"]
    )
    rows.append(_blank_row(
        analysis="correlation",
        grouping="all growers",
        comparison="season_precip_mm vs season_gdd_c",
        test="spearman",
        n=pooled["n"],
        statistic=pooled["rho"],
        p_value=pooled["p_value"],
        effect_size=pooled["rho"],
        effect_metric="rho",
        notes=(
            f"pooled field-years, bootstrap 95% CI "
            f"[{pooled['ci_low']:.2f}, {pooled['ci_high']:.2f}]; "
            "effective n is 5 years per grower, so p is indicative only"
        ),
    ))

    for grower, group in field_years.groupby("grower_name", sort=True):
        result = spearman_with_ci(group["season_precip_mm"], group["season_gdd_c"])
        rows.append(_blank_row(
            analysis="correlation",
            grouping="grower_name",
            comparison=f"{grower}: season_precip_mm vs season_gdd_c",
            test="spearman",
            n=result["n"],
            statistic=result["rho"],
            p_value=result["p_value"],
            effect_size=result["rho"],
            effect_metric="rho",
            notes=(
                f"field-years within one grower; 10 fields share one climate grid, "
                f"so effective n is the 5 years"
            ),
        ))

    farm_years = (
        field_years.groupby(["grower_name", "farm_slug", "year"], as_index=False)[
            ["season_precip_mm", "season_gdd_c"]
        ]
        .mean()
    )
    for value in ["season_precip_mm", "season_gdd_c"]:
        share = variance_share(farm_years, value, "grower_name")
        rows.append(_blank_row(
            analysis="variance-share",
            grouping="grower_name",
            comparison=value,
            test="eta-squared",
            n=int(len(farm_years)),
            effect_size=share,
            effect_metric="between_grower_share",
            notes=(
                "computed on farm-year means (3 growers x 5 years) to avoid "
                "treating 10 fields as independent climate samples"
            ),
        ))
    return _frame(rows)
