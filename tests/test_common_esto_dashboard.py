import base64
import json
import re
import copy
import struct
from pathlib import Path

import pandas as pd
import pytest
import plotly.graph_objects as go

from codebase.common_esto_dashboard_data import (
    ALL_SCOPES,
    DEFAULT_WIDE_FILE_SCOPE,
    apply_sign_semantics,
    enrich_with_component_metadata,
    filter_common_esto_data,
    filter_ninth_pre_base_year_data,
    filter_template_for_leap_demand_coverage,
    load_active_power_interim_branches,
    load_source_category_map,
    load_common_esto_data,
    ninth_base_year_for_economy,
)
from codebase.common_esto_dashboard_emissions import select_emissions_component_rows
from codebase.common_esto_dashboard_output_layout import build_output_layout, publish_to_docs
from codebase.common_esto_dashboard_renderer import (
    _PAGE_CSS,
    _build_td_sector_chart,
    _build_td_fuel_chart,
    _comparison_projection_area_rows,
    apply_chart_chrome,
    assert_unique_line_trace_x,
    assign_pages,
    assign_bespoke_overview_rows,
    build_area_chart,
    build_product_chart,
    compute_ranking_metrics,
    compute_diff_series,
    chart_dataset_tokens_from_figure,
    code_expression_matches_prefix,
    page_keys_without_required_source,
    page_file_name,
    color_for_code,
    color_for_plotting_name,
    drop_excluded_flow_rows,
    effective_chart_suppression_threshold,
    guide_page_context,
    guide_page_mapping_table,
    guide_placeholder_status,
    line_section_tree,
    load_code_colors,
    set_code_colors_path,
    page_placeholder_note,
    pick_area_specs,
    prepare_other_transformation_page_rows,
    render_dashboard,
    finalize_chart_manifest,
    select_transformation_overview_rows,
    select_transformation_total_rows,
    _build_section_aggregate_charts,
    _build_flow_group_aggregate_charts,
    _build_supply_base_year_bar_charts,
    _build_td_fuel_chart,
    _build_supply_stack_chart,
    _add_signed_stack_traces,
    aggregate_only_tfec_note,
    _select_total_rows_by_source,
    _non_overlapping_common_row_frontier,
    _non_overlapping_flow_rows,
    _leaf_flow_rows,
    _flow_subtree_is_page_complete,
    _jump_nav_html,
    _line_sections_html,
)


def test_extended_comparison_keeps_pre_base_year_historical_rows() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "ESTO_EXTENDED", "scenario": "historical", "year": 2021, "_page_key": "industry", "value": 10.0},
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "_page_key": "industry", "value": 12.0},
        ]
    )

    selected, source = _comparison_projection_area_rows(
        rows,
        scenario_name="Target",
        primary_source="LEAP",
        comparison_source="ESTO",
        base_year=2022,
        group_col="_page_key",
        detail_col="_page_key",
        detail_minimum=1,
    )

    assert source == "LEAP"
    assert selected["year"].tolist() == [2021, 2023]


def test_demand_area_frontier_does_not_stack_flow_parents_and_children() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "common_flow_code": "15", "common_flow_label": "15 Transport sector", "value": 10.0},
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "common_flow_code": "15.02", "common_flow_label": "15.02 Road", "value": 10.0},
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "common_flow_code": "15.02.01", "common_flow_label": "15.02.01 Freight road", "value": 4.0},
        ]
    )

    selected = _non_overlapping_flow_rows(rows)

    assert selected["common_flow_code"].tolist() == ["15"]


def test_demand_frontier_does_not_cross_filter_historical_and_projection_sources() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "ESTO_EXTENDED", "scenario": "historical", "common_flow_code": "15.02", "common_flow_label": "15.02 Road", "value": 10.0},
            {"source_system": "LEAP", "scenario": "Target", "common_flow_code": "15", "common_flow_label": "15 Transport sector", "value": 10.0},
            {"source_system": "LEAP", "scenario": "Target", "common_flow_code": "15.02", "common_flow_label": "15.02 Road", "value": 10.0},
        ]
    )

    selected = _non_overlapping_flow_rows(rows)

    assert selected.loc[selected["source_system"] == "ESTO_EXTENDED", "common_flow_code"].tolist() == ["15.02"]
    assert selected.loc[selected["source_system"] == "LEAP", "common_flow_code"].tolist() == ["15"]


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE_PAGES = ["index", "total_demand", "transport"]
DEFAULT_DIAGNOSTIC_PAGES = ["transport_leap_vs_ninth", "datacentres_leap_vs_ninth"]


def test_ranking_metrics_record_normal_paired_series() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "ESTO", "scenario": "historical", "year": 2022, "value": 90.0},
            {"source_system": "LEAP", "scenario": "Target", "year": 2022, "value": 100.0},
            {"source_system": "NINTH", "scenario": "Reference", "year": 2023, "value": 105.0},
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "value": 110.0},
        ]
    )

    metrics = compute_ranking_metrics(rows, base_year=2022)

    assert metrics["model_abs_value"] == pytest.approx(210.0)
    assert metrics["comparison_abs_value"] == pytest.approx(195.0)
    assert metrics["abs_diff"] == pytest.approx(15.0)
    assert metrics["pct_diff"] == pytest.approx(15.0 / 195.0)
    assert metrics["max_annual_absolute_difference"] == pytest.approx(10.0)
    assert metrics["max_annual_percentage_difference"] == pytest.approx(10.0 / 90.0)
    assert metrics["non_zero_year_count"] == 2
    assert metrics["unexpected_sign_count"] == 0
    assert metrics["ranking_warning"] == ""


def test_ranking_metrics_flag_small_comparison_denominator() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "LEAP", "scenario": "Target", "year": 2023, "value": 10.0},
            {"source_system": "NINTH", "scenario": "Reference", "year": 2023, "value": 0.01},
        ]
    )

    metrics = compute_ranking_metrics(rows, base_year=2022)

    assert metrics["abs_diff"] == pytest.approx(9.99)
    assert metrics["pct_diff"] == 0.0
    assert metrics["max_annual_percentage_difference"] == 0.0
    assert "small_comparison_denominator" in str(metrics["ranking_warning"])
    assert "sparse_model_series" in str(metrics["ranking_warning"])


def test_ranking_metrics_flag_missing_model() -> None:
    rows = pd.DataFrame(
        [
            {"source_system": "ESTO", "scenario": "historical", "year": 2022, "value": 5.0},
        ]
    )

    metrics = compute_ranking_metrics(rows, base_year=2022)

    assert metrics["model_abs_value"] == 0.0
    assert "missing_model" in str(metrics["ranking_warning"])


def test_finalize_chart_manifest_records_order_suppression_and_missing_metrics() -> None:
    manifest = pd.DataFrame(
        [
            {"page_key": "supply", "chart_key": "a", "suppressed": False, "model_abs_value": 2.0},
            {"page_key": "supply", "chart_key": "b", "suppressed": True},
            {"page_key": "power", "chart_key": "c", "suppressed": False, "model_abs_value": 3.0},
        ]
    )

    finalized = finalize_chart_manifest(manifest)

    assert finalized["default_order"].tolist() == [0, 1, 0]
    assert "suppressed" in finalized.loc[1, "ranking_warning"]
    assert "ranking_metrics_unavailable" in finalized.loc[1, "ranking_warning"]
    assert finalized.loc[0, "model_abs_value"] == pytest.approx(2.0)


def test_page_navigation_stays_on_one_scrollable_row() -> None:
    navigation_css = _PAGE_CSS.split(".header-inline-controls {", 1)[1].split("}", 1)[0]

    assert "flex-wrap:nowrap" in navigation_css
    assert "overflow-x:auto" in navigation_css


def _load_template() -> dict:
    template_path = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
    return json.loads(template_path.read_text(encoding="utf-8"))


def _load_series_config() -> dict:
    config_path = REPO_ROOT / "config" / "common_esto_dashboard" / "series_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def test_power_interim_placeholder_uses_only_retained_audit_rows(tmp_path: Path) -> None:
    audit_path = tmp_path / "leap_source_branch_fallback_audit.csv"
    pd.DataFrame(
        [
            {
                "economy": "20_USA",
                "year": "2022",
                "status": "interim_only_retained",
                "interim_branch": "Electricity interim",
            },
            {
                "economy": "20_USA",
                "year": "2023",
                "status": "interim_zeroed",
                "interim_branch": "CHP interim",
            },
            {
                "economy": "20_USA",
                "year": "2061",
                "status": "interim_only_retained",
                "interim_branch": "Heat plant interim",
            },
            {
                "economy": "05_PRC",
                "year": "2022",
                "status": "interim_only_retained",
                "interim_branch": "CHP interim",
            },
        ]
    ).to_csv(audit_path, index=False)

    branches = load_active_power_interim_branches(
        audit_path, "20USA", min_year=2010, max_year=2060
    )

    assert branches == ["Electricity interim"]


def test_power_interim_placeholder_adds_page_note_and_guide_status() -> None:
    template = _load_template()
    template["_power_interim_placeholder_branches"] = [
        "Electricity interim",
        "CHP interim",
    ]

    note = page_placeholder_note("power", template)
    status = guide_placeholder_status("power", template)
    context = guide_page_context("power", [], template)

    assert "LEAP placeholder in use" in note
    assert "'Electricity interim', 'CHP interim'" in note
    assert "interim power placeholder branches" in status
    assert "missing detail as unavailable, not as zero" in status
    assert context["placeholder_in_use"] is True


def test_emissions_components_keep_demand_sectors_and_combine_signed_transformation_use() -> None:
    rows = pd.DataFrame([
        {
            "_page_key": "industry", "_page_label": "Industry",
            "common_flow_code": "14", "common_flow_label": "14 Industry",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": 20.0,
        },
        {
            "_page_key": "industry", "_page_label": "Industry",
            "_section_key": "non_energy", "_section_label": "Non-energy use",
            "common_flow_code": "17", "common_flow_label": "17 Non-energy use",
            "common_product_label": "06 Crude oil", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": 8.0,
        },
        {
            "_page_key": "others", "_page_label": "Other demand",
            "common_flow_code": "16.03-16.05,17",
            "common_flow_label": "16.03-16.05,17 Other sector including non-energy (all demand aggregate)",
            "common_product_label": "07 Gasoline", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": 9.0,
        },
        {
            "_page_key": "power", "_page_label": "Power",
            "common_flow_code": "09.01.01", "common_flow_label": "09.01.01 Electricity plants",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -30.0,
        },
        {
            "_page_key": "power", "_page_label": "Power",
            "common_flow_code": "09", "common_flow_label": "09 Total transformation sector",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -37.0,
        },
        {
            "_page_key": "power", "_page_label": "Power",
            "common_flow_code": "09.01.01", "common_flow_label": "09.01.01 Electricity plants",
            "common_product_label": "17 Electricity", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": 27.0,
        },
        {
            "_page_key": "other_transformation", "_page_label": "Other transformation",
            "common_flow_code": "08", "common_flow_label": "08 Transfers",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -4.0,
        },
        {
            "_page_key": "other_transformation", "_page_label": "Other transformation",
            "common_flow_code": "10.01.17", "common_flow_label": "10.01.17 Non-specified own uses",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -5.0,
        },
        {
            "_page_key": "refining", "_page_label": "Refining",
            "common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -7.0,
        },
        {
            "_page_key": "refining", "_page_label": "Refining",
            "common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries (including own use)",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": -7.0,
        },
    ])

    selected, coverage, selection = select_emissions_component_rows(
        rows,
        {"demand_page_keys": ["industry", "transport", "buildings", "others"]},
    )

    assert coverage.empty
    assert set(selected["_sector_label"]) == {"Industry", "Transformation and own use"}
    assert set(selected["value"]) == {20.0, 30.0, 5.0, 7.0}
    assert "08 Transfers" not in set(selected["common_flow_label"])
    assert (selected["_sector_label"] == "Transformation and own use").sum() == 3
    assert set(selection["emissions_component"]) == {"Final demand", "Transformation and own use"}


