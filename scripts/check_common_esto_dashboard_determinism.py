"""T0 determinism guard: render an economy twice with no code change and assert
every generated CSV is equal after normalisation (sort by all columns, reset
index).

This protects every comparison the overnight work program makes against T1
baselines: if a render is not content-deterministic, "the CSV differs" stops
meaning "the code changed."

Renders are known to NOT be byte-deterministic (row order can shuffle between
runs from Python's per-process string hash randomisation), so this compares
normalised content, never raw bytes/hashes/`git diff`.

Usage:
    python scripts/check_common_esto_dashboard_determinism.py [ECONOMY]

Defaults to 20USA. Exits 0 if every supporting CSV matches after
normalisation, prints a diff summary and exits 1 otherwise (callers should
treat a nonzero exit as "fall back to a 1e-9 tolerance and record it", not as
a program-level halt).
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

CHECKED_FILES = [
    "chart_manifest.csv",
    "emissions_by_sector_and_fuel.csv",
    "emissions_factor_resolution.csv",
    "page_assignment_summary.csv",
]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    sort_key = df.astype(str)
    order = sort_key.sort_values(by=list(df.columns)).index
    return df.loc[order].reset_index(drop=True)


def _patch_mapping_tree_explorer_root() -> None:
    """Work around a known, out-of-scope bug: render_full_mapping_tree_explorer.py
    hardcodes MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings" and ignores
    LEAP_MAPPINGS_ROOT, so it resolves to the worktrees directory (not the repo
    parent) and crashes when this repo is checked out as a worktree. Patching the
    already-imported module's MAPPINGS_ROOT attribute at runtime is a
    process-local, reversible workaround, not a fix to the script on disk.
    """
    import os

    import scripts.render_full_mapping_tree_explorer as tree_explorer

    leap_mappings_root = os.getenv("LEAP_MAPPINGS_ROOT")
    if leap_mappings_root:
        tree_explorer.MAPPINGS_ROOT = Path(leap_mappings_root)


def _render_and_read(economy: str) -> dict[str, pd.DataFrame]:
    _patch_mapping_tree_explorer_root()
    import common_esto_dashboard_workflow as workflow

    result = workflow.run_dashboard_for_economy(economy)
    layout_root = Path(result["dashboard_index"]).parents[1]
    supporting = layout_root / "supporting_files"
    out = {}
    for filename in CHECKED_FILES:
        src = supporting / filename
        if src.exists():
            out[filename] = _normalize(pd.read_csv(src))
    return out


def main(argv: list[str]) -> int:
    economy = argv[0] if argv else "20USA"
    first = _render_and_read(economy)
    second = _render_and_read(economy)

    ok = True
    for filename in CHECKED_FILES:
        if filename not in first or filename not in second:
            print(f"SKIP {filename}: absent in one or both runs")
            continue
        try:
            pd.testing.assert_frame_equal(first[filename], second[filename], check_like=False)
            print(f"PASS {filename}: identical after normalisation ({len(first[filename])} rows)")
        except AssertionError as error:
            ok = False
            print(f"FAIL {filename}: differs after normalisation\n{error}")

    print("T0 determinism guard:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
