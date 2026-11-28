"""Command line entry point for the field EDA subskill."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .analysis import assemble, boundary_stats, cdl_stats, weather_stats
from .figures import (
    figure_area_by_grower,
    figure_climatology,
    figure_composition,
    figure_precip_vs_gdd,
    figure_rotation_heatmap,
    figure_shape_vs_area,
)
from .loaders import LoadError, discover_farms, resolve_data_root
from .manifest import build_manifest, write_manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Static field-level EDA for My Farm Advisor growers: boundary shape, "
            "CDL rotation/composition, and weather comparisons."
        )
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Runtime base containing data-pipeline/growers; defaults to DATA_PIPELINE_DATA_ROOT",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory; defaults to <data-root>/eda/field-eda/<run-id>",
    )
    parser.add_argument(
        "--growers",
        nargs="+",
        default=None,
        help="Optional grower slugs to include (default: every grower under the runtime)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the timestamped run id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and validate inputs, print a summary, write nothing",
    )
    parser.add_argument(
        "--no-figures",
        action="store_true",
        help="Write tables and manifest only",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data_root = resolve_data_root(args.data_root)
        farms = discover_farms(data_root, args.growers)
    except LoadError as error:
        print(f"error: {error}")
        return 2

    dataset = assemble(farms)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = (
        Path(args.out).expanduser()
        if args.out
        else data_root / "eda" / "field-eda" / run_id
    )

    _print_summary(farms, dataset, out_root, args.dry_run)
    if dataset.warnings:
        print(f"\n{len(dataset.warnings)} warning(s):")
        for message in dataset.warnings:
            print(f"  - {message}")

    if args.dry_run:
        return 0

    tables_dir = out_root / "tables"
    figures_dir = out_root / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)

    tables: list[Path] = []
    field_metrics = tables_dir / "field-metrics.csv"
    dataset.fields.to_csv(field_metrics, index=False)
    tables.append(field_metrics)

    for name, frame in (
        ("stats-boundaries.csv", boundary_stats(dataset.fields)),
        ("stats-cdl.csv", cdl_stats(dataset.fields)),
        ("stats-weather.csv", weather_stats(dataset.field_years, dataset.fields)),
    ):
        path = tables_dir / name
        frame.to_csv(path, index=False)
        tables.append(path)

    figures: list[Path] = []
    if not args.no_figures:
        cdl_long = pd.concat([farm.cdl for farm in farms], ignore_index=True)
        weather_long = pd.concat([farm.weather for farm in farms], ignore_index=True)
        cdl_years = sorted(int(year) for year in cdl_long["year"].unique())
        figures = [
            figure_area_by_grower(dataset.fields, figures_dir / "F1-boundaries-area-by-grower.png"),
            figure_shape_vs_area(dataset.fields, figures_dir / "F2-boundaries-shape-vs-area.png"),
            figure_rotation_heatmap(
                dataset.fields,
                figures_dir / "F3-cdl-rotation-heatmap.png",
                years=cdl_years,
            ),
            figure_composition(dataset.fields, cdl_long, figures_dir / "F4-cdl-composition.png"),
            figure_climatology(dataset.fields, weather_long, figures_dir / "F5-weather-climatology.png"),
            figure_precip_vs_gdd(dataset.field_years, figures_dir / "F6-weather-precip-vs-gdd.png"),
        ]

    payload = build_manifest(
        run_id=run_id,
        data_root=data_root,
        farms=farms,
        field_table=dataset.fields,
        warnings=dataset.warnings,
        figures=figures,
        tables=tables,
        out_root=out_root,
    )
    write_manifest(out_root / "manifest.json", payload)

    print(f"\nwrote {len(figures)} figure(s) and {len(tables)} table(s) to {out_root}")
    return 0


def _print_summary(farms, dataset, out_root: Path, dry_run: bool) -> None:
    print(f"farms loaded: {len(farms)}")
    header = f"{'grower':14} {'farm':24} {'fields':>6} {'weather rows':>13} {'cdl years':>10}"
    print(header)
    for farm in farms:
        years = sorted(farm.cdl["year"].unique().tolist()) if not farm.cdl.empty else []
        span = f"{years[0]}-{years[-1]}" if years else "-"
        print(
            f"{farm.grower_slug:14} {farm.farm_slug:24} {len(farm.fields):>6} "
            f"{len(farm.weather):>13} {span:>10}"
        )
    print(
        f"fields: {len(dataset.fields)} | field-years: {len(dataset.field_years)} | "
        f"out: {'(dry run)' if dry_run else out_root}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
