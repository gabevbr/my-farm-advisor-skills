---
name: field-eda
description: >
  Field-level exploratory analysis for My Farm Advisor runtime datasets. Use when
  comparing field boundaries and shape, CDL rotation and composition, or weather
  across fields and growers, and when producing the static Assignment 2 field EDA
  figures and statistics tables.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.1.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.1.0"
---

# Field EDA

Use this nested skill for field-level exploratory analysis of a built My Farm Advisor
runtime: the questions a grower or reviewer asks before modeling — how big and how
shaped are the fields, what rotation is each field running, and how much do weather
and climate differ between the sampled growers.

It produces **static Python figures and CSV statistics tables**. It does not build a
dashboard, generate a written report, or analyze soil. Report prose is a separate,
one-time artifact layered on top of these outputs.

## Start Here

- Read [README.md](README.md) for the scope, run command, output layout, and limits.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Read [references/data-contract.md](references/data-contract.md) before pointing the
  tool at a new runtime or changing column expectations.
- Read [references/figure-specs.md](references/figure-specs.md) for what each of the
  ten figures encodes and the story it is meant to tell.
- Read [references/statistics.md](references/statistics.md) for the test choices,
  effect sizes, pseudoreplication caveats, and the current result snapshot.
- Read [examples/README.md](examples/README.md) to reproduce the Assignment 2 run.
- Read [PROVENANCE.md](PROVENANCE.md) before changing sources, defaults, or methods.

## Quick Run

From the repository root, with the runtime already built:

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
python my-farm-advisor/eda/field-eda/run_field_eda.py --dry-run
python my-farm-advisor/eda/field-eda/run_field_eda.py
```

Outputs land under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/<run-id>/`.

## Routing Notes

- Invoke this skill when the request is field-level comparison across a grower's fields
  or across growers, using boundaries, CDL/cropland, or weather.
- Do not use it for soil, imagery indices, terrain derivatives, or in-season satellite
  monitoring; route those to the sibling subtrees.
- Figures are generated into the runtime, not into Git. Commit only reviewed gallery
  figures under an `examples/**/output/` path when a release explicitly needs them.
- The 10 fields per grower are a top-10-by-area sample, not a random sample, and the 10
  fields in a grower share one climate grid. State both when quoting results.
