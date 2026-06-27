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

## Verified history

- Common ESTO first appeared in commit
  `1984a6bdf592cabb49e9f5d4db0d09be1ffc8004`.
- Its parent, `8747ca2bfeece881a34026517589ad9319f66bc4`, is the
  frozen legacy code boundary.
- At introduction, the data module, renderer, and output-layout files in the
  test pack and production directory were byte-identical. The workflow logic
  was also shared, but the production copy already used repository-relative
  paths while the pack copy used pack-relative paths.
- The test-pack implementation received no later code changes. Production
  hardening continued only under the former `codebase/common_esto_dashboard/`
  path before that implementation was flattened into `codebase/`.
- No commit after the introduction independently changed legacy-owned files.
  Changes to those files within the mixed introduction commit were therefore
  excluded from the frozen reference.

## 2026-06-27 visual and functional comparison

The comparison used:

- legacy code boundary `8747ca2`, with tracked USA dashboard pages under
  `leap_dashboard_legacy/docs/USA/`;
- official dashboard commit `398d5bc`, rendered from the tracked 20_USA
  Common ESTO fixture to `outputs/common_esto_dashboard/20USA/`;
- a 1440 x 1000 desktop viewport for Industry, Supply, and Buildings, plus a
  500 x 900 responsive Industry check;
- the legacy LEAP/ESTO/9th dashboard and the Common ESTO fixture as related
  subject matter, not numerically equivalent datasets.

The legacy pages remain stronger at aggregate-first storytelling: one large
stacked chart is easy to scan, fuel colours are prominent, and section links
lead to focused subpages. The Common ESTO pages are stronger at direct
source-series comparison, automatic coverage, signed-flow context, sorting,
auditability, lazy loading, and showing multiple flow rows without manually
enumerated pages.

The first Common ESTO screenshots exposed unreadable four-column overview
cards: long legends and sign subtitles covered plot data. Commit `398d5bc`
changes overviews to two responsive columns, ordinary chart grids to three
columns, moves dense legends below the plot, and wraps mobile navigation. The
rechecked Industry, Supply, and Buildings pages no longer show title/legend
collisions. Dense product legends remain scrollable; this is preferable to
hiding series, but page-noise and aggregate-first presentation still need
representative all-economy review.

The frozen legacy workflow imports and its four retained tests pass. A fresh
legacy render against the current sibling `leap_utilities` workbook is not
reproducible: the historical validator rejects current non-subtotal
many-to-many mapping rows. The tracked legacy HTML is therefore the visual
reference. Weakening the frozen validator or importing current mapping rules
would invalidate the historical boundary.

An additional one-economy batch smoke test used the upstream
`leap_mappings/results/common_esto/` outputs and rendered 20USA successfully:
850 charts from 19,103 visible rows. The mapping repository was at commit
`52d2137`, but its worktree contained unrelated uncommitted mapping changes, so
that commit does not fully identify the generated input state. The comparison
data file was dated 2026-06-27 16:46 and `common_esto_rows.csv` was dated
2026-06-27 11:52. Treat this as a production-path smoke test, not a frozen
numerical benchmark.
