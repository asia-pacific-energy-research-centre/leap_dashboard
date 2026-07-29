from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_mapping_diagnostics import (
    _anchor_value_summary,
    _context_value_formatter,
    _mapping_cardinality_diagnostics,
    _mapped_target_structure_html,
    _paired_anchor_aggregate_summary,
    _reviewed_anchor_exceptions,
    _rollup_boundary_details_html,
    _rollup_graph_data,
    _transformation_rollup_diagram_html,
    load_esto_exact_values_for_economy,
    prefer_compressed_csv_path,
    write_mapping_diagnostics_page,
)


def test_anchor_review_split_keeps_confirmed_failures_and_filters_economy() -> None:
    anchor = pd.DataFrame([
        {
            "status": "failed", "source_system": "NINTH", "validation_axis": "flow",
            "economy": "20USA", "scenario": "reference", "year": 2030,
            "other_axis_value": "Gas", "parent_code": "09_total",
            "parent_value": 10.0, "frontier_sum": 7.0, "difference": 3.0,
            "abs_error": 3.0, "reason": "difference_exceeds_tolerance",
            "known_data_quality_exception": True,
            "exception_review_status": "confirmed", "exception_id": "SRC-001",
            "source_non_additivity_observed": True,
        },
        {
            "status": "failed", "source_system": "LEAP", "validation_axis": "flow",
            "economy": "20_USA", "scenario": "reference", "year": 2030,
            "other_axis_value": "Coal", "parent_code": "Oil Refining",
            "parent_value": 4.0, "frontier_sum": 0.0, "difference": 4.0,
            "abs_error": 4.0, "reason": "frontier_rows_absent",
            "known_data_quality_exception": False,
            "exception_review_status": "",
            "source_non_additivity_observed": False,
        },
        {
            "status": "failed", "source_system": "NINTH", "validation_axis": "flow",
            "economy": "01AUS", "scenario": "reference", "year": 2030,
            "other_axis_value": "Gas", "parent_code": "other_economy_parent",
            "parent_value": 99.0, "frontier_sum": 0.0, "difference": 99.0,
            "abs_error": 99.0, "reason": "difference_exceeds_tolerance",
            "known_data_quality_exception": True,
            "exception_review_status": "confirmed", "exception_id": "SRC-002",
            "source_non_additivity_observed": True,
        },
    ])

    summary = _anchor_value_summary(anchor, "20_USA")
    reviewed = _reviewed_anchor_exceptions(anchor, "20USA")

    assert int(summary["failed_checks"].sum()) == 2
    assert int(summary["confirmed_issue_failed"].sum()) == 1
    assert int(summary["unconfirmed_failed"].sum()) == 1
    assert int(summary["source_non_additivity_observed"].sum()) == 1
    assert reviewed["exception_id"].tolist() == ["SRC-001"]
    assert reviewed["status"].tolist() == ["failed"]


def test_legacy_anchor_flag_is_not_relabelled_as_an_explicit_confirmation() -> None:
    legacy = pd.DataFrame([
        {
            "status": "skipped",
            "known_data_quality_exception": True,
            "economy": "20USA",
        },
    ])

    assert _reviewed_anchor_exceptions(legacy, "20USA").empty


def test_context_value_formatter_uses_at_most_two_decimal_places() -> None:
    scale_label, format_value = _context_value_formatter([12_345.6789, 1_234.5678])

    assert scale_label.startswith("Values in thousands")
    assert format_value(12_345.6789) == "12.35"
    assert format_value(1_234.5678) == "1.23"
    assert format_value(0) == "0"


def test_exact_value_loader_prefers_gzip_and_keeps_plain_csv_fallback(tmp_path: Path) -> None:
    plain_path = tmp_path / "esto_results_exact_rows.csv"
    compressed_path = tmp_path / "esto_results_exact_rows.csv.gz"
    frame = pd.DataFrame([
        {
            "economy": "20USA",
            "esto_flow": "09 Total transformation sector",
            "year": 2023,
            "value": 12.5,
            "scenario": "historical",
        }
    ])
    frame.to_csv(compressed_path, index=False)

    assert prefer_compressed_csv_path(plain_path) == compressed_path
    loaded = load_esto_exact_values_for_economy(plain_path, "20_USA")
    assert loaded["value"].tolist() == [12.5]

    compressed_path.unlink()
    frame.to_csv(plain_path, index=False)
    assert prefer_compressed_csv_path(compressed_path) == plain_path


