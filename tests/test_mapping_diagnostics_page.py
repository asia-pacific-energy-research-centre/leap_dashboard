from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_mapping_diagnostics import (
    _paired_anchor_aggregate_summary,
    write_mapping_diagnostics_page,
)


def test_paired_tree_summary_only_traverses_flow_axis() -> None:
    context_values = pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030, "other_axis_value": "08_01_natural_gas", "parent_code": "09_total", "child_code": "09_child", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
        {"source_system": "NINTH", "validation_axis": "product", "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030, "other_axis_value": "15_pipeline", "parent_code": "08_gas", "child_code": "08_01_natural_gas", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
    ])

    summary = _paired_anchor_aggregate_summary(context_values, "NINTH", "20USA")

    assert summary["parent_code"].tolist() == ["09_total"]


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
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "parent_code": "09_total", "child_code": "09_child", "raw_child_total": 7.0},
    ]).to_csv(tree_root / "source_parent_anchor_child_values.csv", index=False)
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "child_code": "09_child", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
    ]).to_csv(tree_root / "source_parent_anchor_child_context_values.csv", index=False)
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_node_role": "parent", "raw_child_code": "09_total", "component_esto_flow": "09 Total", "component_esto_product": "08.01 Gas", "common_row_id": "parent", "mapped_value": 10.0, "mapping_status": "mapped"},
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_node_role": "parent", "raw_child_code": "09_total", "component_esto_flow": "09 Extra", "component_esto_product": "08.01 Gas", "common_row_id": "extra", "mapped_value": 1.0, "mapping_status": "mapped"},
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_node_role": "child", "raw_child_code": "09_child", "component_esto_flow": "09.00 Total", "component_esto_product": "08.01 Gas", "common_row_id": "common", "mapped_value": 7.0, "mapping_status": "mapped"},
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_child_code": "missing_child", "component_esto_flow": "", "component_esto_product": "", "common_row_id": "", "mapped_value": 0.0, "mapping_status": "missing_source_mapping:missing_child"},
    ]).to_csv(tree_root / "source_parent_anchor_mapped_component_context_values.csv", index=False)
    pd.DataFrame([{
        "enabled": False, "source_system": "NINTH", "validation_axis": "flow",
        "parent_code": "09_total", "other_axis_value": "Gas", "economy": "01AUS",
        "scenario": "reference", "year": 2023, "parent_value": 10.0,
        "direct_children_sum": 7.0, "leaf_descendants_sum": 10.0,
        "candidate_classification": "direct_children_incomplete_but_leaves_reconcile",
        "notes": "Review before enabling.",
    }]).to_csv(tree_root / "source_parent_anchor_leaf_reconciliation_candidates.csv", index=False)
    pd.DataFrame([{ "source_system": "LEAP", "common_row_id": "row", "missing_component_pairs": "flow :: product", "relevance_evidence": "nonzero", "mapping_action": "review", "mapping_sheet_to_review": "leap_combined_esto" }]).to_csv(common_root / "qa_common_esto_unresolved_partial_coverage.csv", index=False)
    pd.DataFrame([{ "leap_flow": "Industry", "leap_product": "Gas", "qa_status": "review" }]).to_csv(common_root / "qa_nonzero_unmapped_leap_branches.csv", index=False)
    pd.DataFrame([{ "leap_sector_name_full_path": "Industry", "raw_leap_fuel_name": "Gas", "presence_status": "ESTO only" }]).to_csv(maintenance_root / "leap_source_presence_conflicts.csv", index=False)
    pd.DataFrame([{ "coverage_status": "UNMAPPED", "mapping_status": "UNMAPPED" }]).to_csv(coverage_root / "all_demand_aggregated_coverage_gaps.csv", index=False)

    layout = {"dashboards": tmp_path / "dashboard", "supporting": tmp_path / "supporting"}
    for path in layout.values():
        path.mkdir()
    result = write_mapping_diagnostics_page(
        layout, mappings_root, dashboard_updated_label="test", economy="01AUS"
    )
    html = Path(result["page"]).read_text(encoding="utf-8")

    assert "How the anchor validator connects the hierarchies" in html
    assert "How to read a hierarchy case" in html
    assert "One-to-many fan-out" in html
    assert "De-duplicated frontier" in html
    assert "Raw source contradiction" in html
    assert "09_total" in html
    assert "absolute mismatch total" in html
    assert "Largest summed anchor mismatches" in html
    assert "09 Child" in html
    assert ">7.00<" in html
    assert "NINTH flow tree: original vs mapped representation" in html
    assert "LEAP flow tree: original vs mapped representation" in html
    assert "Original raw tree" in html
    assert "Mapped Common ESTO frontier (de-duplicated)" in html
    assert "Mapped components reached from source branch" in html
    assert "Resolved from source parent" in html
    assert "09 Total / 08.01 Gas" in html
    assert "Manual LEAP roll-up" in html
    assert "Raw roll-up: this source parent" not in html
    assert "One-to-many mapping: this raw parent reaches 2 ESTO components." in html
    assert "09 Child → 09.00 Total / 08.01 Gas" in html
    assert '<li class="tree-category"><span>Children</span></li>' in html
    assert "Show zero-value children and mapped components" in html
    assert "optional-zero" in html
    assert "onchange=\"document.body.classList.toggle('show-zero-children', this.checked)\"" in html
    assert "Missing source mapping" not in html
    assert "Reviewed source-hierarchy exceptions" in html
    assert "Leaf-reconciliation candidates awaiting review" in html
    assert "direct_children_incomplete_but_leaves_reconcile" in html
    assert "Direct mapping coverage review" in html
    assert '<details class="panel collapsed-panel"><summary><h2>Stage 3 hierarchy failures</h2>' in html
    assert '<details class="panel collapsed-panel"><summary><h2>Direct mapping coverage review</h2>' in html
    assert Path(result["summary"]).exists()
