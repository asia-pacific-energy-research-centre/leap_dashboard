# Workflow Inventory

Last reviewed: 2026-07-07

This repo centers on the Common ESTO dashboard. The inventory below groups the
production dashboard workflow, batch render helpers, and QA/fixture maintenance
scripts so it is clear what is part of the active surface.

## Active Entry Points

| Script | Bucket | Purpose |
|---|---|---|
| `codebase/common_esto_dashboard_workflow.py` | Production workflow | Renders the Common ESTO dashboard for the configured economy and publishes output assets when enabled. |
| `scripts/render_common_esto_dashboard_all_economies.py` | Batch render / QA | Renders dashboards for all available economies and writes a render summary. |
| `scripts/check_common_esto_dashboard_publish_ready.py` | Publish QA | Verifies rendered dashboard pages, chart bundles, and supporting files before publishing to `docs/`. |
| `scripts/analyze_common_esto_dashboard_page_noise.py` | QA / diagnostics | Analyzes page noise and writes summary diagnostics for the rendered dashboard output. |
| `scripts/check_common_esto_sankey_routing.py` | QA / diagnostics | Checks the draft Sankey routing table against dashboard data. |
| `scripts/update_common_esto_dashboard_fixture.py` | Fixture maintenance | Refreshes the test fixture set used by `tests/test_common_esto_dashboard.py`. |

## Supporting Modules

These are not standalone workflows, but they are the core production modules
behind the dashboard entrypoint:

- `codebase/common_esto_dashboard_data.py`
- `codebase/common_esto_dashboard_renderer.py`
- `codebase/common_esto_dashboard_output_layout.py`

## Notes

- The production workflow is notebook-safe and is the main entry point for
  dashboard rendering.
- The scripts under `scripts/` are operational helpers around the same
  dashboard surface, mostly for batch rendering and publish checks.