def test_total_demand_sector_area_uses_non_overlapping_parent_child_frontier() -> None:
    rows = pd.DataFrame([
        {
            "_page_key": "buildings", "_page_label": "Buildings",
            "common_flow_code": "16.01-16.02", "common_flow_label": "16.01-16.02 Buildings",
            "common_product_code": "01", "common_product_label": "01 Coal", "source_system": "ESTO",
            "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            "scenario": "historical", "year": 2022, "value": 20.0,
            "common_row_id": "buildings_parent", "is_non_expanding_rollup": True,
        },
        {
            "_page_key": "buildings", "_page_label": "Buildings",
            "common_flow_code": "16.01.99", "common_flow_label": "16.01.99 Commercial and public services unallocated",
            "common_product_code": "01", "common_product_label": "01 Coal", "source_system": "ESTO",
            "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            "scenario": "historical", "year": 2022, "value": 9.0,
            "common_row_id": "buildings_commercial", "is_non_expanding_rollup": False,
        },
        {
            "_page_key": "buildings", "_page_label": "Buildings",
            "common_flow_code": "16.02", "common_flow_label": "16.02 Residential",
            "common_product_code": "01", "common_product_label": "01 Coal", "source_system": "ESTO",
            "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            "scenario": "historical", "year": 2022, "value": 11.0,
            "common_row_id": "buildings_residential", "is_non_expanding_rollup": False,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert selected["value"].sum() == 20.0


def test_total_demand_fuel_area_uses_non_overlapping_parent_child_frontier() -> None:
    rows = []
    for source_system, scenario, year, parent_value, child_one, child_two in [
        ("ESTO", "historical", 2022, 20.0, 9.0, 11.0),
        ("LEAP", "Target", 2023, 21.0, None, None),
    ]:
        for product_code, value in [("01", parent_value), ("02", 1.0 if source_system == "LEAP" else 2.0)]:
            rows.append({
                "_page_key": "buildings", "_page_label": "Buildings",
                "common_flow_code": "16.01-16.02", "common_flow_label": "16.01-16.02 Buildings",
                "common_product_code": product_code, "common_product_label": f"{product_code} Fuel",
                "source_system": source_system, "scenario": scenario, "year": year,
                "value": value, "common_row_id": f"{source_system}_{product_code}_parent",
                "is_non_expanding_rollup": True, "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            })
        if source_system == "ESTO":
            for flow_code, value, row_id in [
                ("16.01.99", child_one, "commercial"),
                ("16.02", child_two, "residential"),
            ]:
                rows.append({
                    "_page_key": "buildings", "_page_label": "Buildings",
                    "common_flow_code": flow_code, "common_flow_label": flow_code,
                    "common_product_code": "01", "common_product_label": "01 Fuel",
                    "source_system": source_system, "scenario": scenario, "year": year,
                    "value": value, "common_row_id": row_id, "is_non_expanding_rollup": False,
                    "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
                })

    figure = _build_td_fuel_chart(
        pd.DataFrame(rows),
        pd.DataFrame(columns=["source_system", "scenario", "year", "common_flow_code", "value"]),
        {},
        "LEAP",
        "Target",
        base_year=2022,
    )
    fuel_trace = next(trace for trace in figure.data if trace.name == "01 Fuel" and trace.visible)
    values = dict(zip(fuel_trace.x, fuel_trace.y))
    assert values[2022] == 20.0
    assert values[2023] == 21.0


def test_total_demand_fuel_area_keeps_esto_history_without_projection_detail() -> None:
    demand_rows = pd.DataFrame([
        {
            "_page_key": "industry",
            "_page_label": "Industry",
            "common_flow_code": "14",
            "common_flow_label": "14 Industry sector",
            "common_product_code": product_code,
            "common_product_label": product_label,
            "source_system": "ESTO",
            "scenario": "historical",
            "year": 2022,
            "value": value,
        }
        for product_code, product_label, value in [
            ("01", "01 Coal", 20.0),
            ("17", "17 Electricity", 30.0),
        ]
    ])
    overview_rows = pd.DataFrame([
        {
            "source_system": "ESTO",
            "scenario": "historical",
            "year": 2022,
            "common_flow_code": "12",
            "value": 50.0,
        },
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2030,
            "common_flow_code": "12",
            "value": 55.0,
        },
    ])

    figure = _build_td_fuel_chart(
        demand_rows,
        overview_rows,
        {},
        "LEAP",
        "Target",
        base_year=2022,
    )

    visible_area_names = {
        trace.name
        for trace in figure.data
        if trace.visible and getattr(trace, "stackgroup", None)
    }
    assert visible_area_names == {"01 Coal", "17 Electricity"}
    assert any(trace.name == "LEAP|Target total (Domestic TFC)" for trace in figure.data)
    assert (
        "ESTO historical fuel detail through the base year"
        in figure.layout.meta["stacked_area_note"]
    )


def test_energy_balance_demand_totals_exclude_leap_international_transport() -> None:
    demand_rows = pd.DataFrame([
        {
            "_page_key": page_key,
            "_page_label": page_label,
            "common_flow_code": flow_code,
            "common_flow_label": flow_code,
            "common_product_label": product_label,
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2023,
            "value": value,
        }
        for page_key, page_label, flow_code, product_label, value in [
            ("transport", "Transport", "15.02", "07.01 Motor gasoline", 20.0),
            ("industry", "Industry", "14", "08.01 Natural gas", 10.0),
            ("buildings", "Buildings", "16.01-16.02", "17 Electricity", 30.0),
            ("others", "Other demand", "16.03-16.05,17", "07.17 Other products", 40.0),
        ]
    ])
    overview_rows = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_flow_code": "12", "value": 105.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_flow_code": "04-05", "value": 5.0},
    ])

    sector_figure = _build_td_sector_chart(
        demand_rows, overview_rows, {}, "LEAP", "Target", {}, base_year=2022,
    )
    fuel_figure = _build_td_fuel_chart(
        demand_rows, overview_rows, {}, "LEAP", "Target", base_year=2022,
    )
    for figure, trace_name in [
        (sector_figure, "LEAP|Target (Domestic TFC)"),
        (fuel_figure, "LEAP|Target total (Domestic TFC)"),
    ]:
        total_trace = next(trace for trace in figure.data if trace.name == trace_name)
        assert list(total_trace.y) == [100.0]


def _build_common_esto_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope in ["leap_vs_esto_vs_ninth", "leap_vs_ninth"]:
        for source_system, scenario, base_value in [
            ("ESTO", "historical", 8.0),
            ("LEAP", "Target", 10.0),
            ("NINTH", "Target", 9.0),
        ]:
            if scope == "leap_vs_ninth" and source_system == "ESTO":
                continue
            for year in [2022, 2024]:
                rows.append({
                    "comparison_scope": scope,
                    "source_system": source_system,
                    "economy": "20_USA",
                    "scenario": scenario,
                    "year": year,
                    "common_flow_code": "15.01",
                    "common_flow_name": "Road",
                    "common_flow_label": "15.01 Road",
                    "common_product_code": "07.01",
                    "common_product_name": "Motor gasoline",
                    "common_product_label": "07.01 Motor gasoline",
                    "value": base_value + (0.5 if year == 2024 else 0.0),
                })
    for source_system, scenario, is_exact_row, requires_rollup, base_value in [
        ("ESTO", "historical", True, False, -3.0),
        ("LEAP", "Target", False, True, -2.5),
        ("NINTH", "Target", True, False, -2.8),
    ]:
        for year in [2022, 2024]:
            rows.append({
                "comparison_scope": "leap_vs_esto_vs_ninth",
                "source_system": source_system,
                "economy": "20_USA",
                "scenario": scenario,
                "year": year,
                "common_flow_code": "09",
                "common_flow_name": "Total transformation sector",
                "common_flow_label": "09 Total transformation sector",
                "common_product_code": "09",
                "common_product_name": "Nuclear",
                "common_product_label": "09 Nuclear",
                "common_row_id": f"{source_system.lower()}_transformation_total",
                "common_row_basis": "exact_esto_row" if is_exact_row else "connected_component_rollup",
                "is_exact_row": is_exact_row,
                "requires_rollup": requires_rollup,
                "source_aggregate_labels": "Total transformation - no transfers",
                "source_aggregate_group_ids": "rollup_total_transformation_nuclear",
                "value": base_value - (0.1 if year == 2024 else 0.0),
            })
    return pd.DataFrame(rows)


def _assert_generated_dashboard_outputs(layout: dict[str, Path], expected_pages: list[str]) -> None:
    """Check that generated pages and Plotly bundles are present and non-empty."""
    for page_key in expected_pages:
        assert (layout["dashboards"] / f"{page_key}.html").exists()

    for page_key in DEFAULT_DIAGNOSTIC_PAGES:
        assert not (layout["dashboards"] / f"{page_key}.html").exists()
        assert not (layout["chart_bundles"] / f"{page_key}__charts.json").exists()

    for page_key in expected_pages:
        if page_key == "index":
            continue
        bundle_path = layout["chart_bundles"] / f"{page_key}__charts.json"
        assert bundle_path.exists()
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        charts = bundle.get("charts", {})
        assert charts
        for chart_key, figure in charts.items():
            traces = figure.get("data", [])
            assert traces, chart_key
            assert any(trace.get("x") and trace.get("y") for trace in traces), chart_key


def test_common_esto_dashboard_renders_core_pages_by_default(tmp_path: Path) -> None:
    template = _load_template()
    series_config = _load_series_config()
    df = apply_sign_semantics(_build_common_esto_rows(), template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    manifest = render_dashboard(main_df, template, series_config, layout, scope_df=df)

    _assert_generated_dashboard_outputs(layout, DEFAULT_CORE_PAGES)
    assert (layout["supporting"] / "chart_manifest.csv").exists()

    page_keys = set(manifest["page_key"])
    assert "transport" in page_keys
    assert "total_demand" in page_keys
    assert "transport_leap_vs_ninth" not in page_keys
    overview_rows = manifest[manifest["page_key"] == "total_demand"]
    overview_chart_keys = set(overview_rows["chart_key"])
    assert "chart__area__total_demand__transformation_flow" in overview_chart_keys
    assert "chart__area__total_demand__transformation_fuel" in overview_chart_keys
    assert "chart__line__total_transformation_no_transfers" not in overview_chart_keys
    assert set(overview_rows["page_label"]) == {"Energy balance overview"}
    assert page_file_name("total_demand") == "energy_balance_overview.html"
    assert page_file_name("others") == "other_demand.html"
    assert (layout["dashboards"] / "energy_balance_overview.html").exists()
    overview_redirect = (layout["dashboards"] / "total_demand.html").read_text(
        encoding="utf-8"
    )
    assert "url=energy_balance_overview.html" in overview_redirect
    transport_html = (layout["dashboards"] / "transport.html").read_text(
        encoding="utf-8"
    )
    assert 'href="energy_balance_overview.html"' in transport_html
    for bundle_path in layout["chart_bundles"].glob("*__charts.json"):
        page_key = bundle_path.name.removesuffix("__charts.json")
        bundle_keys = set(json.loads(bundle_path.read_text(encoding="utf-8"))["charts"])
        page_manifest = manifest[manifest["page_key"] == page_key]
        suppressed = page_manifest["suppressed"].astype(str).str.casefold().isin(
            {"true", "1", "yes"}
        )
        loadable_manifest_keys = set(page_manifest.loc[~suppressed, "chart_key"])
        assert loadable_manifest_keys == bundle_keys


def test_dataset_membership_is_retained_on_cards_without_header_filter(
    tmp_path: Path,
) -> None:
    template = _load_template()
    template["total_demand_page"] = {"enabled": False}
    template["emissions_page"] = {"enabled": False}
    template["scope_specific_pages"] = {"enabled": False}
    rows = pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth", "source_system": "LEAP",
            "economy": "20_USA", "scenario": "Target", "year": 2030,
            "common_flow_code": "14", "common_flow_name": "Industry sector",
            "common_flow_label": "14 Industry sector", "common_product_code": "17",
            "common_product_name": "Electricity", "common_product_label": "17 Electricity",
            "value": 10.0,
        },
        {
            "comparison_scope": "esto_leap_ninth", "source_system": "ESTO",
            "economy": "20_USA", "scenario": "historical", "year": 2022,
            "common_flow_code": "14", "common_flow_name": "Industry sector",
            "common_flow_label": "14 Industry sector", "common_product_code": "17",
            "common_product_name": "Electricity", "common_product_label": "17 Electricity",
            "value": 9.0,
        },
        {
            "comparison_scope": "esto_leap_ninth", "source_system": "ESTO",
            "economy": "20_USA", "scenario": "historical", "year": 2022,
            "common_flow_code": "14.03", "common_flow_name": "Manufacturing",
            "common_flow_label": "14.03 Manufacturing", "common_product_code": "17",
            "common_product_name": "Electricity", "common_product_label": "17 Electricity",
            "value": 5.0,
        },
        {
            "comparison_scope": "esto_leap_ninth", "source_system": "NINTH",
            "economy": "20_USA", "scenario": "Target", "year": 2030,
            "common_flow_code": "14.03", "common_flow_name": "Manufacturing",
            "common_flow_label": "14.03 Manufacturing", "common_product_code": "17",
            "common_product_name": "Electricity", "common_product_label": "17 Electricity",
            "value": 6.0,
        },
    ])
    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)

    render_dashboard(rows, template, _load_series_config(), layout)

    html = (layout["dashboards"] / "industry.html").read_text(encoding="utf-8")
    cards = re.findall(
        r'<figure class="chart-card"[^>]*data-datasets="([^"]*)"[^>]*>.*?'
        r'<figcaption class="chart-caption">(.*?)</figcaption>',
        html,
        flags=re.DOTALL,
    )
    assert any("LEAP" in datasets and "Industry" in caption for datasets, caption in cards)
    assert any("LEAP" not in datasets and "Electricity" in caption for datasets, caption in cards)
    assert "Charts containing:" not in html
    assert 'data-dataset-filter="LEAP"' not in html


def test_category_basis_variants_preserve_page_economy_and_filter_options(
    tmp_path: Path,
) -> None:
    base_template = _load_template()
    base_template["total_demand_page"] = {"enabled": False}
    base_template["emissions_page"] = {"enabled": False}
    base_template["scope_specific_pages"] = {"enabled": False}
    series_config = _load_series_config()
    base_rows = apply_sign_semantics(
        _build_common_esto_rows(), base_template["sign_semantics"]
    )
    base_rows = base_rows[
        base_rows["comparison_scope"].eq("leap_vs_esto_vs_ninth")
    ].copy()
    options = [
        {
            "comparison_scope": "esto_leap_ninth",
            "label": "LEAP + ESTO + Ninth",
            "dashboard_key": "20USA",
        },
        {
            "comparison_scope": "esto_leap",
            "label": "LEAP + ESTO",
            "dashboard_key": "20USA__esto_leap",
        },
    ]

    for scope, suffix, sources in [
        ("esto_leap_ninth", "", ["LEAP", "ESTO", "NINTH"]),
        ("esto_leap", "__esto_leap", ["LEAP", "ESTO"]),
    ]:
        template = copy.deepcopy(base_template)
        template["_current_dashboard_key"] = "20USA"
        template["_active_comparison_scope"] = scope
        template["_active_dataset_filter_options"] = sources
        template["_dashboard_key_suffix"] = suffix
        template["_category_basis_options"] = options
        rows = base_rows.copy()
        rows["comparison_scope"] = scope
        if scope == "esto_leap":
            rows = rows[~rows["source_system"].astype(str).eq("NINTH")].copy()
        layout = build_output_layout(
            tmp_path / "outputs", f"20USA{suffix}", clear_existing=True
        )
        render_dashboard(rows, template, series_config, layout)

    default_html = (
        tmp_path / "outputs" / "20USA" / "dashboards" / "transport.html"
    ).read_text(encoding="utf-8")
    two_way_html = (
        tmp_path
        / "outputs"
        / "20USA__esto_leap"
        / "dashboards"
        / "transport.html"
    ).read_text(encoding="utf-8")

    assert "Comparison basis" in default_html
    assert "../../20USA__esto_leap/dashboards/transport.html" in default_html
    assert "../../20USA/dashboards/transport.html" in two_way_html
    assert "../../01AUS__esto_leap/dashboards/transport.html" in two_way_html
    assert 'data-dataset-filter="NINTH"' not in default_html
    assert 'data-dataset-filter="NINTH"' not in two_way_html
    assert "Charts containing:" not in default_html
    assert "data-dataset-filter-section" in default_html
    assert "dataset-group-empty" in default_html
    default_manifest = pd.read_csv(
        tmp_path / "outputs" / "20USA" / "supporting_files" / "chart_manifest.csv"
    )
    two_way_manifest = pd.read_csv(
        tmp_path
        / "outputs"
        / "20USA__esto_leap"
        / "supporting_files"
        / "chart_manifest.csv"
    )
    assert set(default_manifest["comparison_scope"]) == {"esto_leap_ninth"}
    assert set(two_way_manifest["comparison_scope"]) == {"esto_leap"}


def test_common_esto_dashboard_excludes_electricity_and_heat_output_rows() -> None:
    template = _load_template()
    df = pd.DataFrame(
        [
            {"common_flow_code": "17", "common_flow_label": "17 Electricity"},
            {"common_flow_code": "18", "common_flow_label": "18 Electricity output in GWh"},
            {"common_flow_code": "19", "common_flow_label": "19 Heat output in PJ"},
            {"common_flow_code": "19.01", "common_flow_label": "19.01 Heat output detail"},
        ]
    )

    filtered = drop_excluded_flow_rows(df, template["excluded_flow_code_prefixes"])

    assert filtered["common_flow_code"].tolist() == ["17"]


def test_refinery_own_use_is_only_shown_in_the_inclusive_boundary() -> None:
    template = _load_template()
    rows = pd.DataFrame([
        {
            "common_flow_code": "09.07",
            "common_flow_label": "09.07 Oil refineries (including own use)",
        },
        {
            "common_flow_code": "10.01.11",
            "common_flow_label": "10.01.11 Oil refineries",
        },
    ])

    filtered = drop_excluded_flow_rows(
        rows,
        template["excluded_flow_code_prefixes"],
    )

    assert filtered["common_flow_label"].tolist() == [
        "09.07 Oil refineries (including own use)",
    ]


def test_gas_works_own_use_is_not_plotted_as_a_standalone_flow() -> None:
    template = _load_template()
    df = pd.DataFrame(
        [
            {"common_flow_code": "09.06.01", "common_flow_label": "09.06.01 Gas works plants (including own use)"},
            {"common_flow_code": "10.01.02", "common_flow_label": "10.01.02 Gas works plants"},
            {"common_flow_code": "10.01.06", "common_flow_label": "10.01.06 Coal mines"},
        ]
    )

    filtered = drop_excluded_flow_rows(df, template["excluded_flow_code_prefixes"])

    assert filtered["common_flow_code"].tolist() == ["09.06.01", "10.01.06"]


def test_losses_and_own_use_area_cards_use_parent_hierarchy_labels() -> None:
    template = _load_template()
    page_df = pd.DataFrame(
        [
            {
                "common_flow_code": "10.01.06",
                "common_flow_label": "10.01.06 Coal mines",
                "source_system": source_system,
            }
            for source_system in ["ESTO", "LEAP", "NINTH"]
        ]
        + [
            {
                "common_flow_code": "10.02",
                "common_flow_label": "10.02 Transmission and distribution losses",
                "source_system": source_system,
            }
            for source_system in ["ESTO", "LEAP", "NINTH"]
        ]
    )

    specs = pick_area_specs(page_df, template)
    labels_by_prefix = {
        str(spec["aggregate_flow_prefix"]): str(spec["aggregate_flow_label"])
        for spec in specs
    }

    assert labels_by_prefix["10"] == "10 Losses and own use"
    assert labels_by_prefix["10.01"] == "10.01 Own use"


def test_single_boundary_overview_prefers_including_own_use_label() -> None:
    template = _load_template()
    page_df = pd.DataFrame(
        [
            {
                "common_flow_code": "09.07",
                "common_flow_label": "09.07 Oil refineries",
                "source_system": "LEAP",
            },
            {
                "common_flow_code": "09.07",
                "common_flow_label": "09.07 Oil refineries (including own use)",
                "source_system": "ESTO",
            },
            {
                "common_flow_code": "09.07",
                "common_flow_label": "09.07 Oil refineries (including own use)",
                "source_system": "NINTH",
            },
        ]
    )

    specs = pick_area_specs(page_df, template)
    refining_overview = next(
        spec for spec in specs if spec["aggregate_flow_prefix"] == "09"
    )

    assert refining_overview["aggregate_flow_label"] == (
        "09.07 Oil refineries (including own use)"
    )


def test_multi_boundary_overview_does_not_inherit_one_child_label() -> None:
    template = _load_template()
    page_df = pd.DataFrame(
        [
            {
                "common_flow_code": flow_code,
                "common_flow_label": flow_label,
                "source_system": source_system,
            }
            for source_system in ["ESTO", "LEAP", "NINTH"]
            for flow_code, flow_label in [
                ("09.07", "09.07 Oil refineries (including own use)"),
                ("09.08", "09.08 Coal transformation"),
            ]
        ]
    )

    specs = pick_area_specs(page_df, template)
    transformation_overview = next(
        spec for spec in specs if spec["aggregate_flow_prefix"] == "09"
    )

    assert transformation_overview["aggregate_flow_label"] not in {
        "09.07 Oil refineries (including own use)",
        "09.08 Coal transformation",
    }


def test_ninth_pre_base_year_rows_are_excluded_by_default() -> None:
    df = pd.DataFrame(
        [
            {"source_system": "NINTH", "year": 2021, "value": 1.0},
            {"source_system": "NINTH", "year": 2022, "value": 2.0},
            {"source_system": "ESTO", "year": 2021, "value": 3.0},
        ]
    )

    filtered = filter_ninth_pre_base_year_data(
        df,
        base_year=2022,
        include_pre_base_year_data=False,
    )

    assert filtered[["source_system", "year"]].to_dict("records") == [
        {"source_system": "NINTH", "year": 2022},
        {"source_system": "ESTO", "year": 2021},
    ]


def test_ninth_pre_base_year_rows_can_be_retained() -> None:
    df = pd.DataFrame([{"source_system": "NINTH", "year": 2021, "value": 1.0}])

    filtered = filter_ninth_pre_base_year_data(
        df,
        base_year=2022,
        include_pre_base_year_data=True,
    )

    assert len(filtered) == 1


def test_russia_uses_2021_as_the_ninth_base_year_only() -> None:
    assert ninth_base_year_for_economy("16_RUS", 2022) == 2021
    assert ninth_base_year_for_economy("16RUS", 2022) == 2021
    assert ninth_base_year_for_economy("20_USA", 2022) == 2022


def test_russia_ninth_comparison_includes_2022_projection() -> None:
    rows = pd.DataFrame(
        [
            {
                "economy": "16_RUS",
                "source_system": source,
                "scenario": scenario,
                "year": year,
                "value": value,
            }
            for source, scenario, year, value in [
                ("ESTO", "historical", 2022, 90.0),
                ("LEAP", "Target", 2022, 100.0),
                ("NINTH", "Target", 2021, 95.0),
                ("NINTH", "Target", 2022, 98.0),
            ]
        ]
    )

    historical, projected = compute_diff_series(rows, base_year=2022)

    assert list(historical.index) == [2022]
    assert list(projected.index) == [2022]
    assert projected.loc[2022] == 2.0


def test_power_sector_rollup_is_not_assigned_to_other_transformation() -> None:
    template = _load_template()
    df = pd.DataFrame([
        {
            "common_flow_code": "09.01-09.02",
            "common_flow_label": "09.01-09.02 Power sector",
        }
    ])

    assigned = assign_pages(df, template["sector_pages"])

    assert assigned.loc[0, "_page_key"] == "power"
    assert assigned.loc[0, "_section_key"] == "power"


def test_page_root_prefix_matching_is_boundary_safe() -> None:
    assert code_expression_matches_prefix("14", "14")
    assert code_expression_matches_prefix("14.03.01", "14")
    assert code_expression_matches_prefix("14.01,14.03", "14")
    assert not code_expression_matches_prefix("5.14", "14")
    assert not code_expression_matches_prefix("05.14", "14")
    assert not code_expression_matches_prefix("114", "14")
    assert not code_expression_matches_prefix("14A", "14")