def test_mapping_cardinality_diagnostics_detects_only_real_overlap_and_many_to_many() -> None:
    source_to_common = pd.DataFrame([
        {"source_system": "NINTH", "original_source_flow": "source_a", "original_source_product": "Gas", "common_row_id": "parent", "common_flow_label": "14.03 Manufacturing", "common_product_label": "08.01 Natural gas"},
        {"source_system": "NINTH", "original_source_flow": "source_a", "original_source_product": "Gas", "common_row_id": "child", "common_flow_label": "14.03.01 Iron and steel", "common_product_label": "08.01 Natural gas"},
        {"source_system": "NINTH", "original_source_flow": "source_b", "original_source_product": "Gas", "common_row_id": "parent", "common_flow_label": "14.03 Manufacturing", "common_product_label": "08.01 Natural gas"},
        {"source_system": "NINTH", "original_source_flow": "source_b", "original_source_product": "Gas", "common_row_id": "child", "common_flow_label": "14.03.01 Iron and steel", "common_product_label": "08.01 Natural gas"},
    ])
    target_tree = pd.DataFrame([
        {"code": "14.03 Manufacturing", "parent_code": "14 Industry sector"},
        {"code": "14.03.01 Iron and steel", "parent_code": "14.03 Manufacturing"},
    ])

    source_tree = pd.DataFrame([
        {"dataset": "ninth", "code": "source_a", "parent_code": ""},
        {"dataset": "ninth", "code": "source_b", "parent_code": "source_a"},
    ])

    overlaps, source_overlaps = _mapping_cardinality_diagnostics(
        source_to_common, target_tree, source_tree,
    )

    assert len(overlaps) == 2
    assert set(overlaps["ancestor_target"]) == {"14.03 Manufacturing / 08.01 Natural gas"}
    assert len(source_overlaps) == 2
    assert set(source_overlaps["source_parent"]) == {"source_a"}


def test_paired_tree_summary_only_traverses_flow_axis() -> None:
    context_values = pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030, "other_axis_value": "08_01_natural_gas", "parent_code": "09_total", "child_code": "09_child", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
        {"source_system": "NINTH", "validation_axis": "product", "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030, "other_axis_value": "15_pipeline", "parent_code": "08_gas", "child_code": "08_01_natural_gas", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
    ])

    summary = _paired_anchor_aggregate_summary(context_values, "NINTH", "20USA")

    assert summary["parent_code"].tolist() == ["09_total"]


def test_transformation_rollup_diagram_keeps_boundary_modes_distinct() -> None:
    tree = pd.DataFrame([
        {"axis": "flow", "code": "09 Total transformation sector", "parent_code": ""},
        {"axis": "flow", "code": "09.06 Gas processing plants", "parent_code": "09 Total transformation sector"},
        {"axis": "flow", "code": "09.08 Coal transformation", "parent_code": "09 Total transformation sector"},
        {"axis": "flow", "code": "09.08.01 Coke ovens", "parent_code": "09.08 Coal transformation (including own use)"},
    ])
    rollups = pd.DataFrame([
        {"source_system": "ESTO", "rollup_mode": "NON_EXPANDING", "non_expanding_rollup_id": "gas", "rolled_flow_label": "09.06 Gas processing plants (including own use)", "input_flow": "09.06 Gas processing plants"},
        {"source_system": "ESTO", "rollup_mode": "NON_EXPANDING", "non_expanding_rollup_id": "gas", "rolled_flow_label": "09.06 Gas processing plants (including own use)", "input_flow": "10.01.02 Gas works plants"},
        {"source_system": "ESTO", "rollup_mode": "DETACHED", "non_expanding_rollup_id": "coal", "rolled_flow_label": "09.08 Coal transformation (including own use)", "input_flow": "09.08 Coal transformation"},
    ])

    html = _transformation_rollup_diagram_html(tree, rollups)

    assert "Solid arrows are ordinary tree edges" in html
    assert "NON_EXPANDING" in html
    assert "DETACHED" in html
    assert "This boundary can support ordinary ancestor/frontier resolution." in html
    assert "This boundary is not folded back into an ordinary ancestor total." in html
    assert "10.01.02 Gas works plants" in html


