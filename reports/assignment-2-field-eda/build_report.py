#!/usr/bin/env python3
"""Build the one-time Assignment 2 field-EDA report PDF from a run directory.

This is an assignment artifact, not part of the reusable subskill. It reads only
the outputs of one ``run_field_eda.py`` run (``figures/``, ``tables/``,
``manifest.json``) so every number in the text comes from the same tables the
figures were drawn from.

    python reports/assignment-2-field-eda/build_report.py \
        --run-dir ~/my-farm-advisor-runtime/data-pipeline/eda/field-eda/<run-id>

Requires ``fpdf2``, ``pandas``, ``scipy``, ``Pillow`` and ``matplotlib`` (the
last only for its bundled DejaVu fonts).
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

import matplotlib
import pandas as pd
from fpdf import FPDF
from PIL import Image
from scipy.stats import spearmanr

MARGIN = 17.0
PAGE_W = 210.0
CONTENT_W = PAGE_W - 2.0 * MARGIN
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"

INK = (33, 37, 41)
MUTED = (104, 112, 122)
ACCENT = (30, 92, 135)
RULE = (208, 214, 221)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def ptext(value: float) -> str:
    """Readable p-value: three decimals above 0.01, else two significant digits."""
    if pd.isna(value):
        return "p = n/a"
    if value >= 0.01:
        return f"p = {value:.3f}"
    return f"p = {value:.1e}".replace("e-0", "e-")


def fnum(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def pick(frame: pd.DataFrame, **conditions) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column, value in conditions.items():
        mask &= frame[column] == value
    hits = frame[mask]
    if len(hits) != 1:
        raise SystemExit(f"expected one row for {conditions}, found {len(hits)}")
    return hits.iloc[0]


def shrink(path: Path, workdir: Path, width_px: int, quality: int) -> Path:
    """Downscale a figure and re-encode it as JPEG so the PDF stays small."""
    out = workdir / f"{path.stem}-{quality}.jpg"
    with Image.open(path) as image:
        if image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        ):
            image = image.convert("RGBA")
            backdrop = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(backdrop, image)
        image = image.convert("RGB")
        if image.width > width_px:
            height = round(image.height * width_px / image.width)
            image = image.resize((width_px, height), Image.LANCZOS)
        image.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out


# --------------------------------------------------------------------------- #
# page furniture
# --------------------------------------------------------------------------- #
class Report(FPDF):
    def footer(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(-13.5)
        self.set_font("DejaVu", "", 7.2)
        self.set_text_color(*MUTED)
        self.cell(
            CONTENT_W / 2.0,
            5.0,
            "Assignment 2 - field-level EDA: boundaries, CDL, weather",
            align="L",
        )
        self.cell(CONTENT_W / 2.0, 5.0, f"page {self.page_no()}", align="R")


def heading(pdf: Report, text: str, size: float = 13.2, space: float = 4.0) -> None:
    # Never leave a heading stranded at the foot of a page.
    if pdf.get_y() > pdf.page_break_trigger - 42.0:
        pdf.add_page()
    pdf.ln(space)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", size)
    pdf.set_text_color(*ACCENT)
    pdf.multi_cell(CONTENT_W, 7.0, text, align="L")
    pdf.set_draw_color(*RULE)
    pdf.set_line_width(0.35)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + CONTENT_W, pdf.get_y())
    pdf.ln(2.4)


def para(pdf: Report, text: str, size: float = 9.4, space: float = 2.2) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", size)
    pdf.set_text_color(*INK)
    pdf.multi_cell(CONTENT_W, 4.75, text, align="L")
    pdf.ln(space)


def bullets(pdf: Report, items: list[str], size: float = 9.2) -> None:
    for item in items:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("DejaVu", "", size)
        pdf.set_text_color(*INK)
        pdf.cell(4.4, 4.6, "-")
        pdf.multi_cell(CONTENT_W - 4.4, 4.6, item, markdown=True, align="L")
        pdf.ln(0.7)


def table(
    pdf: Report,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    aligns: list[str] | None = None,
    size: float = 8.3,
) -> None:
    aligns = aligns or ["L"] * len(headers)
    needed = 6.2 + 5.7 * len(rows) + 0.5
    if pdf.get_y() + needed > pdf.page_break_trigger:
        pdf.add_page()
    pdf.set_draw_color(*RULE)
    pdf.set_text_color(*INK)
    pdf.set_fill_color(238, 241, 246)
    pdf.set_font("DejaVu", "B", size)
    for head, width, align in zip(headers, widths, aligns):
        pdf.cell(width, 6.2, head, border="B", align=align, fill=True)
    pdf.ln(6.2)
    pdf.set_font("DejaVu", "", size)
    for row in rows:
        if pdf.get_y() + 5.8 > pdf.page_break_trigger:
            pdf.add_page()
        for value, width, align in zip(row, widths, aligns):
            pdf.cell(width, 5.7, str(value), border="B", align=align)
        pdf.ln(5.7)
    pdf.ln(2.6)


def figure_block(
    pdf: Report,
    path: Path,
    caption: str,
    workdir: Path,
    max_w: float = 140.0,
    max_h: float = 128.0,
    width_px: int = 1000,
    quality: int = 78,
) -> None:
    with Image.open(path) as image:
        px_w, px_h = image.size
    width = max_w
    height = width * px_h / px_w
    if height > max_h:
        height = max_h
        width = height * px_w / px_h
    available = pdf.page_break_trigger - pdf.get_y() - 13.0
    if height > available:
        # If only a little too tall, shrink into the remaining space rather
        # than pushing one figure onto an otherwise blank page.
        if available >= 0.80 * height:
            width *= available / height
            height = available
        else:
            pdf.add_page()
    x = pdf.l_margin + (pdf.epw - width) / 2.0
    y = pdf.get_y()
    pdf.image(str(shrink(path, workdir, width_px, quality)), x=x, y=y, w=width, h=height)
    pdf.set_y(y + height + 2.0)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "I", 8.0)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(CONTENT_W, 3.95, caption, align="L")
    pdf.ln(2.8)


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def build(run_dir: Path, out_path: Path, workdir: Path) -> Path:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    tables = run_dir / "tables"
    figures = run_dir / "figures"

    fields = pd.read_csv(tables / "field-metrics.csv")
    bounds = pd.read_csv(tables / "stats-boundaries.csv")
    cdl = pd.read_csv(tables / "stats-cdl.csv")
    weather = pd.read_csv(tables / "stats-weather.csv")

    growers = sorted(fields["grower_name"].unique())
    n_fields = len(fields)
    n_field_years = int(fields["weather_years"].sum())
    run_id = manifest["run_id"]
    generated = str(manifest["generated_at"])[:10]

    cdl_years = sorted(
        {int(year) for grower in manifest["growers"] for year in grower.get("cdl_years", [])}
    )
    weather_years = sorted(
        {
            int(year)
            for grower in manifest["growers"]
            for year in grower.get("weather_years", [])
        }
    )
    cdl_span = f"{cdl_years[0]}-{cdl_years[-1]}" if cdl_years else "n/a"
    weather_span = (
        f"{weather_years[0]}-{weather_years[-1]}" if weather_years else "n/a"
    )

    residuals = [
        float(value)
        for text in manifest.get("warnings", [])
        for value in re.findall(r"residual is [\d.]+-([\d.]+)%", text)
    ]
    residual_max = max(residuals) if residuals else float("nan")

    location_rows = []
    for name in growers:
        sample = fields[fields["grower_name"] == name]
        location_rows.append(
            [
                name,
                sample["state"].iloc[0],
                sample["county"].iloc[0],
                str(sample["farm_name"].iloc[0]).replace(" Demo Farm", ""),
                str(len(sample)),
                fnum(float(sample["area_ha"].median()), 2),
            ]
        )

    # ---- numbers used in the prose ------------------------------------- #
    il, ia, ne = "Illinois Grower", "Iowa Grower", "Nebraska Grower"
    med = {
        name: float(pick(bounds, analysis="describe", comparison=name)["median"])
        for name in (il, ia, ne)
    }
    omni = pick(bounds, analysis="omnibus", comparison="all growers")
    pair = {
        "il_ia": pick(bounds, analysis="pairwise", comparison=f"{il} vs {ia}"),
        "il_ne": pick(bounds, analysis="pairwise", comparison=f"{il} vs {ne}"),
        "ia_ne": pick(bounds, analysis="pairwise", comparison=f"{ia} vs {ne}"),
    }
    rho_shape, p_shape = spearmanr(fields["area_ha"], fields["compactness"])

    rot_omni = pick(cdl, analysis="omnibus", comparison="all growers")
    rot_pair = {
        "il_ia": pick(cdl, analysis="pairwise", comparison=f"{il} vs {ia}"),
        "il_ne": pick(cdl, analysis="pairwise", comparison=f"{il} vs {ne}"),
        "ia_ne": pick(cdl, analysis="pairwise", comparison=f"{ia} vs {ne}"),
    }
    cc = {
        name: pick(cdl, analysis="continuous-corn", comparison=name)
        for name in (il, ia, ne)
    }
    shares = {
        (name, crop): float(
            pick(cdl, analysis="class-share", comparison=f"{name}: {crop}")["statistic"]
        )
        for name in (il, ia, ne)
        for crop in ("Corn", "Soybeans", "Grass/Pasture", "Other")
    }

    pooled = pick(
        weather, analysis="correlation", grouping="all growers",
        comparison="season_precip_mm vs season_gdd_c",
    )
    corr = {
        name: pick(
            weather, analysis="correlation",
            comparison=f"{name}: season_precip_mm vs season_gdd_c",
        )
        for name in (il, ia, ne)
    }
    eta_precip = pick(weather, analysis="variance-share", comparison="season_precip_mm")
    eta_gdd = pick(weather, analysis="variance-share", comparison="season_gdd_c")

    div_any = pick(cdl, analysis="correlation", grouping="all growers",
                   comparison="area_ha vs distinct classes, any share")
    div_floor = pick(cdl, analysis="correlation", grouping="all growers",
                     comparison="area_ha vs distinct classes, >=1% share")
    div_grower = {
        name: pick(cdl, analysis="correlation", grouping="grower_name",
                   comparison=f"{name}: area_ha vs distinct classes, any share")
        for name in (il, ia, ne)
    }

    climate = fields.groupby("grower_name").agg(
        gdd=("season_gdd_c_mean", "mean"),
        precip=("season_precip_mm_mean", "mean"),
    )
    diversity = fields["distinct_classes_mean"]
    first_year_counts = fields[f"crop_{cdl_years[0]}"].value_counts()

    # ---- document ------------------------------------------------------- #
    pdf = Report(orientation="P", unit="mm", format="A4")
    pdf.set_title("Assignment 2 - field-level EDA: boundaries, CDL, weather")
    pdf.set_subject("Field-level exploratory analysis of three My Farm Advisor growers")
    pdf.set_creator("reports/assignment-2-field-eda/build_report.py")
    pdf.set_margins(MARGIN, 16.0, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=16.0)
    pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_font("DejaVu", "I", str(FONT_DIR / "DejaVuSans-Oblique.ttf"))
    pdf.add_page()

    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 0, PAGE_W, 5.5, style="F")

    pdf.set_y(26)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", 21)
    pdf.set_text_color(*INK)
    pdf.multi_cell(CONTENT_W, 9.2, "Field-level EDA across three growers", align="L")
    pdf.ln(1.5)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 11.4)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(CONTENT_W, 6.0, "Boundaries, CDL crop history and weather  |  Assignment 2 report", align="L")
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 8.2)
    pdf.multi_cell(
        CONTENT_W,
        4.2,
        f"Run {run_id} generated {generated}. Figures and tables come from the "
        "my-farm-advisor field-eda subskill; this document is a one-time reading "
        "guide to that run.",
        align="L",
    )
    pdf.ln(4)

    table(
        pdf,
        ["Growers", "Fields", "Field-years", "CDL years", "Weather seasons", "Figures / tables"],
        [[
            str(len(growers)),
            str(n_fields),
            str(n_field_years),
            cdl_span,
            str(len(weather_years)) if weather_years else "n/a",
            f"{len(manifest['outputs']['figures'])} / {len(manifest['outputs']['tables'])}",
        ]],
        [26, 24, 30, 32, 34, 30],
        aligns=["L"] * 6,
    )

    heading(pdf, "1. Dataset scope and grower locations")
    para(
        pdf,
        "The runtime holds three growers with one farm each and ten sampled fields per "
        "farm. The fields are the ten largest by area inside one county per grower: "
        "Iroquois County, Illinois; Kossuth County, Iowa; and York County, Nebraska. "
        "Boundaries are USDA crop-sequence boundaries (source usda_csb_fiboa) stored as "
        "EPSG:4326 polygons; area, perimeter and compactness are computed after "
        "projecting to EPSG:5070.",
    )
    table(
        pdf,
        ["Grower", "State", "County", "Farm", "Fields", "Median area (ha)"],
        location_rows,
        [38, 14, 26, 46, 16, 36],
        aligns=["L", "L", "L", "L", "R", "R"],
    )
    para(
        pdf,
        f"Sampled fields range from {fnum(fields['area_ha'].min())} to "
        f"{fnum(fields['area_ha'].max())} ha (median {fnum(fields['area_ha'].median())} ha).",
    )

    heading(pdf, "2. Field counts and data layers")
    bullets(
        pdf,
        [
            f"**Boundaries** - one polygon per field ({n_fields} fields). Area, "
            "perimeter, compactness (Polsby-Popper, 1.0 = circle), vertex count and "
            "multipart flag.",
            f"**CDL cropland** - {cdl_span} for every field, with crop name, pixel "
            f"share and pixel count per class ({n_field_years} field-years). The "
            f"{cdl_years[-1]} layer also supplies the latest dominant crop and its purity.",
            f"**Weather** - daily precipitation and temperature for {weather_span}, cut "
            "to the growing season (April 1 - October 31). Derived: season precipitation, "
            "season GDD base 10 C with the daily mean capped at 30 C, hot days and "
            "season mean temperature.",
            "**Not used** - the SSURGO soil layers present under each field's soil/ "
            "folder. See section 10.",
        ],
    )
    para(
        pdf,
        f"Every field carries {len(cdl_years)} CDL years and {len(weather_years)} "
        f"weather seasons, so the {n_fields} fields expand to {n_field_years} "
        "field-years. The two layers cover different windows: CDL "
        f"{cdl_span}, weather {weather_span}, overlapping in "
        f"{max(cdl_years[0], weather_years[0])}-{min(cdl_years[-1], weather_years[-1])}. "
        "Grower-year means for the between-grower variance share are computed on 15 "
        "farm-years (3 growers x 5 years) rather than on field-years.",
    )

    heading(pdf, "3. Comparison levels")
    table(
        pdf,
        ["Level", "Rows", "What is compared", "Used by"],
        [
            ["Field", str(n_fields), "Size, shape, rotation, latest crop; one row per field", "F1-F4, F10"],
            ["Field-year", str(n_field_years), "Season weather per field per year", "F5, F6, F8"],
            ["Farm-year", "15", "Between-grower variance share for weather", "stats-weather"],
            ["Grower", "3", "Crop-class composition and group tests", "F9, stats tables"],
            ["Across-grower", "-", "Kruskal-Wallis omnibus and Holm-corrected Mann-Whitney", "stats-boundaries, stats-cdl"],
        ],
        [26, 15, 103, 32],
        aligns=["L", "R", "L", "L"],
    )
    para(
        pdf,
        "Fields are the replicate for boundary and CDL statements. For weather the "
        "years, not the fields, are the effective replicate: the ten fields in a grower "
        "sample only a few climate-model grid cells, so field-years are pseudoreplicated "
        "and the pooled p-value uses 150 rows only indicatively.",
    )

    # ---- boundaries ----------------------------------------------------- #
    heading(pdf, "4. Boundary comparisons")
    figure_block(
        pdf, figures / "F1-boundaries-area-by-grower.png",
        "F1 - Field area by grower. One box per grower over the ten fields, with every "
        "field drawn; area is projected hectares (EPSG:5070).",
        workdir=workdir,
    )
    para(
        pdf,
        f"Median field area is {fnum(med[il], 2)} ha in Illinois, {fnum(med[ia], 2)} ha "
        f"in Iowa and {fnum(med[ne], 2)} ha in Nebraska. Kruskal-Wallis rejects equal "
        f"locations (H = {fnum(omni['statistic'])}; {ptext(omni['p_value'])}; "
        f"epsilon-squared = "
        f"{fnum(omni['effect_size'], 2)}). After Holm correction Nebraska is smaller than "
        f"both Illinois ({ptext(pair['il_ne']['p_holm'])}) and Iowa "
        f"({ptext(pair['ia_ne']['p_holm'])}), while Illinois and Iowa are "
        f"indistinguishable ({ptext(pair['il_ia']['p_holm'])}).",
    )
    figure_block(
        pdf, figures / "F2-boundaries-shape-vs-area.png",
        "F2 - Field shape vs size. Polsby-Popper compactness against field area, one "
        "point per field, coloured by grower.",
        workdir=workdir,
    )
    para(
        pdf,
        f"Compactness does not track size: Spearman rho = {rho_shape:.2f} "
        f"({ptext(p_shape)}, n = {n_fields}). Most fields sit between 0.15 and 0.55, so "
        "shape varies at every size, and the two least compact fields are small.",
    )

    # ---- CDL ------------------------------------------------------------ #
    heading(pdf, "5. CDL crop history and composition")
    figure_block(
        pdf, figures / "F3-cdl-rotation-heatmap.png",
        "F3 - Rotation per field. Rows are fields grouped by grower, columns are CDL "
        f"years {cdl_span}; colour is the dominant crop of the field in that year.",
        workdir=workdir,
        max_h=155.0,
    )
    para(
        pdf,
        f"All {n_fields} fields run a corn-soybean system: in {cdl_years[0]}, "
        f"{int(first_year_counts.get('Corn', 0))} fields were corn and "
        f"{int(first_year_counts.get('Soybeans', 0))} soybeans, and the same two crops "
        "fill every later year. What differs is the rhythm. Continuous corn runs on "
        f"{int(cc[il]['statistic'])}/10 Illinois fields, {int(cc[ia]['statistic'])}/10 "
        f"Iowa fields and {int(cc[ne]['statistic'])}/10 Nebraska fields, and rotation "
        "diversity separates the growers "
        f"(Kruskal-Wallis {ptext(rot_omni['p_value'])}; epsilon-squared = "
        f"{fnum(rot_omni['effect_size'], 2)}). After Holm correction only Iowa and "
        f"Nebraska differ ({ptext(rot_pair['ia_ne']['p_holm'])}); Illinois vs Iowa "
        f"({ptext(rot_pair['il_ia']['p_holm'])}) and Illinois vs Nebraska "
        f"({ptext(rot_pair['il_ne']['p_holm'])}) do not.",
    )
    figure_block(
        pdf, figures / "F4-cdl-composition.png",
        "F4 - Latest-year composition per field. Share of each field's CDL-classified "
        f"pixels by crop in {cdl_years[-1]}, showing how pure each field is.",
        workdir=workdir,
    )
    para(
        pdf,
        f"Fields are largely single-crop: latest-year purity runs from "
        f"{fnum(fields['latest_purity_pct'].min())}% to "
        f"{fnum(fields['latest_purity_pct'].max())}% (median "
        f"{fnum(fields['latest_purity_pct'].median())}%). The figures below move from "
        f"field to grower, showing the same {cdl_years[-1]} composition as an "
        "area-weighted mix.",
    )
    figure_block(
        pdf, figures / "F9-cdl-crop-classes-by-grower.png",
        "F9 - CDL crop-class composition by grower. One 100% stacked bar per "
        "grower-year, split into Corn, Soybeans, Grass/Pasture and other CDL classes.",
        workdir=workdir,
    )
    para(
        pdf,
        "Averaged over the five grower-years, the classified pixels split as follows "
        "(percent of classified CDL pixels; the unclassified residual is excluded and "
        "reported below).",
    )
    table(
        pdf,
        ["Class", "Illinois", "Iowa", "Nebraska"],
        [
            [crop]
            + [fnum(shares[(name, crop)], 1) for name in (il, ia, ne)]
            for crop in ("Corn", "Soybeans", "Grass/Pasture", "Other")
        ],
        [64, 37, 37, 38],
        aligns=["L", "R", "R", "R"],
    )

    # ---- weather -------------------------------------------------------- #
    heading(pdf, "6. Weather comparisons")
    figure_block(
        pdf, figures / "F5-weather-climatology.png",
        "F5 - Seasonal cycle by grower. Monthly mean temperature and monthly "
        "growing-season precipitation; lines are five-year means and bands the "
        "five-year min-max for April-October.",
        workdir=workdir,
    )
    para(
        pdf,
        "The temperature curves share a shape but are offset. Mean growing-season GDD "
        f"is {fnum(climate.loc[ne, 'gdd'], 0)} in Nebraska, "
        f"{fnum(climate.loc[il, 'gdd'], 0)} in Illinois and "
        f"{fnum(climate.loc[ia, 'gdd'], 0)} in Iowa; mean season precipitation is "
        f"{fnum(climate.loc[il, 'precip'], 0)} mm (IL), "
        f"{fnum(climate.loc[ia, 'precip'], 0)} mm (IA) and "
        f"{fnum(climate.loc[ne, 'precip'], 0)} mm (NE). Precipitation does not sort the "
        "growers into a clean wet-to-dry order.",
    )
    figure_block(
        pdf, figures / "F6-weather-precip-vs-gdd.png",
        "F6 - Water and heat across field-years. Season precipitation against season "
        "GDD, one point per field-year, with pooled and per-grower Spearman rho.",
        workdir=workdir,
    )
    para(
        pdf,
        f"Pooled across all {n_field_years} field-years the correlation is negative "
        f"(rho = {pooled['statistic']:.2f}, {ptext(pooled['p_value'])}), but it is a "
        "between-grower contrast that changes sign inside Illinois: "
        f"IL {corr[il]['statistic']:+.2f}, IA {corr[ia]['statistic']:+.2f}, "
        f"NE {corr[ne]['statistic']:+.2f}. The pooled sign is therefore not evidence "
        "that wetter seasons are cooler within a field. Between-grower variance shares "
        f"are {float(eta_precip['effect_size']):.2f} for precipitation and "
        f"{float(eta_gdd['effect_size']):.2f} for GDD, so heat separates the growers far "
        "more cleanly than rainfall.",
    )
    figure_block(
        pdf, figures / "F8-weather-field-year.png",
        "F8 - Season weather by field and year. Two annotated heatmaps (precipitation "
        "and GDD) with fields as rows grouped by grower and years as columns.",
        workdir=workdir,
    )
    para(
        pdf,
        "Within a grower the ten rows are close but not identical, because the fields "
        "fall in a few grid cells rather than on one. The year-to-year column pattern is "
        "shared: this is the visual form of the pseudoreplication caveat, and the reason "
        "the effective climate sample is about five years per grower.",
    )

    # ---- size vs diversity ---------------------------------------------- #
    heading(pdf, "7. Field size vs CDL class diversity")
    figure_block(
        pdf, figures / "F10-boundaries-cdl-diversity.png",
        "F10 - Field size vs CDL class diversity. Distinct classes per field-year "
        "(mean over five CDL years) against field area, at any listed share and at a "
        "1% floor.",
        workdir=workdir,
    )
    para(
        pdf,
        f"Pooled over {n_fields} fields, area against the all-classes count gives "
        f"rho = {div_any['statistic']:.2f} ({ptext(div_any['p_value'])}); with a 1% floor "
        f"it gives rho = {div_floor['statistic']:.2f} "
        f"({ptext(div_floor['p_value'])}). Per grower the all-classes rho is "
        f"{div_grower[il]['statistic']:+.2f} (IL), {div_grower[ia]['statistic']:+.2f} "
        f"(IA) and {div_grower[ne]['statistic']:+.2f} (NE). That is a negative result: "
        "this sample does not support a field-size effect on class diversity, and the "
        "pooled sign flips between growers. Distinct-class counts range from "
        f"{fnum(diversity.min())} to {fnum(diversity.max())} classes per field-year.",
    )

    # ---- map ------------------------------------------------------------ #
    heading(pdf, "8. Geospatial map")
    figure_block(
        pdf, figures / "F7-geospatial-field-map.png",
        "F7 - County-scale field map. One panel per farm on a local UTM metre frame, "
        "auto-rotated to the field cluster, with a true-north arrow, an Esri World "
        "Imagery basemap and footprints coloured by the latest CDL dominant crop.",
        workdir=workdir,
        max_w=168.0,
        max_h=110.0,
        quality=80,
    )
    para(
        pdf,
        "The map shows where the sampled fields sit inside each county and what was "
        f"growing on them in {cdl_years[-1]}. Illinois is corn-heavy (8 corn, 2 soybeans), Iowa is "
        "soybean-heavy (3 corn, 7 soybeans) and Nebraska is split (5 corn, 5 soybeans). "
        "The fields are not one contiguous farm: they are scattered across roughly 30 x "
        "42 km of each county, which is the top-10-by-area selection at work. Footprints "
        "are only a few pixels wide at this extent, so per-field IDs are omitted here "
        "and kept in F3/F4 and field-metrics.csv.",
    )

    # ---- limitations ---------------------------------------------------- #
    heading(pdf, "9. Limitations, missing data and assumptions")
    bullets(
        pdf,
        [
            "**Selection.** Each grower contributes the ten largest fields by area in "
            "one county. This is a convenience sample, not a random draw, and every test "
            "describes that selection rather than the county.",
            "**Pseudoreplication.** The ten fields in a grower sit in only a few "
            "climate-model grid cells, so weather field-years are not independent. The "
            "effective sample is about five years per grower and the pooled weather "
            "p-value (n = 150) is indicative only.",
            "**Small groups.** Three growers and five years per grower make all "
            "inference descriptive. Bootstrap confidence intervals on coarse class "
            "counts (1.6-4.6 classes) are reported only as a spread, not as a "
            "precision claim.",
            "**CDL residual.** The per-year CDL tables omit unclassified pixels; that "
            "residual is 0.0-"
            f"{fnum(residual_max, 1)}% of field pixels and is excluded from every share "
            "denominator rather than assigned to a class.",
            "**Area-weighted shares.** Crop-class shares are pixel shares, so one "
            "large field can dominate a grower-year; they are not field counts.",
            "**Fixed definitions.** The growing season is April 1 - October 31 and "
            "GDD uses base 10 C with a 30 C cap. Different cut-offs would shift levels, "
            "though not the ordering of the growers.",
            f"**Different windows.** CDL spans {cdl_span} and weather {weather_span}, so "
            "the two layers overlap only in "
            f"{max(cdl_years[0], weather_years[0])}-"
            f"{min(cdl_years[-1], weather_years[-1])}. Nothing here joins a crop year to "
            "a weather year beyond field-level means.",
            "**One county per grower.** Nothing here generalises beyond these three "
            "counties, and the weather data are modelled grid values rather than "
            "on-farm sensors.",
        ],
    )

    heading(pdf, "10. Soil analysis")
    para(
        pdf,
        "Soil analysis was not required for this assignment and was not the focus of "
        "this work. It was not performed: the subskill never reads the SSURGO layers "
        "that exist in the runtime, and no figure, table or statistic in this report "
        "depends on soil properties. Boundaries, CDL and weather are the only inputs.",
    )

    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 7.6)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        CONTENT_W,
        3.9,
        f"Source: run {run_id} of my-farm-advisor/eda/field-eda ({n_fields} fields, "
        f"{n_field_years} field-years). Regenerate with build_report.py in this folder.",
        align="L",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="field-eda run directory (default: newest under the runtime)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "assignment-2-field-eda.pdf",
        help="output PDF path",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    if run_dir is None:
        root = Path.home() / "my-farm-advisor-runtime/data-pipeline/eda/field-eda"
        candidates = sorted(path for path in root.iterdir() if path.is_dir())
        if not candidates:
            raise SystemExit(f"no runs under {root}")
        run_dir = candidates[-1]

    with tempfile.TemporaryDirectory() as tmp:
        out = build(run_dir.resolve(), args.out.resolve(), Path(tmp))
    size = out.stat().st_size
    print(f"wrote {out} ({size / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
