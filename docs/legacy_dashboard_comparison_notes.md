# Old Dashboard Reference Notes

The old `leap_dashboard` workflow is useful as a rendering reference, but it should not be copied wholesale.

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

