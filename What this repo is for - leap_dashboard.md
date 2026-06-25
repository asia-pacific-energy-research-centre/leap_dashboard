# What this repo is for - leap_dashboard

`leap_dashboard` generates and publishes the LEAP balance dashboard for APERC.
Its job is to compare LEAP balance exports against ESTO base-year data and 9th
projection data on a common ESTO balance-axis structure, then render those
comparisons as HTML dashboards and supporting audit files.

## What the dashboard is for

The dashboard is designed for two related uses:

1. Compare LEAP balance exports with ESTO and 9th data.
2. Audit the mapping that places those three sources onto the same axis.

That means the dashboard is not only a visual report. It is also a mapping and
comparison check. The charted values should be traceable back to the mapping
rows and comparator pairs that produced them.

## Why this repo uses an ESTO axis

The workflow uses ESTO flow/product rows as the common comparison axis because
they sit between the raw LEAP balance labels and the full 9th sector/fuel
hierarchy.

In practice:

- LEAP balance cells are mapped to ESTO flow/product pairs.
- 9th projection rows are mapped back to the same ESTO pairs.
- ESTO base-year data is already available on that axis.

This gives one consistent structure for comparing all three sources.

## How the workflow is organized

The main entry point is
[codebase/leap_results_dashboard_workflow.py](codebase/leap_results_dashboard_workflow.py).
It runs five stages:

1. Extract LEAP balance workbooks into mapped rows.
2. Compare LEAP, ESTO, and 9th data on the ESTO axis.
3. Write comparison tables and diagnostics.
4. Render the HTML dashboards and Plotly chart bundles.
5. Write coverage and audit outputs.

The workflow can also run in re-render-only mode when the comparison data is
already available. That is the normal fast path for dashboard iteration.

## How this repo links to `leap_utilities`

This repo does not own all of its source data and mappings. It depends on the
sibling `leap_utilities` repo for shared inputs, especially:

- `config/leap_mappings.xlsx`
- `config/master_config.xlsx`
- projection and support data used by the comparison workflow

The workflow reads those shared files through `LEAP_UTILITIES_ROOT`. By default
it expects a sibling checkout:

```text
parent_folder/
  leap_dashboard/
  leap_utilities/
```

If `leap_utilities` lives elsewhere, the workflow can be pointed at it with the
`LEAP_UTILITIES_ROOT` environment variable.

## What lives in this repo

This repo owns the dashboard implementation and its local configuration:

- `codebase/` contains the workflow and supporting Python modules.
- `config/` contains the dashboard template and repo-local mappings.
- `docs/` contains the published HTML site that GitHub Pages serves.
- `outputs/` contains generated analysis artifacts and is not the published site.

The dashboard template in
[config/leap_comparison_dashboard_template_v3.json](config/leap_comparison_dashboard_template_v3.json)
defines the page structure, chart grouping, and the user-facing "About this
dashboard" content.

## Published outputs

Running the workflow writes two kinds of outputs:

- `docs/<economy>/...` for the published dashboard site.
- `outputs/<economy>/...` for comparison tables, mapping diagnostics, and
  runtime audit files.

The `docs/` tree is the GitHub Pages source for the published dashboard.

## Short version

`leap_dashboard` is the dashboard layer. `leap_utilities` is the shared mapping
and data layer. The workflow joins them, aligns the data on an ESTO axis, and
publishes the resulting comparisons as a dashboard site with audit artifacts.
