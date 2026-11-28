"""Read-only loaders for canonical My Farm Advisor runtime tables.

Inputs are discovered by glob, never by hard-coded farm prefixes: the runtime
uses ``illinois_demo``, ``iowa`` and ``nebraska_demo`` for the same three table
families, so prefix guessing would silently drop a farm.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

BOUNDARY_COLUMNS = (
    "field_id",
    "area_ha_est",
    "crop",
    "csb_id",
    "county",
    "state_fips",
    "county_fips",
    "geometry",
)
WEATHER_COLUMNS = (
    "field_id",
    "date",
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "RH2M",
    "WS10M",
)
CDL_COLUMNS = ("field_id", "year", "crop_name", "pct")
CDL_PATTERN = re.compile(r"_(?P<year>\d{4})_cdl\.csv$")


class LoadError(RuntimeError):
    """Raised when the runtime layout or a required table is unusable."""


@dataclass
class FarmData:
    grower_slug: str
    grower_name: str
    farm_slug: str
    farm_name: str
    root: Path
    fields: gpd.GeoDataFrame
    weather: pd.DataFrame
    cdl: pd.DataFrame
    rotation: pd.DataFrame | None
    inputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.grower_slug}/{self.farm_slug}"


def resolve_data_root(raw: str | None) -> Path:
    """Resolve the runtime base directory holding ``data-pipeline/growers``."""
    if raw:
        candidate = Path(raw).expanduser()
    else:
        import os

        env = os.environ.get("DATA_PIPELINE_DATA_ROOT")
        if not env:
            raise LoadError(
                "Pass --data-root or set DATA_PIPELINE_DATA_ROOT to the runtime base "
                "(the directory that contains data-pipeline/growers)."
            )
        candidate = Path(env).expanduser()

    if (candidate / "data-pipeline" / "growers").is_dir():
        return candidate / "data-pipeline"
    if (candidate / "growers").is_dir():
        return candidate
    raise LoadError(f"No growers directory found under {candidate}")


def discover_farms(
    data_root: Path, growers: list[str] | None = None
) -> list[FarmData]:
    """Load every farm (or the requested grower slugs) into memory."""
    growers_dir = data_root / "growers"
    farms: list[FarmData] = []
    for grower_dir in sorted(path for path in growers_dir.iterdir() if path.is_dir()):
        if growers and grower_dir.name not in growers:
            continue
        grower_name = _grower_name(grower_dir)
        farms_dir = grower_dir / "farms"
        if not farms_dir.is_dir():
            continue
        for farm_dir in sorted(path for path in farms_dir.iterdir() if path.is_dir()):
            farms.append(_load_farm(grower_dir, farm_dir, grower_name))
    if not farms:
        raise LoadError(f"No farms matched under {growers_dir}")
    farms.sort(key=lambda farm: (farm.grower_name, farm.farm_slug))
    return farms


def _grower_name(grower_dir: Path) -> str:
    metadata = _read_json(grower_dir / "grower.json")
    return str(metadata.get("display_name") or grower_dir.name)


def _farm_name(farm_dir: Path) -> str:
    metadata = _read_json(farm_dir / "farm.json")
    return str(metadata.get("display_name") or metadata.get("farm_name") or farm_dir.name)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_farm(grower_dir: Path, farm_dir: Path, grower_name: str) -> FarmData:
    warnings: list[str] = []
    inputs: list[Path] = []

    boundary_path = farm_dir / "boundary" / "field_boundaries.geojson"
    if not boundary_path.is_file():
        raise LoadError(f"{farm_dir.name}: missing {boundary_path}")
    fields = gpd.read_file(boundary_path)
    inputs.append(boundary_path)
    _require_columns(fields, BOUNDARY_COLUMNS, boundary_path)

    if fields.crs is None:
        raise LoadError(f"{boundary_path}: boundary has no CRS")
    if fields.crs.to_string() != "EPSG:4326":
        warnings.append(
            f"boundary CRS is {fields.crs.to_string()}, expected EPSG:4326; "
            "projected metrics still use EPSG:5070"
        )

    fields["field_id"] = fields["field_id"].astype(str)
    fields["crop"] = fields["crop"].astype(str)
    if fields["field_id"].duplicated().any():
        duplicates = sorted(fields.loc[fields["field_id"].duplicated(), "field_id"])
        warnings.append(f"duplicate field_id in boundary: {duplicates}")
    if fields["csb_id"].duplicated().any():
        duplicates = sorted(fields.loc[fields["csb_id"].duplicated(), "csb_id"].unique())
        warnings.append(f"duplicate csb_id in boundary: {duplicates}")

    inventory_path = farm_dir / "manifests" / "field-inventory.csv"
    if inventory_path.is_file():
        inventory = pd.read_csv(inventory_path, dtype=str)
        inventory_ids = set(inventory["field_id"].astype(str))
        boundary_ids = set(fields["field_id"])
        if inventory_ids - boundary_ids:
            warnings.append(
                "inventory fields missing from boundary: "
                f"{sorted(inventory_ids - boundary_ids)}"
            )
        if boundary_ids - inventory_ids:
            warnings.append(
                "boundary fields missing from inventory: "
                f"{sorted(boundary_ids - inventory_ids)}"
            )
        inputs.append(inventory_path)

    fields = fields.sort_values("field_id", key=lambda series: series.map(
        lambda value: _natural_key(value)
    )).reset_index(drop=True)

    weather, weather_path = _load_weather(farm_dir, fields, warnings)
    if weather_path is not None:
        inputs.append(weather_path)

    cdl, cdl_paths = _load_cdl(farm_dir, fields, warnings)
    inputs.extend(cdl_paths)

    rotation, rotation_path = _load_rotation(farm_dir)
    if rotation_path is not None:
        inputs.append(rotation_path)

    return FarmData(
        grower_slug=grower_dir.name,
        grower_name=grower_name,
        farm_slug=farm_dir.name,
        farm_name=_farm_name(farm_dir),
        root=farm_dir,
        fields=fields,
        weather=weather,
        cdl=cdl,
        rotation=rotation,
        inputs=inputs,
        warnings=warnings,
    )


def _natural_key(value: str) -> tuple:
    parts = re.split(r"(\d+)", str(value))
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts
    )


def _require_columns(frame: pd.DataFrame, columns, path: Path) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise LoadError(f"{path}: missing columns {missing}")


def _pick_table(tables_dir: Path, pattern: str, warnings: list[str], label: str):
    matches = sorted(tables_dir.glob(pattern))
    if not matches:
        return None
    if len(matches) > 1:
        matches.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        warnings.append(
            f"{label}: {len(matches)} matching tables, using newest "
            f"{matches[0].name} and ignoring {[p.name for p in matches[1:]]}"
        )
    return matches[0]


def _load_weather(farm_dir: Path, fields: gpd.GeoDataFrame, warnings: list[str]):
    tables_dir = farm_dir / "derived" / "tables"
    path = _pick_table(tables_dir, "*_weather_*.csv", warnings, "weather")
    if path is None:
        warnings.append("weather: no derived/tables/*_weather_*.csv found")
        return pd.DataFrame(columns=list(WEATHER_COLUMNS)), None

    weather = pd.read_csv(path)
    _require_columns(weather, WEATHER_COLUMNS, path)
    weather["field_id"] = weather["field_id"].astype(str)
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce")
    if weather["date"].isna().any():
        bad = int(weather["date"].isna().sum())
        warnings.append(f"weather: dropped {bad} rows with unparseable dates")
        weather = weather.dropna(subset=["date"])

    boundary_ids = set(fields["field_id"])
    weather_ids = set(weather["field_id"])
    missing = sorted(boundary_ids - weather_ids)
    if missing:
        warnings.append(f"weather: no rows for fields {missing}")
    extra = sorted(weather_ids - boundary_ids)
    if extra:
        warnings.append(f"weather: rows for unknown fields {extra}")

    years = sorted(weather["date"].dt.year.unique().tolist())
    if len(years) < 5:
        warnings.append(f"weather: only {len(years)} years present ({years})")
    counts = weather.groupby("field_id")["date"].nunique()
    thin = counts[counts < 365 * len(years) * 0.95]
    if not thin.empty:
        warnings.append(
            "weather: fields with <95% of expected daily rows: "
            f"{thin.round(0).astype(int).to_dict()}"
        )
    return weather, path


def _load_cdl(farm_dir: Path, fields: gpd.GeoDataFrame, warnings: list[str]):
    tables_dir = farm_dir / "derived" / "tables"
    paths = sorted(
        path
        for path in tables_dir.glob("*_cdl.csv")
        if CDL_PATTERN.search(path.name)
    )
    if not paths:
        warnings.append("cdl: no derived/tables/*_<year>_cdl.csv tables found")
        return pd.DataFrame(columns=list(CDL_COLUMNS)), []

    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        _require_columns(frame, CDL_COLUMNS, path)
        frames.append(frame)
    cdl = pd.concat(frames, ignore_index=True)
    cdl["field_id"] = cdl["field_id"].astype(str)
    cdl["year"] = cdl["year"].astype(int)

    years = sorted(cdl["year"].unique().tolist())
    boundary_ids = set(fields["field_id"])
    per_field_years = cdl.groupby("field_id")["year"].nunique()
    incomplete = per_field_years[per_field_years < len(years)]
    if not incomplete.empty:
        warnings.append(
            f"cdl: fields missing some years {years}: {incomplete.to_dict()}"
        )
    missing = sorted(boundary_ids - set(cdl["field_id"]))
    if missing:
        warnings.append(f"cdl: no rows for fields {missing}")

    purity = cdl.groupby(["field_id", "year"])["pct"].sum()
    residual = 100.0 - purity
    if (residual > 5.0).any():
        bad = residual[residual > 5.0]
        warnings.append(
            f"cdl: unclassified residual above 5% in {len(bad)} field-years "
            f"(max {bad.max():.1f}%)"
        )
    else:
        warnings.append(
            "cdl: per-year tables omit unclassified pixels; residual is "
            f"{residual.min():.1f}-{residual.max():.1f}% of field pixels"
        )
    return cdl, paths


def _load_rotation(farm_dir: Path):
    tables_dir = farm_dir / "derived" / "tables"
    matches = sorted(tables_dir.glob("*_crop_rotation.csv"))
    if not matches:
        return None, None
    path = matches[0]
    return pd.read_csv(path), path
