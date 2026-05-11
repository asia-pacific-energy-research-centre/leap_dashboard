"""
Entry point for the LEAP energy balance dashboard.

This is a thin wrapper — the full workflow lives in:
  codebase/leap_results_dashboard_v2_workflow.py

Run from repo root:
  python codebase/leap_results_dashboard_v2_workflow.py

DATA INPUTS (place in data/ — gitignored):
  data/leap results tables/          LEAP exported workbooks (.xlsx)
  data/00APEC_2025_low_with_subtotals.csv   ESTO base-year table
  data/merged_file_energy_ALL_20251106.csv  9th projection table

CONFIG (committed, edit as needed):
  config/master_config.xlsx          Sector/fuel mappings
  config/leap_comparison_dashboard_template_v2.json  Chart template

OUTPUT (written to docs/ — committed for GitHub Pages):
  docs/dashboards/    navigation HTML pages
  docs/charts/        per-node chart HTML files
  docs/supporting_files/  audit CSVs and diagnostics

KEY CONSTANTS TO UPDATE IN leap_results_dashboard_v2_workflow.py:
  LEAP_RESULTS_DIR      path to LEAP exported tables
  BASE_TABLE_PATH       path to ESTO base-year CSV
  PROJECTION_TABLE_PATH path to 9th projection CSV
  OUTPUT_DIR            set to REPO_ROOT / "docs"  to write to GitHub Pages
  ECONOMY_TOKEN         economy code (currently "USA")
  SCENARIOS             tuple of scenario names
"""
