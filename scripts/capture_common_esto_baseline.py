"""Capture normalised "before" snapshots of the Common ESTO dashboard render.

Renders each requested economy with `common_esto_dashboard_workflow` and
writes normalised copies of the supporting CSVs, a page inventory, and a T3
chart-bundle numeric fingerprint into
``tests/fixtures/common_esto_dashboard/baseline_<economy>/``.

Renders are content-deterministic but not byte-deterministic (row order can
differ between runs because of Python's per-process string hash
randomisation), so every file here is sorted by all columns and index-reset
before being written. Never compare these fixtures with `git diff` on raw
generated output — always go through this normalisation first.

Usage:
    python scripts/capture_common_esto_baseline.py [ECONOMY ...]

Defaults to 20USA and 02BD when no economies are given.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEBASE_ROOT = REPO_ROOT / "codebase"
if str(CODEBASE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEBASE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard"

SUPPORTING_FILES = [
    "chart_manifest.csv",
    "emissions_by_sector_and_fuel.csv",
    "emissions_factor_resolution.csv",
    "page_assignment_summary.csv",
]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by all columns (as strings, to keep mixed dtypes orderable) and reset the index."""
    if df.empty:
        return df.reset_index(drop=True)
    sort_key = df.astype(str)
    order = sort_key.sort_values(by=list(df.columns)).index
    return df.loc[order].reset_index(drop=True)


def _decode_bdata(value: object) -> list:
    """Decode a Plotly-JSON-encoded trace array (plain list, or {dtype, bdata})."""
    if isinstance(value, dict) and "bdata" in value and "dtype" in value:
        raw = base64.b64decode(value["bdata"])
        arr = np.frombuffer(raw, dtype=value["dtype"])
        return arr.tolist()
    if isinstance(value, list):
        return value
    return []


def _bundle_fingerprint_rows(chart_bundles_dir: Path) -> list[dict]:
    """T3: decode every trace's x/y across every chart bundle in a directory."""
    rows: list[dict] = []
    for bundle_path in sorted(chart_bundles_dir.glob("*.json")):
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        charts = payload.get("charts", {})
        for chart_key, figure in charts.items():
            for trace_index, trace in enumerate(figure.get("data", [])):
                trace_name = str(trace.get("name") or "")
                x_values = _decode_bdata(trace.get("x"))
                y_values = _decode_bdata(trace.get("y"))
                if not x_values and not y_values:
                    continue
                for point_index, (x_val, y_val) in enumerate(
                    zip(x_values or [None] * len(y_values), y_values or [None] * len(x_values))
                ):
                    rows.append(
                        {
                            "bundle_file": bundle_path.name,
                            "chart_key": chart_key,
                            "trace_index": trace_index,
                            "trace_name": trace_name,
                            "point_index": point_index,
                            "x": x_val,
                            "y": y_val,
                        }
                    )
    return rows


def _page_inventory_rows(manifest_df: pd.DataFrame) -> pd.DataFrame:
    """T7: the set of page_keys rendered and the chart_key order (nav order proxy) per page."""
    if manifest_df.empty:
        return pd.DataFrame(columns=["page_key", "chart_key", "chart_order"])
    cols = ["page_key", "chart_key"]
    inventory = manifest_df[cols].copy()
    inventory["chart_order"] = inventory.groupby("page_key").cumcount()
    return inventory


def _patch_mapping_tree_explorer_root() -> None:
    """Work around a known, out-of-scope bug: render_full_mapping_tree_explorer.py
    hardcodes MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings" and ignores
    LEAP_MAPPINGS_ROOT, so it resolves to the worktrees directory (not the repo
    parent) and crashes when this repo is checked out as a worktree. Patching the
    already-imported module's MAPPINGS_ROOT attribute at runtime is a process-local,
    reversible workaround — it does not touch the script on disk, which the
    overnight plan marks explicitly out of scope to fix.
    """
    import os

    import scripts.render_full_mapping_tree_explorer as tree_explorer

    leap_mappings_root = os.getenv("LEAP_MAPPINGS_ROOT")
    if leap_mappings_root:
        tree_explorer.MAPPINGS_ROOT = Path(leap_mappings_root)


def capture_economy(economy: str, workflow, existing_results: dict) -> Path:
    """Capture one economy's baseline.

    `common_esto_dashboard_workflow` renders its default economies (20USA,
    02BD) as an import-time side effect (`RUN_DASHBOARD_WORKFLOW = True`), so
    when `economy` is already in `existing_results` we reuse that render
    instead of paying for a second one.
    """
    normalized = economy.replace("_", "")
    result = existing_results.get(economy) or existing_results.get(normalized)
    if result is None:
        result = workflow.run_dashboard_for_economy(economy)
    layout_root = Path(result["dashboard_index"]).parents[1]
    supporting = layout_root / "supporting_files"
    chart_bundles = layout_root / "chart_bundles"

    dest = FIXTURES_ROOT / f"baseline_{economy}"
    dest.mkdir(parents=True, exist_ok=True)

    manifest_df = pd.DataFrame()
    for filename in SUPPORTING_FILES:
        src = supporting / filename
        if not src.exists():
            print(f"[{economy}] MISSING (captured gap, continuing): {filename}")
            continue
        df = pd.read_csv(src)
        if filename == "chart_manifest.csv":
            manifest_df = df.copy()
        _normalize(df).to_csv(dest / filename, index=False)

    inventory_df = _page_inventory_rows(manifest_df)
    _normalize(inventory_df).to_csv(dest / "page_inventory.csv", index=False)

    fingerprint_rows = _bundle_fingerprint_rows(chart_bundles)
    fingerprint_df = pd.DataFrame(
        fingerprint_rows,
        columns=["bundle_file", "chart_key", "trace_index", "trace_name", "point_index", "x", "y"],
    )
    _normalize(fingerprint_df).to_csv(dest / "bundle_fingerprint_t3.csv", index=False)

    print(f"[{economy}] baseline captured -> {dest}")
    return dest


def main(argv: list[str]) -> int:
    economies = argv or ["20USA", "02BD"]
    _patch_mapping_tree_explorer_root()
    import common_esto_dashboard_workflow as workflow

    existing_results = dict(workflow.WORKFLOW_RESULT.get("economy_results", {}))
    for economy in economies:
        capture_economy(economy, workflow, existing_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
