# Assignment 2 field-EDA report

One-time report artifact for the Assignment 2 field-level EDA. It is deliberately
outside the reusable subskill: it consumes one run's figures and tables and explains
them to a reader who does not have the runtime open.

- `assignment-2-field-eda.pdf` - the report (8 pages, under 1 MB, no external assets).
- `build_report.py` - rebuilds the PDF from a run directory:

  ```bash
  python reports/assignment-2-field-eda/build_report.py \
      --run-dir ~/my-farm-advisor-runtime/data-pipeline/eda/field-eda/<run-id>
  ```

The PDF embeds downscaled copies of the ten figures and quotes only numbers read from
`tables/*.csv` and `manifest.json`, so the text cannot drift from the run it documents.
The builder needs `fpdf2`, `pandas`, `scipy`, `Pillow` and `matplotlib` (the last for
its bundled DejaVu fonts). Source run: `20261128T015426Z`.
