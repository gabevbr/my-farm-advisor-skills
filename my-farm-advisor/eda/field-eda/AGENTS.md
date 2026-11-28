# Field EDA Agent Notes

Working rules for agents editing or running this subtree.

## Read order

1. [SKILL.md](SKILL.md) — when to invoke and where to start.
2. [README.md](README.md) — scope, run command, outputs, limits.
3. [references/data-contract.md](references/data-contract.md) — before touching loaders
   or column assumptions.
4. [references/figure-specs.md](references/figure-specs.md) — before changing a figure.
5. [references/statistics.md](references/statistics.md) — before changing a test or
   quoting a p-value.

## Hard rules

- **Runtime data stays out of Git.** Never commit `data/`, `.cache/`, generated
  `figures/`, `tables/`, `manifest.json`, or downloaded bundles.
- **No hard-coded farm prefixes.** Table names differ per farm (`illinois_demo`,
  `iowa`, `nebraska_demo`); keep the glob-based discovery in `loaders.py`.
- **Project before measuring.** Area, perimeter, and compactness must be computed in
  EPSG:5070. Never compute shape metrics in EPSG:4326.
- **Do not sum co-located weather.** The 10 fields in a grower share one climate grid.
  Sum precipitation per field-month, then average across fields. The regression test in
  `tests/test_figures.py` guards this.
- **State the sampling caveat.** Fields are a top-10-by-area selection, and weather
  field-years are pseudoreplicated; the effective weather sample is about five years per
  grower.
- **Do not present pooled weather correlations as field-level responses.** The pooled
  precipitation–GDD sign can differ from within-grower signs. Report both.
- **Keep p-values descriptive.** Small groups, multiple contrasts, and selection bias
  mean a p-value is evidence about this sample, not a population test.

## When changing a figure

- Re-render and inspect every figure the changed renderer draws, not just the one you
  meant to change.
- Check the five-point gate: no empty/under-covered panels, legible labels at README
  size, color semantics matching the data type, no legend/annotation collisions, and a
  title plus footnote that stand alone.
- Record the review verdict in the commit message.
- Leave generated figures in the runtime until a release explicitly asks for a reviewed
  gallery.

## When changing statistics

- Keep effect sizes alongside p-values.
- Keep Holm correction for pairwise contrasts.
- Keep bootstrap seeds fixed when a CI is part of a reviewed output.
- Update the result snapshot in [references/statistics.md](references/statistics.md)
  when the numbers change, and say why they changed.

## Validation

From the repository root:

```bash
./scripts/validate.sh
```

Also run the three offline test files with the runtime interpreter before committing:

```bash
P="$HOME/my-farm-advisor-runtime/data-pipeline/.venv/bin/python"
for t in my-farm-advisor/eda/field-eda/src/field_eda/tests/test_*.py; do "$P" "$t"; done
```