def test_most_specific_page_root_owns_nested_transformation_categories() -> None:
    template = _load_template()
    rows = pd.DataFrame([
        {"common_flow_code": "09.01.03", "common_flow_label": "09.01.03 Power detail"},
        {"common_flow_code": "09.07.01", "common_flow_label": "09.07.01 Refining detail"},
        {"common_flow_code": "09.06.02", "common_flow_label": "09.06.02 Gas processing"},
    ])

    assigned = assign_pages(
        rows,
        template["sector_pages"],
        template["routing_special_cases"],
    )

    assert assigned["_page_key"].tolist() == ["power", "refining", "other_transformation"]
    assert assigned["_routing_status"].tolist() == ["page_root", "page_root", "page_root"]
    assert assigned["_page_rule_priority"].tolist() == ["root:09.01", "root:09.07", "root:09"]


def test_combined_placeholder_is_special_but_exact_17_routes_to_industry_section() -> None:
    template = _load_template()
    rows = pd.DataFrame([
        {
            "common_flow_code": "16.03-16.05,17",
            "common_flow_label": "16.03-16.05,17 Other sector including non-energy",
        },
        {"common_flow_code": "17", "common_flow_label": "17 Non-energy use"},
    ])

    without_special_case = assign_pages(rows.iloc[[0]], template["sector_pages"])
    assert without_special_case.iloc[0]["_page_key"] == "others"

    assigned = assign_pages(
        rows,
        template["sector_pages"],
        template["routing_special_cases"],
    )
    assert assigned["_page_key"].tolist() == ["others", "industry"]
    assert assigned["_routing_status"].tolist() == ["special_case", "special_case"]
    assert assigned.loc[1, "_section_key"] == "non_energy"
    assert assigned.iloc[0]["_routing_special_case"] == "combined_other_and_non_energy_placeholder"


def test_energy_balance_totals_receive_bespoke_routing_status() -> None:
    template = _load_template()
    assigned = assign_pages(
        pd.DataFrame([
            {"common_flow_code": "07", "common_flow_label": "07 Total primary energy supply"},
            {"common_flow_code": "12", "common_flow_label": "12 Total final consumption"},
        ]),
        template["sector_pages"],
        template["routing_special_cases"],
    )

    routed = assign_bespoke_overview_rows(assigned, template["total_demand_page"])

    assert set(routed["_page_key"]) == {"total_demand"}
    assert set(routed["_routing_status"]) == {"bespoke_page"}


def test_non_energy_industry_section_is_available_when_exact_17_has_leap_data() -> None:
    template = _load_template()
    rows = pd.DataFrame([
        {
            "common_flow_code": "17",
            "common_flow_label": "17 Non-energy use",
            "source_system": "ESTO",
        },
        {
            "common_flow_code": "17",
            "common_flow_label": "17 Non-energy use",
            "source_system": "LEAP",
        },
    ])
    assigned = assign_pages(
        rows,
        template["sector_pages"],
        template["routing_special_cases"],
    )
    assert set(assigned["_page_key"]) == {"industry"}
    assert set(assigned["_section_key"]) == {"non_energy"}
    assert template["leap_demand_sector_coverage"]["require_primary_source_page_keys"] == []


def test_chart_dataset_tokens_come_from_final_traces() -> None:
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=[2022], y=[1.0], name="ESTO"))
    figure.update_layout(meta={
        "trace_meta": [
            {"source_system": "ESTO", "tag": "esto", "metric": "both", "active_visible": True}
        ]
    })

    assert chart_dataset_tokens_from_figure(figure) == "ESTO"


def test_jump_navigation_uses_flow_levels_not_parent_or_leaf_status() -> None:
    rows = [
        {"section_label": "Other transformation (including own use)", "flow_group_label": label}
        for label in ["09.06 Gas processing plants", "09.12 Non-specified transformation",
                      "09.06.02 Liquefaction/regasification plants", "09.06.01 Gas works plants",
                      "09.06.02.01 Liquefaction"]
    ] + [
        {"section_label": "Other energy-sector own use", "flow_group_label": label}
        for label in ["10.01.06 Coal mines", "10.01.12 Oil and gas extraction"]
    ]

    html = _jump_nav_html("Other transformation", line_section_tree(rows))

    assert html.count('<div class="jump-nav-row" data-level="1"') == 1
    assert html.count('<div class="jump-nav-row" data-level="2"') == 1
    assert html.count('<div class="jump-nav-row" data-level="3"') == 1
    assert 'data-level="1" data-hierarchy-depth="1">09.06 Gas processing plants</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">09.12 Non-specified transformation</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">10.01.06 Coal mines</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">10.01.12 Oil and gas extraction</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">09.06.02 Liquefaction/regasification plants</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">09.06.01 Gas works plants</a>' in html
    assert 'data-level="3" data-hierarchy-depth="3">09.06.02.01 Liquefaction</a>' in html
    assert '>Other transformation (including own use)</a>' not in html
    assert '>Other energy-sector own use</a>' not in html
    assert html.index('data-hierarchy-depth="1"') < html.index('data-hierarchy-depth="2"')
    assert html.index('data-level="2"') < html.index('data-level="3"')


def test_rendered_sections_follow_numeric_navigation_order() -> None:
    rows = [
        {
            "section_label": "Other energy-sector own use",
            "flow_group_label": "10.01.03 Liquefaction/regasification plants",
            "chart_key": "chart_10",
        },
        {
            "section_label": "Other transformation (including own use)",
            "flow_group_label": "09.06 Gas processing plants",
            "chart_key": "chart_09",
        },
        {
            "section_label": "Transfers",
            "flow_group_label": "08 Transfers",
            "chart_key": "chart_08",
        },
    ]

    html = _line_sections_html(rows, "Other transformation")

    assert html.index(">Transfers</h2>") < html.index(">Other transformation (including own use)</h2>")
    assert html.index(">Other transformation (including own use)</h2>") < html.index(">Other energy-sector own use</h2>")


def test_jump_navigation_replaces_page_name_with_buildings_tree_nodes() -> None:
    rows = [
        {"section_label": "Buildings", "flow_group_label": label}
        for label in [
            "16.01-16.02 Buildings",
            "16.01.99 Commercial and public services unallocated",
            "16.02 Residential",
            "16.01.01 Datacentres",
        ]
    ]

    html = _jump_nav_html("Buildings", line_section_tree(rows))

    assert '>Buildings</a>' not in html
    assert 'data-level="1" data-hierarchy-depth="1">16.01-16.02 Buildings</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">16.02 Residential</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">16.01.99 Commercial and public services unallocated</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">16.01.01 Datacentres</a>' in html


def test_jump_navigation_restores_real_industry_overview_parent() -> None:
    rows = [
        {"section_label": "Industry", "flow_group_label": label}
        for label in [
            "14.01 Mining and quarrying",
            "14.02 Construction",
            "14.03 Manufacturing",
            "14.03.01 Iron and steel",
            "14.03.11 Non-specified industry",
        ]
    ]
    roots = [{"label": "14 Industry sector", "target": "overview-industry__14_industry_sector"}]

    html = _jump_nav_html("Industry", line_section_tree(rows, roots))

    assert 'href="#overview-industry__14_industry_sector"' in html
    assert 'data-level="1" data-hierarchy-depth="1">14 Industry sector</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">14.01 Mining and quarrying</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">14.02 Construction</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">14.03 Manufacturing</a>' in html
    assert 'data-level="3" data-hierarchy-depth="3">14.03.01 Iron and steel</a>' in html
    assert 'data-level="3" data-hierarchy-depth="3">14.03.11 Non-specified industry</a>' in html


def test_flow_subtree_root_requires_all_descendants_to_share_page() -> None:
    assigned = pd.DataFrame(
        [
            {"common_flow_code": "16", "_page_key": "others"},
            {"common_flow_code": "16.01-16.02", "_page_key": "buildings"},
            {"common_flow_code": "16.03", "_page_key": "others"},
            {"common_flow_code": "14", "_page_key": "industry"},
            {"common_flow_code": "14.03.01", "_page_key": "industry"},
        ]
    )

    assert not _flow_subtree_is_page_complete(assigned, "others", "16")
    assert _flow_subtree_is_page_complete(assigned, "industry", "14")


def test_page_defined_overview_aggregates_parent_renderer_sections() -> None:
    rows = [
        {"section_label": "Other transformation (including own use)", "flow_group_label": label}
        for label in [
            "09.06 Gas processing plants (including own use)",
            "09.06.01 Gas works plants (including own use)",
            "09.12 Non-specified transformation (including own use)",
        ]
    ] + [
        {"section_label": "Other energy-sector own use", "flow_group_label": "10.01.06 Coal mines"},
    ]
    roots = [
        {
            "label": "Other transformation (including own use)",
            "section_label": "Other transformation (including own use)",
            "target": "overview-other_transformation__other_transformation_including_own_use",
        },
        {
            "label": "Other energy-sector own use",
            "section_label": "Other energy-sector own use",
            "target": "overview-other_transformation__other_energy_sector_own_use",
        },
    ]

    html = _jump_nav_html("Other transformation", line_section_tree(rows, roots))

    assert 'data-level="1" data-hierarchy-depth="1">Other transformation (including own use)</a>' in html
    assert 'data-level="1" data-hierarchy-depth="1">Other energy-sector own use</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">09.06 Gas processing plants (including own use)</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">09.12 Non-specified transformation (including own use)</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">10.01.06 Coal mines</a>' in html
    assert 'data-level="3" data-hierarchy-depth="3">09.06.01 Gas works plants (including own use)</a>' in html
    assert 'href="#sec-other_transformation__other_energy_sector_own_use"' in html
    assert 'href="#sec-other_transformation__other_energy_sector_own_use__10_01_06_coal_mines"' not in html


def test_jump_navigation_preserves_compound_rollup_containment() -> None:
    rows = [
        {"section_label": "International transport", "flow_group_label": label}
        for label in [
            "04 International marine bunkers",
            "04-05 International transport (bunkers)",
            "05 International aviation bunkers",
        ]
    ]

    html = _jump_nav_html("International transport", line_section_tree(rows))

    assert 'data-level="1" data-hierarchy-depth="1">04-05 International transport (bunkers)</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">04 International marine bunkers</a>' in html
    assert 'data-level="2" data-hierarchy-depth="2">05 International aviation bunkers</a>' in html


def test_unparented_top_level_flows_remain_level_one() -> None:
    rows = [
        {"section_label": "Supply", "flow_group_label": "01 Production"},
        {"section_label": "Supply", "flow_group_label": "02 Imports"},
        {"section_label": "Supply", "flow_group_label": "03 Exports"},
    ]

    html = _jump_nav_html("Supply", line_section_tree(rows))

    assert html.count('class="jump-chip" data-level="1" data-hierarchy-depth="1"') == 3
    assert 'data-level="2"' not in html


def test_supply_sections_follow_natural_esto_code_order() -> None:
    labels = [
        "06 Stock changes",
        "11 Statistical discrepancy",
        "01 Production",
        "02 Imports",
        "03 Exports",
        "04 International marine bunkers",
        "05 International aviation bunkers",
    ]
    rows = [
        {
            "section_label": "Supply",
            "flow_group_label": label,
            "chart_key": f"chart-{index}",
            "product_label": "All products",
        }
        for index, label in enumerate(labels)
    ]
    expected = [
        "01 Production",
        "02 Imports",
        "03 Exports",
        "04 International marine bunkers",
        "05 International aviation bunkers",
        "06 Stock changes",
        "11 Statistical discrepancy",
    ]

    navigation_html = _jump_nav_html("Supply", line_section_tree(rows))
    body_html = _line_sections_html(rows, "Supply")

    assert [navigation_html.index(f">{label}</a>") for label in expected] == sorted(
        navigation_html.index(f">{label}</a>") for label in expected
    )
    assert [body_html.index(f">{label}</h3>") for label in expected] == sorted(
        body_html.index(f">{label}</h3>") for label in expected
    )


def test_section_sorting_uses_code_order_within_each_hierarchy_level() -> None:
    rows = [
        {"section_label": "Industry", "flow_group_label": label}
        for label in [
            "14.03 Manufacturing",
            "14.01 Mining and quarrying",
            "14.03.11 Non-specified industry",
            "14.03.01 Iron and steel",
            "14.02 Construction",
        ]
    ]
    roots = [{"label": "14 Industry sector", "target": "overview-industry"}]

    html = _jump_nav_html("Industry", line_section_tree(rows, roots))

    assert html.index(">14.01 Mining and quarrying</a>") < html.index(">14.02 Construction</a>")
    assert html.index(">14.02 Construction</a>") < html.index(">14.03 Manufacturing</a>")
    assert html.index(">14.03.01 Iron and steel</a>") < html.index(">14.03.11 Non-specified industry</a>")


def test_single_visible_flow_is_a_level_one_aggregate() -> None:
    rows = [{"section_label": "Transfers", "flow_group_label": "08 Transfers"}]

    html = _jump_nav_html("Other transformation", line_section_tree(rows))

    assert 'data-level="1" data-hierarchy-depth="1">08 Transfers</a>' in html


def test_aggregate_only_domestic_demand_pages_remain_visible() -> None:
    template = _load_template()

    filtered = filter_template_for_leap_demand_coverage(
        template,
        {"Industry", "Buildings", "Other sector", "Transport non road"},
    )

    assert "_hidden_page_keys" not in filtered["leap_demand_sector_coverage"]
    assert filtered["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] == {
        "industry": ["Industry"],
        "transport": ["Transport non road"],
        "buildings": ["Buildings"],
        "others": ["Other sector"],
    }


def test_buildings_guide_context_uses_source_mapping_and_placeholder() -> None:
    chart_rows = [
        {
            "chart_type": "stacked_area",
            "flow_group_label": "Buildings summary",
            "product_label": "Overview",
        },
        {
            "chart_type": "line",
            "flow_group_label": "16.02 Residential",
            "product_label": "17 Electricity",
            "common_row_id": "residential_electricity",
        },
        {
            "chart_type": "line",
            "flow_group_label": "16.02 Residential",
            "product_label": "08.01 Natural gas",
            "common_row_id": "residential_gas",
        },
    ]
    template = filter_template_for_leap_demand_coverage(
        _load_template(), ["Buildings"]
    )

    source_map = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "source_system": "ESTO",
                "source_flow": "16.02 Residential",
                "source_product": "17 Electricity",
                "common_flow_label": "16.02 Residential",
                "common_product_label": "17 Electricity",
                "common_row_id": "residential_electricity",
            },
            {
                "comparison_scope": "esto_leap_ninth",
                "source_system": "LEAP",
                "source_flow": "All demand aggregated/Buildings",
                "source_product": "Electricity",
                "common_flow_label": "16.02 Residential",
                "common_product_label": "17 Electricity",
                "common_row_id": "residential_electricity",
            },
            {
                "comparison_scope": "esto_leap_ninth",
                "source_system": "NINTH",
                "source_flow": "16_other_sector/16_02_residential",
                "source_product": "17_electricity",
                "common_flow_label": "16.02 Residential",
                "common_product_label": "17 Electricity",
                "common_row_id": "residential_electricity",
            },
        ]
    )
    table = guide_page_mapping_table(
        chart_rows,
        source_map,
        "esto_leap_ninth",
    )
    assert table["headers"] == [
        "Common sector",
        "Common fuel",
        "ESTO sector",
        "ESTO fuel",
        "LEAP sector",
        "LEAP fuel",
        "9th sector",
        "9th fuel",
    ]
    assert table["rows"][0] == [
        "16.02 Residential",
        "17 Electricity",
        "16.02 Residential",
        "17 Electricity",
        "All demand aggregated/Buildings",
        "Electricity",
        "16_other_sector/16_02_residential",
        "17_electricity",
    ]
    status = guide_placeholder_status("buildings", template)
    assert "All demand aggregated" in status
    assert "Buildings" in status
    assert "unavailable, not as zero" in status
    note = page_placeholder_note("buildings", template)
    assert "LEAP placeholder in use" in note
    assert "missing detail should not be read as zero" in note


def test_mapping_guide_context_applies_to_other_chart_pages() -> None:
    chart_rows = [
        {
            "chart_type": "line",
            "flow_group_label": "01 Production",
            "product_label": "08.01 Natural gas",
            "common_row_id": "production_gas",
        }
    ]
    source_map = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "source_system": "ESTO",
                "source_flow": "01 Production",
                "source_product": "08.01 Natural gas",
                "common_flow_label": "01 Production",
                "common_product_label": "08.01 Natural gas",
                "common_row_id": "production_gas",
            }
        ]
    )
    template = _load_template()
    template["_active_comparison_scope"] = "esto_leap_ninth"

    context = guide_page_context("supply", chart_rows, template, source_map)

    assert context["page_mapping_table"]["headers"][0] == "Common flow"
    assert context["page_mapping_table"]["rows"][0][2] == "01 Production"
    assert context["placeholder_in_use"] is False


def test_mapping_guide_table_columns_follow_comparison_basis() -> None:
    chart_rows = [
        {
            "chart_type": "line",
            "flow_group_label": "14 Industry sector",
            "product_label": "17 Electricity",
            "common_row_id": "industry_electricity",
        }
    ]
    source_map = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap",
                "source_system": source_system,
                "source_flow": source_system + " industry",
                "source_product": "Electricity",
                "common_flow_label": "14 Industry sector",
                "common_product_label": "17 Electricity",
                "common_row_id": "industry_electricity",
            }
            for source_system in ["ESTO", "LEAP"]
        ]
    )

    table = guide_page_mapping_table(
        chart_rows,
        source_map,
        "esto_leap",
        source_systems=["LEAP", "ESTO"],
    )

    assert table["headers"] == [
        "Common sector",
        "Common fuel",
        "ESTO sector",
        "ESTO fuel",
        "LEAP sector",
        "LEAP fuel",
    ]
    assert "9th sector" not in table["headers"]
    assert table["note"] == ""


