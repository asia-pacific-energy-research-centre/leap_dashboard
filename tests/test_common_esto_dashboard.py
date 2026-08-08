import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.common_esto_dashboard_data import (
    ALL_SCOPES,
    DEFAULT_WIDE_FILE_SCOPE,
    apply_sign_semantics,
    filter_common_esto_data,
    filter_ninth_pre_base_year_data,
    filter_template_for_leap_demand_coverage,
    load_common_esto_data,
)
from codebase.common_esto_dashboard_emissions import select_emissions_component_rows
from codebase.common_esto_dashboard_output_layout import build_output_layout, publish_to_docs
from codebase.common_esto_dashboard_renderer import (
    _build_td_fuel_chart,
    apply_chart_chrome,
    assert_unique_line_trace_x,
    assign_pages,
    build_area_chart,
    build_product_chart,
    color_for_code,
    color_for_plotting_name,
    drop_excluded_flow_rows,
    pick_area_specs,
    render_dashboard,
    select_transformation_total_rows,
    _build_section_aggregate_charts,
    _build_td_fuel_chart,
    _build_supply_stack_chart,
    aggregate_only_tfec_note,
    _select_total_rows_by_source,
    _non_overlapping_common_row_frontier,
    _non_overlapping_flow_rows,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE_PAGES = ["index", "total_demand", "transport"]
DEFAULT_DIAGNOSTIC_PAGES = ["transport_leap_vs_ninth", "datacentres_leap_vs_ninth"]


def _load_template() -> dict:
    template_path = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
    return json.loads(template_path.read_text(encoding="utf-8"))


def _load_series_config() -> dict:
    config_path = REPO_ROOT / "config" / "common_esto_dashboard" / "series_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def test_emissions_components_keep_demand_sectors_and_combine_signed_transformation_use() -> None:
    rows = pd.DataFrame([
        {
            "_page_key": "industry", "_page_label": "Industry",
            "common_flow_code": "14", "common_flow_label": "14 Industry",
            "common_product_label": "01 Coal", "source_system": "LEAP",
            "scenario": "Target", "year": 2030, "value": 20.0,
        },
        {
            "_page_key": "non_energy", "_page_label": "Non-energy use",
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
        {"demand_page_keys": ["industry", "transport", "buildings", "others", "non_energy"]},
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
        pd.DataFrame(columns=["source_system", "scenario", "year", "value"]),
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
    assert "chart__line__total_transformation_no_transfers" in set(overview_rows["chart_key"])
    assert set(overview_rows["page_label"]) == {"Energy balance overview"}


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


def test_aggregate_only_demand_pages_remain_visible_but_unmapped_page_is_hidden() -> None:
    template = _load_template()

    filtered = filter_template_for_leap_demand_coverage(
        template,
        {"Industry", "Buildings", "Other sector", "Transport non road"},
    )

    assert filtered["leap_demand_sector_coverage"]["_hidden_page_keys"] == [
        "bunkers",
        "non_energy",
    ]


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


def test_all_demand_other_sector_placeholder_is_routed_before_non_energy() -> None:
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

    assigned = assign_pages(df, template["sector_pages"])

    assert assigned.loc[0, "_page_key"] == "others"
    assert assigned.loc[1, "_page_key"] == "non_energy"


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
    # A rolled-up row keeps the first component's name but spans several codes;
    # the colour must follow the code span, not the name it happens to carry.
    assert color_for_code("01.02-01.04 Other bituminous coal", "product") == color_for_code("01.02", "product")
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


def test_supply_stack_uses_aggregate_leap_demand_when_detail_is_absent() -> None:
    supply = pd.DataFrame([
        {
            "source_system": "LEAP", "scenario": "Target", "year": 2039,
            "common_flow_label": "01 Production", "value": 150.0,
        },
    ])
    demand = pd.DataFrame([
        {"source_system": "NINTH", "scenario": "target", "year": 2039, "value": 230.0},
    ])
    overview = pd.DataFrame([
        {
            "source_system": "LEAP", "scenario": "Target", "year": 2039,
            "common_flow_code": "12", "value": 100.0,
        },
        {
            "source_system": "NINTH", "scenario": "target", "year": 2039,
            "common_flow_code": "12", "value": 105.0,
        },
    ])

    fig = _build_supply_stack_chart(
        supply,
        demand,
        overview,
        series_labels=_load_series_config()["series_labels"],
        primary_source="LEAP",
        primary_scenario="Target",
        group_col="common_flow_label",
        chart_title="Demand vs Supply by component",
    )
    traces = {trace.name: list(trace.y) for trace in fig.data}

    assert traces["LEAP Target demand (TFC)"] == [100.0]
    assert traces["9th Target demand (TFC)"] == [105.0]


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


def test_area_charts_drop_zero_only_categories_and_align_esto_frontier() -> None:
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
    assert area_names == {"07.01 Motor gasoline"}
    assert "12.99 Solar nonspecified" not in area_names


def test_energy_balance_fuel_area_uses_esto_history_on_leap_category_frontier() -> None:
    rows = pd.DataFrame([
        {"source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_label": "07.01 Motor gasoline", "value": 10.0},
        {"source_system": "ESTO", "scenario": "historical", "year": 2022,
         "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_label": "07.01 Motor gasoline", "value": 20.0},
        {"source_system": "LEAP", "scenario": "Target", "year": 2023,
         "common_product_label": "12.99 Solar nonspecified", "value": 0.0},
    ])
    figure = _build_td_fuel_chart(
        rows,
        pd.DataFrame(columns=rows.columns),
        pd.DataFrame(columns=rows.columns),
        {"ESTO|historical": "ESTO historical", "LEAP|Target": "LEAP Target"},
        "LEAP",
        "Target",
        base_year=2022,
    )
    area_names = {str(trace.name) for trace in figure.data if trace.stackgroup}
    assert area_names == {"07.01 Motor gasoline"}
    motor = next(trace for trace in figure.data if trace.name == "07.01 Motor gasoline")
    assert list(motor.x) == [2022, 2023]


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
            "common_flow_name": "Oil refineries",
            "common_flow_label": "09.07 Oil refineries",
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
