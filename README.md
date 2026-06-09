# leap_dashboard

Generates and publishes an interactive HTML dashboard comparing LEAP energy balance results against ESTO base-year data and 9th projection data.

## How it works

The central script is [codebase/leap_results_dashboard_workflow.py](codebase/leap_results_dashboard_workflow.py). It runs five sequential stages:

1. **Extract** — reads LEAP balance export workbooks and maps rows to ESTO flow/product pairs
2. **Compare** — aligns LEAP, ESTO base-year, and 9th projection data on a common ESTO axis
3. **Write outputs** — writes comparison tables and diagnostics CSVs
4. **Render dashboards** — generates HTML/JS dashboard pages under `docs/`
5. **Write coverage** — writes mapping coverage checks and audit workbooks

The rendered dashboard is published via GitHub Pages from the `docs/` folder.

## Dependencies

This repo requires a sibling `leap_utilities` repo that contains shared config and data files:

```text
parent_folder/
  leap_dashboard/     ← this repo
  leap_utilities/     ← sibling repo (config, mappings, projection data)
```

If `leap_utilities` is elsewhere, set `LEAP_UTILITIES_ROOT` to its path before running.

## Getting data from LEAP (Export Balances)

In LEAP, use **Results > Export Balances** to export the balance workbook for each scenario. Export at **level 4 (high detail)** — reduced-detail exports will be rejected.

Name the exported files exactly as LEAP produces them:

```
full model output all years <date_id> REF.xlsx
full model output all years <date_id> TGT.xlsx
```

Place each file in the folder matching its economy code:

```
data/leap balances exports/
  20_USA/
    full model output all years 492026 REF.xlsx
    full model output all years 492026 TGT.xlsx
```

The workflow auto-detects the most recent export by date. These files are gitignored — do not commit them.

## Running the workflow

1. Open [codebase/leap_results_dashboard_workflow.py](codebase/leap_results_dashboard_workflow.py) and set the `ECONOMIES` list to the economy codes you want to process (e.g. `["20_USA"]`).

2. Run:

```bash
python codebase/leap_results_dashboard_workflow.py
```

Dashboard HTML is written to `docs/<economy>/`. Analytical outputs and diagnostics go to `outputs/<economy>/` (gitignored). Commit the `docs/` changes to publish.

## Stage skipping

Each stage can be skipped to reload cached outputs instead of recomputing. Common patterns at the top of the workflow file:

```python
# Re-render only (skip everything except dashboard rendering)
STAGE_EXTRACT = False
STAGE_COMPARE = False
STAGE_WRITE_OUTPUTS = False
STAGE_WRITE_COVERAGE = False

# Skip just the slow Excel read
STAGE_EXTRACT = False
```

## Repository structure

```
codebase/                   Python source
config/                     Templates, mappings, schema files
data/leap balances exports/ Raw LEAP exports, gitignored
docs/                       Published dashboard site (GitHub Pages)
  index.html                Economy selector
  <economy>/dashboards/     Navigation HTML pages
  <economy>/chart_bundles/  Per-page chart JS/JSON bundles
outputs/                    Analytical outputs, gitignored
```
