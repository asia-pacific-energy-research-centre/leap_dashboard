# Common ESTO Dashboard Generator

This package builds the static Common ESTO comparison dashboard from long-form
or wide-form common ESTO comparison data. It is separate from the older LEAP
results dashboard workflow and does not use `relationship_id -> graph_id` links
or the old ESTO-axis mapping pipeline.

## Run

From the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard\common_esto_dashboard_workflow.py
```

Default output:

```text
outputs/common_esto_dashboard/<economy>/dashboards/index.html
```

The default sample economy is `20_USA`.

## Inputs

By default, the workflow reads the tracked weekly sample fixture:

```text
tests/fixtures/common_esto_dashboard/common_esto_comparison_wide.csv
tests/fixtures/common_esto_dashboard/common_esto_rows.csv
```

Update these fixture files when the upstream common ESTO data changes so the
sample remains representative and dashboard regressions are easier to spot.

For production or ad hoc runs, override the input paths with environment
variables:

```powershell
$env:COMMON_ESTO_INPUT_DATA_PATH = "C:\path\to\common_esto_comparison_data.csv"
$env:COMMON_ESTO_ROWS_PATH = "C:\path\to\common_esto_rows.csv"
$env:COMMON_ESTO_ECONOMY = "20_USA"
$env:COMMON_ESTO_COMPARISON_SCOPE = "leap_vs_esto_vs_ninth"
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard\common_esto_dashboard_workflow.py
```

## Config

Dashboard config lives in:

```text
config/common_esto_dashboard/common_esto_dashboard_template.json
config/common_esto_dashboard/series_config.json
```

The template controls page assignment, sign semantics, total demand, optional
scope-specific pages, and the disabled Sankey scaffold. `series_config.json`
controls visible source/scenario series, labels, economy display text, and the
static dashboard switcher.

## Publish

Generated outputs stay under `outputs/` by default and are ignored by git. To
copy serving assets to GitHub Pages, set `PUBLISH_TO_DOCS = True` in the workflow.
Only `.html`, `.js`, and `.json` dashboard-serving files are copied to `docs/`;
supporting CSVs remain in `outputs/`.

## Smoke Tests

Run the Common ESTO smoke tests from the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
```
