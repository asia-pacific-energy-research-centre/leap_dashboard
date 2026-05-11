"""
Main entry point: build the LEAP results dashboard and write output to docs/.

Inputs (from data/inputs/ and config/):
  - LEAP balance exports (CSV/Excel)
  - config/leap_mappings.xlsx
  - config/leap_comparison_dashboard_template_v2.json

Outputs written to docs/:
  - docs/dashboards/   navigation HTML pages
  - docs/charts/       per-node energy balance chart HTML files
  - docs/supporting_files/  audit CSVs and diagnostics

Transfer the dashboard engine modules from leap_utilities:
  codebase/utilities/leap_results_dashboard_v2/
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
DATA_INPUTS = REPO_ROOT / "data" / "inputs"
CONFIG_DIR = REPO_ROOT / "config"
OUTPUTS_DIR = REPO_ROOT / "outputs"


def main() -> None:
    raise NotImplementedError(
        "Transfer dashboard engine modules from leap_utilities and wire up here. "
        "See leap_utilities/codebase/leap_results_dashboard_v2_workflow.py for reference."
    )


if __name__ == "__main__":
    main()