def test_mapping_guide_table_flags_mismatched_provenance_generation() -> None:
    chart_rows = [
        {
            "chart_type": "line",
            "flow_group_label": "14.03.01 Iron and steel",
            "product_label": "02.02 Gas coke",
            "common_row_id": "stale_common_row_id",
        }
    ]

    table = guide_page_mapping_table(
        chart_rows,
        pd.DataFrame(),
        "esto_leap_ninth",
        source_systems=["LEAP", "ESTO", "NINTH"],
    )

    assert table["rows"][0][2:] == ["Provenance unavailable*"] * 6
    assert "Regenerate the comparison data and mapping files together" in table["note"]


def test_mapping_guide_table_explains_when_provenance_files_were_not_supplied() -> None:
    chart_rows = [
        {
            "chart_type": "line",
            "flow_group_label": "08 Transfers",
            "product_label": "07.01 Motor gasoline",
            "common_row_id": "transfers_motor_gasoline",
        }
    ]

    table = guide_page_mapping_table(
        chart_rows,
        None,
        "esto_leap_ninth",
        source_systems=["LEAP", "ESTO", "NINTH"],
    )

    assert table["rows"][0][2:] == ["Provenance unavailable*"] * 6
    assert "were not included in this app build" in table["note"]
    assert "does not mean these categories are unmapped" in table["note"]
    assert "Regenerate the comparison data" not in table["note"]


def test_source_category_map_combines_native_and_esto_mappings(tmp_path: Path) -> None:
    source_path = tmp_path / "source_to_common.csv"
    esto_path = tmp_path / "esto_to_common.csv"
    pd.DataFrame(
        [
            {
                "scope": "esto_leap_ninth",
                "system": "LEAP",
                "source_flow": "Buildings",
                "source_product": "Electricity",
                "common_flow_label": "16.01-16.02 Buildings",
                "common_product_label": "17 Electricity",
                "common_row_id": "buildings_electricity",
            }
        ]
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "component_esto_flow": "16.02 Residential",
                "component_esto_product": "17 Electricity",
                "common_flow_label": "16.01-16.02 Buildings",
                "common_product_label": "17 Electricity",
                "common_row_id": "buildings_electricity",
                "component_sign": 1,
            }
        ]
    ).to_csv(esto_path, index=False)

    combined = load_source_category_map(source_path, esto_path)

    assert set(combined["source_system"]) == {"LEAP", "ESTO"}
    esto_row = combined[combined["source_system"] == "ESTO"].iloc[0]
    assert esto_row["source_flow"] == "16.02 Residential"
    assert esto_row["source_product"] == "17 Electricity"


def test_aggregate_placeholder_overviews_require_leap_rows() -> None:
    from codebase.common_esto_dashboard_renderer import (
        area_chart_allowed_for_demand_coverage,
    )

    template = _load_template()
    detailed_rows = pd.DataFrame(
        [
            {"source_system": "ESTO", "common_flow_label": "16.02 Residential"},
            {"source_system": "NINTH", "common_flow_label": "16.02 Residential"},
        ]
    )

    assert not area_chart_allowed_for_demand_coverage(
        "buildings",
        detailed_rows,
        template,
    )
    assert area_chart_allowed_for_demand_coverage(
        "buildings",
        pd.concat(
            [
                detailed_rows,
                pd.DataFrame(
                    [{"source_system": "LEAP", "common_flow_label": "16 Buildings"}]
                ),
            ],
            ignore_index=True,
        ),
        template,
    )
    assert area_chart_allowed_for_demand_coverage(
        "refining",
        detailed_rows,
        template,
    )


def test_all_demand_other_sector_placeholder_is_routed_before_industry_non_energy_section() -> None:
    template = _load_template()
    df = pd.DataFrame([
        {
            "common_flow_code": "16.03-16.05,17",
            "common_flow_label": "16.03-16.05,17 Other sector including non-energy (all demand aggregate)",
        },
        {
            "common_flow_code": "17",
            "common_flow_label": "17 Non-energy use",
        },
    ])

    assigned = assign_pages(
        df,
        template["sector_pages"],
        template["routing_special_cases"],
    )

    assert assigned.loc[0, "_page_key"] == "others"
    assert assigned.loc[1, "_page_key"] == "industry"
    assert assigned.loc[1, "_section_key"] == "non_energy"


def test_transformation_total_selection_uses_rollup_membership_and_source_role() -> None:
    df = _build_common_esto_rows()
    config = {
        "source_aggregate_label": "Total transformation - no transfers",
        "generated_source_systems": ["LEAP"],
    }

    selected = select_transformation_total_rows(df, config)

    assert set(selected["source_system"]) == {"ESTO", "LEAP", "NINTH"}
    leap_rows = selected[selected["source_system"] == "LEAP"]
    reference_rows = selected[selected["source_system"].isin(["ESTO", "NINTH"])]
    assert leap_rows["requires_rollup"].all()
    assert reference_rows["is_exact_row"].all()


def test_transformation_overview_adds_transfers_own_use_and_losses() -> None:
    rows = _build_common_esto_rows()
    supplements = pd.DataFrame([
        {
            **rows.iloc[0].to_dict(),
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2024,
            "common_flow_code": flow_code,
            "common_flow_label": flow_label,
            "common_product_code": "17",
            "common_product_label": "17 Electricity",
            "common_row_id": f"supplement_{flow_code}",
            "is_exact_row": True,
            "requires_rollup": False,
            "source_aggregate_labels": "",
            "value": value,
        }
        for flow_code, flow_label, value in [
            ("08", "08 Transfers", -2.0),
            ("10.01.17", "10.01.17 Non-specified own uses", -3.0),
            ("10.02", "10.02 Transmission and distribution losses", -4.0),
        ]
    ])
    rows = pd.concat([rows, supplements], ignore_index=True, sort=False)
    config = {
        "flow_code_prefixes": ["09", "08", "10.01", "10.02"],
    }
    presentation_config = {
        "enabled": True,
        "append_inclusive_transformation_label": True,
    }

    selected = select_transformation_overview_rows(
        rows,
        config,
        presentation_config,
    )

    selected_codes = set(selected["common_flow_code"].astype(str))
    assert "09" in selected_codes
    assert {"08", "10.01.17", "10.02"}.issubset(selected_codes)


def test_transformation_overview_leaf_frontier_replaces_parent_flow() -> None:
    rows = _build_common_esto_rows()
    parent = rows[
        rows["common_flow_code"].astype(str).eq("09")
    ].iloc[0].to_dict()
    child = {
        **parent,
        "common_flow_code": "09.07",
        "common_flow_label": "09.07 Oil refineries",
        "common_row_id": "transformation_leaf_09_07",
    }
    rows = pd.concat([rows, pd.DataFrame([child])], ignore_index=True, sort=False)

    selected = select_transformation_overview_rows(
        rows,
        {"flow_code_prefixes": ["09", "08", "10.01", "10.02"]},
        {"enabled": True, "append_inclusive_transformation_label": True},
        prefer_leaf_flows=True,
    )

    matching_context = selected[
        selected["source_system"].eq(parent["source_system"])
        & selected["scenario"].eq(parent["scenario"])
    ]
    selected_codes = set(matching_context["common_flow_code"].astype(str))
    assert "09.07" in selected_codes
    assert "09" not in selected_codes


def test_transformation_leaf_frontier_does_not_treat_broad_rollup_as_terminal() -> None:
    common = {
        "comparison_scope": "esto_leap_ninth",
        "economy": "01_AUS",
        "year": 2022,
        "common_product_code": "08.01",
        "common_product_label": "08.01 Natural gas",
        "value": -10.0,
    }
    categories = [
        ("09", "09 Transformation (including own use)", True),
        (
            "09.06.02",
            "09.06.02 Liquefaction/regasification plants (including own use)",
            True,
        ),
        ("09.06.02.01", "09.06.02.01 Liquefaction", False),
        ("09.07", "09.07 Oil refineries", False),
    ]
    rows = pd.DataFrame([
        {
            **common,
            "source_system": source_system,
            "scenario": scenario,
            "common_flow_code": flow_code,
            "common_flow_label": flow_label,
            # The ESTO rows carry the mapping declaration; it must determine
            # the equivalent LEAP comparison frontier on the same surface.
            "is_non_expanding_rollup": is_rollup if source_system == "ESTO" else False,
        }
        for source_system, scenario in [("ESTO", "historical"), ("LEAP", "Reference")]
        for flow_code, flow_label, is_rollup in categories
    ])

    selected = _leaf_flow_rows(rows)

    for source_system in ("ESTO", "LEAP"):
        selected_codes = set(
            selected.loc[
                selected["source_system"].eq(source_system),
                "common_flow_code",
            ].astype(str)
        )
        assert selected_codes == {"09.06.02", "09.07"}


def test_common_esto_dashboard_can_render_opt_in_scope_pages(tmp_path: Path) -> None:
    template = _load_template()
    template["scope_specific_pages"]["enabled"] = True
    series_config = _load_series_config()
    df = apply_sign_semantics(_build_common_esto_rows(), template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    manifest = render_dashboard(main_df, template, series_config, layout, scope_df=df)

    assert (layout["dashboards"] / "transport_leap_vs_ninth.html").exists()

    page_keys = set(manifest["page_key"])
    assert "transport_leap_vs_ninth" in page_keys


def test_common_esto_dashboard_keeps_international_transport_on_supply_without_secondary_page(
    tmp_path: Path,
) -> None:
    template = _load_template()
    series_config = _load_series_config()
    rows = _build_common_esto_rows()
    bunker_rows: list[dict[str, object]] = []
    for source_system, scenario, value in [
        ("ESTO", "historical", -4.0),
        ("LEAP", "Target", -4.5),
        ("NINTH", "Target", -4.2),
    ]:
        for year in [2022, 2024]:
            bunker_rows.append({
                "comparison_scope": "leap_vs_esto_vs_ninth",
                "source_system": source_system,
                "economy": "20_USA",
                "scenario": scenario,
                "year": year,
                "common_flow_code": "04-05",
                "common_flow_name": "International transport (bunkers)",
                "common_flow_label": "04-05 International transport (bunkers)",
                "common_product_code": "07.05",
                "common_product_name": "Kerosene type jet fuel",
                "common_product_label": "07.05 Kerosene type jet fuel",
                "value": value,
            })
    for flow_code, flow_name, flow_label, product_code, product_name, product_label in [
        (
            "04",
            "International marine bunkers",
            "04 International marine bunkers",
            "07.08",
            "Fuel oil",
            "07.08 Fuel oil",
        ),
        (
            "05",
            "International aviation bunkers",
            "05 International aviation bunkers",
            "07.05",
            "Kerosene type jet fuel",
            "07.05 Kerosene type jet fuel",
        ),
    ]:
        for source_system, scenario, value in [
            ("ESTO", "historical", -3.0),
            ("NINTH", "Target", -3.2),
        ]:
            for year in [2022, 2024]:
                bunker_rows.append({
                    "comparison_scope": "leap_vs_esto_vs_ninth",
                    "source_system": source_system,
                    "economy": "20_USA",
                    "scenario": scenario,
                    "year": year,
                    "common_flow_code": flow_code,
                    "common_flow_name": flow_name,
                    "common_flow_label": flow_label,
                    "common_product_code": product_code,
                    "common_product_name": product_name,
                    "common_product_label": product_label,
                    "value": value,
                })
    rows = pd.concat([rows, pd.DataFrame(bunker_rows)], ignore_index=True, sort=False)
    df = apply_sign_semantics(rows, template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    manifest = render_dashboard(main_df, template, series_config, layout, scope_df=df)

    page_path = layout["dashboards"] / "international_transport.html"
    assert not page_path.exists()
    assert "international_transport" not in set(manifest["page_key"])

    supply_html = (layout["dashboards"] / "supply.html").read_text(encoding="utf-8")
    index_html = (layout["dashboards"] / "index.html").read_text(encoding="utf-8")
    assert 'href="international_transport.html"' not in supply_html
    assert 'href="international_transport.html"' not in index_html

    supply_flows = set(manifest.loc[manifest["page_key"].eq("supply"), "common_flow_label"])
    assert "04 International marine bunkers" in supply_flows
    assert "05 International aviation bunkers" in supply_flows
    assert "04-05 International transport (bunkers)" not in supply_flows

    assignments = pd.read_csv(layout["supporting"] / "page_assignment_summary.csv")
    assert "international_transport" not in set(assignments["page_key"])
    assert "supply" in set(assignments["page_key"])


def test_supply_placeholder_explains_missing_marine_and_aviation_leap_detail() -> None:
    template = _load_template()
    template["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] = {
        "supply": ["International transport"]
    }

    note = page_placeholder_note("supply", template)
    status = guide_placeholder_status("supply", template)

    assert "All demand aggregated/International transport" in note
    assert "marine (04) and aviation (05) cannot be viewed separately" in note
    assert "04-05 International transport (bunkers)" in status
    assert "when their separate source branches replace the placeholder" in status


def test_supply_uses_combined_bunker_boundary_while_placeholder_is_active(
    tmp_path: Path,
) -> None:
    template = _load_template()
    template["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] = {
        "supply": ["International transport"]
    }
    series_config = _load_series_config()
    rows = _build_common_esto_rows()
    bunker_rows: list[dict[str, object]] = []
    for flow_code, flow_name, flow_label in [
        (
            "04-05",
            "International transport (bunkers)",
            "04-05 International transport (bunkers)",
        ),
        ("04", "International marine bunkers", "04 International marine bunkers"),
        ("05", "International aviation bunkers", "05 International aviation bunkers"),
    ]:
        for source_system, scenario, value in [
            ("ESTO", "historical", -4.0),
            ("LEAP", "Target", -4.5),
            ("NINTH", "Target", -4.2),
        ]:
            bunker_rows.append({
                "comparison_scope": "leap_vs_esto_vs_ninth",
                "source_system": source_system,
                "economy": "20_USA",
                "scenario": scenario,
                "year": 2024,
                "common_flow_code": flow_code,
                "common_flow_name": flow_name,
                "common_flow_label": flow_label,
                "common_product_code": "07.05",
                "common_product_name": "Kerosene type jet fuel",
                "common_product_label": "07.05 Kerosene type jet fuel",
                "value": value,
            })
    rows = pd.concat([rows, pd.DataFrame(bunker_rows)], ignore_index=True, sort=False)
    df = apply_sign_semantics(rows, template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    manifest = render_dashboard(main_df, template, series_config, layout, scope_df=df)

    supply_flows = set(
        manifest.loc[manifest["page_key"].eq("supply"), "common_flow_label"]
    )
    assert "04-05 International transport (bunkers)" in supply_flows
    assert "04 International marine bunkers" not in supply_flows
    assert "05 International aviation bunkers" not in supply_flows

    supply_html = (layout["dashboards"] / "supply.html").read_text(encoding="utf-8")
    assert (
        "cannot be viewed separately until the placeholder demand sector is replaced"
        in supply_html
    )


def test_common_esto_dashboard_switcher_uses_current_dashboard_label(tmp_path: Path) -> None:
    template = _load_template()
    series_config = _load_series_config()
    df = apply_sign_semantics(_build_common_esto_rows(), template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "01AUS", clear_existing=True)
    render_dashboard(main_df, template, series_config, layout, scope_df=df)

    html = (layout["dashboards"] / "transport.html").read_text(encoding="utf-8")
    assert "<strong>Australia</strong>" in html
    assert '<option value="transport.html" selected>Australia</option>' in html
    assert '../../20USA/dashboards/transport.html' in html
    assert ".dashboard-grid.overview-grid" in html

    bundle = json.loads(
        (layout["chart_bundles"] / "transport__charts.json").read_text(encoding="utf-8")
    )
    overview_figure = next(
        figure
        for chart_key, figure in bundle["charts"].items()
        if chart_key.startswith("chart__area__")
    )
    assert overview_figure["layout"]["legend"]["y"] == -0.20
    assert overview_figure["layout"]["margin"]["b"] == 160


def test_common_esto_dashboard_shows_updated_label(tmp_path: Path) -> None:
    template = _load_template()
    series_config = _load_series_config()
    df = apply_sign_semantics(_build_common_esto_rows(), template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    render_dashboard(
        main_df,
        template,
        series_config,
        layout,
        scope_df=df,
        dashboard_updated_label="2026-07-10 14:30 JST",
    )

    transport_html = (layout["dashboards"] / "transport.html").read_text(encoding="utf-8")
    index_html = (layout["dashboards"] / "index.html").read_text(encoding="utf-8")
    assert "Economy: <strong>United States</strong>" in transport_html
    assert "Updated: 2026-07-10 14:30 JST" in transport_html
    assert "Updated: 2026-07-10 14:30 JST" in index_html


def test_common_esto_dashboard_writes_page_aware_guides(tmp_path: Path) -> None:
    template = _load_template()
    series_config = _load_series_config()
    df = apply_sign_semantics(_build_common_esto_rows(), template["sign_semantics"])
    main_df = df[df["comparison_scope"] == "leap_vs_esto_vs_ninth"].copy()

    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    render_dashboard(main_df, template, series_config, layout, scope_df=df)

    transport_html = (layout["dashboards"] / "transport.html").read_text(encoding="utf-8")
    index_html = (layout["dashboards"] / "index.html").read_text(encoding="utf-8")

    for html in (transport_html, index_html):
        assert 'id="dashboard-guide-launch"' in html
        assert 'id="dashboard-guide-dialog"' in html
        assert 'class="dashboard-guide-backdrop"' in html
        assert "dashboard-guide-highlight" in html

    assert "Use Transport to review road and non-road energy demand" in transport_html
    assert "Choose what you are viewing" in transport_html
    assert "How common categories make comparison possible" in transport_html
    assert 'data-guide-id="page-navigation"' in transport_html
    assert 'data-guide-id="chart-card"' in transport_html
    assert 'data-guide-id="sort-controls"' not in transport_html
    assert "Largest difference" not in transport_html
    assert "Choose where to begin" in index_html
    assert 'data-guide-id="page-list"' in index_html
    assert "Compare projection scenarios" not in index_html


def _write_multi_scope_wide_file(path: Path) -> None:
    """A wide file where 'ESTO historical' is identical across two scopes."""
    rows = []
    for scope in ["esto_leap", "esto_leap_ninth"]:
        rows.append(
            {
                "comparison_scope": scope,
                "economy": "20_USA",
                "scenario": "ESTO ESTO historical",
                "product": "08.01 Natural gas",
                "flow": "01 Production",
                "is_subtotal": False,
                "2022": 35785.0,
            }
        )
    # NINTH exists only in the 3-way scope.
    rows.append(
        {
            "comparison_scope": "esto_leap_ninth",
            "economy": "20_USA",
            "scenario": "NINTH NINTH reference",
            "product": "08.01 Natural gas",
            "flow": "01 Production",
            "is_subtotal": False,
            "2022": 35785.0,
        }
    )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_wide_loader_selects_single_scope_without_double_counting(tmp_path: Path) -> None:
    wide_path = tmp_path / "wide.csv"
    _write_multi_scope_wide_file(wide_path)

    df = load_common_esto_data(wide_path)  # defaults to the 3-way scope

    esto_ng = df[(df["source_system"] == "ESTO") & (df["year"] == 2022)]
    assert len(esto_ng) == 1, "ESTO historical must not be duplicated across scopes"
    assert esto_ng["value"].iloc[0] == 35785.0
    # NINTH is unique to esto_leap_ninth and must survive the selection.
    assert (df["source_system"] == "NINTH").any()


def test_wide_loader_can_select_alternate_scope(tmp_path: Path) -> None:
    wide_path = tmp_path / "wide.csv"
    _write_multi_scope_wide_file(wide_path)

    df = load_common_esto_data(wide_path, wide_file_scope="esto_leap")

    assert DEFAULT_WIDE_FILE_SCOPE == "esto_leap_ninth"
    # esto_leap has no NINTH rows.
    assert not (df["source_system"] == "NINTH").any()
    assert len(df[df["source_system"] == "ESTO"]) == 1


def test_wide_loader_preserves_numeric_looking_flow_and_product_codes(tmp_path: Path) -> None:
    wide_path = tmp_path / "wide_numeric_codes.csv"
    pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth",
            "economy": "02_BD",
            "scenario": "ESTO historical",
            "product": "08.02",
            "flow": "09.01",
            "2022": 12.5,
        }
    ]).to_csv(wide_path, index=False)

    loaded = load_common_esto_data(wide_path)
    row = loaded.iloc[0]

    assert row["common_product_code"] == "08.02"
    assert row["common_product_label"] == "08.02"
    assert row["common_flow_code"] == "09.01"
    assert row["common_flow_label"] == "09.01"
    assert row["year"] == 2022
    assert row["value"] == 12.5


def test_long_loader_preserves_identifier_code_and_label_strings(tmp_path: Path) -> None:
    long_path = tmp_path / "long_numeric_codes.csv"
    pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth",
            "source_system": "ESTO",
            "economy": "02_BD",
            "scenario": "historical",
            "year": 2022,
            "common_flow_code": "09.01",
            "common_flow_name": "",
            "common_flow_label": "09.01",
            "common_product_code": "08.02",
            "common_product_name": "",
            "common_product_label": "08.02",
            "common_row_id": "000123",
            "is_exact_row": True,
            "requires_rollup": False,
            "value": 12.5,
        }
    ]).to_csv(long_path, index=False)

    loaded = load_common_esto_data(long_path)
    row = loaded.iloc[0]

    assert row["common_row_id"] == "000123"
    assert row["common_product_code"] == "08.02"
    assert row["common_product_label"] == "08.02"
    assert row["common_flow_code"] == "09.01"
    assert row["common_flow_label"] == "09.01"
    assert row["year"] == 2022
    assert row["value"] == 12.5
    assert bool(row["is_exact_row"])
    assert not bool(row["requires_rollup"])


