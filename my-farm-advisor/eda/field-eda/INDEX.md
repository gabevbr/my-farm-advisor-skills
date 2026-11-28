# Field EDA Index

File-level navigation for the `field-eda` subskill. Start with [SKILL.md](SKILL.md) for
routing and [README.md](README.md) for the human overview.

## Entry points

- [`run_field_eda.py`](run_field_eda.py) — checkout runner; adds `src/` to the path and
  calls the CLI. Use this from the repository without installing anything.
- [`src/field_eda/cli.py`](src/field_eda/cli.py) — argument parsing, output layout,
  figure/table wiring, and run summary.
- [`src/field_eda/__main__.py`](src/field_eda/__main__.py) — `python -m field_eda` from
  the `src` directory.

## Analysis modules

- [`src/field_eda/loaders.py`](src/field_eda/loaders.py) — runtime root resolution,
  farm discovery, glob-based table loading, column and coverage validation.
- [`src/field_eda/metrics.py`](src/field_eda/metrics.py) — projected boundary metrics,
  dominant crop, Shannon diversity, continuous corn, GDD, season aggregation.
- [`src/field_eda/analysis.py`](src/field_eda/analysis.py) — assembles the field table
  and field-year weather table; builds the three statistics tables.
- [`src/field_eda/stats.py`](src/field_eda/stats.py) — Holm correction,
  Kruskal–Wallis, Mann–Whitney with rank-biserial effect, Spearman with bootstrap CI,
  variance share.
- [`src/field_eda/figures.py`](src/field_eda/figures.py) — the six static figures and
  shared palette/style helpers.
- [`src/field_eda/manifest.py`](src/field_eda/manifest.py) — input hashes, counts,
  environment versions, output inventory, warnings.

## Tests

Run each file directly with the runtime interpreter:

- [`src/field_eda/tests/test_metrics.py`](src/field_eda/tests/test_metrics.py) —
  compactness, Shannon, GDD cap, season mask, dominant crop, natural sort.
- [`src/field_eda/tests/test_stats.py`](src/field_eda/tests/test_stats.py) — Holm
  monotonicity, Kruskal separation, pairwise shape, bootstrap CI behavior, variance
  share.
- [`src/field_eda/tests/test_figures.py`](src/field_eda/tests/test_figures.py) —
  regression guard that monthly precipitation averages co-located fields instead of
  summing them.

```bash
P="$HOME/my-farm-advisor-runtime/data-pipeline/.venv/bin/python"
for t in my-farm-advisor/eda/field-eda/src/field_eda/tests/test_*.py; do "$P" "$t"; done
```

## References

- [references/data-contract.md](references/data-contract.md) — runtime inputs, columns,
  discovery rules, output schemas, warning semantics.
- [references/figure-specs.md](references/figure-specs.md) — one section per figure:
  question, encoding, story, caveats, review verdict.
- [references/statistics.md](references/statistics.md) — method choices, formulas,
  assumptions, result snapshot, interpretation traps.
- [examples/README.md](examples/README.md) — reproduce the Assignment 2 run and verify
  the expected counts.
- [PROVENANCE.md](PROVENANCE.md) — source and method provenance.
- [AGENTS.md](AGENTS.md) — agent-facing working rules for this subtree.