def test_rollup_graph_data_includes_every_flow_root_and_mode() -> None:
    tree = pd.DataFrame([
        {"axis": "flow", "code": "09 Total transformation sector", "label": "09 Total transformation sector", "level": 1, "parent_code": ""},
        {"axis": "flow", "code": "09.06 Gas processing plants", "label": "09.06 Gas processing plants", "level": 2, "parent_code": "09 Total transformation sector"},
        {"axis": "flow", "code": "14 Industry sector", "label": "14 Industry sector", "level": 1, "parent_code": ""},
        {"axis": "flow", "code": "14.03 Manufacturing", "label": "14.03 Manufacturing", "level": 2, "parent_code": "14 Industry sector"},
        {"axis": "flow", "code": "10.01.06 Coal mines", "label": "10.01.06 Coal mines", "level": 3, "parent_code": ""},
        {"axis": "flow", "code": "09.06 inclusive", "label": "09.06 inclusive", "level": 0, "parent_code": ""},
    ])
    rollups = pd.DataFrame([
        {"source_system": "ESTO", "rollup_mode": "NON_EXPANDING", "rollup_id": "gas", "rolled_flow_label": "09.06 inclusive", "input_flow": "09.06 Gas processing plants"},
        {"source_system": "ESTO", "rollup_mode": "EXPANDING", "rollup_id": "industry", "rolled_flow_label": "14 Industry inclusive", "input_flow": "14 Industry sector"},
        {"source_system": "ESTO", "rollup_mode": "DETACHED", "rollup_id": "coal", "rolled_flow_label": "09.08 inclusive", "input_flow": "09.08 Coal transformation"},
    ])

    validation = pd.DataFrame([
        {
            "validation_axis": "flow", "source_system": "ESTO", "economy": "20USA",
            "parent_code": "14 Industry sector", "status": "failed",
            "reason": "difference_exceeds_tolerance",
        },
    ])
    graph = _rollup_graph_data(tree, rollups, validation=validation, economy="20_USA")

    assert {sector["root"] for sector in graph["sectors"]} == {"09 Total transformation sector", "14 Industry sector"}
    assert {node["code"] for node in graph["nodes"]} == {
        "09 Total transformation sector", "09.06 Gas processing plants",
        "14 Industry sector", "14.03 Manufacturing", "10.01.06 Coal mines",
        "09.06 inclusive",
    }
    assert {boundary["mode"] for boundary in graph["all_boundaries"]} == {"NON_EXPANDING", "EXPANDING", "DETACHED"}
    industry = next(node for node in graph["nodes"] if node["code"] == "14 Industry sector")
    assert industry["validation"]["ESTO"]["failed"] == 1
    assert industry["validation"]["ESTO"]["reasons"] == ["difference_exceeds_tolerance"]
    assert all("id" in boundary for boundary in graph["all_boundaries"])
    node_by_code = {node["code"]: node for node in graph["nodes"]}
    assert node_by_code["14.03 Manufacturing"]["flow_code"] == "14.03"
    assert node_by_code["14.03 Manufacturing"]["flow_label"] == "Manufacturing"
    assert node_by_code["09.06 inclusive"]["is_ordinary_hierarchy"] is False
    assert node_by_code["10.01.06 Coal mines"]["structural_flags"] == ["ORPHANED_HIERARCHY_ROW"]


