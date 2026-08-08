"""T6 baseline: capture the exact tuple set select_non_overlapping_rows retains.

Monkeypatches common_esto_dashboard_emissions.select_non_overlapping_rows to
record its input/output during a real render (the Emissions page is its only
caller), then writes the retained
(source_system, scenario, common_flow_label, common_product_label) tuple set
per economy to
tests/fixtures/common_esto_dashboard/baseline_<economy>/frontier_tuples_t6.csv.

Must be captured on unmodified code, same as T1 - there is no way to recover
a "before" snapshot once select_non_overlapping_rows changes. Asserting on
the set (not a count or a total) is the point: totals can coincide while the
wrong rows are retained (the bug class that produced 4,838-vs-3,443).

Usage:
    python scripts/capture_frontier_baseline.py [ECONOMY ...]

Defaults to 20USA and 02BD when no economies are given.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEBASE_ROOT = REPO_ROOT / "codebase"
if str(CODEBASE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEBASE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard"
TUPLE_COLUMNS = ["source_system", "scenario", "common_flow_label", "common_product_label"]

captured_by_economy: dict[str, pd.DataFrame] = {}
_current_economy: list[str] = []


def _patch_mapping_tree_explorer_root() -> None:
    import os

    import scripts.render_full_mapping_tree_explorer as tree_explorer

    leap_mappings_root = os.getenv("LEAP_MAPPINGS_ROOT")
    if leap_mappings_root:
        tree_explorer.MAPPINGS_ROOT = Path(leap_mappings_root)


def _install_capture_hook() -> None:
    import common_esto_dashboard_emissions as emissions

    original = emissions.select_non_overlapping_rows

    def wrapped(df: pd.DataFrame) -> pd.DataFrame:
        result = original(df)
        if _current_economy:
            captured_by_economy[_current_economy[-1]] = result.copy()
        return result

    emissions.select_non_overlapping_rows = wrapped
    import common_esto_dashboard_renderer as renderer

    renderer.build_emissions_page.__globals__["select_non_overlapping_rows"] = wrapped


def main(argv: list[str]) -> int:
    economies = argv or ["20USA", "02BD"]
    _patch_mapping_tree_explorer_root()
    _install_capture_hook()

    import common_esto_dashboard_workflow as workflow

    for economy in economies:
        _current_economy.append(economy)
        workflow.run_dashboard_for_economy(economy)
        _current_economy.pop()

    for economy in economies:
        frontier = captured_by_economy.get(economy)
        dest = FIXTURES_ROOT / f"baseline_{economy}"
        dest.mkdir(parents=True, exist_ok=True)
        if frontier is None or frontier.empty:
            print(f"[{economy}] WARNING: no frontier captured (Emissions page disabled?)")
            pd.DataFrame(columns=TUPLE_COLUMNS).to_csv(dest / "frontier_tuples_t6.csv", index=False)
            continue
        tuples = frontier[TUPLE_COLUMNS].drop_duplicates()
        tuples = tuples.astype(str).sort_values(TUPLE_COLUMNS).reset_index(drop=True)
        tuples.to_csv(dest / "frontier_tuples_t6.csv", index=False)
        print(f"[{economy}] T6 baseline captured: {len(tuples)} retained tuples -> {dest / 'frontier_tuples_t6.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
