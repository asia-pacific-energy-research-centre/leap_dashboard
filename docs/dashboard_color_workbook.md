# Dashboard colour workbook

The dashboard colour scheme can be reviewed by a colleague in an ordinary,
macro-free Excel workbook. Production still reads
`config/common_esto_dashboard/code_colors.json`; the workbook is a friendly
editing surface, not a second runtime format.

## Send a workbook for review

1. Open `scripts/manage_dashboard_colors.py` in Jupyter or VS Code's notebook
   view.
2. Set `EXPORT_WORKBOOK = True` in the controls at the bottom.
3. Run the file. It writes
   `outputs/dashboard_color_mapping/dashboard_color_mapping.xlsx`.
4. Send that workbook to the reviewer.

The workbook has only three visible sheets: **START HERE**, **Products**, and
**Flows**. Product and flow codes are joined to their names in one visible
**Category** column, such as `01 Coal`. The reviewer edits only the
**Colour — EDIT** column. They can type a six-digit hex colour such as
`#1F77B4` or use Excel's paint-bucket fill.

Blue **Common rollup** rows are automatic equal-weight OKLab averages of the
listed ESTO components. Leave them unchanged to keep automatic calculation.
Edit one only when that particular rollup needs a deliberate override.

## Apply the returned workbook

1. Save the returned file at the path set by `WORKBOOK_PATH`.
2. Set `EXPORT_WORKBOOK = False` and `IMPORT_WORKBOOK = True`.
3. Run the file.

The import fails clearly if a hex code is invalid, a required row or tab was
removed, or a cell's typed hex and fill colour were both changed to different
colours. A successful import writes the complete reviewed scheme to
`config/common_esto_dashboard/code_colors_custom.json` and applies it to
`code_colors.json`. The normal colour generator reapplies the custom layer on
future runs, so reviewed changes are not lost.

After importing, render the tracked USA fixture and run the usual publication
readiness and page-noise checks. Review charts with many stacked categories in
particular: two individually attractive colours can still be too similar when
they appear next to each other.

## How these colours reach Common ESTO dashboard categories

This workbook does not convert source data into the Common ESTO structure.
That conversion is owned by `leap_mappings`. For each participating dataset,
the upstream process merges each native flow/product pair onto its declared
`common_row_id`, then aggregates by that identifier. It does not split or
allocate values. The dashboard reads the resulting
`common_esto_comparison_data` output.

Colours are applied after that conversion. Exact Common ESTO categories use
their configured ESTO product or flow colour. Multi-component categories use
an equal-weight average in OKLab colour space. For example,
`01.02-01.04 Coal` averages the colours of `01.02`, `01.03`, and `01.04`.
Using equal component weights keeps the colour stable across economies,
scenarios, years, and data values. If an exact component has no colour, it
inherits the nearest configured parent colour before the average is taken.

Component membership comes from the mapping-owned `common_esto_rows.csv`; the
dashboard does not infer membership from the category label. An optional
rollup override from the workbook is applied after the automatic average.

This separation is deliberate: mapping logic determines which values belong
to a Common ESTO category, while this workbook determines only how the
resulting category is displayed.

## Usability recommendations

- Prefer medium-dark, saturated colours that remain visible on a white chart.
- Check colour-blind distinguishability and contrast after import. Excel is the
  editing interface, but rendered dashboard charts remain the final review.
- Keep one approved workbook with the dashboard release so the human-readable
  palette and deployed config can be traced together.
