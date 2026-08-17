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

The reviewer starts on **START HERE**. In the other tabs, they edit only the
**Proposed colour — EDIT** column. They can either type a six-digit hex colour
such as `#1F77B4` or use Excel's paint-bucket fill. Product and flow codes must
not be changed. The special label tabs are optional.

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
