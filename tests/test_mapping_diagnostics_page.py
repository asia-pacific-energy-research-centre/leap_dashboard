from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_mapping_diagnostics import write_mapping_diagnostics_page


def test_mapping_diagnostics_page_renders_tree_and_coverage_tables(tmp_path: Path) -> None:
    mappings_root = tmp_path / "leap_mappings"
    tree_root = mappings_root / "results" / "tree_structure"
    common_root = mappings_root / "results" / "common_esto"
    maintenance_root = mappings_root / "results" / "maintenance"
    coverage_root = mappings_root / "results" / "source_coverage"
    for path in [tree_root, common_root, maintenance_root, coverage_root]:
        path.mkdir(parents=True, exist_ok=True)

    tree = pd.DataFrame([
        {"axis": "sector", "code": "09_total", "label": "09 Total", "level": 1, "parent_code": ""},
        {"axis": "sector", "code": "09_child", "label": "09 Child", "level": 2, "parent_code": "09_total"},
    ])
    tree.to_csv(tree_root / "ninth_tree.csv", index=False)
    tree.assign(code=["Oil Refining", "Oil Refining/Child"]).to_csv(tree_root / "leap_tree.csv", index=False)
    pd.DataFrame([
        {"status": "failed", "source_system": "NINTH", "validation_axis": "flow", "parent_code": "09_total"},
    ]).to_csv(tree_root / "common_esto_validation.csv", index=False)
    pd.DataFrame([
        {"status": "failed", "source_system": "NINTH", "validation_axis": "flow", "reason": "difference_exceeds_tolerance", "parent_code": "09_total", "parent_value": 10.0, "frontier_sum": 7.0, "difference": 3.0, "abs_error": 3.0},
        {"status": "failed", "source_system": "LEAP", "validation_axis": "flow", "reason": "frontier_rows_absent", "parent_code": "Oil Refining", "parent_value": 4.0, "frontier_sum": 0.0, "difference": 4.0, "abs_error": 4.0},
    ]).to_csv(tree_root / "source_parent_anchor_validation.csv", index=False)
    pd.DataFrame([{ "source_system": "LEAP", "common_row_id": "row", "missing_component_pairs": "flow :: product", "relevance_evidence": "nonzero", "mapping_action": "review", "mapping_sheet_to_review": "leap_combined_esto" }]).to_csv(common_root / "qa_common_esto_unresolved_partial_coverage.csv", index=False)
    pd.DataFrame([{ "leap_flow": "Industry", "leap_product": "Gas", "qa_status": "review" }]).to_csv(common_root / "qa_nonzero_unmapped_leap_branches.csv", index=False)
    pd.DataFrame([{ "leap_sector_name_full_path": "Industry", "raw_leap_fuel_name": "Gas", "presence_status": "ESTO only" }]).to_csv(maintenance_root / "leap_source_presence_conflicts.csv", index=False)
    pd.DataFrame([{ "coverage_status": "UNMAPPED", "mapping_status": "UNMAPPED" }]).to_csv(coverage_root / "all_demand_aggregated_coverage_gaps.csv", index=False)

    layout = {"dashboards": tmp_path / "dashboard", "supporting": tmp_path / "supporting"}
    for path in layout.values():
        path.mkdir()
    result = write_mapping_diagnostics_page(layout, mappings_root, dashboard_updated_label="test")
    html = Path(result["page"]).read_text(encoding="utf-8")

    assert "How the anchor validator connects the trees" in html
    assert "09 Total" in html
    assert "Mismatch total 3.00" in html
    assert "Largest summed anchor mismatches" in html
    assert "Direct mapping coverage review" in html
    assert Path(result["summary"]).exists()
