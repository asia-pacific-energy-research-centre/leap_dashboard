from __future__ import annotations

from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_convergence import (
    select_latest_convergence_run,
    write_capacity_unmet_convergence_page,
)
from codebase.common_esto_dashboard_output_layout import build_output_layout


def _write_convergence_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "run_id": "",
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
                "mode": "capacity_unmet_iterative_balanced",
                "iteration_run_mode": "results_update",
                "pass_count": 1,
                "gap_at_first_pass": 20.0,
                "gap_at_current_pass": 20.0,
                "gap_closure_pct": 0.0,
                "gap_delta_last_pass": 0.0,
                "allocated_cumulative": 2.0,
                "clipped_total_current": 0.0,
                "unresolved_count_current": 2,
                "trend": "unknown",
                "unresolved_fuels_current": "01 Coal; 02 Gas",
            },
            {
                "run_id": "",
                "timestamp_utc": "2026-01-01T01:00:00+00:00",
                "mode": "capacity_unmet_iterative_balanced",
                "iteration_run_mode": "results_update",
                "pass_count": 2,
                "gap_at_first_pass": 20.0,
                "gap_at_current_pass": 8.0,
                "gap_closure_pct": 60.0,
                "gap_delta_last_pass": -12.0,
                "allocated_cumulative": 12.0,
                "clipped_total_current": 0.0,
                "unresolved_count_current": 1,
                "trend": "converging",
                "unresolved_fuels_current": "02 Gas",
            },
            {
                "run_id": "",
                "timestamp_utc": "2026-01-02T00:00:00+00:00",
                "mode": "capacity_unmet_iterative_balanced",
                "iteration_run_mode": "results_update",
                "pass_count": 1,
                "gap_at_first_pass": 5.0,
                "gap_at_current_pass": 5.0,
                "gap_closure_pct": 0.0,
                "gap_delta_last_pass": 0.0,
                "allocated_cumulative": 1.0,
                "clipped_total_current": 0.0,
                "unresolved_count_current": 0,
                "trend": "unknown",
                "unresolved_fuels_current": "",
            },
        ]
    ).to_csv(path, index=False)


def test_select_latest_convergence_run_infers_legacy_segment(tmp_path: Path) -> None:
    csv_path = tmp_path / "capacity_unmet_convergence.csv"
    _write_convergence_csv(csv_path)
    df = pd.read_csv(csv_path, dtype=object).fillna("")
    if "run_id" not in df.columns:
        df.insert(0, "run_id", "")
    for column in ["pass_count", "gap_at_current_pass"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    latest, run_label = select_latest_convergence_run(df)

    assert run_label == "legacy_segment_2"
    assert latest["pass_count"].tolist() == [1]
    assert latest["gap_at_current_pass"].tolist() == [5.0]


def test_write_capacity_unmet_convergence_page_outputs_page_and_index_link(tmp_path: Path) -> None:
    csv_path = tmp_path / "capacity_unmet_convergence.csv"
    _write_convergence_csv(csv_path)
    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    index_path = layout["dashboards"] / "index.html"
    index_path.write_text("<html><body><ul></ul></body></html>", encoding="utf-8")

    result = write_capacity_unmet_convergence_page(csv_path, layout, enabled=True)

    assert result is not None
    page_path = layout["dashboards"] / "capacity_unmet_convergence.html"
    assert page_path.exists()
    assert "Capacity-unmet convergence" in page_path.read_text(encoding="utf-8")
    assert (layout["supporting"] / "capacity_unmet_convergence_history.csv").exists()
    assert (layout["supporting"] / "capacity_unmet_convergence_latest_run.csv").exists()
    assert "capacity_unmet_convergence.html" in index_path.read_text(encoding="utf-8")

    write_capacity_unmet_convergence_page(csv_path, layout, enabled=True)
    index_html = index_path.read_text(encoding="utf-8")
    assert index_html.count("capacity_unmet_convergence.html") == 1
