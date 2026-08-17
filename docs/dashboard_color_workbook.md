# Dashboard colour workbook

The dashboard colour scheme can be reviewed by a colleague in an ordinary,
macro-free Excel workbook. Production still reads
`config/common_esto_dashboard/code_colors.json`; the workbook is a friendly
editing surface, not a second runtime format.

## Send a workbook for review

1. Save the authoritative APERC file as
   `config/common_esto_dashboard/colors.json`.
2. Run the normal dashboard workflow. It creates or refreshes
   `outputs/dashboard_color_mapping/dashboard_color_mapping.xlsx` before
   rendering.
3. Send that workbook to the reviewer.

Workbook export treats `fuels.standard` in the downloaded JSON as the
authoritative, most detailed external palette. It does not infer colours from
the website display or replace detailed values with an aggregate grouping.
The EBT and Common ESTO 16.x code spaces differ, so their semantic bridge is
explicit rather than based on coincidentally equal codes.

Export stops with a list of missing or invalid fuels if the JSON omits any
required standard colour, contains a duplicate required code, or supplies an
invalid hex value. This happens before a workbook is written, so a partial
external palette cannot silently fall back to an older workbook colour.

The workbook has four visible sheets: **START HERE**, **Products**, **Flows**,
and **Other categories**. Product and flow codes are joined to their names in
one visible **Category** column, such as `01 Coal`. Placeholder codes without a
current hierarchy category are not shown. The reviewer edits the **Colour —
EDIT** column. They can type a six-digit hex colour such as `#1F77B4` or use
Excel's paint-bucket fill.

Products and Flows also have a **SYNC_WITH_JSON** switch and an automatic
**EXISTS_IN_JSON** indicator. `TRUE` sync uses the exact JSON colour when one
exists. Otherwise it uses the equal-weight OKLab average of the category's
mapping-owned components. If the category has neither an exact JSON colour nor
declared components, its current workbook colour is retained; it is never
replaced with `NA`, blank, or null. Set sync to `FALSE` only when a manual
workbook colour must override this behaviour.

For standalone comparison-boundary rollups such as transformation categories
labelled `(including own use)`, the component list comes from the upstream ESTO
rollup rules. This combines the transformation colour with its declared own-use
flow colours without inferring membership from the label.

**Other categories** contains the five comparison-line colours: ESTO
Historical, LEAP Reference, LEAP Target, 9th Reference, and 9th Target.

Common rollups are intentionally not shown. They are always regenerated as
equal-weight OKLab averages of their mapping-owned ESTO components.

## Apply the returned workbook

1. Save the returned file at the path set by `WORKBOOK_PATH`.
2. Run the normal dashboard workflow. The workbook is validated and reconciled
   automatically before any chart is rendered.

The import fails clearly if a hex code is invalid; a category, required row, or
tab was changed; the automatic `EXISTS_IN_JSON` indicator was edited; or a
cell's typed hex and fill colour were both changed to different colours. Hidden placeholder
codes remain unchanged. A successful import writes the complete reviewed scheme to
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
dashboard does not infer membership from the category label. The averages are
recomputed whenever an edited workbook is imported.

This separation is deliberate: mapping logic determines which values belong
to a Common ESTO category, while this workbook determines only how the
resulting category is displayed.

## Usability recommendations

- Prefer medium-dark, saturated colours that remain visible on a white chart.
- Check colour-blind distinguishability and contrast after import. Excel is the
  editing interface, but rendered dashboard charts remain the final review.
- Keep one approved workbook with the dashboard release so the human-readable
  palette and deployed config can be traced together.
