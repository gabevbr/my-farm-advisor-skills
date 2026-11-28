# Field EDA Statistics

Method choices, formulas, assumptions, the current result snapshot, and the
interpretation traps that matter more than the p-values.

## Sample and inference unit

- **Fields** are the unit for boundary and CDL comparisons: 10 fields per grower,
  3 growers, 30 fields.
- **Field-years** are the rows for weather plots: 10 fields × 5 years × 3 growers = 150.
- **Years**, not fields, are the effective weather replicate. The 10 fields in a grower
  sample only a few climate-model grid cells, so field-years are pseudoreplicates for climate.
- **Farm-years** (3 growers × 5 years = 15) are used for the between-grower variance
  share, not field-years.
- The fields are the **top 10 by area** inside each county, not a random sample. All
  tests describe this selection.

## Tests and effect sizes

| Question | Test | Effect size | Reported in |
| --- | --- | --- | --- |
| Field area differs across growers | Kruskal–Wallis | epsilon-squared | `stats-boundaries.csv` |
| Which grower pairs differ in area | Mann–Whitney U, Holm | rank-biserial | `stats-boundaries.csv` |
| Area vs compactness | Spearman rho | rho, bootstrap 95% CI | F2 annotation |
| Rotation diversity differs across growers | Kruskal–Wallis | epsilon-squared | `stats-cdl.csv` |
| Which grower pairs differ in diversity | Mann–Whitney U, Holm | rank-biserial | `stats-cdl.csv` |
| Continuous-corn prevalence | count and share | share of fields | `stats-cdl.csv` |
| Class mix across growers | mean of grower-year pixel shares | percent of classified pixels | F9, `stats-cdl.csv` |
| Field area vs distinct CDL classes | Spearman rho | rho, bootstrap 95% CI | F10, `stats-cdl.csv` |
| Season precip vs GDD | Spearman rho | rho, bootstrap 95% CI | F6, `stats-weather.csv` |
| Share of weather variance between growers | eta-squared on farm-year means | between-group share | `stats-weather.csv` |

### Formulas

- **Kruskal–Wallis epsilon-squared:** `(H - k + 1) / (n - k)`, clipped to `[0, 1]`,
  where `H` is the test statistic, `k` the number of groups, `n` the pooled sample size.
- **Rank-biserial (Mann–Whitney):** `1 - 2U / (n_a · n_b)`. Sign is group A relative to
  group B; magnitude is the separation of the rank distributions.
- **Holm adjustment:** sort p-values ascending, multiply the i-th by `(m - i)`, enforce
  monotonicity, clip at 1.
- **Spearman rho:** rank correlation; the bootstrap CI resamples pairs with a fixed seed
  (`20261127`) and 2,000 draws, skipped when `n < 10`.
- **Eta-squared (variance share):** `SS_between / SS_total` on farm-year means. It is
  the share of total variance explained by grower membership, not a model R².

### Why nonparametric

Ten fields per group and five years per climate series are too small for normal-theory
tests, and area/compactness are bounded and skewed. Rank tests do not assume normality;
they do assume exchangeability within a group, which the top-10 selection weakens. The
p-values are therefore descriptive evidence about this sample, not population inference.

## Current result snapshot

Assignment 2 dataset, run `20261128T120000Z`.

### Boundaries (`stats-boundaries.csv`)

| Grower | n | Median area (ha) | IQR (ha) |
| --- | --- | --- | --- |
| Illinois | 10 | 245.2 | 227.1–272.2 |
| Iowa | 10 | 242.8 | 236.1–266.5 |
| Nebraska | 10 | 207.9 | 192.8–210.2 |

- Omnibus: `H = 18.23`, `p = 0.00011`, epsilon-squared `0.60`.
- Illinois vs Iowa: `p_holm = 0.970`, rank-biserial `0.02` — no detectable difference.
- Illinois vs Nebraska: `p_holm = 0.00088`, rank-biserial `-0.94`.
- Iowa vs Nebraska: `p_holm = 0.00055`, rank-biserial `-1.00`.

Reading: the area difference is driven by Nebraska's smaller, tighter fields; Illinois and
Iowa are indistinguishable at this sample size.

### CDL (`stats-cdl.csv`)

| Grower | Diversity median | IQR | Continuous corn |
| --- | --- | --- | --- |
| Illinois | 0.673 | 0.673–0.673 | 1/10 |
| Iowa | 0.673 | 0.673–0.673 | 0/10 |
| Nebraska | 0.587 | 0.125–0.673 | 3/10 |

- Omnibus: `H = 8.05`, `p = 0.018`, epsilon-squared `0.22`.
- Only Iowa vs Nebraska survives Holm (`p_holm = 0.044`, rank-biserial `-0.50`);
  Illinois vs Iowa and Illinois vs Nebraska do not.

Reading: diversity is bimodal by rotation type, not a smooth gradient. A clean corn/soy
alternation scores `ln 2 ≈ 0.693`; continuous corn scores 0. Nebraska's lower median and
wider IQR come from its three continuous-corn fields; Illinois and Iowa are dominated by
alternating fields. A significant omnibus with only one surviving pair is a sample-size
story, not a strong grower ranking.

