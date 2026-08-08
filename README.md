# LEAP Common ESTO Dashboard

This repository contains the official static dashboard for Common ESTO
comparison outputs. It consumes the comparison dataset produced by the sibling
`leap_mappings` repository and renders one dashboard per economy.

## Start here

For the connected three-repository ownership and reading route, start with
[`leap_mappings/docs/start_here.md`](../leap_mappings/docs/start_here.md).

Within this repository:

| Need | Authoritative route |
|---|---|
| understand or run the dashboard pipeline | [`docs/handover/dashboard_pipeline_guide.md`](docs/handover/dashboard_pipeline_guide.md) |
| execute safely as an agent | [`docs/handover/dashboard_pipeline_agent_guide.md`](docs/handover/dashboard_pipeline_agent_guide.md) |
| understand mapping diagnostics | [`docs/handover_mapping_diagnostics.md`](docs/handover_mapping_diagnostics.md) |
| choose current or deferred work | [`docs/work_queue.md`](docs/work_queue.md) |
| review output/page status after a fresh render | [`docs/common_esto_dashboard_page_status.md`](docs/common_esto_dashboard_page_status.md) |

The dated
[`documentation audit`](docs/documentation_audit_20260728.md) records the
disposition of every tracked Markdown document; it is evidence, not the
operating queue.

The production entry point is
`codebase/common_esto_dashboard_workflow.py`. Supporting modules are flattened
directly under `codebase/`; configuration is under
`config/common_esto_dashboard/`; tests and sample fixtures are under `tests/`.

The previous ESTO-axis dashboard is frozen separately for historical and visual
comparison at:

```text
C:\Users\Work\github\leap_dashboard_legacy
```

## Run the dashboard

From the repository root:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

The ordinary workflow reuses existing Common ESTO outputs and writes generated
files to:

```text
outputs/common_esto_dashboard/20USA/
```

The main artifacts are `dashboards/index.html`, page-level Plotly bundles under
`chart_bundles/`, and audit files under `supporting_files/`, including
`chart_manifest.csv` and `page_assignment_summary.csv`.

Focused tests use the tracked `20_USA` fixture. The workflow currently renders
`20_USA` and `02_BD` by default; set `COMMON_ESTO_ECONOMIES` to select a
different reviewed set. Set
`COMMON_ESTO_INPUT_DATA_PATH` and `COMMON_ESTO_ROWS_PATH` for an explicit
fixture render. Refreshing upstream inputs and publishing into tracked
`docs/` are opt-in via `COMMON_ESTO_UPDATE_DATA=1` and
`COMMON_ESTO_PUBLISH_TO_DOCS=1`.

## Tests and operational checks

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_dashboard_publish_ready.py
C:\Users\Work\miniconda3\python.exe scripts\analyze_common_esto_dashboard_page_noise.py
```

Additional scripts refresh fixtures from `leap_mappings`, render all available
economies, and validate the disabled Sankey routing scaffold. See
`docs/common_esto_dashboard_guide.md` for operational details and
`docs/common_esto_dashboard_plan.md` for the design. The approved contract for
page-root ownership, routing special cases, and dataset-presence chart filtering
is in `docs/dashboard_page_routing_and_chart_visibility.md`.

## Repository structure

```text
codebase/                         production workflow and renderer modules
config/common_esto_dashboard/     dashboard, series, and routing configuration
tests/                            smoke tests
tests/fixtures/common_esto_dashboard/
scripts/                          refresh, batch render, QA, and publish checks
docs/                             design and decision documentation
outputs/                          generated dashboards and diagnostics (ignored)
```
