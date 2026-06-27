# Legacy Dashboard Reference Notes

The frozen repository at `C:\Users\Work\github\leap_dashboard_legacy` is the
rendering reference. Its main entry point is
`codebase/leap_results_dashboard_workflow.py`; do not copy that architecture
back into the official repository.

Reusable ideas:

- Write one folder per economy under `outputs/<economy>/`.
- Write page-level Plotly JSON bundles under `chart_bundles/`.
- Write static HTML pages under `dashboards/`.
- Write a manifest/ledger that explains what each chart contains.
- Optional: compare current chart bundles with a previous run.

Avoid carrying over:

- The old LEAP extraction stage.
- The old ESTO-axis mapping pipeline.
- `relationship_id -> graph_id` links.
- `dashboard_chart` as a required mapping use case.
- Old `sheet` / `fuel_label` assumptions as the primary data model.

The new dashboard should start from `common_esto_comparison_data.csv` and use:

- `comparison_scope`
- `source_system`
- `economy`
- `scenario`
- `year`
- `common_flow_label`
- `common_product_label`
- `value`