def test_long_parquet_loader_handles_categorical_nulls(tmp_path: Path) -> None:
    long_path = tmp_path / "long_categorical.parquet"
    frame = pd.DataFrame([
        {
            "comparison_scope": "esto_extended_leap",
            "source_system": "LEAP",
            "economy": "01_AUS",
            "scenario": "Target",
            "year": 2022,
            "common_flow_code": "15.02.01",
            "common_flow_name": "Freight road",
            "common_flow_label": "15.02.01 Freight road",
            "common_product_code": "17",
            "common_product_name": "Electricity",
            "common_product_label": "17 Electricity",
            "common_row_id": "road-freight-electricity",
            "is_exact_row": True,
            "requires_rollup": False,
            "value": 1.0,
        }
    ])
    frame["scenario"] = pd.Categorical(frame["scenario"], categories=["Target", "Reference"])
    frame["common_flow_name"] = pd.Categorical(
        [None], categories=["Freight road"]
    )
    frame.to_parquet(long_path, index=False)

    loaded = load_common_esto_data(long_path)

    assert loaded.iloc[0]["scenario"] == "Target"
    assert loaded.iloc[0]["common_flow_name"] == ""
    assert loaded.iloc[0]["value"] == 1.0


def test_common_esto_scope_filter_rejects_unavailable_scope() -> None:
    df = pd.DataFrame(
        [
            {"economy": "20_USA", "comparison_scope": "esto_leap_ninth"},
        ]
    )

    try:
        filter_common_esto_data(df, comparison_scope="missing_scope", economy="20_USA")
    except ValueError as exc:
        assert "missing_scope" in str(exc)
        assert "esto_leap_ninth" in str(exc)
    else:
        raise AssertionError("Unavailable comparison scopes must raise ValueError")


def test_common_esto_scope_filter_rejects_missing_scope_column() -> None:
    df = pd.DataFrame([{"economy": "20_USA"}])

    try:
        filter_common_esto_data(df, comparison_scope="esto_leap_ninth", economy="20_USA")
    except ValueError as exc:
        assert "comparison_scope" in str(exc)
    else:
        raise AssertionError("Missing comparison_scope must raise ValueError")


def test_weekly_common_esto_sample_fixture_is_present() -> None:
    fixture_dir = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard"
    assert (fixture_dir / "common_esto_comparison_data_sample.csv").exists()
    assert (fixture_dir / "common_esto_rows.csv").exists()
    fixture = pd.read_csv(fixture_dir / "common_esto_comparison_data_sample.csv", low_memory=False)
    assert len(fixture) < 50_000
    assert fixture["comparison_scope"].nunique() >= 2
    assert fixture["common_flow_label"].nunique() >= 50
    assert fixture["common_product_label"].nunique() >= 50


def test_publishing_copies_browser_bundles_but_not_qa_json(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    docs_root = tmp_path / "docs"
    layout = build_output_layout(output_root, "20USA")
    (layout["dashboards"] / "index.html").write_text("html", encoding="utf-8")
    (layout["chart_bundles"] / "transport__charts.js").write_text("js", encoding="utf-8")
    (layout["chart_bundles"] / "transport__charts.json").write_text("json", encoding="utf-8")
    stale_json = docs_root / "20USA" / "chart_bundles" / "stale__charts.json"
    stale_json.parent.mkdir(parents=True, exist_ok=True)
    stale_json.write_text("stale", encoding="utf-8")

    counts = publish_to_docs(layout, docs_root)

    assert counts["chart_bundles"] == 1
    assert (docs_root / "20USA" / "dashboards" / "index.html").exists()
    assert (docs_root / "20USA" / "chart_bundles" / "transport__charts.js").exists()
    assert not (docs_root / "20USA" / "chart_bundles" / "transport__charts.json").exists()
    assert not stale_json.exists()


def test_code_colors_resolve_by_code_not_display_name() -> None:
    # A rolled-up row uses its mapping-owned components' OKLab average rather
    # than borrowing the first component's colour or display name.
    colors = load_code_colors()
    assert color_for_code("01.02-01.04 Other bituminous coal", "product") == colors["common"]["product"]["01.02-01.04"]
    assert color_for_code("01.02-01.04 Other bituminous coal", "product") != color_for_code("01.02", "product")
    assert color_for_code("19.01,19.03 Heat output in PJ", "flow") == colors["common"]["flow"]["19.01,19.03"]
    # A renamed label with the same code keeps its colour.
    assert color_for_code("07.99 Anything At All", "product") == color_for_code("07.99 PetProd nonspecified", "product")


def test_code_colors_walk_up_to_the_nearest_mapped_ancestor() -> None:
    # An unmapped sub-code inherits its family colour rather than falling through.
    assert color_for_code("10.99 Some New Hydro Split", "product") == color_for_code("10 Hydro", "product")
    assert color_for_code("14.03.99 New Subsector", "flow") == color_for_code("14.03 Manufacturing", "flow")


def test_code_colors_keep_product_and_flow_namespaces_separate() -> None:
    # Product 16 is Others; flow 16.01 is Commercial and public services.
    assert color_for_code("16 Others", "product") != color_for_code("16.01 Commercial and public services", "flow")


def test_code_colors_return_empty_for_unmapped_and_uncoded_labels() -> None:
    assert color_for_code("ESTO Historical total", "product") == ""
    assert color_for_code("", "product") == ""


def test_archived_plotting_catalogue_is_used_for_new_label_fallbacks() -> None:
    assert color_for_plotting_name("electricity", "product") == "#FFD757"
    assert color_for_code("99 Electricity", "product") == "#FFD757"
    assert color_for_code("99 Power_input", "flow") == "#00B9CC"
    assert color_for_plotting_name("Coal gasification production", "flow") == "#000001"


def test_archived_plotting_catalogue_records_mapping_coverage() -> None:
    colors_path = REPO_ROOT / "config" / "common_esto_dashboard" / "code_colors.json"
    colors = json.loads(colors_path.read_text(encoding="utf-8"))
    assert colors["_color_source"].endswith("master_config 9th visualisation.xlsx, colors sheet")
    assert colors["_plotting_color_coverage"]["product"]["mapped"] > 0
    assert colors["_plotting_color_coverage"]["flow"]["mapped"] > 0
    assert colors["_plotting_color_coverage"]["capacity"]["mapped"] > 0
    assert colors["_common_color_method"].startswith("equal-weight OKLab")
    assert not Path(colors["_common_color_source"]).is_absolute()


def test_every_common_esto_label_in_the_sample_resolves_to_a_colour() -> None:
    fixture = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard" / "common_esto_comparison_data_sample.csv"
    df = pd.read_csv(fixture, low_memory=False)
    for axis, column in (("product", "common_product_label"), ("flow", "common_flow_label")):
        if column not in df.columns:
            continue
        unmapped = sorted({str(v) for v in df[column].dropna().unique() if not color_for_code(v, axis)})
        assert not unmapped, f"unmapped {axis} labels: {unmapped}"


def test_stacked_traces_take_their_code_colour_and_totals_keep_theirs() -> None:
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[2020], y=[1.0], stackgroup="s", name="17 Electricity"))
    fig.add_trace(go.Scatter(x=[2020], y=[2.0], mode="lines+markers", name="ESTO Historical total"))
    apply_chart_chrome(fig, base_year=None, code_axis="product")

    assert fig.data[0].fillcolor == color_for_code("17 Electricity", "product")
    # The total line must keep its stable source colour, not a code colour.
    assert fig.data[1].line.color == "#0072B2"


def test_comparison_reference_and_target_lines_use_editable_series_colours(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    config_path.write_text(
        json.dumps({
            "plotting": {
                "series": {
                    "LEAP Reference": "#112233",
                    "LEAP Target": "#445566",
                }
            }
        }),
        encoding="utf-8",
    )
    set_code_colors_path(config_path)
    try:
        fig = go.Figure([
            go.Scatter(x=[2030], y=[1.0], mode="lines", name="LEAP Reference total"),
            go.Scatter(x=[2030], y=[2.0], mode="lines", name="LEAP Target total"),
        ])
        apply_chart_chrome(fig, base_year=None)
        assert fig.data[0].line.color == "#112233"
        assert fig.data[1].line.color == "#445566"
    finally:
        set_code_colors_path(None)


def test_shared_chart_chrome_keeps_legend_for_one_trace() -> None:
    fig = go.Figure(
        [go.Scatter(x=[2020, 2021], y=[1.0, 2.0], name="ESTO Historical total")]
    )

    apply_chart_chrome(fig, base_year=None)

    assert fig.layout.showlegend is True
    assert fig.data[0].name == "ESTO Historical total"


def test_signed_stack_trace_crossing_zero_uses_both_stacks_and_one_legend_item() -> None:
    fig = go.Figure()

    trace_count = _add_signed_stack_traces(
        fig=fig,
        x_values=pd.Series([2020, 2021, 2022]),
        y_values=pd.Series([10.0, -4.0, 5.0]),
        stackgroup_prefix="scenario_tgt",
        trace_name="02.01-02.08 Coal products",
        visible=True,
        hovertemplate="%{y}",
    )

    assert trace_count == 2
    assert [trace.stackgroup for trace in fig.data] == [
        "scenario_tgt_pos",
        "scenario_tgt_neg",
    ]
    assert [list(trace.y) for trace in fig.data] == [
        [10.0, 0.0, 5.0],
        [0.0, -4.0, 0.0],
    ]
    assert [trace.showlegend for trace in fig.data] == [True, False]
    assert fig.data[0].legendgroup == fig.data[1].legendgroup


@pytest.mark.parametrize(
    ("group_col", "historical_categories", "projected_categories"),
    [
        (
            "common_flow_label",
            [("09.07 Oil refineries", "06.01 Crude oil", -80.0),
             ("09.07 Oil refineries", "07.01 Motor gasoline", 100.0)],
            [("09.07 Oil refineries", "06.01 Crude oil", -90.0),
             ("09.07 Oil refineries", "07.01 Motor gasoline", 120.0)],
        ),
        (
            "common_product_label",
            [("09.01 Electricity plants", "08.01 Natural gas", -80.0),
             ("09.06 Gas works plants", "08.01 Natural gas", 100.0)],
            [("09.01 Electricity plants", "08.01 Natural gas", -90.0),
             ("09.06 Gas works plants", "08.01 Natural gas", 120.0)],
        ),
    ],
)
def test_area_chart_preserves_gross_signs_before_category_aggregation(
    group_col: str,
    historical_categories: list[tuple[str, str, float]],
    projected_categories: list[tuple[str, str, float]],
) -> None:
    rows = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "economy": "20_USA",
                "source_system": source_system,
                "scenario": scenario,
                "year": year,
                "common_flow_code": flow_label.split()[0],
                "common_flow_label": flow_label,
                "common_product_code": product_label.split()[0],
                "common_product_label": product_label,
                "is_non_expanding_rollup": False,
                "value": value,
            }
            for source_system, scenario, year, categories in [
                ("ESTO", "historical", 2022, historical_categories),
                ("LEAP", "Target", 2023, projected_categories),
            ]
            for flow_label, product_label, value in categories
        ]
    )

    figure = build_area_chart(
        rows,
        {
            "aggregate_flow_label": "Transformation",
            "source_flow_labels": sorted(rows["common_flow_label"].unique()),
            "source_flow_labels_by_system": {},
        },
        {"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
        {
            "chart_generation": {
                "comparison_source_system": "ESTO",
                "base_year": 2022,
                "primary_area_source_system": "LEAP",
                "primary_area_scenario": "Target",
            }
        },
        group_col=group_col,
    )

    visible_areas = [
        trace for trace in figure.data
        if trace.stackgroup and trace.visible is True
    ]
    assert [trace.stackgroup for trace in visible_areas] == [
        "scenario_tgt_pos",
        "scenario_tgt_neg",
    ]
    assert [list(trace.y) for trace in visible_areas] == [
        [100.0, 120.0],
        [-80.0, -90.0],
    ]
    assert [trace.showlegend for trace in visible_areas] == [True, False]


def test_supply_demand_comparison_lines_keep_stable_source_colour() -> None:
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[2020], y=[1.0], stackgroup="s", name="17 Electricity"))
    fig.add_trace(go.Scatter(x=[2020], y=[2.0], mode="lines", name="LEAP Target supply (01–03)"))
    fig.add_trace(go.Scatter(x=[2020], y=[3.0], mode="lines", name="9th Target supply (01–03)"))
    fig.add_trace(go.Scatter(x=[2020], y=[4.0], mode="lines+markers", name="ESTO Historical (TFC)"))
    apply_chart_chrome(fig, base_year=None, code_axis="product")

    # Comparison lines named with a suffix other than "total" (supply/(TFC)/...)
    # must still resolve to their source's stable colour, not Plotly's default
    # auto-colourway, so they stay visually distinct on crowded charts.
    assert fig.data[1].line.color == "#D55E00"  # LEAP
    assert fig.data[2].line.color == "#009E73"  # 9th / NINTH
    assert fig.data[3].line.color == "#0072B2"  # ESTO
    assert len({fig.data[1].line.color, fig.data[2].line.color, fig.data[3].line.color}) == 3


def test_stacked_trace_keeps_code_colour_even_if_named_like_a_source() -> None:
    import plotly.graph_objects as go

    # Guards the invariant the source-substring match relies on: a stacked
    # trace takes its colour from the code map, never from _TOTAL_SERIES_COLORS,
    # even if a future label were to contain a source name.
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[2020], y=[1.0], stackgroup="s", name="17 Electricity"))
    fig.add_trace(go.Scatter(x=[2020], y=[1.0], stackgroup="s", name="99 LEAP-like label"))
    apply_chart_chrome(fig, base_year=None, code_axis="product")

    assert fig.data[1].line.color != "#D55E00"


def test_total_demand_lines_prefer_declared_aggregate_for_every_source() -> None:
    demand = pd.DataFrame([
        {"source_system": "NINTH", "scenario": "target", "year": 2022, "value": 60.0},
        {"source_system": "NINTH", "scenario": "target", "year": 2022, "value": 40.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2022, "value": 5.0},
    ])
    overview = pd.DataFrame([
        {"source_system": "NINTH", "scenario": "target", "year": 2022, "common_flow_code": "12", "value": 50.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2022, "common_flow_code": "12", "value": 75.0},
    ])

    selected = _select_total_rows_by_source(demand, overview, flow_code="12")
    totals = selected.groupby("source_system")["value"].sum().to_dict()

    assert totals == {"LEAP": 75.0, "NINTH": 50.0}


def test_total_demand_lines_fall_back_to_visible_detail_without_aggregate() -> None:
    demand = pd.DataFrame([
        {"source_system": "ESTO", "scenario": "historical", "year": 2022, "value": 60.0},
        {"source_system": "ESTO", "scenario": "historical", "year": 2022, "value": 40.0},
    ])
    overview = pd.DataFrame(columns=[
        "source_system", "scenario", "year", "common_flow_code", "value"
    ])

    selected = _select_total_rows_by_source(demand, overview, flow_code="12")

    assert selected["value"].sum() == 100.0


