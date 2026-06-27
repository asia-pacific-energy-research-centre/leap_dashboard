# AGENTS.md

Project instructions for the production Common ESTO dashboard.

## Repository scope

- This repository owns the official Common ESTO dashboard.
- Production implementation files live directly under `codebase/`:
  - `common_esto_dashboard_workflow.py`
  - `common_esto_dashboard_data.py`
  - `common_esto_dashboard_renderer.py`
  - `common_esto_dashboard_output_layout.py`
- Production configuration lives under `config/common_esto_dashboard/`.
- Tests and fixtures live under `tests/` and
  `tests/fixtures/common_esto_dashboard/`.
- Supporting scripts under `scripts/` handle fixture refresh, all-economy
  rendering, visual/page-noise review, routing QA, and publication readiness.
- Do not place new implementation work under `test/`.

The frozen historical and visual comparison repository is:

```text
C:\Users\Work\github\leap_dashboard_legacy
```

Do not reintroduce its ESTO-axis workflow, direct mapping pipeline, or config
into this repository. Use that repository when a legacy comparison is needed.

## Upstream data boundary

`leap_mappings` owns mapping logic and produces the Common ESTO comparison
data consumed here. Read
`C:\Users\Work\github\leap_mappings\docs\mappings_system.md` before changing
assumptions about comparison scopes, hierarchy, component membership, rollups,
or generated category labels. Do not reproduce mapping logic in dashboard code.

## Running and validation

Use the Windows Python environment documented in the project instructions:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
```

The default workflow renders the tracked `20_USA` fixture to
`outputs/common_esto_dashboard/20USA/`. Before completing code or config work:

1. Run the focused tests.
2. Render the sample fixture.
3. Confirm dashboard HTML, Plotly bundles, `chart_manifest.csv`, and
   `page_assignment_summary.csv` exist.
4. Run the publication-readiness and page-noise scripts.
5. For production-data changes, smoke-test the all-economy renderer when the
   upstream dataset is available.

Generated outputs stay under `outputs/` unless publication is explicitly
enabled. Do not edit generated dashboard files directly.

## Development rules

- Keep workflow scripts notebook-safe with `#%%` cells and editable constants.
- Resolve paths from `REPO_ROOT`, independently of the current working directory.
- Treat `comparison_scope`, `common_flow_label`, and `common_product_label` as
  dashboard axes; component membership remains the source of truth for
  generated categories.
- Do not use `relationship_id -> graph_id` links or require `dashboard_chart`.
- Track presentation rules and unresolved semantics in
  `docs/special_rules_and_design_decisions.md`.
- Commit small, verified checkpoints and never push unless explicitly asked.