**Class shares (`analysis=class-share`).** Mean of the five grower-year shares of
CDL-classified pixels, using `pixel_count` as the exclusive unit:

| Grower | Corn | Soybeans | Grass/Pasture | Other |
| --- | --- | --- | --- | --- |
| Illinois | 59.7 | 39.6 | 0.57 | 0.14 |
| Iowa | 46.2 | 53.4 | 0.35 | 0.03 |
| Nebraska | 65.7 | 34.0 | 0.09 | 0.20 |

Reading: all three are corn–soybean systems; the class mix differs only in which side of
the rotation dominates. Grass/Pasture and Other are under 1% everywhere, so they are
reported here rather than being visible in F9.

**Size vs class diversity (A4).** Spearman of field area against `distinct_classes_mean`
(mean over five CDL years), pooled and per grower:

| Comparison | n | rho | p |
| --- | --- | --- | --- |
| Pooled, any share | 30 | 0.34 | 0.069 |
| Pooled, `>=1%` floor | 30 | 0.07 | 0.72 |
| Illinois | 10 | -0.05 | 0.89 |
| Iowa | 10 | 0.51 | 0.13 |
| Nebraska | 10 | 0.59 | 0.07 |

Bootstrap 95% CI for the pooled any-share rho: `[-0.04, 0.68]`; the `>=1%` CI is
`[-0.32, 0.42]`, comfortably including zero. Reading: no supported relationship. The
pooled positive sign is a between-grower contrast — Illinois has both larger fields and
more listed classes, but its own rho is flat — and the literal count is dominated by
edge slivers, because it collapses once a 1% floor is applied. This is a reported
negative result, not a null that was hidden.

### Weather (`stats-weather.csv`)

| Comparison | n | rho | p |
| --- | --- | --- | --- |
| Pooled season precip vs GDD | 150 | -0.40 | < 0.001 |
| Illinois | 50 | +0.59 | < 0.001 |
| Iowa | 50 | -0.48 | < 0.001 |
| Nebraska | 50 | -0.48 | < 0.001 |

- Pooled bootstrap 95% CI for rho: `[-0.56, -0.24]`.
- Between-grower variance share: precipitation `0.27`, GDD `0.84` (farm-year means,
  `n = 15`).

Reading: the pooled negative sign is a between-grower contrast. Within Illinois the sign
is positive. GDD is far more grower-determined than precipitation, which is consistent
with latitude/longitude dominating heat while rain varies year to year everywhere.

## Interpretation traps

1. **Pseudoreplication.** Do not quote the pooled `n = 150` as independent weather
   observations. The effective weather sample is about 5 years per grower; the pooled
   p-value is illustrative.
2. **Pooling can flip a sign.** Illinois is positive while Iowa and Nebraska are
   negative; the pooled rho is negative. Always read F6 with the per-grower lines, not
   just the pooled number.
3. **Multiple contrasts.** Three pairwise tests per category are Holm-corrected. An
   unadjusted `p = 0.03` among three pairs is not a finding.
4. **Selection bias.** Top-10-by-area fields are larger and probably more regularly
   shaped than the county population; do not generalize shape or area results.
5. **Shannon on a sequence, not an area.** Diversity here measures rotation variety, not
   within-field crop mixture. A field that is 60% corn and 40% soy in one year still has
   one dominant class for that year.
6. **GDD cap.** Capping daily mean temperature at 30 °C depresses GDD in the hottest
   Nebraska days. It is a deliberate project convention, not a neutral physical constant;
   changing it changes the GDD spread and the correlation.
7. **Five years is a short climate record.** A min–max band over five years is a range,
   not a confidence interval, and one anomalous year dominates it.
8. **CDL residual is coverage, not a crop.** The grey band in F4 is unclassified or
   ungrouped pixels; do not read it as a specific land use.
9. **Two diversity measures, two questions.** `rotation_diversity` is Shannon over the
   five-year dominant-crop sequence; `distinct_classes_mean` counts classes present in a
   single field-year. A field can be 60% corn and 40% soy in one year and still have one
   dominant crop for that year, so the class count is the higher of the two and is far
   more sensitive to edge pixels. Never substitute one for the other.
10. **A class count is partly a labelling artefact.** One- or two-pixel slivers along a
    field edge can add a class without any management decision. Always report the
    `>=1%` floor next to the literal count, and treat a literal-count trend that
    vanishes at the floor as an artefact.
11. **Class shares are area-weighted.** F9 and `analysis=class-share` weight by CDL pixel
    count, so one large field can dominate a grower-year. That is the right unit for a
    land-cover mix and the wrong unit for "how many fields did X".

## Reporting guidance

- Quote an effect size with every p-value.
- Say "in this sample" or "among the selected fields" when describing a difference.
- Prefer the per-grower view for weather and the pairwise table for boundaries/CDL.
- Treat the three demo growers as a pipeline exercise, not an agronomic benchmark.
