import json
from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard.common_esto_dashboard_data import apply_sign_semantics
from codebase.common_esto_dashboard.common_esto_dashboard_renderer import render_dashboard
from codebase.common_esto_dashboard.output_layout import build_output_layout


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


def test_weekly_common_esto_sample_fixture_is_present() -> None:
    fixture_dir = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard"
    assert (fixture_dir / "common_esto_comparison_data_sample.csv").exists()
    assert (fixture_dir / "common_esto_rows.csv").exists()
