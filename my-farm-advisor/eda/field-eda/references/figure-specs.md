# Field EDA Figure Specifications

Seven static figures: two per category (boundaries, CDL, weather) plus one geospatial
map. Each section states the question, the encoding, the story the figure is meant to
tell, the caveat a reader must carry, and the review verdict from the 2026-11-27/28
render pass.

All figures are 200 dpi PNGs, Agg backend, Okabe–Ito palette. Grower colors are keyed to
state: Illinois `#0072B2`, Iowa `#D55E00`, Nebraska `#009E73`.

## F1 — Field size by grower sample

**File:** `F1-boundaries-area-by-grower.png`

**Question.** Are the sampled fields different in size across growers, and how much do
they overlap?

**Encoding.** One box per grower over individual field area (ha); jittered points are
the 30 fields. The box shows the median and IQR; whiskers extend to the non-outlier
range. Each group is annotated with `n` and its median.

**Story.** Illinois and Iowa medians sit near 245 ha and overlap heavily; Nebraska
fields are smaller (median ~208 ha) and much tighter. The boundary table confirms this:
Kruskal–Wallis `H = 18.2`, `p = 0.0001`, epsilon-squared `0.60`; only the Illinois–Iowa
pair is non-significant after Holm correction.

**Caveat.** This is a top-10-by-area sample inside each county, so the distributions
describe the selected fields, not the county's field-size population.

**Verdict.** Pass. No empty panels, labels legible, y-axis is a continuous scale, and
the annotation does not collide with the boxes.

## F2 — Field shape vs size

**File:** `F2-boundaries-shape-vs-area.png`

**Question.** Does field size track shape complexity, or are small fields systematically
more irregular?

**Encoding.** Scatter of projected area (ha) against Polsby-Popper compactness
(`4πA/P²`), colored by grower. The two least-compact fields are labeled. A boxed
annotation reports the Spearman rho, p, and n.

**Story.** The relationship is weak and negative (`rho ≈ -0.33`, `p ≈ 0.08`, `n = 30`):
there is a hint that larger fields are slightly less compact, but the sample does not
support a strong claim. Most fields sit between 0.15 and 0.55 compactness, so shape
varies substantially at every size.

**Caveat.** Compactness is scale-free but sensitive to boundary vertex noise and to
multipart fields; it is a shape description, not a farming-quality score.

**Verdict.** Pass after fix. The first render put the legend at lower right, where it
collided with the low-compactness annotations; the legend moved to upper right and the
annotation offsets were flipped. No collision remains.

## F3 — Dominant crop by field and year

**File:** `F3-cdl-rotation-heatmap.png`

**Question.** What rotation is each field actually running across the CDL years?

**Encoding.** Field × CDL-year grid, one cell per field-year, colored by dominant crop
(Corn, Soybeans, Other, no data). Rows are grouped by grower with a labeled rule.

**Story.** Illinois shows a near-clean corn/soy alternation with one continuous-corn
field; Iowa is almost entirely alternating corn/soy with no continuous corn; Nebraska
mixes alternating fields with three continuous-corn fields and two fields that break
sequence late in the window. The rotation table quantifies this: continuous corn is
1/10 in Illinois, 0/10 in Iowa, 3/10 in Nebraska.

**Caveat.** "Dominant" means the largest CDL pixel share, not a management declaration.
The heatmap stops at 2023 because that is the CDL coverage; the boundary's `crop_2025`
attribute is excluded because it would introduce a gap year (2024) and is not CDL.

**Verdict.** Pass after fix. The first render included a 2025 column sourced from the
boundary attribute; it was removed so the axis is a contiguous CDL series. The row/column
grid, group rules, and legend are legible at README size.

## F4 — Latest crop composition per field

**File:** `F4-cdl-composition.png`

**Question.** Within the latest CDL year, how much of each field is the dominant crop,
and how much is other classes or unclassified residual?

**Encoding.** Horizontal 100%-stacked bars per field, ordered by grower then field id.
Segments are Corn, Soybeans, Grass/Pasture, and Other/unclassified. The dominant
Corn/Soybeans share is printed to the right of each bar.

**Story.** Most fields are 95–100% one crop, confirming that field boundaries align well
with CDL pixels. The exceptions are informative: `ne-r1`, `ne-r7`, and `ne-r8` carry
6–8% soybeans or grass alongside corn, and `ne-r1`/`ne-r7` also show a visible grey
unclassified residual. `ia-r5` and `ne-r10` are effectively 100% single-crop.

**Caveat.** The grey band is not a measured "other crop"; it is the residual left after
the CDL class shares are summed, so it mixes unclassified pixels with any class outside
the three named ones. Read it as data coverage, not agronomy.

**Verdict.** Pass after fix. The first render placed percentage labels at `share + 1.2`,
which pushed them onto the bar ends and the grey band; labels now sit at a fixed position
right of the 100% bar. Colors are categorical, not a ramp.

## F5 — Seasonal climate by grower, 2021–2025