def test_rollup_boundary_details_show_parent_children_components_and_mode_meaning() -> None:
    rollups = pd.DataFrame([
        {
            "source_system": "ESTO", "rollup_mode": "DETACHED", "rollup_id": "coal",
            "rolled_flow_label": "09.08 Coal transformation (including own use)",
            "input_flow": "10.01.05 Coke ovens", "parent_flow_label": "09 Total transformation sector",
            "child_flow_labels": "09.08.01 Coke ovens; 09.08.02 Blast furnaces",
            "note": "Separate comparison boundary.",
        },
    ])

    tree = pd.DataFrame([
        {"axis": "flow", "code": "09 Total transformation sector", "parent_code": ""},
        {"axis": "flow", "code": "09.07 Oil refineries", "parent_code": "09 Total transformation sector"},
        {"axis": "flow", "code": "09.08 Coal transformation", "parent_code": "09 Total transformation sector"},
        {"axis": "flow", "code": "09.09 Petrochemical industry", "parent_code": "09 Total transformation sector"},
    ])
    html = _rollup_boundary_details_html(rollups, tree)

    assert "Ordinary hierarchy" in html
    assert "Composition components" in html
    assert "09 Total transformation sector" in html
    assert "09.08.01 Coke ovens" in html
    assert "10.01.05 Coke ovens" in html
    assert "09.07 Oil refineries" in html
    assert "09.09 Petrochemical industry" in html
    assert "deliberately not folded into an ordinary ancestor total" in html
    assert html.count('data-rollup-flow="09 Total transformation sector"') == 1
    assert html.count('data-rollup-flow="09.08.01 Coke ovens"') == 1
    assert html.count('data-rollup-flow="10.01.05 Coke ovens"') == 1


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
        {"axis": "flow", "code": "09 Total", "label": "09 Total", "level": 1, "parent_code": ""},
        {"axis": "flow", "code": "09.00 Total", "label": "09.00 Total", "level": 2, "parent_code": "09 Total"},
        {"axis": "flow", "code": "09 Extra", "label": "09 Extra", "level": 3, "parent_code": ""},
    ]).to_csv(tree_root / "common_esto_tree.csv", index=False)
    pd.DataFrame([
        {"status": "failed", "source_system": "NINTH", "validation_axis": "flow", "parent_code": "09_total"},
    ]).to_csv(tree_root / "common_esto_validation.csv", index=False)
    pd.DataFrame([
        {"status": "failed", "source_system": "NINTH", "validation_axis": "flow", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "reason": "difference_exceeds_tolerance", "parent_code": "09_total", "parent_value": 10.0, "frontier_sum": 7.0, "difference": 3.0, "abs_error": 3.0, "known_data_quality_exception": True, "exception_review_status": "confirmed", "exception_id": "SRC-001", "exception_issue_class": "confirmed_source_non_additivity", "source_non_additivity_observed": True, "data_quality_exception_notes": "Reviewed source total."},
        {"status": "failed", "source_system": "LEAP", "validation_axis": "flow", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "reason": "frontier_rows_absent", "parent_code": "Oil Refining", "parent_value": 4.0, "frontier_sum": 0.0, "difference": 4.0, "abs_error": 4.0, "known_data_quality_exception": False, "exception_review_status": "", "exception_id": "", "exception_issue_class": "", "source_non_additivity_observed": False, "data_quality_exception_notes": ""},
        {"status": "failed", "source_system": "NINTH", "validation_axis": "flow", "economy": "20USA", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "reason": "difference_exceeds_tolerance", "parent_code": "other_economy_parent", "parent_value": 999.0, "frontier_sum": 0.0, "difference": 999.0, "abs_error": 999.0, "known_data_quality_exception": True, "exception_review_status": "confirmed", "exception_id": "SRC-OTHER", "exception_issue_class": "confirmed_source_non_additivity", "source_non_additivity_observed": True, "data_quality_exception_notes": "Must not leak."},
    ]).to_csv(tree_root / "source_parent_anchor_validation.csv", index=False)
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "parent_code": "09_total", "child_code": "09_child", "raw_child_total": 7.0},
    ]).to_csv(tree_root / "source_parent_anchor_child_values.csv", index=False)
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "child_code": "09_child", "parent_value": 10.0, "frontier_sum": 7.0, "raw_child_value": 7.0},
    ]).to_csv(tree_root / "source_parent_anchor_child_context_values.csv", index=False)
    pd.DataFrame([
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap_ninth", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_node_role": "parent", "raw_child_code": "09_total", "component_esto_flow": "09 Total", "component_esto_product": "08.01 Gas", "common_row_id": "parent", "mapped_value": 10.0, "mapping_status": "mapped"},
        {"source_system": "NINTH", "validation_axis": "flow", "comparison_scope": "esto_leap", "economy": "01AUS", "scenario": "reference", "year": 2023, "other_axis_value": "Gas", "parent_code": "09_total", "raw_node_role": "parent", "raw_child_code": "09_total", "component_esto_flow": "09 Total", "component_esto_product": "08.01 Gas", "common_row_id": "parent", "mapped_value": 10.0, "mapping_status": "mapped"},
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
        layout, mappings_root, dashboard_updated_label="test", economy="01AUS",
        comparison_data=pd.DataFrame([
            {"source_system": "ESTO", "scenario": "historical", "year": 2023, "common_flow_label": "09 Total", "value": 10.0},
            {"source_system": "ESTO", "scenario": "historical", "year": 2023, "common_flow_label": "09.00 Total", "value": 10.0},
            {"source_system": "ESTO_EXTENDED", "scenario": "historical", "year": 2023, "common_flow_label": "09 Total", "value": 12.0},
        ]),
        esto_exact_values=pd.DataFrame([
            {"source_system": "ESTO_RAW", "scenario": "historical", "year": 2023, "common_flow_label": "09 raw component", "value": 4.0},
            {"source_system": "ESTO_EXTENDED_RAW", "scenario": "historical", "year": 2023, "common_flow_label": "09 raw component", "value": 5.0},
        ]),
    )
    html = Path(result["page"]).read_text(encoding="utf-8")

    assert "How the anchor validator connects the hierarchies" in html
    assert "How to read a hierarchy case" in html
    assert "One-to-many fan-out" in html
    assert "De-duplicated frontier" in html
    assert "Raw source contradiction" in html
    assert "09_total" in html
    assert "absolute mismatch total" in html
    assert "Hierarchy validation: failures and reviewed exceptions" in html
    assert "Final output hierarchy" in html
    assert "Source / mapping anchor" in html
    assert "A failure means the difference exceeded tolerance" in html
    assert "09 Child" in html
    assert ">7<" in html
    assert "NINTH flow tree: original vs mapped representation" in html
    assert "LEAP flow tree: original vs mapped representation" in html
    assert "Original raw source tree" in html
    assert "Original source parent" in html
    assert "Validator mapped total (detail incomplete)" in html
    assert "The mapped rows shown above add to" in html
    assert "Mapped Common ESTO representation" in html
    assert "Mapped Common ESTO hierarchy" in html
    assert "09 Total / 08.01 Gas" in html
    assert ">10<" in html
    assert ">20<" not in html
    assert "Manual LEAP roll-up" in html
    assert "Raw roll-up: this source parent" not in html
    assert "Mapped target hierarchy" in html
    assert "Direct mapping fan-out" not in html
    assert '<li class="tree-category"><span>Original source children</span></li>' in html
    assert "Show zero-value children and mapped components" in html
    assert "optional-zero" in html
    assert "onchange=\"document.body.classList.toggle('show-zero-children', this.checked)\"" in html
    assert "Missing source mapping" not in html
    assert "Confirmed source issues attached to anchor evidence" in html
    assert "Confirmed source issues among failed anchor rows" in html
    assert "Unconfirmed failed anchor rows" in html
    assert "SRC-001" in html
    assert "other_economy_parent" not in html
    assert "SRC-OTHER" not in html
    assert "skipped from actionable failures" not in html
    assert "Exception candidates awaiting review" in html
    assert "direct_children_incomplete_but_leaves_reconcile" in html
    assert "Direct mapping coverage review" in html
    assert "Dataset<select id=\"rollup-source\"" in html
    assert "ROLLUP_VALUES=" in html
    assert "ESTO_RAW" in html
    assert "ESTO_EXTENDED_RAW" in html
    assert 'id="rollup-basis"' in html
    assert "Original ESTO only" in html
    assert "ESTO + ESTO Extended" in html
    assert "Compare ESTO vs Extended" in html
    assert 'id="rollup-sector"' in html
    assert 'id="rollup-mode"' not in html
    assert 'id="show-special-rollups"' in html
    assert "Show NON_EXPANDING and DETACHED rollups" in html
    assert "boundary.mode === 'EXPANDING' || showSpecialRollups.checked" in html
    assert "const specialBoundaries = filteredBoundaries.filter" in html
    assert 'class="edge rollup${detachedClass}"' in html
    assert "belongsToMajor(boundary.label)" in html
    assert 'id="rollup-status"' in html
    assert 'id="rollup-search"' in html
    assert 'id="rollup-summary-table"' not in html
    assert "Rows in the current graph" not in html
    assert "EXPANDING rollups appear in the hierarchy view by default" in html
    assert "Rollup display child" in html
    assert "REGISTERED ROLLUP COMPOSITION" not in html
    assert "Normal hierarchy child" in html
    assert "Registered rollup composition target" in html
    assert "Registered rollup input" in html
    assert "ORPHANED_HIERARCHY_ROW" in html
    assert "intentional DETACHED" in html
    assert "value-pass" in html
    assert '<details class="panel collapsed-panel"><summary><h2>Direct mapping coverage review</h2>' in html
    assert '<details class="panel collapsed-panel"><summary><h2>Hierarchy validation: failures and reviewed exceptions</h2>' in html
    assert Path(result["summary"]).exists()


def test_mapped_target_structure_uses_direct_fanout_without_target_edge() -> None:
    components = pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030,
            "common_row_id": "coal", "component_esto_flow": "10.01.06 Coal mines",
            "component_esto_product": "08.01 Natural gas", "mapped_value": -11.4, "mapping_status": "mapped",
        },
        {
            "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "reference", "year": 2030,
            "common_row_id": "oil", "component_esto_flow": "10.01.12 Oil and gas extraction",
            "component_esto_product": "08.01 Natural gas", "mapped_value": -24488.6, "mapping_status": "mapped",
        },
    ])
    target_tree = pd.DataFrame([
        {"code": "10.01.06 Coal mines", "parent_code": "10.01 Own Use"},
        {"code": "10.01.12 Oil and gas extraction", "parent_code": "10.01 Own Use"},
    ])

    html, note, matches = _mapped_target_structure_html(
        components, target_tree, "Other loss and own use", str, -24500.0,
    )

    assert "Direct mapping fan-out" in html
    assert "Other loss and own use maps directly to these target rows." in note
    assert matches
