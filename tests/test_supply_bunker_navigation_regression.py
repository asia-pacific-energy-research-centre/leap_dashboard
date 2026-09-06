"""End-to-end regressions for Supply bunker representation and navigation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from test_common_esto_dashboard import (  # noqa: E402
    _build_common_esto_rows,
    _load_series_config,
    _load_template,
)
from codebase.common_esto_dashboard_data import apply_sign_semantics  # noqa: E402
from codebase.common_esto_dashboard_output_layout import (  # noqa: E402
    build_output_layout,
)
from codebase.common_esto_dashboard_renderer import render_dashboard  # noqa: E402


def _bunker_rows(
    *,
    include_children: bool,
    include_combined: bool = True,
    leap_children_nonzero: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    source_values = [
        ("ESTO", "historical", -4.0),
        ("LEAP", "Target", -4.5),
        ("NINTH", "Target", -4.2),
    ]
    definitions = [
        (
            "04-05",
            "International transport (bunkers)",
            "07.05",
            "Kerosene type jet fuel",
        ),
        (
            "04",
            "International marine bunkers",
            "07.08",
            "Fuel oil",
        ),
        (
            "05",
            "International aviation bunkers",
            "07.05",
            "Kerosene type jet fuel",
        ),
    ]
    for source_system, scenario, value in source_values:
        for year in [2022, 2024]:
            for index, (flow_code, flow_name, product_code, product_name) in enumerate(
                definitions
            ):
                if index == 0 and not include_combined:
                    continue
                if index > 0 and not include_children:
                    continue
                label = f"{flow_code} {flow_name}"
                child_value = (
                    value / 2
                    if source_system != "LEAP" or leap_children_nonzero
                    else 0.0
                )
                rows.append({
                    "comparison_scope": "leap_vs_esto_vs_ninth",
                    "source_system": source_system,
                    "economy": "20_USA",
                    "scenario": scenario,
                    "year": year,
                    "common_flow_code": flow_code,
                    "common_flow_name": flow_name,
                    "common_flow_label": label,
                    "common_product_code": product_code,
                    "common_product_name": product_name,
                    "common_product_label": f"{product_code} {product_name}",
                    "value": value if index == 0 else child_value,
                })
    return pd.DataFrame(rows)


def _render_supply_page(
    tmp_path: Path,
    *,
    include_children: bool,
    leap_children_nonzero: bool = False,
) -> tuple[pd.DataFrame, str, dict[str, object]]:
    template = _load_template()
    # Simulate stale audit metadata from an older aggregate-only export. The
    # current-run presentation resolver must override it when both comparison
    # child boundaries are populated, while retaining it for a combined-only
    # export.
    template["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] = {
        "supply": ["International transport"],
    }
    rows = pd.concat(
        [
            _build_common_esto_rows(),
            _bunker_rows(
                include_children=include_children,
                leap_children_nonzero=leap_children_nonzero,
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    data = apply_sign_semantics(rows, template["sign_semantics"])
    main_df = data[data["comparison_scope"].eq("leap_vs_esto_vs_ninth")].copy()
    layout = build_output_layout(tmp_path / "outputs", "20USA", clear_existing=True)
    manifest = render_dashboard(
        main_df,
        template,
        _load_series_config(),
        layout,
        scope_df=data,
    )
    html = (layout["dashboards"] / "supply.html").read_text(encoding="utf-8")
    charts = json.loads(
        (layout["chart_bundles"] / "supply__charts.json").read_text(
            encoding="utf-8"
        )
    )["charts"]
    return manifest, html, charts


def test_zero_leap_bunker_children_still_publish_detail_structure(
    tmp_path: Path,
) -> None:
    """Explicit zero LEAP children are detail structure, not a placeholder."""
    manifest, supply_html, charts = _render_supply_page(
        tmp_path, include_children=True
    )
    supply_manifest = manifest[manifest["page_key"].eq("supply")]
    aggregate_flows = set(
        supply_manifest.loc[
            supply_manifest["chart_type"].eq("stacked_area"),
            "common_flow_label",
        ]
    )
    assert {
        "04 International marine bunkers",
        "05 International aviation bunkers",
    }.issubset(aggregate_flows)
    assert "04-05 International transport (bunkers)" not in aggregate_flows
    assert 'data-chart-key="chart__area__04__' in supply_html
    assert 'data-chart-key="chart__area__05__' in supply_html
    assert 'data-placeholder="true">04-05 International transport' not in supply_html
    child_area_keys = [
        key
        for key in charts
        if key.startswith(("chart__area__04__", "chart__area__05__"))
    ]
    assert len(child_area_keys) == 2


def test_detailed_leap_bunkers_use_separate_supply_pills_and_charts(
    tmp_path: Path,
) -> None:
    """Separate LEAP Air and Shipping values activate 04 and 05."""
    manifest, supply_html, charts = _render_supply_page(
        tmp_path,
        include_children=True,
        leap_children_nonzero=True,
    )
    aggregate_flows = set(
        manifest.loc[
            manifest["page_key"].eq("supply")
            & manifest["chart_type"].eq("stacked_area"),
            "common_flow_label",
        ]
    )
    assert {
        "04 International marine bunkers",
        "05 International aviation bunkers",
    }.issubset(aggregate_flows)
    assert "04-05 International transport (bunkers)" not in aggregate_flows
    assert 'data-chart-key="chart__area__04__' in supply_html
    assert 'data-chart-key="chart__area__05__' in supply_html
    assert 'data-placeholder="true">04-05 International transport' not in supply_html
    child_area_keys = [
        key
        for key in charts
        if key.startswith(("chart__area__04__", "chart__area__05__"))
    ]
    assert len(child_area_keys) == 2
    for key in child_area_keys:
        assert "LEAP Target total" in {
            str(trace.get("name", "")) for trace in charts[key]["data"]
        }


def test_aggregate_only_bunkers_keep_combined_placeholder_supply_pill(tmp_path: Path) -> None:
    """Combined-only exports retain one explicit placeholder owner."""
    manifest, supply_html, _charts = _render_supply_page(
        tmp_path, include_children=False
    )
    supply_manifest = manifest[manifest["page_key"].eq("supply")]
    aggregate_flows = set(
        supply_manifest.loc[
            supply_manifest["chart_type"].eq("stacked_area"),
            "common_flow_label",
        ]
    )
    assert "04-05 International transport (bunkers)" in aggregate_flows
    assert {
        "04 International marine bunkers",
        "05 International aviation bunkers",
    }.isdisjoint(aggregate_flows)
    assert supply_html.count(
        'data-placeholder="true">04-05 International transport (bunkers)'
    ) == 1
    assert 'data-placeholder="false">04 International marine bunkers</a>' not in supply_html
    assert 'data-placeholder="false">05 International aviation bunkers</a>' not in supply_html
    assert 'data-chart-key="chart__area__04__' not in supply_html
    assert 'data-chart-key="chart__area__05__' not in supply_html