**File:** `F5-weather-climatology.png`

**Question.** How do the growers' seasonal temperature and precipitation cycles compare,
and how much year-to-year spread sits behind the mean?

**Encoding.** Two stacked panels sharing a month axis. Top: monthly mean temperature;
bottom: monthly precipitation total. Lines are the five-year mean per grower; shaded
bands are the five-year min–max. The April–October growing season is shaded grey.

**Story.** The temperature curves are similar in shape but offset: Nebraska runs warmest
through the growing season, Iowa coolest. Precipitation is noisier and less separated,
with growing-season totals in the 40–130 mm/month range and wide year-to-year bands; the
growers do not sort into a clean wet/dry order.

**Caveat.** The band is min–max over five years, not a confidence interval, and it is
wide because n is five. The 10 fields in a grower share one climate grid; the lines are
not 10 independent weather stations.

**Verdict.** Pass after fix. The first render summed `PRECTOTCORR` across all 10 fields
in a grower, inflating monthly totals roughly 10× (up to ~2,300 mm/month). The
aggregation now sums per field-month and then averages fields, restoring physical totals
(0–230 mm/month). A regression test guards the behavior.

## F6 — Water and heat across field-years

**File:** `F6-weather-precip-vs-gdd.png`

**Question.** Within the growing season, do wetter field-years also run cooler or
warmer, and does that hold inside each grower?

**Encoding.** Scatter of season precipitation (Apr–Oct, mm) against season GDD
(base 10 °C, cap 30 °C), one point per field-year, colored by grower. The boxed
annotation reports the pooled Spearman rho and the per-grower rho.

**Story.** The pooled correlation is negative (`rho = -0.40`, `p < 0.001`, `n = 150`),
but it is a between-grower contrast: Illinois is positive (`rho = 0.59`), while Iowa and
Nebraska are both negative (`rho = -0.48`). Illinois occupies the wetter, higher-GDD
side of the cloud; Nebraska is hotter at lower precipitation. The pooled sign is
therefore not evidence that wetter seasons are cooler within a field.

**Caveat.** Field-years are pseudoreplicated: 10 fields share one climate grid, so the
effective sample is about five years per grower. The pooled p-value uses 150 rows and is
indicative only. The footnote states this and the sign flip.

**Verdict.** Pass after fix. The legend moved from lower right (where it overlapped Iowa
points) to lower left; p-values below 0.001 now print as `< 0.001`; the footnote makes the
pooled-versus-within distinction explicit.

## F7 — Field footprints and 2023 dominant crop

**File:** `F7-geospatial-field-map.png`

**Question.** Where are the sampled fields inside each grower's county, and what crop
was on each in the latest CDL year?

**Encoding.** One panel per farm, each on its own local UTM metre frame
(`field_frame.frame_for`), auto-rotated to the sampled-field cluster and decorated with
a true-north arrow. Footprints are filled by 2023 dominant crop (Corn, Soybeans,
Grass/Pasture, Other) over an Esri World Imagery basemap. Each panel title states the
state, farm, and crop counts.

**Story.** The sampled fields are not one contiguous farm: they are scattered across
roughly 30 × 42 km of each county, which is the top-10-by-area selection at work.
Illinois is corn-heavy in 2023 (8 corn / 2 soybeans), Iowa is soybean-heavy (3 corn /
7 soybeans), and Nebraska is split (5 corn / 5 soybeans). Read together with F3, the
map shows that the rotation differences are spatial as well as temporal.

**Caveat.** This is a county-scale distribution map, not a field close-up; individual
footprints are a few pixels wide. Per-field IDs are therefore omitted for legibility and
remain in F3/F4 and `field-metrics.csv`. The basemap is keyless Esri World Imagery; if
tile access fails the panel keeps a plain background and the rest of the run continues.

**Verdict.** Pass after redesign. The first render collapsed the x-axis because
`view_extent` was called with the wrong argument order, and the 6 m basemap resolution
was inappropriate for a 30 km extent; both were fixed. The halo was then thinned from a
3.2 pt stroke (about 700 m at this scale) to 1 pt, the in-panel rotation callout was
dropped because the axis note already carries the tilt, and per-field IDs were removed
after they failed the README legibility check. The final panel keeps 15% viewport
padding, local metre axes, per-panel north arrows, and a legible crop legend.

## Cross-figure conventions

- Corn `#E69F00`, Soybeans `#56B4E9`, Grass/Pasture `#009E73`, Other/unclassified
  `#B0B0B0`, no data white with a grey edge.
- Grower colors follow state, not alphabetical order, so a grower keeps one color across
  F1, F2, F5, and F6. F7 uses the crop palette because panels are already separated by
  grower.
- No figure uses a continuous colormap for a categorical variable, and no figure uses a
  categorical palette for a continuous variable.
- Grid lines are light grey and sit below the data; top and right spines are removed on
  non-grid figures. F7 keeps metre tick axes because distance is read from them.
