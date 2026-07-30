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
    load_common_esto_data,
)
from codebase.common_esto_dashboard_output_layout import build_output_layout, publish_to_docs
from codebase.common_esto_dashboard_renderer import (
    apply_chart_chrome,
    assert_unique_line_trace_x,
    assign_pages,
    build_area_chart,
    build_product_chart,
    color_for_code,
    color_for_plotting_name,
    drop_excluded_flow_rows,
    render_dashboard,
    select_transformation_total_rows,
    _build_section_aggregate_charts,
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


def test_total_demand_lines_use_visible_frontier_for_esto_and_ninth() -> None:
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

    assert totals == {"LEAP": 75.0, "NINTH": 100.0}


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


def test_section_aggregate_suppresses_chart_with_no_renderable_series() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "LEAP",
            "scenario": "Target",
            "year": 2023,
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