def test_supply_stack_keeps_supply_totals_and_excludes_demand_comparison_lines() -> None:
    supply = pd.DataFrame([
        {
            "source_system": "LEAP", "scenario": "Target", "year": 2039,
            "common_flow_label": "01 Production", "value": 150.0,
        },
    ])
    fig = _build_supply_stack_chart(
        supply,
        series_labels=_load_series_config()["series_labels"],
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_flow_label",
        chart_title="Energy supply by balance component",
    )
    traces = {trace.name: list(trace.y) for trace in fig.data}

    assert traces["LEAP Target supply total"] == [150.0]
    assert not any("demand" in name.casefold() for name in traces)


def test_transformation_stack_preserves_gross_inputs_and_outputs() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2030,
            "common_flow_label": "09 Total transformation sector",
            "value": value,
        }
        for value in [10.0, -8.0]
    ] + [{
        "source_system": "LEAP",
        "scenario": "Target",
        "year": 2030,
        "common_flow_label": "08 Transfers",
        "value": 1.0,
    }])

    figure = _build_supply_stack_chart(
        rows,
        series_labels={},
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_flow_label",
        chart_title="Transformation by flow",
        base_year=2022,
        total_line_suffix="net total",
        composition_subject="flow",
        stack_prefix="transformation",
        preserve_gross_signs=True,
    )

    area_traces = [
        trace
        for trace in figure.data
        if trace.stackgroup and trace.name == "09 Total transformation sector"
    ]
    assert sorted(float(trace.y[0]) for trace in area_traces) == [-8.0, 10.0]
    net_trace = next(trace for trace in figure.data if trace.name == "LEAP|Target net total")
    assert list(net_trace.y) == [3.0]


def test_transformation_leaf_stack_uses_authoritative_boundary_total() -> None:
    leaf_rows = pd.DataFrame([{
        "source_system": "LEAP", "scenario": "Target", "year": 2030,
        "common_flow_label": "09.07 Oil refineries", "value": -8.0,
    }])
    boundary_rows = pd.DataFrame([{
        "source_system": "LEAP", "scenario": "Target", "year": 2030,
        "common_flow_label": "09 Total transformation sector", "value": 3.0,
    }])

    figure = _build_supply_stack_chart(
        leaf_rows,
        series_labels={},
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_flow_label",
        chart_title="Transformation by flow",
        total_line_suffix="net total",
        composition_subject="flow",
        stack_prefix="transformation",
        preserve_gross_signs=True,
        total_detail_df=boundary_rows,
    )

    net_trace = next(trace for trace in figure.data if trace.name == "LEAP|Target net total")
    assert list(net_trace.y) == [3.0]


def test_lng_coverage_note_follows_090602_data_across_chart_shapes() -> None:
    rows = pd.DataFrame([
        {
            "source_system": source_system,
            "scenario": scenario,
            "year": year,
            "common_flow_code": "09.06.02.01",
            "common_flow_label": "09.06.02.01 Liquefaction",
            "common_product_code": "08.01",
            "common_product_label": "08.01 Natural gas",
            "value": value,
        }
        for source_system, scenario, year, value in [
            ("ESTO", "historical", 2022, -10.0),
            ("LEAP", "Target", 2023, -500.0),
        ]
    ])

    figures = [
        _build_supply_stack_chart(
            rows,
            series_labels={},
            primary_source="LEAP",
            primary_scenario="Target",
            group_col="common_flow_label",
            chart_title="Transformation by flow",
            base_year=2022,
        ),
        _build_supply_stack_chart(
            rows,
            series_labels={},
            primary_source="LEAP",
            primary_scenario="Target",
            group_col="common_product_label",
            chart_title="Transformation by product",
            base_year=2022,
        ),
        build_product_chart(
            rows,
            "09.06.02.01 Liquefaction",
            "08.01 Natural gas",
            {},
            primary_source="LEAP",
            primary_scenario="Target",
            base_year=2022,
        ),
    ]

    for figure in figures:
        note = figure.layout.meta["stacked_area_note"]
        assert "ESTO historical data do not contain all LNG activity" in note
        assert "does not indicate a dashboard or mapping error;" in note


def test_lng_coverage_note_is_absent_without_090602_data() -> None:
    rows = pd.DataFrame([{
        "source_system": "LEAP",
        "scenario": "Target",
        "year": 2030,
        "common_flow_code": "09.07",
        "common_flow_label": "09.07 Oil refineries",
        "common_product_label": "08.01 Natural gas",
        "value": -10.0,
    }])

    figure = _build_supply_stack_chart(
        rows,
        series_labels={},
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_flow_label",
        chart_title="Transformation by flow",
    )

    assert "LNG activity" not in figure.layout.meta["stacked_area_note"]


def test_lng_coverage_note_can_follow_detailed_context_behind_broad_frontier() -> None:
    broad_rows = pd.DataFrame([{
        "source_system": "LEAP",
        "scenario": "Target",
        "year": 2030,
        "common_flow_code": "09",
        "common_flow_label": "09 Total transformation sector",
        "common_product_label": "08.01 Natural gas",
        "value": -500.0,
    }])
    detailed_context = broad_rows.assign(
        common_flow_code="09.06.02.01",
        common_flow_label="09.06.02.01 Liquefaction",
    )

    figure = _build_supply_stack_chart(
        broad_rows,
        series_labels={},
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_product_label",
        chart_title="Transformation by product",
        note_context_df=detailed_context,
    )

    assert "ESTO historical data do not contain all LNG activity" in (
        figure.layout.meta["stacked_area_note"]
    )


def test_aggregate_only_leap_demand_warns_about_tfec_non_energy() -> None:
    note = aggregate_only_tfec_note({"NINTH"}, "LEAP")

    assert "aggregate-only" in note
    assert "cannot remove non-energy use" in note
    assert aggregate_only_tfec_note({"LEAP"}, "LEAP") == ""


def test_aggregate_flow_rows_drop_nested_refinery_categories_per_source() -> None:
    rows = pd.DataFrame([
        {"common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries", "source_system": "ESTO", "scenario": "historical"},
        {"common_flow_code": "10.01.11", "common_flow_label": "10.01.11 Oil refineries", "source_system": "ESTO", "scenario": "historical"},
        {"common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries (including own use)", "source_system": "ESTO", "scenario": "historical"},
        {"common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries", "source_system": "LEAP", "scenario": "Target"},
    ])

    filtered = _non_overlapping_flow_rows(rows)

    assert set(filtered.loc[filtered["source_system"] == "ESTO", "common_flow_label"]) == {
        "09.07 Oil refineries (including own use)"
    }
    assert set(filtered.loc[filtered["source_system"] == "LEAP", "common_flow_label"]) == {
        "09.07 Oil refineries (including own use)"
    }


def test_refining_page_keeps_only_inclusive_comparison_boundary() -> None:
    rows = pd.DataFrame([
        {"common_flow_code": "09.07", "common_flow_label": "09.07 Oil refineries"},
        {
            "common_flow_code": "09.07",
            "common_flow_label": "09.07 Oil refineries (including own use)",
        },
    ])

    filtered = drop_excluded_flow_rows(
        rows,
        [],
        ["09.07 Oil refineries"],
    )

    assert filtered["common_flow_label"].tolist() == [
        "09.07 Oil refineries (including own use)"
    ]


def test_other_transformation_page_uses_inclusive_boundaries_and_residual_sections() -> None:
    rows = pd.DataFrame([
        {
            "common_flow_code": "09.06.01",
            "common_flow_label": "09.06.01 Gas works plants",
            "component_flow_code": "09.06.01",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.06.01",
            "common_flow_label": "09.06.01 Gas works plants (including own use)",
            "component_flow_code": "09.06.01",
            "non_expanding_contributor_inputs": (
                "ESTO: 09.06.01 Gas works plants|ESTO: 10.01.02 Gas works plants"
            ),
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.02",
            "common_flow_label": "10.01.02 Gas works plants",
            "component_flow_code": "10.01.02",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.08.01",
            "common_flow_label": "09.08.01 Coke ovens",
            "component_flow_code": "09.08.01",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.08.01",
            "common_flow_label": "09.08.01 Coke ovens (including own use)",
            "component_flow_code": "09.08.01",
            "non_expanding_contributor_inputs": (
                "ESTO: 09.08.01 Coke ovens|ESTO: 10.01.05 Coke ovens"
            ),
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.05",
            "common_flow_label": "10.01.05 Coke ovens",
            "component_flow_code": "10.01.05",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.08.02",
            "common_flow_label": "09.08.02 Blast furnaces",
            "component_flow_code": "09.08.02",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.08.02",
            "common_flow_label": "09.08.02 Blast furnaces (including own use)",
            "component_flow_code": "09.08.02",
            "non_expanding_contributor_inputs": (
                "ESTO: 09.08.02 Blast furnaces|ESTO: 10.01.07 Blast furnaces"
            ),
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.07",
            "common_flow_label": "10.01.07 Blast furnaces",
            "component_flow_code": "10.01.07",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "09.13.03",
            "common_flow_label": "09.13.03 SMR w CCS",
            "component_flow_code": "09.13.03",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.06",
            "common_flow_label": "10.01.06 Coal mines",
            "component_flow_code": "10.01.06",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.02",
            "common_flow_label": "10.02 Transmission and distribution losses",
            "component_flow_code": "10.02",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "08",
            "common_flow_label": "08 Transfers",
            "component_flow_code": "08",
            "_section_label": "Transfers",
        },
    ])
    config = _load_template()["other_transformation_page"]

    prepared = prepare_other_transformation_page_rows(rows, rows, config)

    assert set(prepared["common_flow_label"]) == {
        "09.06.01 Gas works plants (including own use)",
        "09.08.01 Coke ovens (including own use)",
        "09.08.02 Blast furnaces (including own use)",
        "09.13.03 SMR w CCS (including own use)",
        "10.01.06 Coal mines",
        "10.02 Transmission and distribution losses",
        "08 Transfers",
    }
    sections = dict(zip(prepared["common_flow_code"], prepared["_section_label"]))
    assert sections["09.13.03"] == "Other transformation (including own use)"
    assert sections["10.01.06"] == "Other energy-sector own use"
    assert sections["10.02"] == "Transmission and distribution losses"
    assert sections["08"] == "Transfers"


def test_other_transformation_hides_process_linked_own_use_without_metadata() -> None:
    rows = pd.DataFrame([
        {
            "common_flow_code": "10.01.03",
            "common_flow_label": "10.01.03 Liquefaction/regasification plants",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.05",
            "common_flow_label": "10.01.05 Coke ovens",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.06",
            "common_flow_label": "10.01.06 Coal mines",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.12",
            "common_flow_label": "10.01.12 Oil and gas extraction",
            "_section_label": "Other transformation",
        },
        {
            "common_flow_code": "10.01.17",
            "common_flow_label": "10.01.17 Non-specified own uses",
            "_section_label": "Other transformation",
        },
    ])

    prepared = prepare_other_transformation_page_rows(
        rows,
        rows,
        _load_template()["other_transformation_page"],
    )

    assert prepared["common_flow_code"].tolist() == [
        "10.01.06",
        "10.01.12",
        "10.01.17",
    ]


def test_transformation_comparison_frontier_survives_other_source_inclusive_row() -> None:
    rows = pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth",
            "source_system": "ESTO",
            "economy": "01AUS",
            "scenario": "historical",
            "year": 2022,
            "common_flow_code": "09.06.02",
            "common_flow_label": (
                "09.06.02 Liquefaction/regasification plants (including own use)"
            ),
            "common_product_code": "08.01",
            "common_product_label": "08.01 Natural gas",
            "is_non_expanding_rollup": True,
            "value": -10.0,
        },
        {
            "comparison_scope": "esto_leap_ninth",
            "source_system": "LEAP",
            "economy": "01AUS",
            "scenario": "Reference",
            "year": 2023,
            "common_flow_code": "09.06.02",
            "common_flow_label": "09.06.02 Liquefaction/regasification plants",
            "common_product_code": "08.01",
            "common_product_label": "08.01 Natural gas",
            "is_non_expanding_rollup": True,
            "value": -500.0,
        },
        {
            "comparison_scope": "esto_leap_ninth",
            "source_system": "LEAP",
            "economy": "01AUS",
            "scenario": "Reference",
            "year": 2023,
            "common_flow_code": "09.06.02.01",
            "common_flow_label": "09.06.02.01 Liquefaction",
            "common_product_code": "08.01",
            "common_product_label": "08.01 Natural gas",
            "is_non_expanding_rollup": False,
            "value": -500.0,
        },
    ])

    selected = select_transformation_overview_rows(
        rows,
        {"flow_code_prefixes": ["09", "08", "10.01", "10.02"]},
        {"enabled": True, "append_inclusive_transformation_label": True},
        prefer_leaf_flows=True,
    )

    leap_rows = selected[
        selected["source_system"].eq("LEAP")
        & selected["scenario"].eq("Reference")
    ]
    assert set(leap_rows["common_flow_code"]) == {"09.06.02"}
    assert leap_rows.iloc[0]["common_flow_label"] == (
        "09.06.02 Liquefaction/regasification plants (including own use)"
    )
    assert leap_rows["value"].sum() == -500.0


def test_component_metadata_includes_upstream_rollup_contributors(tmp_path: Path) -> None:
    common_rows_path = tmp_path / "common_esto_rows.csv"
    pd.DataFrame([
        {
            "comparison_scope": "esto_leap",
            "common_row_id": "inclusive_coke_ovens",
            "common_flow_label": "09.08.01 Coke ovens (including own use)",
            "common_product_label": "17 Electricity",
            "component_flow_code": "09.08.01",
            "non_expanding_rollup_id": "nonexp_coke_ovens",
        }
    ]).to_csv(common_rows_path, index=False)
    pd.DataFrame([
        {
            "comparison_scope": "esto_leap",
            "non_expanding_rollup_id": "nonexp_coke_ovens",
            "contributor_inputs": (
                "ESTO: 09.08.01 Coke ovens|ESTO: 10.01.05 Coke ovens"
            ),
        }
    ]).to_csv(
        tmp_path / "qa_common_esto_non_expanding_rollups.csv",
        index=False,
    )
    facts = pd.DataFrame([
        {
            "comparison_scope": "esto_leap",
            "common_row_id": "inclusive_coke_ovens",
        }
    ])

    enriched = enrich_with_component_metadata(facts, common_rows_path)

    assert enriched.iloc[0]["non_expanding_contributor_inputs"] == (
        "ESTO: 09.08.01 Coke ovens|ESTO: 10.01.05 Coke ovens"
    )


def test_pump_storage_own_use_routes_to_power() -> None:
    template = _load_template()
    rows = pd.DataFrame([
        {
            "common_flow_code": "10.01.13",
            "common_flow_label": "10.01.13 Pump storage plants",
        }
    ])

    routed = assign_pages(
        rows,
        template["sector_pages"],
        template["routing_special_cases"],
    )

    assert routed.iloc[0]["_page_key"] == "power"


def test_product_chart_omits_optional_difference_traces() -> None:
    chart_df = pd.DataFrame([
        {
            "source_system": "ESTO",
            "scenario": "historical",
            "year": 2022,
            "value": 10.0,
        },
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2022,
            "value": 12.0,
        },
    ])

    figure = build_product_chart(
        chart_df,
        "01 Production",
        "08.01 Natural gas",
        {},
        base_year=2022,
    )

    assert {str(trace.name) for trace in figure.data} == {
        "ESTO|historical",
        "LEAP|Target",
    }
    assert not any(" minus " in str(trace.name).casefold() for trace in figure.data)


