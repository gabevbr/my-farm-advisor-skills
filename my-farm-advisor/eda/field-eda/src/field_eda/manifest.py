"""Run manifest: inputs, counts, environment, and output inventory."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd
import scipy


def sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    run_id: str,
    data_root: Path,
    farms,
    field_table: pd.DataFrame,
    warnings: list[str],
    figures: list[Path],
    tables: list[Path],
    out_root: Path,
) -> dict:
    inputs = []
    for farm in farms:
        for path in farm.inputs:
            try:
                relative = path.relative_to(data_root)
            except ValueError:
                relative = path
            stat = path.stat()
            inputs.append(
                {
                    "path": str(relative),
                    "bytes": stat.st_size,
                    "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "sha256": sha256(path),
                }
            )

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_root": str(data_root),
        "growers": [
            {
                "slug": farm.grower_slug,
                "name": farm.grower_name,
                "farm": farm.farm_slug,
                "fields": int(len(farm.fields)),
                "weather_rows": int(len(farm.weather)),
                "cdl_rows": int(len(farm.cdl)),
                "cdl_years": sorted(int(year) for year in farm.cdl["year"].unique())
                if not farm.cdl.empty
                else [],
                "weather_years": sorted(
                    int(year)
                    for year in pd.to_datetime(farm.weather["date"]).dt.year.unique()
                )
                if not farm.weather.empty
                else [],
            }
            for farm in farms
        ],
        "counts": {
            "fields": int(len(field_table)),
            "growers": int(field_table["grower_slug"].nunique()),
            "farms": int(field_table["farm_slug"].nunique()),
        },
        "outputs": {
            "root": str(out_root),
            "figures": [path.name for path in figures],
            "tables": [path.name for path in tables],
        },
        "warnings": warnings,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "geopandas": gpd.__version__,
            "matplotlib": matplotlib.__version__,
            "scipy": scipy.__version__,
        },
    }


def write_manifest(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
