# Common ESTO Dashboard Generator

The production workflow builds the static Common ESTO comparison dashboard from long-form
or wide-form common ESTO comparison data. The frozen predecessor is at
`C:\Users\Work\github\leap_dashboard_legacy`. This implementation does not use
`relationship_id -> graph_id` links or the legacy ESTO-axis mapping pipeline.

## Run

From the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

Default output:

```text
outputs/common_esto_dashboard/<economy>/dashboards/index.html
```

The default sample economy is `20_USA`.

## Inputs

By default, the workflow reads the tracked weekly sample fixture:

```text
tests/fixtures/common_esto_dashboard/common_esto_comparison_data_sample.csv
tests/fixtures/common_esto_dashboard/common_esto_rows.csv
```

Update these fixture files when the upstream common ESTO data changes so the
sample remains representative and dashboard regressions are easier to spot.

To refresh the weekly sample from `leap_mappings/results/common_esto/` and run
the standard checks:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\update_common_esto_dashboard_fixture.py
```

The script copies:

```text
C:\Users\Work\github\leap_mappings\results\common_esto\common_esto_comparison_data.csv
C:\Users\Work\github\leap_mappings\results\common_esto\common_esto_rows.csv
```

into `tests/fixtures/common_esto_dashboard/`, then runs the smoke test and a
full dashboard render. The comparison fixture is written as a long-form
single-economy sample for `20_USA`, preserving all comparison scopes including
`leap_vs_ninth`. If `leap_mappings` is somewhere else, set `LEAP_MAPPINGS_ROOT`
before running the script.

To render every available economy from the upstream common ESTO output:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

This writes one dashboard folder per compact economy code under
`outputs/common_esto_dashboard/` and a compact run summary at:

```text
outputs/common_esto_dashboard/render_summary.csv
```

For quick checks, render a subset:

```powershell
$env:COMMON_ESTO_ECONOMIES = "01AUS,20USA"
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

To rebuild only the summary from existing rendered folders:

```powershell
$env:COMMON_ESTO_RENDER_DASHBOARDS = "0"
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

To flag dense or noisy pages after rendering:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\analyze_common_esto_dashboard_page_noise.py
```

This writes:

```text
outputs/common_esto_dashboard/page_noise_summary.csv
outputs/common_esto_dashboard/page_noise_flags.csv
```

For production or ad hoc runs, override the input paths with environment
variables:

```powershell
$env:COMMON_ESTO_INPUT_DATA_PATH = "C:\path\to\common_esto_comparison_data.csv"
$env:COMMON_ESTO_ROWS_PATH = "C:\path\to\common_esto_rows.csv"
$env:COMMON_ESTO_ECONOMY = "20_USA"
$env:COMMON_ESTO_COMPARISON_SCOPE = "leap_vs_esto_vs_ninth"
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

## Config

Dashboard config lives in:

```text
config/common_esto_dashboard/common_esto_dashboard_template.json
config/common_esto_dashboard/series_config.json
```

The template controls page assignment, sign semantics, total demand, optional
diagnostic scope-specific pages, and the disabled Sankey scaffold.
Scope-specific pages are disabled by default until their content has been
reviewed for production usefulness; enable `scope_specific_pages.enabled` only
for focused review runs. `series_config.json` controls visible source/scenario
series, labels, economy display text, and the static dashboard switcher.

Page status and diagnostic-page review notes are tracked in:

```text
docs/common_esto_dashboard_page_status.md
```

Sankey routing remains disabled. The draft routing table and QA checker are:

```text
config/common_esto_dashboard/sankey_routing_table_draft.csv
scripts/check_common_esto_sankey_routing.py
```

Run the QA checker before enabling any route:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_sankey_routing.py
```

## Publish

Generated outputs stay under `outputs/` by default and are ignored by git. To
check that the rendered dashboard is ready for manual publication, run:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_dashboard_publish_ready.py
```

The readiness check scans every rendered economy under
`outputs/common_esto_dashboard/` and validates the pages and Plotly bundles
listed in each economy's chart manifest.

To copy serving assets to GitHub Pages, set `PUBLISH_TO_DOCS = True` in the
workflow and rerun it. This stays as a manual toggle so fixture refreshes and
ordinary render checks do not accidentally update `docs/`.
Only `.html`, `.js`, and `.json` dashboard-serving files are copied to `docs/`;
supporting CSVs remain in `outputs/`.

## Smoke Tests

Run the Common ESTO smoke tests from the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
```