def test_non_expanding_subtotal_is_selected_once_for_dashboard_aggregates() -> None:
    subtotal_value = 30.0
    detail_frontier_value = 10.0 + 20.0
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "source_system": "ESTO",
        "economy": "20_USA",
        "scenario": "historical",
        "year": 2022,
        "common_flow_code": "16.03-16.04",
        "common_flow_label": "16.03-16.04 Agriculture and fishing",
        "common_product_code": "07.07",
        "common_product_label": "07.07 Gas/diesel oil",
        "source_aggregate_group_ids": "rollup_agriculture_gas_diesel",
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "common_row_id": "row_subtotal",
            "is_non_expanding_rollup": True,
            "non_expanding_rollup_id": "nonexp_agriculture_and_fishing",
            "value": subtotal_value,
        },
        {
            **common_values,
            "common_row_id": "row_detail_frontier",
            "is_non_expanding_rollup": False,
            "non_expanding_rollup_id": "",
            "value": detail_frontier_value,
        },
        {
            **common_values,
            "source_system": "NINTH",
            "scenario": "Target",
            "year": 2024,
            "common_row_id": "row_detail_frontier",
            "is_non_expanding_rollup": False,
            "non_expanding_rollup_id": "",
            "value": detail_frontier_value,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert list(selected["common_row_id"]) == ["row_subtotal", "row_detail_frontier"]
    assert selected.groupby("source_system")["value"].sum().to_dict() == {
        "ESTO": 30.0,
        "NINTH": 30.0,
    }

    figure = build_area_chart(
        rows,
        {
            "aggregate_flow_label": "16.03-16.04 Agriculture and fishing",
            "source_flow_labels": ["16.03-16.04 Agriculture and fishing"],
            "source_flow_labels_by_system": {},
        },
        {
            "ESTO|historical": "ESTO historical",
            "NINTH|Target": "NINTH Target",
        },
        {
            "chart_generation": {
                "comparison_source_system": "ESTO",
                "base_year": 2023,
                "primary_area_source_system": "LEAP",
                "primary_area_scenario": "Target",
            }
        },
    )
    total_traces = {
        trace.name: list(trace.y)
        for trace in figure.data
        if str(trace.name).endswith(" total")
    }
    assert total_traces == {
        "ESTO historical total": [30.0],
        "NINTH Target total": [30.0],
    }


def test_non_expanding_frontier_does_not_fall_back_when_a_year_is_exact_zero() -> None:
    common_values = {
        "comparison_scope": "esto_extended_leap_ninth",
        "source_system": "NINTH",
        "economy": "20_USA",
        "scenario": "target",
        "common_flow_code": "09.07",
        "common_product_code": "07.10",
        "source_aggregate_group_ids": "refinery_including_own_use",
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "year": 2023,
            "common_row_id": "refinery_including_own_use",
            "is_non_expanding_rollup": True,
            "value": 1e-13,
        },
        {
            **common_values,
            "year": 2023,
            "common_row_id": "refinery_output",
            "is_non_expanding_rollup": False,
            "value": 637.08,
        },
        {
            **common_values,
            "year": 2027,
            "common_row_id": "refinery_output",
            "is_non_expanding_rollup": False,
            "value": 623.93,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert selected[["year", "common_row_id"]].to_dict("records") == [
        {"year": 2023, "common_row_id": "refinery_including_own_use"},
    ]


def test_area_charts_drop_zero_only_categories_and_keep_historical_only_categories() -> None:
    common = {
        "comparison_scope": "esto_leap_ninth",
        "economy": "20_USA",
        "common_flow_code": "16.02",
        "common_flow_label": "16.02 Residential",
        "is_non_expanding_rollup": False,
    }
    rows = pd.DataFrame([
        {**common, "source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_code": "07.01", "common_product_label": "07.01 Motor gasoline", "value": 10.0},
        {**common, "source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_code": "12.99", "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
        {**common, "source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_code": "07.10", "common_product_label": "07.10 Refinery gas (not liquefied)", "value": 5.0},
        {**common, "source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_code": "07.01", "common_product_label": "07.01 Motor gasoline", "value": 20.0},
        {**common, "source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_code": "12.99", "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
    ])
    figure = build_area_chart(
        rows,
        {
            "aggregate_flow_label": "16.02 Residential",
            "source_flow_labels": ["16.02 Residential"],
            "source_flow_labels_by_system": {},
        },
        {"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
        {"chart_generation": {"comparison_source_system": "ESTO", "base_year": 2022,
                               "primary_area_source_system": "LEAP", "primary_area_scenario": "Target"}},
    )
    area_names = {str(trace.name) for trace in figure.data if trace.stackgroup}
    assert area_names == {"07.01 Motor gasoline", "07.10 Refinery gas (not liquefied)"}
    assert "12.99 Solar nonspecified" not in area_names
    historical_only = next(
        trace for trace in figure.data
        if trace.name == "07.10 Refinery gas (not liquefied)" and trace.visible is True
    )
    assert list(historical_only.x) == [2022]
    esto_total = next(trace for trace in figure.data if trace.name == "ESTO historical total")
    assert list(esto_total.y) == [15.0]


def test_energy_balance_fuel_area_uses_esto_history_on_leap_category_frontier() -> None:
    rows = pd.DataFrame([
        {"source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_label": "07.01 Motor gasoline", "value": 10.0},
        {"source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
        {"source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_label": "07.10 Refinery gas (not liquefied)", "value": 5.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_label": "07.01 Motor gasoline", "value": 20.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
    ])
    figure = _build_td_fuel_chart(
        rows,
        pd.DataFrame(columns=rows.columns),
        {"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
        "LEAP",
        "Target",
        base_year=2022,
    )
    area_names = {str(trace.name) for trace in figure.data if trace.stackgroup}
    assert area_names == {"07.01 Motor gasoline", "07.10 Refinery gas (not liquefied)"}
    motor = next(
        trace
        for trace in figure.data
        if trace.name == "07.01 Motor gasoline" and trace.visible
    )
    assert list(motor.x) == [2022, 2023]
    assert figure.layout.title.text == "Final energy demand by fuel (Domestic TFC)"
    assert not any("supply" in str(trace.name).casefold() for trace in figure.data)


def test_leap_and_ninth_lines_include_available_base_year_values() -> None:
    series_labels = {
        "ESTO|historical": "ESTO Historical",
        "LEAP|Target": "LEAP Target",
        "NINTH|Target": "9th Target",
    }
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "economy": "20_USA",
        "common_flow_code": "16.02",
        "common_flow_label": "16.02 Residential",
        "common_product_code": "17",
        "common_product_label": "17 Electricity",
        "is_non_expanding_rollup": False,
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "source_system": source_system,
            "scenario": scenario,
            "year": year,
            "value": value,
        }
        for source_system, scenario, year, value in [
            ("ESTO", "historical", 2022, 100.0),
            ("LEAP", "Target", 2021, 91.0),
            ("LEAP", "Target", 2022, 105.0),
            ("LEAP", "Target", 2023, 108.0),
            ("NINTH", "Target", 2021, 93.0),
            ("NINTH", "Target", 2022, 103.0),
            ("NINTH", "Target", 2023, 106.0),
        ]
    ])
    area_figure = build_area_chart(
        rows,
        {
            "aggregate_flow_label": "16.02 Residential",
            "source_flow_labels": ["16.02 Residential"],
            "source_flow_labels_by_system": {},
        },
        series_labels,
        {
            "chart_generation": {
                "comparison_source_system": "ESTO",
                "base_year": 2022,
                "primary_area_source_system": "LEAP",
                "primary_area_scenario": "Target",
            }
        },
    )
    area_years = {
        trace.name: list(trace.x)
        for trace in area_figure.data
        if str(trace.name).endswith(" total")
    }

    product_figure = build_product_chart(
        rows,
        "16.02 Residential",
        "17 Electricity",
        series_labels,
        comparison_source="ESTO",
        base_year=2022,
    )
    product_years = {trace.name: list(trace.x) for trace in product_figure.data}

    assert area_years["LEAP Target total"] == [2022, 2023]
    assert area_years["9th Target total"] == [2022, 2023]
    assert product_years["LEAP Target"] == [2022, 2023]
    assert product_years["9th Target"] == [2022, 2023]


def test_non_expanding_frontier_uses_shared_aggregate_id_when_axis_codes_differ() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "ESTO", "scenario": "historical", "year": 2022,
            "common_flow_code": "16.03-16.04", "common_product_code": "07.07",
            "source_aggregate_group_ids": "shared-rollup",
            "is_non_expanding_rollup": True, "value": 30.0,
        },
        {
            "source_system": "ESTO", "scenario": "historical", "year": 2022,
            "common_flow_code": "16.03|16.04", "common_product_code": "07.07",
            "source_aggregate_group_ids": "shared-rollup",
            "is_non_expanding_rollup": False, "value": 30.0,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert list(selected["value"]) == [30.0]
    assert bool(selected.iloc[0]["is_non_expanding_rollup"])


def test_non_expanding_frontier_uses_compound_component_code_membership() -> None:
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "source_system": "ESTO",
        "economy": "05_PRC",
        "scenario": "historical",
        "year": 2022,
        "common_product_code": "07.04-07.05",
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "common_row_id": "transport_non_road_rollup",
            "common_flow_code": "15.01,15.03-15.06",
            "component_flow_code": "15.01,15.03-15.06",
            "component_product_code": "07.05",
            "is_non_expanding_rollup": True,
            "value": 30.0,
        },
        {
            **common_values,
            "common_row_id": "domestic_air",
            "common_flow_code": "15.01",
            "component_flow_code": "15.01",
            "component_product_code": "07.04; 07.05",
            "is_non_expanding_rollup": False,
            "value": 10.0,
        },
        {
            **common_values,
            "common_row_id": "rail",
            "common_flow_code": "15.03",
            "component_flow_code": "15.03",
            "component_product_code": "07.04; 07.05",
            "is_non_expanding_rollup": False,
            "value": 20.0,
        },
        {
            **common_values,
            "common_row_id": "road",
            "common_flow_code": "15.02",
            "component_flow_code": "15.02",
            "component_product_code": "07.04; 07.05",
            "is_non_expanding_rollup": False,
            "value": 40.0,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert set(selected["common_row_id"]) == {"transport_non_road_rollup", "road"}
    assert selected["value"].sum() == 70.0


def test_detached_compound_flow_suppresses_its_observed_components() -> None:
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "economy": "20_USA",
        "common_product_code": "07.07",
        "common_product_label": "07.07 Gas/diesel oil",
        "is_non_expanding_rollup": False,
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "source_system": "ESTO", "scenario": "historical", "year": 2022,
            "common_row_id": "all_demand_other", "common_flow_code": "16.03-16.05,17",
            "common_flow_label": "16.03-16.05,17 Other sector including non-energy (all demand aggregate)",
            "value": 30.0,
        },
        {
            **common_values,
            "source_system": "ESTO", "scenario": "historical", "year": 2022,
            "common_row_id": "agriculture", "common_flow_code": "16.03-16.04",
            "common_flow_label": "16.03-16.04 Agriculture and fishing", "value": 10.0,
        },
        {
            **common_values,
            "source_system": "ESTO", "scenario": "historical", "year": 2022,
            "common_row_id": "nonspecified", "common_flow_code": "16.05",
            "common_flow_label": "16.05 Non-specified others", "value": 20.0,
        },
        {
            **common_values,
            "source_system": "NINTH", "scenario": "target", "year": 2022,
            "common_row_id": "agriculture", "common_flow_code": "16.03-16.04",
            "common_flow_label": "16.03-16.04 Agriculture and fishing", "value": 10.0,
        },
        {
            **common_values,
            "source_system": "NINTH", "scenario": "target", "year": 2022,
            "common_row_id": "nonspecified", "common_flow_code": "16.05",
            "common_flow_label": "16.05 Non-specified others", "value": 20.0,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert selected.groupby("source_system")["common_row_id"].agg(list).to_dict() == {
        "ESTO": ["all_demand_other"],
        "NINTH": ["agriculture", "nonspecified"],
    }
    assert selected.groupby("source_system")["value"].sum().to_dict() == {
        "ESTO": 30.0,
        "NINTH": 30.0,
    }


def test_detached_flow_frontier_does_not_suppress_transfer_products() -> None:
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "source_system": "LEAP",
        "economy": "20_USA",
        "scenario": "Target",
        "year": 2060,
        "common_flow_code": "08",
        "common_flow_label": "08 Transfers",
        "is_non_expanding_rollup": False,
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "common_row_id": "combined_hydrocarbons",
            "common_product_code": "06.02-06.04",
            "common_product_label": "06.02-06.04 Crude oil and NGL",
            "value": 8728.0,
        },
        {
            **common_values,
            "common_row_id": "natural_gas_liquids",
            "common_product_code": "06.02",
            "common_product_label": "06.02 Natural gas liquids",
            "value": -6594.0,
        },
    ])

    selected = _non_overlapping_common_row_frontier(rows)

    assert set(selected["common_row_id"]) == {
        "combined_hydrocarbons",
        "natural_gas_liquids",
    }
    assert selected["value"].sum() == 2134.0


def test_mixed_depth_transformation_total_is_its_own_overview_frontier() -> None:
    from codebase.common_esto_dashboard_renderer import pick_area_specs as build_specs

    broad_label = "09,09.03 Total transformation - no transfers"
    rows = pd.DataFrame([
        {
            "common_flow_code": code,
            "common_flow_label": label,
            "source_system": source_system,
        }
        for source_system, code, label in [
            ("ESTO", "09,09.03", broad_label),
            ("LEAP", "09,09.03", broad_label),
            ("NINTH", "09,09.03", broad_label),
            ("ESTO", "09.06.01", "09.06.01 Gas works plants"),
            ("LEAP", "09.06.01", "09.06.01 Gas works plants"),
            ("NINTH", "09.06.01", "09.06.01 Gas works plants"),
        ]
    ])

    specs = build_specs(
        rows,
        {
            "chart_generation": {
                "deep_chain_min_depth": 3,
                "top_levels_for_other_chains": 2,
                "max_area_charts_per_page": 30,
            }
        },
    )
    total_spec = next(
        spec for spec in specs if spec["aggregate_flow_prefix"] == "09"
    )

    assert total_spec["source_flow_labels_by_system"] == {
        "ESTO": [broad_label],
        "LEAP": [broad_label],
        "NINTH": [broad_label],
    }


def test_incomplete_transport_non_road_overview_keeps_precise_label() -> None:
    from codebase.common_esto_dashboard_renderer import area_chart_display_label

    label = "15.01,15.03-15.06 Transport non-road"

    assert area_chart_display_label(label, "", False) == label


def test_incomplete_overview_uses_explicit_page_scope_label() -> None:
    from codebase.common_esto_dashboard_renderer import area_chart_display_label

    assert (
        area_chart_display_label(
            "16.03-16.05,17 Other sector including non-energy",
            "Other demand",
            False,
        )
        == "Other demand"
    )


def test_page_routing_keeps_transformation_total_and_sector_details(tmp_path: Path) -> None:
    template = _load_template()
    series_config = _load_series_config()
    common_values = {
        "comparison_scope": "esto_leap_ninth",
        "source_system": "LEAP",
        "economy": "20_USA",
        "scenario": "Target",
        "year": 2024,
        "common_product_code": "08.01",
        "common_product_name": "Natural gas",
        "common_product_label": "08.01 Natural gas",
        "is_non_expanding_rollup": False,
    }
    rows = pd.DataFrame([
        {
            **common_values,
            "common_flow_code": "09,09.03",
            "common_flow_name": "Total transformation - no transfers",
            "common_flow_label": "09,09.03 Total transformation - no transfers",
            "value": -30.0,
        },
        {
            **common_values,
            "common_flow_code": "09.01-09.02",
            "common_flow_name": "Power sector",
            "common_flow_label": "09.01-09.02 Power sector",
            "value": -10.0,
        },
        {
            **common_values,
            "common_flow_code": "09.07",
            "common_flow_name": "Oil refineries (including own use)",
            "common_flow_label": "09.07 Oil refineries (including own use)",
            "value": -20.0,
        },
    ])
    rows = apply_sign_semantics(rows, template["sign_semantics"])
    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)

    render_dashboard(rows, template, series_config, layout)

    summary = pd.read_csv(layout["supporting"] / "page_assignment_summary.csv")
    assignments = dict(zip(summary["common_flow_code"], summary["page_key"]))
    assert assignments["09,09.03"] == "other_transformation"
    assert assignments["09.01-09.02"] == "power"
    assert assignments["09.07"] == "refining"


def test_compound_buildings_range_does_not_create_an_incomplete_prefix_card() -> None:
    from codebase.common_esto_dashboard_renderer import pick_area_specs as build_specs

    rows = pd.DataFrame([
        {
            "common_flow_code": code,
            "common_flow_label": label,
            "source_system": source,
        }
        for source, code, label in [
            ("ESTO", "16.01-16.02", "16.01-16.02 Buildings"),
            ("ESTO", "16.02", "16.02 Residential"),
            ("LEAP", "16.01-16.02", "16.01-16.02 Buildings"),
            ("NINTH", "16.01", "16.01 Commercial and public services"),
            ("NINTH", "16.02", "16.02 Residential"),
        ]
    ])

    specs = build_specs(
        rows,
        {
            "chart_generation": {
                "deep_chain_min_depth": 3,
                "top_levels_for_other_chains": 2,
                "max_area_charts_per_page": 30,
            }
        },
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == ["16", "16.02"]
    assert specs[0]["source_flow_labels_by_system"] == {
        "ESTO": ["16.01-16.02 Buildings", "16.02 Residential"],
        "LEAP": ["16.01-16.02 Buildings"],
        "NINTH": ["16.01 Commercial and public services", "16.02 Residential"],
    }


def test_section_aggregate_suppresses_chart_with_only_pre_base_year_projection() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2022,
            "common_flow_code": "08",
            "common_flow_label": "08 Transfers",
            "common_product_label": "07.01 Motor gasoline",
            "_section_label": "Transfers",
            "value": 30.0,
        }
    ])
    template = {
        "chart_generation": {
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "comparison_source_system": "ESTO",
            "ninth_source_system": "NINTH",
            "base_year": 2023,
            "suppression_threshold": 1.0,
        }
    }

    charts, chart_rows, manifest_rows = _build_section_aggregate_charts(
        rows,
        page_key="other_transformation",
        page_label="Other transformation",
        parent_flow_labels=set(),
        template=template,
        series_labels={},
    )

    assert charts == {}
    assert chart_rows == []
    assert len(manifest_rows) == 2
    assert all(row["suppressed"] for row in manifest_rows)


def test_esto_extended_scopes_disable_magnitude_suppression() -> None:
    template = {
        "chart_generation": {"suppression_threshold": 1.0},
    }
    extended_rows = pd.DataFrame(
        {"comparison_scope": ["esto_extended_leap", "esto_extended_leap"]}
    )
    ordinary_rows = pd.DataFrame(
        {"comparison_scope": ["esto_leap", "esto_leap"]}
    )

    assert effective_chart_suppression_threshold(template, extended_rows) == 0.0
    assert effective_chart_suppression_threshold(template, ordinary_rows) == 1.0

    template["_active_comparison_scope"] = "esto_extended_leap_ninth"
    assert effective_chart_suppression_threshold(template, ordinary_rows) == 0.0


