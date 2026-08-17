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

The reviewer starts on **START HERE**. Product and flow codes are joined to
their names in one visible **Category** column, such as `01 Coal`. In the other
tabs, the reviewer edits only the **Proposed colour — EDIT** column. They can
either type a six-digit hex colour such as `#1F77B4` or use Excel's
paint-bucket fill. The Category column must not be changed. The special label
tabs are optional.

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

Colours are applied after that conversion. The renderer reads the first ESTO
code in each Common ESTO label and looks it up in the product or flow colour
map. For example, the rolled product `01.02-01.04 Coal` uses the configured
colour for `01.02`. If an exact code has no colour, the renderer walks up the
code hierarchy, so an unseen `14.03.99` flow can inherit the colour for
`14.03 Manufacturing`.

This separation is deliberate: mapping logic determines which values belong
to a Common ESTO category, while this workbook determines only how the
resulting category is displayed.

## Usability recommendations

- Ask the reviewer to add a short note for major changes. This makes later
  palette discussions much easier.
- Start with Products and Flows; expose the special label tabs only when they
  need them.
- Prefer medium-dark, saturated colours that remain visible on a white chart.
- Check colour-blind distinguishability and contrast after import. Excel is the
  editing interface, but rendered dashboard charts remain the final review.
- Keep one approved workbook with the dashboard release so the human-readable
  palette and deployed config can be traced together.
