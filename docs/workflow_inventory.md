# Workflow Inventory

Last reviewed: 2026-08-17

This repo centers on the Common ESTO dashboard. The inventory below groups the
production dashboard workflow, batch render helpers, and QA/fixture maintenance
scripts so it is clear what is part of the active surface.

## Active Entry Points

| Script | Bucket | Purpose |
|---|---|---|
| `codebase/common_esto_dashboard_workflow.py` | Production workflow | Renders the Common ESTO dashboard for the configured economy and publishes output assets when enabled. |
| `codebase/common_esto_dashboard_from_export.py` | Export-driven workflow | Renders from a supplied LEAP export through the maintained mapping-chain boundary. |
| `codebase/common_esto_dashboard_portable.py` | Portable workflow | Builds reduced portable/web comparison variants without claiming the full production mapping-diagnostics contract. |
| `scripts/render_common_esto_dashboard_all_economies.py` | Batch render / QA | Renders dashboards for all available economies and writes a render summary. |
| `scripts/check_common_esto_dashboard_publish_ready.py` | Publish QA | Verifies rendered dashboard pages, chart bundles, and supporting files before publishing to `docs/`. |
| `scripts/analyze_common_esto_dashboard_page_noise.py` | QA / diagnostics | Analyzes page noise and writes summary diagnostics for the rendered dashboard output. |
| `scripts/check_common_esto_sankey_routing.py` | QA / diagnostics | Checks the draft Sankey routing table against dashboard data. |
| `scripts/update_common_esto_dashboard_fixture.py` | Fixture maintenance | Refreshes the test fixture set used by `tests/test_common_esto_dashboard.py`. |
| `scripts/check_common_esto_dashboard_determinism.py` | Regression QA | Re-renders and checks stable dashboard artifacts. |
| `scripts/capture_common_esto_baseline.py` | Regression QA | Captures normalized dashboard evidence used by focused comparisons. |
| `scripts/capture_frontier_baseline.py` | Regression QA | Captures selected chart-frontier tuples before routing/frontier changes. |
| `scripts/manage_dashboard_colors.py` | Colour maintenance | Exports, validates, and imports the editable dashboard colour workbook. |
| `scripts/generate_code_colors.py` | Colour maintenance | Rebuilds derived code colours from the maintained colour configuration. |
| `scripts/render_mapping_pipeline_health_report.py` | QA / diagnostics | Summarizes upstream Stage 3 provenance, validation status, and mapping-pipeline health without loading the full comparison dataset. |
| `scripts/render_full_mapping_tree_explorer.py` | Structural diagnostics | Renders the maintained source / ESTO-component / Common ESTO tree explorer. |
| `scripts/render_transformation_rollup_diagnostics_prototype.py` | Maintained investigation helper | Renders the focused mapping-diagnostics prototype and body fragment used to review rollup arithmetic. |

## Supporting Modules

These are not standalone workflows, but they are the core production modules
behind the dashboard entrypoint:

- `codebase/common_esto_dashboard_data.py`
- `codebase/common_esto_dashboard_renderer.py`
- `codebase/common_esto_dashboard_output_layout.py`
- `codebase/common_esto_dashboard_convergence.py`
- `codebase/common_esto_dashboard_emissions.py`
- `codebase/common_esto_dashboard_guide.py`
- `codebase/common_esto_dashboard_mapping_diagnostics.py`
- `codebase/dashboard_color_config.py`
- `codebase/hierarchy_subtotal_contract_loader.py`
- `codebase/mapping_diagnostics_contract.py`
- `codebase/mapping_pipeline_provenance.py`
- `codebase/dashboard_page_fragment.py`

## Retained investigation prototypes

These are direct-artifact readers retained for comparison or focused
investigation. They are not production data-loading entry points and should not
be extended as though they own the dashboard contract:

| Script | Status | Use |
|---|---|---|
| `scripts/render_mapping_tree_explorer_prototype.py` | Superseded prototype, retained | Earlier three-case explorer used for historical comparison; new explorer work belongs in `render_full_mapping_tree_explorer.py`. |

The transformation rollup prototype remains actively useful because it renders
the same diagnostics surface used for focused review. Its fixed investigation
inputs are intentionally outside the v1 contract migration until the prototype
is promoted into a separate maintained production workflow.

## Notes

- The production workflow is notebook-safe and is the main entry point for
  dashboard rendering.
- The scripts under `scripts/` are operational helpers around the same
  dashboard surface, mostly for batch rendering, diagnostics, and publish
  checks.
- The production loader defaults to the manifested Common ESTO parquet table
  and validates the upstream generation manifest before rendering. Legacy CSV
  fixture paths remain supported only when selected explicitly for regression
  tests or a deliberately supplied input.