def test_section_aggregate_suppresses_redundant_single_flow_chart() -> None:
    rows = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "economy": "20_USA",
                "source_system": source_system,
                "scenario": scenario,
                "year": year,
                "common_flow_code": "09.07",
                "common_flow_label": "09.07 Oil refineries",
                "common_product_code": product_code,
                "common_product_label": product_label,
                "is_non_expanding_rollup": False,
                "_section_label": "Refining",
                "value": value,
            }
            for source_system, scenario, year, product_code, product_label, value in [
                ("ESTO", "historical", 2022, "06.01", "06.01 Crude oil", -80.0),
                ("ESTO", "historical", 2022, "07.01", "07.01 Motor gasoline", 100.0),
                ("LEAP", "Target", 2023, "06.01", "06.01 Crude oil", -90.0),
                ("LEAP", "Target", 2023, "07.01", "07.01 Motor gasoline", 120.0),
            ]
        ]
    )
    template = {
        "chart_generation": {
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "comparison_source_system": "ESTO",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "suppression_threshold": 1.0,
        }
    }

    charts, chart_rows, manifest_rows = _build_section_aggregate_charts(
        rows,
        page_key="refining",
        page_label="Refining",
        parent_flow_labels=set(),
        template=template,
        series_labels={"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
    )

    assert set(charts) == {"chart__area__section__refining__refining__product"}
    assert [row["chart_key"] for row in chart_rows] == [
        "chart__area__section__refining__refining__product"
    ]
    suppression_by_key = {
        row["chart_key"]: row["suppressed"] for row in manifest_rows
    }
    assert suppression_by_key == {
        "chart__area__section__refining__refining__product": False,
        "chart__area__section__refining__refining__flow": True,
    }


def test_other_transformation_section_summaries_are_promoted_to_overview() -> None:
    section_flows = [
        ("Other transformation (including own use)", "09.06.01", "09.06.01 Gas works plants (including own use)"),
        ("Other transformation (including own use)", "09.08.01", "09.08.01 Coke ovens (including own use)"),
        ("Other energy-sector own use", "10.01.06", "10.01.06 Coal mines"),
        ("Other energy-sector own use", "10.01.12", "10.01.12 Oil and gas extraction"),
        ("Transmission and distribution losses", "10.02", "10.02 Transmission and distribution losses"),
        ("Transfers", "08", "08 Transfers"),
    ]
    rows = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "economy": "20_USA",
                "source_system": source_system,
                "scenario": scenario,
                "year": year,
                "common_flow_code": flow_code,
                "common_flow_label": flow_label,
                "common_product_code": "17",
                "common_product_label": "17 Electricity",
                "is_non_expanding_rollup": False,
                "_section_label": section_label,
                "value": value,
            }
            for section_label, flow_code, flow_label in section_flows
            for source_system, scenario, year, value in [
                ("ESTO", "historical", 2022, -10.0),
                ("LEAP", "Target", 2023, -12.0),
            ]
        ]
    )
    template = {
        "other_transformation_page": {
            "page_key": "other_transformation",
            "overview_summaries": [
                {"section_label": "Other transformation (including own use)", "group_by": "flow_or_product"},
                {"section_label": "Other energy-sector own use", "group_by": "flow_or_product"},
                {"section_label": "Transmission and distribution losses", "group_by": "product"},
                {"section_label": "Transfers", "group_by": "product"},
            ],
        },
        "chart_generation": {
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "comparison_source_system": "ESTO",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "suppression_threshold": 1.0,
        },
    }

    charts, chart_rows, manifest_rows = _build_section_aggregate_charts(
        rows,
        page_key="other_transformation",
        page_label="Other transformation",
        parent_flow_labels=set(),
        template=template,
        series_labels={"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
    )

    assert list(charts) == [
        "chart__area__section__other_transformation__other_transformation_including_own_use__flow",
        "chart__area__section__other_transformation__other_energy_sector_own_use__flow",
        "chart__area__section__other_transformation__transmission_and_distribution_losses__product",
        "chart__area__section__other_transformation__transfers__product",
    ]
    assert all(row["section_label"] == "Overview" for row in chart_rows)
    assert all(row["section_label"] == "Overview" for row in manifest_rows)


def test_flow_group_aggregates_replace_hierarchy_parents_with_safe_summaries() -> None:
    flow_rows = [
        ("ESTO", "historical", 2022, "09", "09 Total transformation sector", "19 Total", -50.0),
        ("ESTO", "historical", 2022, "09.06", "09.06 Gas processing plants", "06 Natural gas", -30.0),
        ("LEAP", "Target", 2023, "09.06.01", "09.06.01 Gas works plants", "06 Natural gas", -12.0),
        ("LEAP", "Target", 2023, "09.06.02", "09.06.02 Liquefaction/regasification plants", "06 Natural gas", -18.0),
        ("ESTO", "historical", 2022, "09.08", "09.08 Coal transformation", "01 Coal", -20.0),
        ("LEAP", "Target", 2023, "09.08.01", "09.08.01 Coke ovens", "01 Coal", -11.0),
        ("LEAP", "Target", 2023, "09.08.02", "09.08.02 Blast furnaces", "01 Coal", -9.0),
    ]
    rows = pd.DataFrame(
        [
            {
                "comparison_scope": "esto_leap_ninth",
                "economy": "20_USA",
                "source_system": source,
                "scenario": scenario,
                "year": year,
                "common_flow_code": flow_code,
                "common_flow_label": flow_label,
                "common_product_code": product_label.split(" ", 1)[0],
                "common_product_label": product_label,
                "is_non_expanding_rollup": False,
                "_section_label": "Other transformation (including own use)",
                "value": value,
            }
            for source, scenario, year, flow_code, flow_label, product_label, value in flow_rows
        ]
    )
    template = {
        "chart_generation": {
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "comparison_source_system": "ESTO",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "suppression_threshold": 1.0,
        }
    }

    charts, chart_rows, manifest_rows = _build_flow_group_aggregate_charts(
        rows,
        page_key="other_transformation",
        page_label="Other transformation",
        parent_flow_labels={
            "09 Total transformation sector",
            "09.06 Gas processing plants",
            "09.08 Coal transformation",
        },
        template=template,
        series_labels={"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
    )

    parent_keys = {
        "chart__area__flowgroup_parent__other_transformation__09_06__product",
        "chart__area__flowgroup_parent__other_transformation__09_08__product",
    }
    assert parent_keys.issubset(charts)
    assert "chart__area__flowgroup_parent__other_transformation__09__product" not in charts
    assert {
        row["flow_group_label"]
        for row in chart_rows
        if row["chart_key"] in parent_keys
    } == {"09.06 Gas processing plants", "09.08 Coal transformation"}
    gas_manifest = next(
        row for row in manifest_rows
        if row["chart_key"].endswith("09_06__product")
    )
    assert gas_manifest["source_flow_labels"] == (
        "09.06 Gas processing plants | 09.06.01 Gas works plants | "
        "09.06.02 Liquefaction/regasification plants"
    )


def test_flow_group_aggregate_synthesizes_configured_missing_intermediate_parent() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": "ESTO",
                "scenario": "historical",
                "year": 2022,
                "common_flow_code": flow_code,
                "common_flow_label": flow_label,
                "common_product_code": "17",
                "common_product_label": "17 Electricity",
                "_section_label": "Industry",
                "value": value,
            }
            for flow_code, flow_label, value in [
                ("14.03.01", "14.03.01 Iron and steel", 10.0),
                ("14.03.02", "14.03.02 Chemical (incl. petrochemical)", 20.0),
            ]
        ]
    )
    template = {
        "chart_generation": {
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "comparison_source_system": "ESTO",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "suppression_threshold": 1.0,
            "synthetic_intermediate_flow_labels": {
                "14.03": "14.03 Manufacturing",
            },
        }
    }

    charts, chart_rows, manifest_rows = _build_flow_group_aggregate_charts(
        rows,
        page_key="industry",
        page_label="Industry",
        parent_flow_labels=set(),
        template=template,
        series_labels={"ESTO|historical": "ESTO historical"},
    )

    parent_key = "chart__area__flowgroup_parent__industry__14_03__product"
    assert parent_key in charts
    parent_row = next(row for row in chart_rows if row["chart_key"] == parent_key)
    assert parent_row["flow_group_label"] == "14.03 Manufacturing"
    parent_manifest = next(row for row in manifest_rows if row["chart_key"] == parent_key)
    assert parent_manifest["source_flow_labels"] == (
        "14.03.01 Iron and steel | 14.03.02 Chemical (incl. petrochemical)"
    )


def test_supply_balancing_flows_use_base_year_bar_charts() -> None:
    rows = pd.DataFrame(
        [
            {
                "source_system": source,
                "scenario": scenario,
                "year": year,
                "common_flow_code": flow_code,
                "common_flow_label": flow_label,
                "common_product_code": product_code,
                "common_product_label": product_label,
                "_section_label": "Supply",
                "value": value,
            }
            for source, scenario, year, flow_code, flow_label, product_code, product_label, value in [
                ("ESTO", "historical", 2022, "06", "06 Stock changes", "01", "01 Coal", 5.0),
                ("LEAP", "Target", 2022, "06", "06 Stock changes", "01", "01 Coal", 7.0),
                ("LEAP", "Target", 2030, "06", "06 Stock changes", "01", "01 Coal", 99.0),
                ("ESTO", "historical", 2022, "11", "11 Statistical discrepancy", "17", "17 Electricity", -3.0),
                ("LEAP", "Target", 2022, "11", "11 Statistical discrepancy", "17", "17 Electricity", 4.0),
                ("LEAP", "Reference", 2022, "11", "11 Statistical discrepancy", "17", "17 Electricity", -2.0),
                ("LEAP", "Target", 2030, "01", "01 Production", "01", "01 Coal", 100.0),
            ]
        ]
    )

    charts, chart_rows, manifest_rows, remaining_rows = _build_supply_base_year_bar_charts(
        page_df=rows,
        page_key="supply",
        page_label="Supply",
        flow_codes=["06", "11"],
        base_year=2022,
        suppression_threshold=1.0,
        primary_source="LEAP",
        primary_scenario="Target",
        comparison_source="ESTO",
        ninth_source="NINTH",
        series_labels={
            "ESTO|historical": "ESTO historical",
            "LEAP|Reference": "LEAP Reference",
            "LEAP|Target": "LEAP Target",
        },
        comparison_scope="esto_leap",
        comparison_scope_label="ESTO and LEAP only",
        source_value_multipliers_by_flow={"11": {"LEAP": -1}},
    )

    assert set(charts) == {
        "chart__bar__base_year__supply__06_stock_changes",
        "chart__bar__base_year__supply__11_statistical_discrepancy",
    }
    assert all(row["chart_type"] == "bar" for row in chart_rows)
    assert all(row["chart_type"] == "bar" for row in manifest_rows)
    assert set(remaining_rows["common_flow_code"]) == {"01"}
    stock_chart = charts["chart__bar__base_year__supply__06_stock_changes"]
    assert {value for trace in stock_chart.data for value in trace.y} == {5.0, 7.0}
    discrepancy_chart = charts[
        "chart__bar__base_year__supply__11_statistical_discrepancy"
    ]
    discrepancy_values = {
        trace.name: list(trace.y)
        for trace in discrepancy_chart.data
    }
    assert discrepancy_values == {
        "ESTO historical": [-3.0],
        "LEAP Reference": [2.0],
        "LEAP Target": [-4.0],
    }
    assert rows.loc[
        rows["source_system"].eq("LEAP") & rows["common_flow_code"].eq("11"),
        "value",
    ].tolist() == [4.0, -2.0]
    assert "ESTO and LEAP only" in stock_chart.layout.title.text
    assert {row["data_comparison_scope"] for row in manifest_rows} == {"esto_leap"}


def test_supply_balancing_bars_use_estoleap_scope_on_default_dashboard(
    tmp_path: Path,
) -> None:
    template = _load_template()
    template["_active_comparison_scope"] = "esto_leap_ninth"
    series_config = _load_series_config()
    rows = []
    for source_system, scenario, value in [
        ("ESTO", "historical", 20.0),
        ("LEAP", "Target", 22.0),
        ("NINTH", "Target", 21.0),
    ]:
        rows.append({
            "comparison_scope": "esto_leap_ninth",
            "source_system": source_system,
            "economy": "16_RUS",
            "scenario": scenario,
            "year": 2022,
            "common_flow_code": "01",
            "common_flow_name": "Production",
            "common_flow_label": "01 Production",
            "common_product_code": "08.01",
            "common_product_name": "Natural gas",
            "common_product_label": "08.01 Natural gas",
            "common_row_id": f"production_{source_system}",
            "value": value,
        })
    for source_system, scenario, flow_code, flow_label, value in [
        ("ESTO", "historical", "06", "06 Stock changes", -2.0),
        ("LEAP", "Target", "06", "06 Stock changes", -3.0),
        ("ESTO", "historical", "11", "11 Statistical discrepancy", 4.0),
        ("LEAP", "Target", "11", "11 Statistical discrepancy", 5.0),
    ]:
        rows.append({
            "comparison_scope": "esto_leap",
            "source_system": source_system,
            "economy": "16_RUS",
            "scenario": scenario,
            "year": 2022,
            "common_flow_code": flow_code,
            "common_flow_name": flow_label.split(" ", 1)[1],
            "common_flow_label": flow_label,
            "common_product_code": "08.01",
            "common_product_name": "Natural gas",
            "common_product_label": "08.01 Natural gas",
            "common_row_id": f"balancing_{flow_code}_{source_system}",
            "value": value,
        })
    all_rows = apply_sign_semantics(pd.DataFrame(rows), template["sign_semantics"])
    main_rows = all_rows[all_rows["comparison_scope"].eq("esto_leap_ninth")].copy()
    layout = build_output_layout(tmp_path / "outputs", "16RUS", clear_existing=True)

    manifest = render_dashboard(
        main_rows,
        template,
        series_config,
        layout,
        scope_df=all_rows,
    )

    balancing_manifest = manifest[manifest["chart_key"].astype(str).str.contains(
        "chart__bar__base_year__supply"
    )]
    assert set(balancing_manifest["common_flow_label"]) == {
        "06 Stock changes",
        "11 Statistical discrepancy",
    }
    assert set(balancing_manifest["data_comparison_scope"]) == {"esto_leap"}
    bundle = json.loads(
        (layout["chart_bundles"] / "supply__charts.json").read_text(encoding="utf-8")
    )["charts"]
    for chart_key in balancing_manifest["chart_key"]:
        figure = bundle[chart_key]
        assert "ESTO and LEAP only" in figure["layout"]["title"]["text"]
        assert all("9th" not in trace["name"] for trace in figure["data"])
    discrepancy_figure = bundle[
        "chart__bar__base_year__supply__11_statistical_discrepancy"
    ]

    def decoded_y_values(trace: dict) -> list[float]:
        encoded = trace["y"]
        if isinstance(encoded, list):
            return encoded
        raw_values = base64.b64decode(encoded["bdata"])
        return list(struct.unpack(f"<{len(raw_values) // 8}d", raw_values))

    discrepancy_values = {
        trace["name"]: decoded_y_values(trace)
        for trace in discrepancy_figure["data"]
    }
    assert discrepancy_values == {
        "ESTO Historical": [4.0],
        "LEAP Target": [-5.0],
    }


def test_chart_chrome_resolves_duplicate_configured_category_colours() -> None:
    import plotly.graph_objects as go
    from codebase.common_esto_dashboard_renderer import load_code_colors

    product_colors = load_code_colors()["product"]
    labels_by_color: dict[str, list[str]] = {}
    for code, color in product_colors.items():
        labels_by_color.setdefault(color.casefold(), []).append(code)
    duplicate_codes = next(values for values in labels_by_color.values() if len(values) > 1)

    fig = go.Figure([
        go.Scatter(x=[2020], y=[1.0], stackgroup="s", name=duplicate_codes[0]),
        go.Scatter(x=[2020], y=[2.0], stackgroup="s", name=duplicate_codes[1]),
    ])
    apply_chart_chrome(fig, base_year=None, code_axis="product")

    assert fig.data[0].fillcolor != fig.data[1].fillcolor


def test_product_chart_sums_component_rows_to_one_point_per_year() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2030,
            "common_row_id": "coal_a",
            "value": -10.0,
            "sign_status": "expected_negative",
            "sign_interpretation": "transformation input",
        },
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2030,
            "common_row_id": "coal_b",
            "value": -20.0,
            "sign_status": "expected_negative",
            "sign_interpretation": "transformation input",
        },
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2031,
            "common_row_id": "coal_a",
            "value": -12.0,
            "sign_status": "expected_negative",
            "sign_interpretation": "transformation input",
        },
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2031,
            "common_row_id": "coal_b",
            "value": -21.0,
            "sign_status": "expected_negative",
            "sign_interpretation": "transformation input",
        },
    ])

    figure = build_product_chart(
        rows,
        "09 Electricity plants",
        "01.02-01.04 Coal",
        {"LEAP|Target": "LEAP Target"},
    )

    assert list(figure.data[0].x) == [2030, 2031]
    assert list(figure.data[0].y) == [-30.0, -33.0]
    assert_unique_line_trace_x({"coal_chart": figure})


def test_line_trace_duplicate_years_are_blocking() -> None:
    import plotly.graph_objects as go

    figure = go.Figure([
        go.Scatter(
            x=[2030, 2030],
            y=[-10.0, -20.0],
            mode="lines+markers",
            name="LEAP Target",
        )
    ])

    with pytest.raises(
        ValueError,
        match="at most one point per x value",
    ):
        assert_unique_line_trace_x({"bad_chart": figure})


def test_all_scopes_sentinel_keeps_every_scope_but_still_filters_economy_and_year() -> None:
    df = pd.DataFrame([
        {"economy": "20USA", "comparison_scope": "esto_leap", "year": 2020, "value": 1.0},
        {"economy": "20USA", "comparison_scope": "esto_leap_ninth", "year": 2020, "value": 2.0},
        {"economy": "20USA", "comparison_scope": "esto_leap_ninth", "year": 1990, "value": 3.0},
        {"economy": "02BD", "comparison_scope": "esto_leap_ninth", "year": 2020, "value": 4.0},
    ])

    out = filter_common_esto_data(df, comparison_scope=ALL_SCOPES, economy="20USA", min_year=2010, max_year=2060)

    assert sorted(out["comparison_scope"].unique()) == ["esto_leap", "esto_leap_ninth"]
    assert set(out["economy"]) == {"20USA"}
    assert set(out["year"]) == {2020}


def test_all_scopes_sentinel_still_requires_the_scope_column() -> None:
    df = pd.DataFrame([{"economy": "20USA", "year": 2020}])

    try:
        filter_common_esto_data(df, comparison_scope=ALL_SCOPES, economy="20USA")
    except ValueError as exc:
        assert "comparison_scope" in str(exc)
    else:
        raise AssertionError("Missing comparison_scope must raise ValueError even for ALL_SCOPES")


def test_configured_balance_flows_are_assigned_to_energy_balance_overview() -> None:
    fixture = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard" / "common_esto_rows.csv"
    df = pd.read_csv(fixture, low_memory=False)
    template = json.loads((REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json").read_text(encoding="utf-8"))
    assigned = assign_pages(df, template["sector_pages"])
    codes = set(template["total_demand_page"]["overview_flow_codes"])
    mask = assigned["common_flow_code"].astype(str).isin(codes)
    assigned.loc[mask, "_page_key"] = "total_demand"
    assert set(assigned.loc[mask, "_page_key"]) == {"total_demand"}
