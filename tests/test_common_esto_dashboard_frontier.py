"""Regression tests for source/product-specific dashboard area frontiers."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERER_CODEBASE = REPO_ROOT / "codebase"
if str(RENDERER_CODEBASE) not in sys.path:
    sys.path.insert(0, str(RENDERER_CODEBASE))

import common_esto_dashboard_renderer as renderer  # noqa: E402
from common_esto_dashboard_data import (  # noqa: E402
    filter_template_for_leap_demand_coverage,
)


def _row(flow: str, product: str, value: float, scenario: str = "Target") -> dict[str, object]:
    return {
        "comparison_scope": "esto_extended_leap_ninth",
        "source_system": "NINTH",
        "economy": "02_BD",
        "scenario": scenario,
        "year": 2030,
        "common_flow_code": flow,
        "common_product_code": product,
        "is_non_expanding_rollup": False,
        "value": value,
    }


def test_area_frontier_keeps_detail_when_parent_lacks_that_product() -> None:
    """Brunei 08.99 stays in the Industry total without a synthetic parent."""
    rows = pd.DataFrame([
        _row("14", "07.07", 19.0),
        _row("14.03.11", "08.99", 0.162072),
        _row("14", "07.07", 20.0, scenario="Reference"),
        _row("14.03.11", "08.99", 0.25, scenario="Reference"),
    ])

    selected = renderer.area_spec_rows(
        rows,
        {"aggregate_flow_prefix": "14", "source_flow_labels_by_system": {"NINTH": ["14"]}},
    )
    frontier = renderer._non_overlapping_common_row_frontier(selected)

    assert set(frontier["common_flow_code"]) == {"14", "14.03.11"}
    totals = frontier.groupby("scenario")["value"].sum().to_dict()
    assert totals == {"Reference": 20.25, "Target": 19.162072}


def test_area_frontier_uses_observed_parent_without_double_counting_detail() -> None:
    """A published parent wins only for the matching product/year fact."""
    rows = pd.DataFrame([
        _row("14", "08.99", 1.0),
        _row("14.03.11", "08.99", 1.0),
        _row("14.03.11", "07.07", 2.0),
    ])

    frontier = renderer._non_overlapping_common_row_frontier(rows)

    assert list(frontier.sort_values("common_product_code")["common_flow_code"]) == ["14.03.11", "14"]
    assert frontier["value"].sum() == 3.0


def _area_product_row(
    source: str,
    scenario: str,
    year: int,
    flow: str,
    product: str,
    value: float,
) -> dict[str, object]:
    return {
        "comparison_scope": "esto_extended_leap_ninth",
        "source_system": source,
        "economy": "12_NZ",
        "scenario": scenario,
        "year": year,
        "common_flow_code": flow,
        "common_flow_label": (
            "15 Transport sector" if flow == "15" else "15.02 Road"
        ),
        "common_product_code": product,
        "common_product_label": (
            "07.01 Motor gasoline" if product == "07.01" else "16.12 Hydrogen"
        ),
        "is_non_expanding_rollup": False,
        "value": value,
    }


def test_placeholder_product_cards_reuse_aggregate_frontier_and_keep_ninth() -> None:
    """Area-derived cards retain the area rows without allocating a placeholder."""
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 90.0),
        _area_product_row("LEAP", "Target", 2022, "15", "07.01", 100.0),
        _area_product_row("LEAP", "Target", 2030, "15", "07.01", 80.0),
        _area_product_row("NINTH", "Reference", 2022, "15", "07.01", 110.0),
        _area_product_row("NINTH", "Target", 2022, "15", "07.01", 105.0),
        # This child is an alternative NINTH representation of the parent,
        # not an extra 50 PJ that can be added to it.
        _area_product_row("NINTH", "Target", 2022, "15.02", "07.01", 50.0),
        # The same is true for the published non-road compound expression. A
        # simple parent must own it when both exist for one product/year.
        {
            **_area_product_row(
                "NINTH", "Target", 2022, "15.01,15.03-15.06", "07.01", 25.0
            ),
            "common_flow_label": "15.01,15.03-15.06 Transport non-road",
            "is_non_expanding_rollup": True,
        },
        # Source-only products remain visible as ordinary source data.
        _area_product_row("NINTH", "Target", 2030, "15", "16.12", 3.0),
    ])
    area_spec = {"aggregate_flow_prefix": "15", "aggregate_flow_label": "15 Transport sector"}
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        }
    }
    series_labels = {
        "ESTO_EXTENDED|historical": "ESTO Historical",
        "LEAP|Target": "LEAP Target",
        "NINTH|Reference": "9th Reference",
        "NINTH|Target": "9th Target",
    }

    resolved = renderer.resolved_area_chart_rows(rows, area_spec)
    ninth_target_gasoline = resolved.loc[
        (resolved["source_system"] == "NINTH")
        & (resolved["scenario"] == "Target")
        & (resolved["common_product_code"] == "07.01")
    ]
    assert ninth_target_gasoline["value"].sum() == 105.0

    area = renderer.build_area_chart(rows, area_spec, series_labels, template)
    assert {trace.name for trace in area.data if trace.name.endswith(" total")} == {
        "ESTO Historical total",
        "LEAP Target total",
        "9th Reference total",
        "9th Target total",
    }

    aggregate_rows = renderer.resolved_area_chart_rows(rows, area_spec)
    aggregate_specs = [
        {
            "chart_key": "chart__line__aggregate_product__transport__15__07_01",
            "flow_label": "15 Transport sector",
            "product_label": "07.01 Motor gasoline",
            "section_label": "Overview by product",
            "flow_group_label": "",
            "rows": aggregate_rows[
                aggregate_rows["common_product_label"].eq("07.01 Motor gasoline")
            ],
        },
        {
            "chart_key": "chart__line__aggregate_product__transport__15__16_12",
            "flow_label": "15 Transport sector",
            "product_label": "16.12 Hydrogen",
            "section_label": "Overview by product",
            "flow_group_label": "",
            "rows": aggregate_rows[
                aggregate_rows["common_product_label"].eq("16.12 Hydrogen")
            ],
        },
    ]
    charts, chart_rows, _ = renderer._build_ordinary_product_line_charts(
        aggregate_specs,
        "transport",
        "Transport",
        template,
        series_labels,
    )
    assert {row["product_label"] for row in chart_rows} == {
        "07.01 Motor gasoline",
        "16.12 Hydrogen",
    }
    assert {row["flow_group_label"] for row in chart_rows} == {""}
    gasoline_key = next(
        key for key, row in zip(charts, chart_rows)
        if row["product_label"] == "07.01 Motor gasoline"
    )
    assert {trace.name for trace in charts[gasoline_key].data} == {
        "ESTO Historical",
        "LEAP Target",
        "9th Reference",
        "9th Target",
    }
    ordinary_charts, _, _ = renderer._build_ordinary_product_line_charts(
        [{
            "chart_key": "chart__line__15_transport_sector__07_01_motor_gasoline",
            "flow_label": "15 Transport sector",
            "product_label": "07.01 Motor gasoline",
            "section_label": "Transport",
            "rows": aggregate_specs[0]["rows"],
        }],
        "transport",
        "Transport",
        template,
        series_labels,
    )
    assert charts[gasoline_key].to_plotly_json() == next(
        iter(ordinary_charts.values())
    ).to_plotly_json()


def test_placeholder_overview_ownership_prevents_duplicate_ninth_detail_cards() -> None:
    """Only the displayed placeholder frontier is consumed from detail sections."""
    transport_rows = [
        _area_product_row("NINTH", "Reference", 2030, "15", "07.01", 110.0),
        _area_product_row("NINTH", "Target", 2030, "15", "07.01", 105.0),
    ]
    agriculture_rows = [
        {
            **_area_product_row("NINTH", "Reference", 2030, "16.03", "16.12", 4.0),
            "common_flow_label": "16.03 Agriculture",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "16.03", "16.12", 3.0),
            "common_flow_label": "16.03 Agriculture",
        },
    ]
    rows = pd.DataFrame([*transport_rows, *agriculture_rows])
    rows["_dashboard_row_owner_id"] = range(len(rows))
    area_spec = {"aggregate_flow_prefix": "15", "aggregate_flow_label": "15 Transport sector"}

    overview_rows = renderer.resolved_area_chart_rows(rows, area_spec)
    remaining_detail = renderer.drop_overview_owned_detail_rows(rows, overview_rows)

    # The source-only Transport facts have already been displayed in the
    # placeholder overview/cards, so a second NINTH-only Transport card cannot
    # be emitted by the ordinary source-routed section loop.
    assert not remaining_detail["common_flow_label"].eq("15 Transport sector").any()
    # Ownership is exact, not a blanket NINTH filter: a genuine unrelated
    # source-only Agriculture section remains available to the normal pipeline.
    assert set(remaining_detail["common_flow_label"]) == {"16.03 Agriculture"}
    assert set(remaining_detail["source_system"]) == {"NINTH"}


def test_other_demand_suppresses_only_redundant_comparison_rollups() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "16.03-16.05", "17", 30.0),
        _area_product_row("LEAP", "Target", 2023, "16.03-16.04", "17", 20.0),
        _area_product_row("LEAP", "Target", 2023, "16.03", "17", 12.0),
        _area_product_row("LEAP", "Target", 2023, "16.05", "17", 8.0),
    ])
    template = {
        "other_demand_page": {
            "page_key": "others",
            "suppress_redundant_detail_flow_codes": [
                "16.03-16.04", "16.03-16.05"
            ],
        }
    }

    remaining = renderer.drop_configured_redundant_detail_rows(
        "others", rows, template
    )

    assert set(remaining["common_flow_code"]) == {"16.03", "16.05"}


def test_overview_product_roots_include_placeholder_and_configured_peer() -> None:
    """Industry and exact non-energy use share one Overview/product treatment."""
    template = {
        "leap_demand_sector_coverage": {
            "show_aggregate_only_page_keys": ["industry"],
            "_aggregate_only_page_branches": {"industry": ["Industry"]},
            "_placeholder_only_page_branches": {
                "industry": ["Industry"],
                "others": ["Other sector"],
            },
            "placeholder_component_flow_prefixes": {
                "Industry": ["14"],
                "Other sector": ["16.03", "16.04", "16.05", "17"],
            },
            "placeholder_component_product_sections": {
                "Industry": {"flow_code": "14", "label": "14 Industry sector"},
            },
            "overview_product_flow_prefixes_by_page": {"industry": ["17"]},
        }
    }

    assert renderer.overview_product_root_prefixes("industry", template) == {"14", "17"}
    assert renderer.flow_boundary_is_active_demand_placeholder("17", template)

    # Flow 17 remains an Overview peer when Industry later gains detailed LEAP
    # branches; the placeholder-only root 14 no longer suppresses that detail.
    template["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] = {}
    template["leap_demand_sector_coverage"]["_placeholder_only_page_branches"] = {}
    assert renderer.overview_product_root_prefixes("industry", template) == {"17"}
    assert not renderer.flow_boundary_is_active_demand_placeholder("17", template)


def test_unavailable_nonenergy_branch_is_marked_as_placeholder() -> None:
    """A missing separate flow-17 branch remains visibly transitional."""
    template = {
        "leap_demand_sector_coverage": {
            "enabled": True,
            "aggregate_placeholder_branch": "All demand aggregated",
            "page_leap_branches": {
                "industry": ["Industry", "Non Energy Use"],
                "others": ["Other sector"],
            },
            "overview_product_flow_prefixes_by_page": {"industry": ["17"]},
            "placeholder_component_product_sections": {
                "Industry": {"flow_code": "14", "label": "14 Industry sector"},
                "Non Energy Use": {
                    "flow_code": "17",
                    "label": "17 Non-energy use",
                },
            },
            "placeholder_component_flow_prefixes": {
                "Industry": ["14"],
                "Non Energy Use": ["17"],
            },
        }
    }
    status = pd.DataFrame([
        {
            "component_branch": "Industry",
            "detailed_branches": "Industry",
            "representation_status": "placeholder_only_retained",
        },
        {
            "component_branch": "Non Energy Use",
            "detailed_branches": "Non Energy Use",
            "representation_status": "no_data_unavailable",
        },
    ])

    filtered = filter_template_for_leap_demand_coverage(template, status)
    coverage = filtered["leap_demand_sector_coverage"]

    assert coverage["_aggregate_only_page_branches"] == {
        "industry": ["Industry"]
    }
    assert coverage["_unavailable_page_branches"] == {
        "industry": ["Non Energy Use"]
    }
    assert renderer.active_placeholder_product_sections(
        "industry", filtered
    ) == [
        {
            "component": "Industry",
            "flow_code": "14",
            "label": "14 Industry sector",
        },
        {
            "component": "Non Energy Use",
            "flow_code": "17",
            "label": "17 Non-energy use",
        },
    ]
    assert renderer.flow_boundary_is_active_demand_placeholder("17", filtered)
    note = renderer.page_placeholder_note("industry", filtered)
    assert "separate LEAP branch is unavailable for Non Energy Use" in note


def test_buildings_placeholder_hides_residential_only_while_active() -> None:
    """A placeholder owns 16 Buildings; a detailed model may publish 16.02."""
    template = {
        "leap_demand_sector_coverage": {
            "show_aggregate_only_page_keys": ["buildings"],
            "_aggregate_only_page_branches": {"buildings": ["Buildings"]},
            "_placeholder_only_page_branches": {"buildings": ["Buildings"]},
            "placeholder_component_flow_prefixes": {
                "Buildings": ["16.01", "16.02"],
            },
        }
    }
    residential = {
        "aggregate_flow_prefix": "16.02",
        "aggregate_flow_label": "16.02 Residential",
    }

    assert renderer.area_spec_is_placeholder_only_demand_child(
        "buildings", residential, template
    )

    template["leap_demand_sector_coverage"]["_aggregate_only_page_branches"] = {}
    template["leap_demand_sector_coverage"]["_placeholder_only_page_branches"] = {}
    assert not renderer.area_spec_is_placeholder_only_demand_child(
        "buildings", residential, template
    )


def test_placeholder_owner_area_remains_visible_while_children_are_hidden() -> None:
    """The Industry owner is kept while unsupported child areas stay hidden."""
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {"industry": ["Industry"]},
            "_placeholder_only_page_branches": {"industry": ["Industry"]},
            "placeholder_component_flow_prefixes": {"Industry": ["14"]},
            "placeholder_component_product_sections": {
                "Industry": {"flow_code": "14", "label": "14 Industry sector"},
            },
        }
    }

    assert not renderer.area_spec_is_placeholder_only_demand_child(
        "industry",
        {"aggregate_flow_prefix": "14", "aggregate_flow_label": "14 Industry sector"},
        template,
    )
    assert renderer.area_spec_is_placeholder_only_demand_child(
        "industry",
        {"aggregate_flow_prefix": "14.01", "aggregate_flow_label": "14.01 Iron and steel"},
        template,
    )


def test_placeholder_components_create_separate_owned_product_boundaries() -> None:
    """Road and non-road retain separate audited placeholder sections."""
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {
                "transport": ["Road", "Transport non road"],
            },
            "placeholder_component_product_sections": {
                "Road": {"flow_code": "15.02", "label": "15.02 Road"},
                "Transport non road": {
                    "flow_code": "15.01,15.03-15.06",
                    "label": "15.01,15.03-15.06 Transport non-road",
                },
            },
            "placeholder_overview_components_by_page": {
                "transport": ["Road", "Transport non road"],
            },
        }
    }
    sections = renderer.active_placeholder_product_sections("transport", template)

    assert [(row["flow_code"], row["label"]) for row in sections] == [
        ("15.02", "15.02 Road"),
        ("15.01,15.03-15.06", "15.01,15.03-15.06 Transport non-road"),
    ]

    rows = pd.DataFrame([
        _area_product_row("LEAP", "Target", 2030, "15.02", "07.01", 80.0),
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.01,15.03-15.06", "07.01", 7.0
            ),
            "common_flow_label": "15.01,15.03-15.06 Transport non-road",
            "is_non_expanding_rollup": True,
        },
        _area_product_row("NINTH", "Target", 2030, "15", "07.01", 100.0),
    ])
    road_rows = renderer.resolved_flow_boundary_rows(rows, "15.02")
    nonroad_rows = renderer.resolved_flow_boundary_rows(
        rows, "15.01,15.03-15.06"
    )

    assert road_rows["value"].sum() == 80.0
    assert nonroad_rows["value"].sum() == 7.0
    assert set(road_rows["common_flow_code"]) == {"15.02"}
    assert set(nonroad_rows["common_flow_code"]) == {"15.01,15.03-15.06"}

    existing_specs = [{
        "area_level": 1,
        "aggregate_flow_prefix": "15",
        "aggregate_flow_label": "15 Transport sector",
        "source_flow_labels": ["15 Transport sector"],
        "source_flow_labels_by_system": {},
    }, {
        "area_level": 2,
        "aggregate_flow_prefix": "15.02",
        "aggregate_flow_label": "15.02 Road",
        "source_flow_labels": ["15.02 Road"],
        "source_flow_labels_by_system": {},
    }]
    area_specs = renderer.add_active_placeholder_area_specs(
        "transport", rows, existing_specs, template
    )

    assert [spec["aggregate_flow_prefix"] for spec in area_specs] == [
        "15",
        "15.02",
        "15.01,15.03-15.06",
    ]
    nonroad_spec = area_specs[-1]
    assert nonroad_spec["explicit_flow_boundary"] is True
    assert set(renderer.area_spec_rows(rows, nonroad_spec)["common_flow_code"]) == {
        "15.01,15.03-15.06"
    }


def test_transport_nonroad_placeholder_is_connected_to_overview_pipeline() -> None:
    """The rendered Overview includes sector, Road, and compound non-road."""
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {
                "transport": ["Road", "Transport non road"],
            },
            "placeholder_component_product_sections": {
                "Road": {"flow_code": "15.02", "label": "15.02 Road"},
                "Transport non road": {
                    "flow_code": "15.01,15.03-15.06",
                    "label": "15.01,15.03-15.06 Transport non-road",
                },
            },
            "placeholder_overview_components_by_page": {
                "transport": ["Road", "Transport non road"],
            },
        }
    }
    rows = pd.DataFrame([
        _area_product_row("LEAP", "Target", 2030, "15", "07.01", 87.0),
        _area_product_row("LEAP", "Target", 2030, "15.02", "07.01", 80.0),
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.01,15.03-15.06", "07.01", 7.0
            ),
            "common_flow_label": "15.01,15.03-15.06 Transport non-road",
            "is_non_expanding_rollup": True,
        },
    ])
    generic_specs = [
        {
            "aggregate_flow_prefix": "15",
            "aggregate_flow_label": "15 Transport sector",
        },
        {
            "aggregate_flow_prefix": "15.02",
            "aggregate_flow_label": "15.02 Road",
        },
    ]

    specs = renderer.prepare_area_specs_for_page(
        "transport", rows, generic_specs, template
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == [
        "15",
        "15.02",
        "15.01,15.03-15.06",
    ]


def test_transport_nonroad_overview_remains_after_placeholder_is_replaced() -> None:
    template = {
        "leap_demand_sector_coverage": {
            "placeholder_component_product_sections": {
                "Transport non road": {
                    "flow_code": "15.01,15.03-15.06",
                    "label": "15.01,15.03-15.06 Transport non-road",
                },
            },
            "placeholder_component_flow_prefixes": {
                "Transport non road": ["15.01", "15.03", "15.04", "15.05", "15.06"],
            },
            "placeholder_overview_components_by_page": {
                "transport": ["Transport non road"],
            },
            "page_placeholder_components": {
                "transport": ["Transport non road"],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2030, "15.03", "07.07", 6.0),
            "common_flow_label": "15.03 Rail",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "15.04", "07.08", 4.0),
            "common_flow_label": "15.04 Domestic navigation",
        },
    ])

    specs = renderer.add_active_placeholder_area_specs(
        "transport", rows, [], template
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == [
        "15.01,15.03-15.06",
        "15.01,15.03-15.06",
    ]
    assert [spec.get("overview_variant", "by_product") for spec in specs] == [
        "by_product", "by_flow"
    ]
    assert all(
        spec["prefer_published_detail_over_parent_total"] is True
        for spec in specs
    )
    assert set(renderer.area_spec_rows(rows, specs[0])["common_flow_code"]) == {
        "15.03",
        "15.04",
    }


def test_other_demand_placeholder_replaces_broad_16_overview() -> None:
    """Other demand compares exact 16.03-16.05, never NINTH parent 16."""
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {"others": ["Other sector"]},
            "placeholder_component_product_sections": {
                "Other sector": {
                    "flow_code": "16.03-16.05",
                    "label": "16.03-16.05 Other sector",
                },
            },
            "placeholder_overview_components_by_page": {
                "others": ["Other sector"],
            },
            "placeholder_overview_replacements_by_page": {
                "others": [
                    {"component": "Other sector", "replace_flow_codes": ["16"]},
                ],
            },
        }
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "16.03-16.05", "17", 32.987823
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2023, "16.03-16.04", "17", 30.955676
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row("NINTH", "Target", 2023, "16.05", "17", 2.032123),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("NINTH", "Target", 2023, "16", "17", 153.522906),
            "common_flow_label": "16 Other sector",
            "common_product_label": "17 Electricity",
        },
    ])
    generic_specs = [{
        "area_level": 1,
        "aggregate_flow_prefix": "16",
        "aggregate_flow_label": "16 Other sector",
        "source_flow_labels": ["16 Other sector"],
        "source_flow_labels_by_system": {},
    }]

    replaced = renderer.replace_active_placeholder_area_specs(
        "others", generic_specs, template
    )
    assert renderer.active_placeholder_replaced_area_flow_codes(
        "others", template
    ) == {"16"}
    specs = renderer.add_active_placeholder_area_specs(
        "others", rows, replaced, template
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == ["16.03-16.05"]
    resolved = renderer.resolved_area_chart_rows(rows, specs[0])
    ninth_total = resolved.loc[resolved["source_system"].eq("NINTH"), "value"].sum()
    assert ninth_total == pytest.approx(32.987799)
    assert not resolved["common_flow_code"].eq("16").any()


def test_generic_placeholder_overview_drops_uninformative_by_flow_companion() -> None:
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {"industry": ["Industry"]},
            "_placeholder_only_page_branches": {"industry": ["Industry"]},
            "placeholder_component_product_sections": {
                "Industry": {"flow_code": "14", "label": "14 Industry sector"}
            },
            "placeholder_component_flow_prefixes": {"Industry": ["14"]},
            "placeholder_overview_components_by_page": {},
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2030, "14", "17", 20.0),
            "common_flow_label": "14 Industry sector",
            "common_product_label": "17 Electricity",
        }
    ])
    specs = renderer.prepare_area_specs_for_page(
        "industry",
        rows,
        [
            {"aggregate_flow_prefix": "14", "aggregate_flow_label": "14 Industry sector"},
            {
                "aggregate_flow_prefix": "14",
                "aggregate_flow_label": "14 Industry sector",
                "overview_variant": "by_flow",
            },
        ],
        template,
    )

    assert [spec.get("overview_variant", "by_product") for spec in specs] == [
        "by_product"
    ]


def test_supply_bunker_overview_keeps_one_combined_placeholder() -> None:
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "supply_page": {
            "page_key": "supply",
            "bunker_overview": {
                "enabled": True,
                "flow_boundary": "04-05",
                "label": "04-05 International transport (bunkers)",
                "preferred_detail_flow_boundaries": ["04", "05"],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2030, "04-05", "07.08", -30.0),
            "common_flow_label": "04-05 International transport (bunkers)",
            "common_product_label": "07.08 Fuel oil",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "04", "07.08", -12.0),
            "common_flow_label": "04 International marine bunkers",
            "common_product_label": "07.08 Fuel oil",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "05", "07.07", -18.0),
            "common_flow_label": "05 International aviation bunkers",
            "common_product_label": "07.07 Gas/diesel oil",
        },
    ])

    existing = [
        {"aggregate_flow_prefix": "04", "aggregate_flow_label": "04 Marine"},
        {"aggregate_flow_prefix": "05", "aggregate_flow_label": "05 Aviation"},
        {"aggregate_flow_prefix": "04-05"},
        {"aggregate_flow_prefix": "04-05"},
        {"aggregate_flow_prefix": "04-05", "overview_variant": "by_flow"},
    ]
    specs = renderer.add_supply_bunker_overview_specs(
        "supply", rows, existing, template
    )

    assert len(specs) == 1
    assert specs[0]["aggregate_flow_prefix"] == "04-05"
    assert specs[0].get("overview_variant", "by_product") == "by_product"


def test_supply_bunker_overview_omits_combined_total_when_children_have_cards() -> None:
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "supply_page": {
            "page_key": "supply",
            "bunker_overview": {
                "enabled": True,
                "flow_boundary": "04-05",
                "label": "04-05 International transport (bunkers)",
                "preferred_detail_flow_boundaries": ["04", "05"],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2030, "04-05", "07.08", -30.0),
            "common_flow_label": "04-05 International transport (bunkers)",
            "common_product_label": "07.08 Fuel oil",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "04", "07.08", -12.0),
            "common_flow_label": "04 International marine bunkers",
            "common_product_label": "07.08 Fuel oil",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "05", "07.07", -18.0),
            "common_flow_label": "05 International aviation bunkers",
            "common_product_label": "07.07 Gas/diesel oil",
        },
    ])
    existing = [
        {"aggregate_flow_prefix": "04", "aggregate_flow_label": "04 Marine"},
        {"aggregate_flow_prefix": "05", "aggregate_flow_label": "05 Aviation"},
        {"aggregate_flow_prefix": "04-05", "aggregate_flow_label": "Combined"},
    ]

    specs = renderer.add_supply_bunker_overview_specs(
        "supply", rows, existing, template
    )

    assert [spec.get("aggregate_flow_prefix") for spec in specs] == ["04", "05"]
    assert all(spec.get("overview_variant") != "by_flow" for spec in specs)


def test_supply_bunker_detail_overrides_stale_placeholder_status() -> None:
    """Observed LEAP 04/05 rows are stronger evidence than a stale audit flag."""
    template = {
        "leap_demand_sector_coverage": {
            "_aggregate_only_page_branches": {
                "supply": ["International transport"],
            },
        },
        "supply_page": {
            "page_key": "supply",
            "bunker_overview": {
                "enabled": True,
                "flow_boundary": "04-05",
                "label": "04-05 International transport (bunkers)",
                "preferred_detail_flow_boundaries": ["04", "05"],
            },
        },
    }
    rows = pd.DataFrame([
        _area_product_row("LEAP", "Target", 2030, "04-05", "07.08", -30.0),
        _area_product_row("LEAP", "Target", 2030, "04", "07.08", -12.0),
        _area_product_row("LEAP", "Target", 2030, "05", "07.07", -18.0),
    ])
    existing = [
        {"aggregate_flow_prefix": "04", "aggregate_flow_label": "04 Marine"},
        {"aggregate_flow_prefix": "05", "aggregate_flow_label": "05 Aviation"},
        {"aggregate_flow_prefix": "04-05", "aggregate_flow_label": "Combined"},
    ]

    specs = renderer.add_supply_bunker_overview_specs(
        "supply", rows, existing, template
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == ["04", "05"]


def test_supply_bunker_children_are_always_displayed_as_withdrawals() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "04", "07.08", 5.0),
        _area_product_row("LEAP", "Target", 2023, "04", "07.08", 6.0),
        _area_product_row("NINTH", "Target", 2023, "05", "07.06", -20.0),
        _area_product_row("LEAP", "Target", 2023, "01", "07.01", 100.0),
    ])

    fixed = renderer.normalize_supply_bunker_withdrawal_signs(
        "supply",
        rows,
        {
            "supply_page": {
                "page_key": "supply",
                "normalize_bunker_withdrawal_signs": True,
                "bunker_child_flow_codes": ["04", "05"],
            }
        },
    )

    assert fixed.loc[fixed["common_flow_code"].eq("04"), "value"].tolist() == [
        -5.0,
        -6.0,
    ]
    assert fixed.loc[fixed["common_flow_code"].eq("05"), "value"].tolist() == [
        -20.0
    ]
    assert fixed.loc[fixed["common_flow_code"].eq("01"), "value"].tolist() == [
        100.0
    ]


def test_other_demand_exact_overview_does_not_depend_on_placeholder_status() -> None:
    """Broad flow 16 never becomes the Other-demand comparison boundary."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "suppress_generic_overview_flow_codes": ["16"],
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("NINTH", "Target", 2042, "16", "17", 890.4),
            "common_flow_label": "16 Other sector",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2042, "16.03-16.04", "17", 99.4
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("NINTH", "Target", 2042, "16.05", "17", 1.3),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])
    generic_specs = [{
        "area_level": 1,
        "aggregate_flow_prefix": "16",
        "aggregate_flow_label": "16 Other sector",
        "source_flow_labels": ["16 Other sector"],
    }]

    replaced = renderer.replace_active_placeholder_area_specs(
        "others", generic_specs, template
    )
    specs = renderer.add_other_demand_flow_overview_spec(
        "others", rows, replaced, template
    )

    assert replaced == []
    assert [spec["aggregate_flow_prefix"] for spec in specs] == [
        "16.03-16.05",
        "16.03-16.05",
    ]
    product_spec = next(
        spec for spec in specs if spec.get("overview_variant", "by_product") == "by_product"
    )
    resolved = renderer.resolved_area_chart_rows(rows, product_spec)
    assert resolved["value"].sum() == pytest.approx(100.7)
    assert not resolved["common_flow_code"].eq("16").any()


def test_exact_other_demand_boundary_is_connected_to_overview_pipeline() -> None:
    """The rendered Overview cannot retain broad flow 16 or its non-energy."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "suppress_generic_overview_flow_codes": ["16"],
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("NINTH", "Target", 2042, "16", "17", 890.4),
            "common_flow_label": "16 Other sector",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2042, "16.03-16.04", "17", 99.4
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("NINTH", "Target", 2042, "16.05", "17", 1.3),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])
    generic_specs = [{
        "aggregate_flow_prefix": "16",
        "aggregate_flow_label": "16 Other sector",
        "source_flow_labels": ["16 Other sector"],
    }]

    specs = renderer.prepare_area_specs_for_page(
        "others", rows, generic_specs, template
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == [
        "16.03-16.05",
        "16.03-16.05",
    ]
    product_spec = next(
        spec for spec in specs
        if spec.get("overview_variant", "by_product") == "by_product"
    )
    resolved = renderer.resolved_area_chart_rows(rows, product_spec)
    assert resolved["value"].sum() == pytest.approx(100.7)
    assert not resolved["common_flow_code"].eq("16").any()


def test_other_demand_by_flow_overview_switches_sources_at_base_year() -> None:
    """ESTO child flows give way to one LEAP placeholder after 2022."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": ["16.03-16.04", "16.05"],
                "chart_caption": "Other demand — by flow",
                "stacked_area_note": "Configured explanatory note.",
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.05", "17", 30.0
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.04", "17", 20.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.05", "17", 10.0
            ),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "16.03-16.05", "17", 30.0
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
    ])

    unchanged = renderer.add_other_demand_flow_overview_spec(
        "transport", rows, [], template
    )
    specs = renderer.add_other_demand_flow_overview_spec(
        "others", rows, [], template
    )

    assert unchanged == []
    assert len(specs) == 2
    flow_spec = next(spec for spec in specs if spec.get("overview_variant") == "by_flow")
    assert flow_spec["group_col"] == "common_flow_label"
    resolved = renderer.resolved_area_chart_rows(
        rows,
        flow_spec,
        group_col="common_flow_label",
    )
    historical_flows = set(
        resolved.loc[
            resolved["source_system"].eq("ESTO_EXTENDED"),
            "common_flow_code",
        ]
    )
    projected_flows = set(
        resolved.loc[resolved["source_system"].eq("LEAP"), "common_flow_code"]
    )
    assert historical_flows == {"16.03-16.04", "16.05"}
    assert projected_flows == {"16.03-16.05"}
    assert resolved.groupby(["source_system", "year"])["value"].sum().to_dict() == {
        ("ESTO_EXTENDED", 2022): 30.0,
        ("LEAP", 2023): 30.0,
    }


def test_other_demand_by_flow_overview_uses_real_leap_detail_when_available() -> None:
    """Published LEAP child flows replace the combined placeholder area."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": ["16.03-16.04", "16.05"],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "16.03-16.04", "17", 24.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "16.05", "17", 6.0),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])

    spec = next(
        spec
        for spec in renderer.add_other_demand_flow_overview_spec(
            "others", rows, [], template
        )
        if spec.get("overview_variant") == "by_flow"
    )
    resolved = renderer.resolved_area_chart_rows(
        rows,
        spec,
        group_col="common_flow_label",
    )

    assert set(resolved["common_flow_code"]) == {"16.03-16.04", "16.05"}
    assert resolved["value"].sum() == 30.0


def test_other_demand_flow_overview_keeps_ninth_compound_agriculture_rollup() -> None:
    """The preferred frontier must not drop 16.03-16.04 from Ninth."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": [
                    "16.03-16.04", "16.03", "16.04", "16.05"
                ],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "NINTH", "Target", 2030, "16.03-16.04", "17", 210.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "16.05", "17", 2.5),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])

    spec = next(
        spec
        for spec in renderer.add_other_demand_flow_overview_spec(
            "others", rows, [], template
        )
        if spec.get("overview_variant") == "by_flow"
    )
    resolved = renderer.resolved_area_chart_rows(
        rows,
        spec,
        group_col="common_flow_label",
    )

    assert set(resolved["common_flow_code"]) == {"16.03-16.04", "16.05"}
    assert resolved["value"].sum() == pytest.approx(212.5)


def test_other_demand_chart_collapses_compound_when_history_proves_one_child() -> None:
    """A projected compound may use the sole matching observed child label."""
    spec = {
        "aggregate_flow_prefix": "16.03-16.05",
        "aggregate_flow_label": "16.03-16.05 Other sector",
        "source_flow_labels": [
            "16.03 Agriculture",
            "16.03-16.04 Agriculture and fishing",
        ],
        "collapse_compound_to_historical_child": {
            "16.03-16.04": ["16.03", "16.04"],
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03", "17", 20.0
            ),
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.04", "17", 20.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "16.03-16.04", "17", 21.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
    ])

    resolved = renderer.collapse_compound_projection_to_historical_child(
        rows,
        rows,
        spec,
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    projected = resolved[resolved["year"].eq(2023)]
    assert projected["common_flow_code"].tolist() == ["16.03"]
    assert projected["common_flow_label"].tolist() == ["16.03 Agriculture"]


def test_other_demand_chart_keeps_compound_when_child_does_not_reconcile() -> None:
    """A material historical residual prevents a projected compound relabel."""
    source_rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03", "17", 18.0
            ),
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.04", "17", 20.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "16.03-16.04", "17", 21.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
    ])
    resolved = renderer.collapse_compound_projection_to_historical_child(
        source_rows,
        source_rows,
        {
            "collapse_compound_to_historical_child": {
                "16.03-16.04": ["16.03", "16.04"],
            },
        },
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    projected = resolved[resolved["year"].eq(2023)]
    assert projected["common_flow_code"].tolist() == ["16.03-16.04"]


def test_compound_chart_label_uses_child_when_rendered_series_matches_child() -> None:
    """An allocated residual uses the child label it exactly reproduces."""
    source_rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "15.01", "17", 20.0
            ),
            "common_flow_label": "15.01 Domestic air transport",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "15.01", "17", 21.0
            ),
            "common_flow_label": "15.01 Domestic air transport",
        },
    ])
    chart_rows = source_rows.copy()
    chart_rows["common_flow_label"] = (
        "15.01,15.03-15.06 Transport non-road"
    )

    resolved = renderer.collapse_compound_projection_to_historical_child(
        chart_rows,
        source_rows,
        {
            "collapse_compound_to_historical_child": {
                "15.01,15.03-15.06": [
                    "15.01", "15.03", "15.04", "15.05", "15.06"
                ],
            },
        },
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    assert set(resolved["common_flow_code"]) == {"15.01"}
    assert set(resolved["common_flow_label"]) == {
        "15.01 Domestic air transport"
    }


def test_compound_chart_label_fills_sole_missing_child_per_source_year() -> None:
    chart_rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2023, "15", "07.05", 10.0),
            "common_flow_label": "15.01,15.03-15.06 Transport non-road",
        },
        *[
            {
                **_area_product_row("LEAP", "Target", 2023, code, product, value),
                "common_flow_label": label,
            }
            for code, label, product, value in (
                ("15.03", "15.03 Rail", "17", 8.0),
                ("15.04", "15.04 Domestic navigation", "07.08", 6.0),
                ("15.05", "15.05 Pipeline transport", "08.01", 4.0),
                ("15.06", "15.06 Non-specified transport", "07.07", 2.0),
            )
        ],
    ])
    source_rows = pd.concat([
        chart_rows,
        pd.DataFrame([{
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "15.01", "07.05", 9.0
            ),
            "common_flow_label": "15.01 Domestic air transport",
        }]),
    ], ignore_index=True)

    resolved = renderer.collapse_compound_projection_to_historical_child(
        chart_rows,
        source_rows,
        {
            "collapse_compound_to_historical_child": {
                "15.01,15.03-15.06": [
                    "15.01", "15.03", "15.04", "15.05", "15.06"
                ],
            },
        },
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    assert "15.01,15.03-15.06 Transport non-road" not in set(
        resolved["common_flow_label"]
    )
    assert "15.01 Domestic air transport" in set(resolved["common_flow_label"])


def test_compound_alias_prefers_canonical_child_label_over_stale_duplicate() -> None:
    canonical = "15.01 Domestic air transport"
    stale = "15.01,15.03-15.06 Transport non-road"
    chart_rows = pd.DataFrame([
        {
            **_area_product_row("ESTO_EXTENDED", "historical", 2022, "15.01", "07.05", 6.0),
            "common_flow_label": canonical,
        },
        {
            **_area_product_row("ESTO_EXTENDED", "historical", 2022, "15.01", "17", 4.0),
            "common_flow_label": canonical,
        },
        {
            **_area_product_row("LEAP", "Target", 2023, "15.01", "07.05", 7.0),
            "common_flow_label": canonical,
        },
    ])
    source_rows = pd.concat([
        chart_rows,
        pd.DataFrame([
            {
                **_area_product_row("ESTO_EXTENDED", "historical", 2022, "15.01-15.06", "07.05", 6.0),
                "common_flow_code": "15.01,15.03-15.06",
                "common_flow_label": stale,
            },
            {
                **_area_product_row("ESTO_EXTENDED", "historical", 2022, "15.01-15.06", "17", 4.0),
                "common_flow_code": "15.01,15.03-15.06",
                "common_flow_label": stale,
            },
        ]),
    ], ignore_index=True)
    # Reproduce a source where the first label seen on the child code is stale,
    # while another product row retains the canonical published child label.
    source_rows.loc[0, "common_flow_label"] = stale

    resolved = renderer.collapse_compound_projection_to_historical_child(
        chart_rows,
        source_rows,
        {
            "collapse_compound_to_historical_child": {
                "15.01,15.03-15.06": [
                    "15.01", "15.03", "15.04", "15.05", "15.06"
                ],
            },
        },
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    assert set(resolved["common_flow_label"]) == {canonical}


def test_corrected_compound_label_updates_immediate_child_grouping() -> None:
    rows = pd.DataFrame([{
        "common_flow_code": "15.01",
        "common_flow_label": "15.01 Domestic air transport",
        "_child_flow_label": "15.01,15.03-15.06 Transport non-road",
        "value": 10.0,
    }])

    resolved = renderer.synchronize_compound_grouping_labels(
        rows,
        {
            "collapse_compound_to_historical_child": {
                "15.01,15.03-15.06": [
                    "15.01", "15.03", "15.04", "15.05", "15.06"
                ],
            },
        },
        "_child_flow_label",
    )

    assert resolved["_child_flow_label"].tolist() == [
        "15.01 Domestic air transport"
    ]


def test_transport_root_flow_overview_enables_nonroad_child_label_collapse() -> None:
    specs = renderer.prepare_area_specs_for_page(
        "transport",
        pd.DataFrame(),
        [{
            "aggregate_flow_prefix": "15",
            "overview_variant": "by_flow",
        }],
        {
            "transport_page": {
                "page_key": "transport",
                "by_flow_overview": {
                    "flow_boundary": "15",
                    "prefer_detail_frontier": True,
                    "collapse_compound_to_child": {
                        "15.01,15.03-15.06": [
                            "15.01", "15.03", "15.04", "15.05", "15.06"
                        ],
                    },
                },
            },
        },
    )

    assert specs[0]["collapse_compound_to_historical_child"] == {
        "15.01,15.03-15.06": [
            "15.01", "15.03", "15.04", "15.05", "15.06"
        ],
    }
    assert specs[0]["use_demand_coverage_frontier"] is True
    assert specs[0]["prefer_transport_detail_frontier"] is True


def test_other_demand_chart_uses_economy_verified_child_after_page_pruning() -> None:
    """A documented economy rule survives removal of the exact child rows."""
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03", "17", 20.0
            ),
            "economy": "01_AUS",
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2023, "16.03-16.05", "17", 21.0
            ),
            "economy": "01_AUS",
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
        },
    ])
    resolved = renderer.collapse_compound_projection_to_historical_child(
        rows,
        rows,
        {
            "collapse_compound_to_historical_child": {
                "16.03-16.04": ["16.03", "16.04"],
            },
            "verified_compound_child_by_economy": {
                "01AUS": {
                    "16.03-16.04": {
                        "code": "16.03",
                        "label": "16.03 Agriculture",
                    },
                },
            },
        },
        comparison_source="ESTO_EXTENDED",
        base_year=2022,
    )

    projected = resolved[resolved["year"].eq(2023)]
    assert projected["common_flow_code"].tolist() == ["16.03"]
    assert projected["common_flow_label"].tolist() == ["16.03 Agriculture"]


def test_other_demand_by_flow_labels_parent_gap_as_unallocated() -> None:
    """Incomplete child coverage is not attributed without source evidence."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": ["16.03", "16.04", "16.05"],
                "detail_coverage_residual_label": (
                    "Unallocated within 16.03-16.05 Other demand"
                ),
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2018, "16.03-16.05", "17", 30.0
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2018, "16.03", "17", 20.0
            ),
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2018, "16.05", "17", 5.0
            ),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])

    spec = next(
        spec
        for spec in renderer.add_other_demand_flow_overview_spec(
            "others", rows, [], template
        )
        if spec.get("overview_variant") == "by_flow"
    )
    resolved = renderer.resolved_area_chart_rows(
        rows,
        spec,
        group_col="common_flow_label",
    )

    assert set(resolved["common_flow_label"]) == {
        "16.03 Agriculture",
        "16.05 Non-specified others",
        "Unallocated within 16.03-16.05 Other demand",
    }
    assert "16.03-16.05 Other sector" not in set(resolved["common_flow_label"])
    residual = resolved.loc[
        resolved["common_flow_code"].eq("16.03-16.05 residual"),
        "value",
    ]
    assert residual.tolist() == [5.0]
    assert resolved["value"].sum() == 30.0


def test_other_demand_by_flow_does_not_repeat_compound_and_child_frontiers() -> None:
    """A preferred compound boundary owns its contained simple child rows."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": [
                    "16.03-16.04", "16.03", "16.04", "16.05"
                ],
                "detail_coverage_residual_label": "Unallocated",
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.05", "17", 30.0
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.04", "17", 20.0
            ),
            "common_flow_label": "16.03-16.04 Agriculture and fishing",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03", "17", 20.0
            ),
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.05", "17", 10.0
            ),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])

    spec = next(
        spec
        for spec in renderer.add_other_demand_flow_overview_spec(
            "others", rows, [], template
        )
        if spec.get("overview_variant") == "by_flow"
    )
    resolved = renderer.resolved_area_chart_rows(
        rows, spec, group_col="common_flow_label"
    )

    assert set(resolved["common_flow_code"]) == {"16.03-16.04", "16.05"}
    assert resolved["value"].sum() == pytest.approx(30.0)
    assert not resolved["common_flow_label"].eq("Unallocated").any()


def test_other_demand_by_flow_deduplicates_compound_fallback_child() -> None:
    """A missing compound row must not select its fallback child twice."""
    template = {
        "other_demand_page": {
            "page_key": "others",
            "by_flow_overview": {
                "enabled": True,
                "flow_boundary": "16.03-16.05",
                "label": "16.03-16.05 Other sector",
                "preferred_detail_flow_boundaries": [
                    "16.03-16.04", "16.03", "16.04", "16.05"
                ],
                "detail_coverage_residual_label": "Unallocated",
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03-16.05", "17", 30.0
            ),
            "common_flow_label": "16.03-16.05 Other sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.03", "17", 20.0
            ),
            "common_flow_label": "16.03 Agriculture",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "16.05", "17", 5.0
            ),
            "common_flow_label": "16.05 Non-specified others",
            "common_product_label": "17 Electricity",
        },
    ])

    spec = next(
        spec
        for spec in renderer.add_other_demand_flow_overview_spec(
            "others", rows, [], template
        )
        if spec.get("overview_variant") == "by_flow"
    )
    resolved = renderer.resolved_area_chart_rows(
        rows, spec, group_col="common_flow_label"
    )

    agriculture = resolved.loc[
        resolved["common_flow_code"].eq("16.03"), "value"
    ]
    assert agriculture.tolist() == [20.0]
    assert resolved.loc[resolved["common_flow_label"].eq("Unallocated"), "value"].tolist() == [5.0]
    assert resolved["value"].sum() == pytest.approx(30.0)


def test_detailed_buildings_overview_uses_only_two_configured_pairs() -> None:
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "buildings_page": {
            "page_key": "buildings",
            "overview": {
                "enabled": True,
                "aggregates": [
                    {
                        "flow_boundary": "16.01-16.02",
                        "label": "16.01-16.02 Buildings",
                        "preferred_detail_flow_boundaries": ["16.01", "16.02"],
                        "flow_groups": [
                            {"flow_boundary": "16.01", "label": "16.01 Services"},
                            {"flow_boundary": "16.02", "label": "16.02 Residential"},
                        ],
                    },
                    {
                        "flow_boundary": "16.01",
                        "label": "16.01 Commercial and public services",
                        "preferred_detail_flow_boundaries": [
                            "16.01.01", "16.01.99"
                        ],
                        "flow_groups": [
                            {"flow_boundary": "16.01.01", "label": "16.01.01 Datacentres"},
                            {"flow_boundary": "16.01.99", "label": "16.01.99 Unallocated"},
                        ],
                    },
                ],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "Target", 2023, code, "17", value),
            "common_flow_label": label,
            "common_product_label": "17 Electricity",
        }
        for code, label, value in [
            ("16.01-16.02", "16.01-16.02 Buildings", 30.0),
            ("16.01", "16.01 Commercial and public services", 20.0),
            ("16.02", "16.02 Residential", 10.0),
            ("16.01.01", "16.01.01 Datacentres", 5.0),
            (
                "16.01.99",
                "16.01.99 Commercial and public services unallocated",
                15.0,
            ),
        ]
    ])
    generic = [{
        "aggregate_flow_prefix": "16",
        "aggregate_flow_label": "16 Buildings",
    }]

    specs = renderer.add_buildings_overview_specs(
        "buildings", rows, generic, template
    )

    assert [spec["chart_caption"] for spec in specs] == [
        "16.01-16.02 Buildings — by product",
        "16.01-16.02 Buildings — by flow",
        "16.01 Commercial and public services — by product",
        "16.01 Commercial and public services — by flow",
    ]
    whole_rows = renderer.configured_flow_group_rows(
        rows, specs[1]["configured_flow_groups"]
    )
    whole_flow = renderer.resolved_area_chart_rows(
        whole_rows, specs[1], group_col="_configured_flow_group_label"
    )
    assert set(whole_flow["_configured_flow_group_label"]) == {
        "16.01 Services", "16.02 Residential"
    }
    assert whole_flow["value"].sum() == pytest.approx(30.0)
    services_rows = renderer.configured_flow_group_rows(
        rows, specs[3]["configured_flow_groups"]
    )
    services_flow = renderer.resolved_area_chart_rows(
        services_rows, specs[3], group_col="_configured_flow_group_label"
    )
    assert set(services_flow["_configured_flow_group_label"]) == {
        "16.01.01 Datacentres", "16.01.99 Unallocated"
    }
    assert services_flow["value"].sum() == pytest.approx(20.0)


def test_detailed_road_section_keeps_only_technology_summary_under_road() -> None:
    """Detailed Road has one technology summary, owned by Road navigation."""
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.01.01.01", "17", 8.0
            ),
            "common_flow_label": "15.02.01.01.01 BEV",
            "common_product_label": "17 Electricity",
            "_section_label": "Transport",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.01.01.02", "07.01", 12.0
            ),
            "common_flow_label": "15.02.01.01.02 ICE",
            "common_product_label": "07.01 Motor gasoline",
            "_section_label": "Transport",
        },
    ])
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        },
        "section_aggregate_overrides": {
            "transport": {
                "Transport": {
                    "required_flow_boundary": "15.02",
                    "include_groupings": ["flow"],
                    "grouping_titles": {
                        "flow": "15.02 Road — detailed model by technology",
                    },
                    "navigation_owner": "15.02 Road",
                    "section_label": "15.02 Road — by product",
                }
            }
        },
    }

    charts, chart_rows, manifest_rows = renderer._build_section_aggregate_charts(
        rows,
        "transport",
        "Transport",
        set(),
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    assert set(charts) == {"chart__area__section__transport__transport__flow"}
    assert not any(row["chart_key"].endswith("__product") for row in manifest_rows)
    assert len(chart_rows) == 1
    assert chart_rows[0]["title"] == "15.02 Road — detailed model by technology"
    assert chart_rows[0]["section_label"] == "15.02 Road — by product"
    assert chart_rows[0]["flow_group_label"] == "15.02 Road"
    assert chart_rows[0]["content_kind"] == "technology_overview"
    assert charts[chart_rows[0]["chart_key"]].layout.title.text == (
        "15.02 Road — detailed model by technology"
    )

    html = renderer._line_sections_html(
        [
            *chart_rows,
            {
                "chart_key": "road-product",
                "chart_type": "line",
                "title": "Road fuel",
                "product_label": "Road fuel",
                "section_label": "15.02 Road — by product",
                "flow_group_label": "15.02 Road",
                "content_kind": "by_product",
            },
            {
                "chart_key": "freight-product",
                "chart_type": "line",
                "title": "Freight fuel",
                "product_label": "Freight fuel",
                "section_label": "Transport",
                "flow_group_label": "15.02.01 Freight road",
                "content_kind": "by_product",
            },
        ],
        "Transport",
    )
    assert html.index("15.02 Road — detailed model by technology") < html.index(
        "Road fuel"
    )
    tree = renderer.line_section_tree(
        [
            *chart_rows,
            {
                "section_label": "15.02 Road — by product",
                "flow_group_label": "15.02 Road",
            },
        ]
    )
    assert sum(
        node["label"] == "15.02 Road"
        for _section, nodes in tree
        for node in nodes
    ) == 1


def test_detailed_road_section_override_remains_component_local() -> None:
    """Detailed non-road rows do not leak into the Road-owned aggregate."""
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.01", "07.01", 12.0
            ),
            "common_flow_label": "15.02.01 Freight road",
            "_section_label": "Transport",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.02", "07.01", 8.0
            ),
            "common_flow_label": "15.02.02 Passenger road",
            "_section_label": "Transport",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.03", "07.01", 3.0
            ),
            "common_flow_label": "15.03 Rail",
            "_section_label": "Transport",
        },
    ])
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        },
        "section_aggregate_overrides": {
            "transport": {
                "Transport": {
                    "required_flow_boundary": "15.02",
                    "include_groupings": ["flow"],
                    "navigation_owner": "15.02 Road",
                }
            }
        },
    }

    charts, chart_rows, _ = renderer._build_section_aggregate_charts(
        rows,
        "transport",
        "Transport",
        set(),
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    assert set(charts) == {
        "chart__area__section__transport__transport__flow",
    }
    assert all(
        "rail" not in str(trace.name).casefold()
        for trace in charts[
            "chart__area__section__transport__transport__flow"
        ].data
    )
    assert {row.get("flow_group_label") for row in chart_rows} == {"15.02 Road"}


def _passenger_road_hierarchy_rows(second_child_value: float) -> pd.DataFrame:
    rows = []
    for flow, label, value in (
        ("15.02.02", "15.02.02 Passenger road", 30.0),
        ("15.02.02.01", "15.02.02.01 Buses", 10.0),
        ("15.02.02.02", "15.02.02.02 LPVs", second_child_value),
    ):
        row = _area_product_row(
            "LEAP", "Target", 2030, flow, "07.01", value
        )
        row.update({
            "common_flow_label": label,
            "common_product_label": "07.01 Motor gasoline",
            "_section_label": "Transport",
        })
        rows.append(row)
    return pd.DataFrame(rows)


def test_top_two_hierarchy_levels_emit_only_qualifying_pairs() -> None:
    rows = []
    for flow, label, value in (
        ("15", "15 Transport sector", 60.0),
        ("15.01", "15.01 Transport non-road", 10.0),
        ("15.02", "15.02 Road", 50.0),
        ("15.02.01", "15.02.01 Freight road", 20.0),
        ("15.02.02", "15.02.02 Passenger road", 30.0),
    ):
        row = _area_product_row(
            "LEAP", "Target", 2030, flow, "07.01", value
        )
        row.update({
            "common_flow_label": label,
            "common_product_label": "07.01 Motor gasoline",
        })
        rows.append(row)
    specs = renderer.pick_area_specs(
        pd.DataFrame(rows),
        {
            "chart_generation": {
                "deep_chain_min_depth": 3,
                "top_levels_for_deep_chains": 2,
                "max_area_charts_per_page": 30,
            },
            "aggregate_chart_policy": {
                "minimum_nonzero_child_flows": 2,
            },
        },
        page_key="transport",
    )

    assert [spec["aggregate_flow_prefix"] for spec in specs] == [
        "15", "15", "15.02", "15.02"
    ]
    assert [spec.get("group_col", "common_product_label") for spec in specs] == [
        "common_product_label", "_child_flow_label",
        "common_product_label", "_child_flow_label",
    ]


def test_explicit_leaf_aggregate_exception_keeps_product_summary_only() -> None:
    row = _area_product_row(
        "LEAP", "Target", 2030, "17", "07.12-07.17", 5.0
    )
    row.update({
        "common_flow_label": "17 Non-energy use",
        "common_product_label": "07.12-07.17 Petroleum products",
    })
    specs = renderer.pick_area_specs(
        pd.DataFrame([row]),
        {
            "chart_generation": {},
            "aggregate_chart_policy": {
                "minimum_nonzero_child_flows": 2,
                "always_show_flow_codes_by_page": {"industry": ["17"]},
            },
        },
        page_key="industry",
    )

    assert len(specs) == 1
    assert specs[0]["aggregate_flow_prefix"] == "17"
    assert specs[0].get("group_col", "common_product_label") == (
        "common_product_label"
    )


def test_parent_product_summary_adds_flow_companion_for_two_nonzero_children() -> None:
    """Passenger road gains a child-flow view without losing its fuel view."""
    rows = _passenger_road_hierarchy_rows(second_child_value=20.0)
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        },
    }

    charts, chart_rows, _ = renderer._build_flow_group_aggregate_charts(
        rows,
        "transport",
        "Transport",
        {"15.02.02 Passenger road"},
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    parent_rows = [
        row for row in chart_rows
        if row.get("flow_group_label") == "15.02.02 Passenger road"
    ]
    assert {row["content_kind"] for row in parent_rows} == {
        "by_product",
        "by_flow",
    }
    flow_row = next(row for row in parent_rows if row["content_kind"] == "by_flow")
    flow_figure = charts[flow_row["chart_key"]]
    area_names = {
        str(trace.name)
        for trace in flow_figure.data
        if str(getattr(trace, "stackgroup", "") or "")
    }
    assert area_names == {"15.02.02.01 Buses", "15.02.02.02 LPVs"}


def test_parent_product_summary_omits_flow_companion_for_one_nonzero_child() -> None:
    """A zero-only sibling suppresses the whole redundant aggregate pair."""
    rows = _passenger_road_hierarchy_rows(second_child_value=0.0)
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        },
    }

    _charts, chart_rows, _ = renderer._build_flow_group_aggregate_charts(
        rows,
        "transport",
        "Transport",
        {"15.02.02 Passenger road"},
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    parent_rows = [
        row for row in chart_rows
        if row.get("flow_group_label") == "15.02.02 Passenger road"
    ]
    assert parent_rows == []


def test_parent_flow_companion_defers_to_configured_flow_overview() -> None:
    """A bespoke technology overview keeps sole ownership of its boundary."""
    rows = _passenger_road_hierarchy_rows(second_child_value=20.0)
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "ninth_source_system": "NINTH",
            "base_year": 2022,
            "chart_suppression_threshold": 0.0,
        },
        "section_aggregate_overrides": {
            "transport": {
                "Transport": {
                    "required_flow_boundary": "15.02.02",
                    "include_groupings": ["flow"],
                },
            },
        },
    }

    _charts, chart_rows, _ = renderer._build_flow_group_aggregate_charts(
        rows,
        "transport",
        "Transport",
        {"15.02.02 Passenger road"},
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    parent_rows = [
        row for row in chart_rows
        if row.get("flow_group_label") == "15.02.02 Passenger road"
    ]
    assert parent_rows == []


def test_power_navigation_marks_only_active_interim_rollup_owners() -> None:
    """Interim branches map to ESTO plant roll-ups, not CHP child names."""
    template = {
        "_power_interim_placeholder_branches": [
            "Electricity interim",
            "CHP interim",
        ],
        "placeholder_navigation": {
            "power": {
                "interim_branch_owners": [
                    {
                        "interim_branch": "Electricity interim",
                        "flow_code": "09.01.01,09.02.01",
                        "label": "09.01.01,09.02.01 Electricity plants",
                    },
                    {
                        "interim_branch": "CHP interim",
                        "flow_code": "09.01.02,09.02.02",
                        "label": "09.01.02,09.02.02 CHP plants",
                    },
                    {
                        "interim_branch": "Heat plant interim",
                        "flow_code": "09.01.03,09.02.03",
                        "label": "09.01.03,09.02.03 Heat plants",
                    },
                ]
            }
        },
    }
    assert renderer.active_power_placeholder_product_sections(template) == [
        {
            "interim_branch": "Electricity interim",
            "flow_code": "09.01.01,09.02.01",
            "label": "09.01.01,09.02.01 Electricity plants",
        },
        {
            "interim_branch": "CHP interim",
            "flow_code": "09.01.02,09.02.02",
            "label": "09.01.02,09.02.02 CHP plants",
        },
    ]

    line_rows = [
        {
            "section_label": "Power",
            "flow_group_label": "09.01.01,09.02.01 Electricity plants",
        },
        {
            "section_label": "Power",
            "flow_group_label": "09.01.02,09.02.02 CHP plants",
        },
        {
            "section_label": "Power",
            "flow_group_label": "Gas CHP (all producers)",
        },
        {
            "section_label": "Power",
            "flow_group_label": "10.01.01 Electricity, CHP and heat plants",
        },
    ]
    renderer.mark_active_placeholder_navigation("power", line_rows, template)

    tree = renderer.line_section_tree(line_rows)
    nodes = [node for _section, section_nodes in tree for node in section_nodes]
    placeholder_labels = {
        node["label"] for node in nodes if node["placeholder"]
    }
    assert placeholder_labels == {
        "09.01.01,09.02.01 Electricity plants",
        "09.01.02,09.02.02 CHP plants",
    }

    html = renderer._jump_nav_html("Power", tree)
    assert html.count('data-placeholder="true"') == 2
    assert html.count("jump-placeholder-label") == 2
    assert "Gas CHP (all producers)" in html
    assert 'data-placeholder="false">Gas CHP (all producers)' in html


def test_power_overview_publishes_flow_pair_and_product_only_leaf() -> None:
    """Power keeps product summaries while requiring children for by-flow."""
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "power_page": {
            "page_key": "power",
            "overview": {
                "enabled": True,
                "replace_overview_flow_codes": [
                    "09", "09.01", "10", "10.01", "10.02"
                ],
                "aggregates": [
                    {
                        "flow_boundary": "09.01-09.02",
                        "child_flow_parent_prefix": "09.01",
                        "label": "09.01-09.02 Power generation",
                    },
                    {
                        "flow_boundary": "10.01,10.02",
                        "child_flow_parent_prefix": "10",
                        "label": "Power-related losses and own use",
                        "child_flow_labels": {
                            "10.01": "10.01 Own use",
                            "10.02": "10.02 Transmission and distribution losses",
                        },
                    },
                    {
                        "flow_boundary": "10.01",
                        "child_flow_parent_prefix": "10.01",
                        "label": "10.01 Own use",
                    },
                    {
                        "flow_boundary": "10.02",
                        "child_flow_parent_prefix": "10.02",
                        "label": "10.02 Transmission and distribution losses",
                    },
                ],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01-09.02", "17", 100.0
            ),
            "common_flow_label": "09.01-09.02 Power sector",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01", "17", 60.0
            ),
            "common_flow_label": "09.01.01 Electricity plants",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.02", "17", 40.0
            ),
            "common_flow_label": "09.01.02 CHP plants",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "10.01.01", "17", -5.0
            ),
            "common_flow_label": "10.01.01 Electricity, CHP and heat plants",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "10.01.13", "17", -2.0
            ),
            "common_flow_label": "10.01.13 Pump storage plants",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "10.02", "17", -3.0),
            "common_flow_label": "10.02 Transmission and distribution losses",
            "common_product_label": "17 Electricity",
        },
    ])
    generic_specs = [
        {
            "aggregate_flow_prefix": "09",
            "aggregate_flow_label": "09.01-09.02 Power sector",
            "source_flow_labels": ["09.01-09.02 Power sector"],
        },
        {
            "aggregate_flow_prefix": "10",
            "aggregate_flow_label": "10 Losses and own use",
            "source_flow_labels": ["10 Losses and own use"],
        },
    ]

    specs = renderer.add_power_sector_overview_specs(
        "power", rows, generic_specs, template
    )

    assert len(specs) == 7
    assert {
        spec["aggregate_flow_label"] for spec in specs
    } == {
        "09.01-09.02 Power generation",
        "Power-related losses and own use",
        "10.01 Own use",
        "10.02 Transmission and distribution losses",
    }
    assert all(
        sum(
            spec["aggregate_flow_label"] == label
            for spec in specs
        ) == 2
        for label in {
            "09.01-09.02 Power generation",
            "Power-related losses and own use",
            "10.01 Own use",
        }
    )
    losses_leaf_specs = [
        spec for spec in specs
        if spec["aggregate_flow_label"].startswith("10.02")
    ]
    assert len(losses_leaf_specs) == 1
    assert losses_leaf_specs[0]["group_col"] == "common_product_label"
    losses_flow_spec = next(
        spec for spec in specs
        if spec["aggregate_flow_label"] == "Power-related losses and own use"
        and spec["group_col"] == "_child_flow_label"
    )
    child_rows = renderer.immediate_child_flow_rows(
        renderer.area_spec_rows(rows, losses_flow_spec),
        renderer.get_existing_flow_nodes(rows),
        "10",
        losses_flow_spec["immediate_child_flow_labels"],
    )
    resolved = renderer.resolved_area_chart_rows(
        child_rows,
        losses_flow_spec,
        group_col="_child_flow_label",
    )
    assert set(resolved["_child_flow_label"]) == {
        "10.01 Own use",
        "10.02 Transmission and distribution losses",
    }
    assert resolved["value"].sum() == -10.0


def test_power_plant_overview_can_promote_itself_to_navigation_root() -> None:
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "power_page": {
            "page_key": "power",
            "overview": {
                "enabled": True,
                "aggregates": [{
                    "flow_boundary": "09.01.01,09.02.01",
                    "child_flow_parent_prefix": "09.01.01",
                    "label": "09.01.01,09.02.01 Electricity plants",
                    "navigation_root": True,
                }],
            },
        },
    }
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01.01", "17", 60.0
            ),
            "common_flow_label": "Coal power (all producers)",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01.02", "17", 40.0
            ),
            "common_flow_label": "Gas power (all producers)",
            "common_product_label": "17 Electricity",
        },
    ])

    specs = renderer.add_power_sector_overview_specs(
        "power", rows, [], template
    )

    assert len(specs) == 2
    assert all(spec["force_navigation_root"] for spec in specs)
    roots = [
        {
            "label": "09.01-09.02 Power",
            "target": "overview-power__09_01_09_02_power",
            "force_top_level": True,
        },
        {
            "label": specs[0]["aggregate_flow_label"],
            "target": "overview-power__09_01_01_09_02_01_electricity_plants",
            "force_top_level": True,
        },
    ]
    tree = renderer.line_section_tree(
        [{
            "section_label": "Power generation and transformation",
            "flow_group_label": "Coal power (all producers)",
        }],
        roots,
    )
    html = renderer._jump_nav_html("Power", tree)
    assert (
        'data-level="1" data-hierarchy-depth="1" data-placeholder="false">'
        '09.01.01,09.02.01 Electricity plants</a>'
    ) in html
    assert (
        'data-level="1" data-hierarchy-depth="1" data-placeholder="false">'
        '09.01-09.02 Power</a>'
    ) in html


def test_power_by_flow_reconciles_process_detail_to_product_frontier() -> None:
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01,09.02.01", "17", -100.0
            ),
            "common_flow_label": "09.01.01,09.02.01 Electricity plants",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01.01", "17", -100.0
            ),
            "common_flow_label": "Coal power (all producers)",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01.02", "17", -100.0
            ),
            "common_flow_label": "Gas power (all producers)",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "09.01.01,09.02.01", "18", 40.0
            ),
            "common_flow_label": "09.01.01,09.02.01 Electricity plants",
            "common_product_label": "18 Heat",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030,
                "09.01.01.01,09.02.01.01", "18", 40.0
            ),
            "common_flow_label": "Coal power (all producers)",
            "common_product_label": "18 Heat",
        },
    ])
    spec = {
        "aggregate_flow_prefix": "09.01.01,09.02.01",
        "aggregate_flow_label": "09.01.01,09.02.01 Electricity plants",
        "explicit_flow_boundary": True,
    }

    flow_rows = renderer.reconciled_immediate_child_flow_rows(
        rows,
        renderer.get_existing_flow_nodes(rows),
        "09.01.01",
        spec,
    )

    totals = flow_rows.groupby("common_product_code")["value"].sum().to_dict()
    assert totals == pytest.approx({"17": -100.0, "18": 40.0})
    electricity = flow_rows[flow_rows["common_product_code"].eq("17")]
    assert electricity.set_index("_child_flow_label")["value"].to_dict() == {
        "Coal power (all producers)": -50.0,
        "Gas power (all producers)": -50.0,
    }
    assert set(flow_rows["_child_flow_label"]) == {
        "Coal power (all producers)",
        "Gas power (all producers)",
    }


def test_power_by_flow_keeps_siblings_of_compound_interim_child() -> None:
    """A repeated plant parent inside one child cannot suppress its siblings."""
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "NINTH",
                "Target",
                2030,
                "09.01.02,09.02.02,09.01.02.01,09.02.02.01",
                "17",
                100.0,
            ),
            "common_flow_label": "Total transformation - no transfers",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2030,
                "09.01.02.02,09.02.02.02", "17", 60.0
            ),
            "common_flow_label": "Gas CHP (all producers)",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2030,
                "09.01.02.03,09.02.02.03", "17", 40.0
            ),
            "common_flow_label": "Others CHP (all producers)",
            "common_product_label": "17 Electricity",
        },
    ])
    spec = {
        "aggregate_flow_prefix": "09.01.02,09.02.02",
        "aggregate_flow_label": "09.01.02,09.02.02 CHP plants",
        "explicit_flow_boundary": True,
    }

    child_count = renderer.nonzero_immediate_child_flow_count(
        rows,
        renderer.get_existing_flow_nodes(rows),
        "09.01.02",
        spec,
    )
    flow_rows = renderer.reconciled_immediate_child_flow_rows(
        rows,
        renderer.get_existing_flow_nodes(rows),
        "09.01.02",
        spec,
    )

    assert child_count == 3
    assert set(flow_rows["_child_flow_label"]) == {
        "Total transformation - no transfers",
        "Gas CHP (all producers)",
        "Others CHP (all producers)",
    }
    assert flow_rows["value"].sum() == 100.0


def test_power_by_flow_reconciles_uncoded_all_producer_processes() -> None:
    """Wide scopes can retain process labels without hierarchy flow codes."""
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030,
                "09.01.02,09.02.02", "17", 100.0,
            ),
            "common_flow_label": "09.01.02,09.02.02 CHP plants",
            "common_product_label": "17 Electricity",
            "is_non_expanding_rollup": True,
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "Gas", "17", 60.0,
            ),
            "common_flow_label": "Gas CHP (all producers)",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "Others", "17", 40.0,
            ),
            "common_flow_label": "Others CHP (all producers)",
            "common_product_label": "17 Electricity",
        },
    ])
    spec = {
        "aggregate_flow_prefix": "09.01.02,09.02.02",
        "aggregate_flow_label": "09.01.02,09.02.02 CHP plants",
        "explicit_flow_boundary": True,
    }

    flow_rows = renderer.reconciled_immediate_child_flow_rows(
        rows,
        renderer.get_existing_flow_nodes(rows),
        "09.01.02",
        spec,
    )

    assert set(flow_rows["_child_flow_label"]) == {
        "Gas CHP (all producers)",
        "Others CHP (all producers)",
    }
    assert flow_rows.groupby("_child_flow_label")["value"].sum().to_dict() == {
        "Gas CHP (all producers)": 60.0,
        "Others CHP (all producers)": 40.0,
    }


def test_power_own_use_navigation_stays_below_primary_owners() -> None:
    tree = renderer.line_section_tree(
        [{
            "section_label": "Power-sector own use and storage",
            "flow_group_label": "10.01.01 Electricity, CHP and heat plants",
        }],
        navigation_depth_overrides={
            "10.01.01 Electricity, CHP and heat plants": 2,
        },
    )

    node = tree[0][1][0]
    assert node["label"] == "10.01.01 Electricity, CHP and heat plants"
    assert node["depth"] == 2


def test_power_plant_overview_keeps_product_card_when_only_one_child_is_nonzero() -> None:
    template = {
        "aggregate_chart_policy": {"minimum_nonzero_child_flows": 2},
        "power_page": {
            "page_key": "power",
            "overview": {
                "enabled": True,
                "aggregates": [{
                    "flow_boundary": "09.01.03,09.02.03",
                    "child_flow_parent_prefix": "09.01.03",
                    "label": "09.01.03,09.02.03 Heat plants",
                    "navigation_root": True,
                }],
            },
        },
    }
    rows = pd.DataFrame([{
        **_area_product_row(
            "LEAP", "Target", 2030, "09.01.03.01", "18", 60.0
        ),
        "common_flow_label": "Coal HP (all producers)",
        "common_product_label": "18 Heat",
    }])

    specs = renderer.add_power_sector_overview_specs(
        "power", rows, [], template
    )

    assert len(specs) == 1
    assert specs[0]["group_col"] == "common_product_label"
    assert specs[0]["force_navigation_root"] is True


def test_power_residual_section_has_clear_name_and_no_duplicate_summary() -> None:
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "10.01.01", "17", -5.0
            ),
            "common_flow_label": "10.01.01 Electricity, CHP and heat plants",
            "common_product_label": "17 Electricity",
            "_section_label": "Power",
        },
    ])
    prepared = renderer.prepare_power_page_rows(rows)
    assert prepared["_section_label"].tolist() == [
        "Power-sector own use and storage"
    ]
    template = {
        "section_aggregate_overrides": {
            "power": {
                "Power-sector own use and storage": {
                    "hide_aggregate": True,
                },
            },
        },
    }

    charts, chart_rows, manifest_rows = renderer._build_section_aggregate_charts(
        prepared,
        "power",
        "Power",
        set(),
        template,
        {"LEAP|Target": "LEAP Target"},
    )

    assert charts == {}
    assert chart_rows == []
    assert manifest_rows == []


def _demand_frontier_row(
    source: str,
    flow: str,
    value: float,
    product: str = "07.07",
) -> dict[str, object]:
    return {
        "comparison_scope": "esto_extended_leap_ninth",
        "source_system": source,
        "economy": "01_AUS",
        "scenario": "Target",
        "year": 2023,
        "common_flow_code": flow,
        "common_flow_label": flow,
        "common_product_code": product,
        "common_product_label": product,
        "is_non_expanding_rollup": flow == "15.01,15.03-15.06",
        "value": value,
    }


def test_mixed_transport_frontier_keeps_detailed_road_and_placeholder_nonroad() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "15", 100.0),
        _demand_frontier_row("LEAP", "15.02", 100.0),
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 25.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01,15.03-15.06"
    }
    assert selected["value"].sum() == 125.0


def test_mixed_transport_frontier_stops_at_road_before_technology_detail() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "15", 100.0),
        _demand_frontier_row("LEAP", "15.02", 100.0),
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 25.0),
        _demand_frontier_row("LEAP", "15.02.01", 60.0),
        _demand_frontier_row("LEAP", "15.02.02", 40.0),
        _demand_frontier_row("LEAP", "15.02.01.01.02", 60.0),
        _demand_frontier_row("LEAP", "15.02.02.02.12", 40.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01,15.03-15.06"
    }
    assert selected["value"].sum() == 125.0


def test_mixed_transport_frontier_replaces_nonroad_rollup_with_published_children() -> None:
    """A detailed non-road branch replaces, rather than supplements, its rollup."""
    rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "15.02", 100.0),
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 30.0),
        _demand_frontier_row("LEAP", "15.01", 10.0),
        _demand_frontier_row("LEAP", "15.03", 8.0),
        _demand_frontier_row("LEAP", "15.04", 6.0),
        _demand_frontier_row("LEAP", "15.05", 4.0),
        _demand_frontier_row("LEAP", "15.06", 2.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01", "15.03", "15.04", "15.05", "15.06"
    }
    assert "15.01,15.03-15.06" not in set(selected["common_flow_code"])
    assert selected["value"].sum() == 130.0


def test_transport_frontier_uses_reconciled_nonroad_children_across_products() -> None:
    """A compound rollup cannot survive merely because its product grain differs."""
    rows = pd.DataFrame([
        _demand_frontier_row("ESTO_EXTENDED", "15.02", 100.0),
        _demand_frontier_row(
            "ESTO_EXTENDED", "15.01,15.03-15.06", 30.0, "07.04-07.05"
        ),
        _demand_frontier_row("ESTO_EXTENDED", "15.01", 10.0, "07.05"),
        _demand_frontier_row("ESTO_EXTENDED", "15.03", 8.0, "07.07"),
        _demand_frontier_row("ESTO_EXTENDED", "15.04", 6.0, "07.08"),
        _demand_frontier_row("ESTO_EXTENDED", "15.05", 4.0, "08.01"),
        _demand_frontier_row("ESTO_EXTENDED", "15.06", 2.0, "17"),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01", "15.03", "15.04", "15.05", "15.06"
    }
    assert selected["value"].sum() == 130.0


def test_transport_frontier_prefers_populated_children_to_mislabeled_compound() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row(
            "LEAP", "15.01,15.03-15.06", 31.0, "07.04-07.05"
        ),
        _demand_frontier_row("LEAP", "15.01", 10.0, "07.05"),
        _demand_frontier_row("LEAP", "15.03", 8.0, "07.07"),
        _demand_frontier_row("LEAP", "15.04", 6.0, "07.08"),
        _demand_frontier_row("LEAP", "15.05", 4.0, "08.01"),
        _demand_frontier_row("LEAP", "15.06", 2.0, "17"),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert set(selected["common_flow_code"]) == {
        "15.01", "15.03", "15.04", "15.05", "15.06"
    }
    assert selected["value"].sum() == 30.0


def test_transport_frontier_keeps_compound_for_one_partial_child() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 31.0),
        _demand_frontier_row("LEAP", "15.01", 10.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert selected[["common_flow_code", "value"]].to_dict("records") == [
        {"common_flow_code": "15.01,15.03-15.06", "value": 31.0}
    ]


def test_transport_frontier_switches_from_placeholder_to_detail_by_year() -> None:
    rows = pd.DataFrame([
        {
            **_demand_frontier_row(
                "LEAP", "15.01,15.03-15.06", 30.0
            ),
            "year": 2023,
        },
        {
            **_demand_frontier_row(
                "LEAP", "15.01,15.03-15.06", 31.0
            ),
            "year": 2024,
        },
        {**_demand_frontier_row("LEAP", "15.01", 11.0), "year": 2024},
        {**_demand_frontier_row("LEAP", "15.03", 20.0), "year": 2024},
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert selected[selected["year"].eq(2023)][
        ["common_flow_code", "value"]
    ].to_dict("records") == [
        {"common_flow_code": "15.01,15.03-15.06", "value": 30.0}
    ]
    assert set(selected.loc[
        selected["year"].eq(2024), "common_flow_code"
    ]) == {"15.01", "15.03"}


def test_true_transport_parent_remains_authoritative() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row("NINTH", "15", 125.0),
        _demand_frontier_row("NINTH", "15.02", 100.0),
        _demand_frontier_row("NINTH", "15.01,15.03-15.06", 25.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(rows)

    assert selected[["common_flow_code", "value"]].to_dict("records") == [
        {"common_flow_code": "15", "value": 125.0}
    ]


def test_transport_flow_overview_prefers_children_over_authoritative_parent() -> None:
    """The flow stack decomposes Transport while its total line stays authoritative."""
    rows = pd.DataFrame([
        _demand_frontier_row("NINTH", "15", 130.0),
        _demand_frontier_row("NINTH", "15.02", 100.0),
        _demand_frontier_row("NINTH", "15.01", 10.0),
        _demand_frontier_row("NINTH", "15.03", 8.0),
        _demand_frontier_row("NINTH", "15.04", 6.0),
        _demand_frontier_row("NINTH", "15.05", 4.0),
        _demand_frontier_row("NINTH", "15.06", 2.0),
    ])

    selected = renderer._coverage_selected_demand_frontier(
        rows,
        prefer_transport_detail=True,
    )

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01", "15.03", "15.04", "15.05", "15.06"
    }
    assert selected["value"].sum() == 130.0


def test_transport_flow_overview_detects_detail_across_products() -> None:
    """Child availability is a yearly source decision, not a per-fuel decision."""
    rows = pd.DataFrame([
        _demand_frontier_row("NINTH", "15", 10.0, "07.05"),
        _demand_frontier_row("NINTH", "15", 8.0, "07.07"),
        _demand_frontier_row("NINTH", "15.01", 10.0, "07.05"),
        _demand_frontier_row("NINTH", "15.03", 8.0, "07.07"),
    ])

    selected = renderer._coverage_selected_demand_frontier(
        rows,
        prefer_transport_detail=True,
    )

    assert set(selected["common_flow_code"]) == {"15.01", "15.03"}
    assert selected["value"].sum() == 18.0


def test_domestic_tfc_total_uses_the_displayed_hybrid_frontier() -> None:
    declared = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "year": 2023, "value": 100.0},
        {"source_system": "ESTO", "scenario": "historical", "year": 2022, "value": 90.0},
    ])
    frontier = pd.DataFrame([
        _demand_frontier_row("LEAP", "15.02", 100.0),
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 25.0),
    ])

    totals = renderer._coverage_aligned_domestic_tfc_totals(declared, [frontier])

    values = totals.set_index(["source_system", "scenario", "year"])["value"].to_dict()
    assert values[("LEAP", "Target", 2023)] == 125.0
    assert values[("ESTO", "historical", 2022)] == 90.0


def test_balance_tfc_total_includes_mixed_detailed_and_placeholder_sectors() -> None:
    """A stale LEAP flow-12 row cannot omit sectors moved out of a placeholder."""
    demand_rows = []
    for page_key, page_label, flow_code, value in (
        ("transport", "Transport", "15.02", 100.0),
        ("transport", "Transport", "15.01,15.03-15.06", 20.0),
        ("buildings", "Buildings", "16.01-16.02", 50.0),
        ("industry", "Industry and non-energy", "14", 30.0),
        ("others", "Other demand", "16.03-16.05", 10.0),
    ):
        demand_rows.append({
            **_area_product_row(
                "LEAP", "Target", 2030, flow_code, "17", value
            ),
            "common_flow_label": flow_code,
            "common_product_label": "17 Electricity",
            "_page_key": page_key,
            "_page_label": page_label,
        })
    demand_df = pd.DataFrame(demand_rows)
    overview_flow_df = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "12", "17", 120.0
            ),
            "common_flow_label": "12 Total final consumption",
            "common_product_label": "17 Electricity",
        },
        {
            **_area_product_row(
                "NINTH", "Target", 2030, "12", "17", 200.0
            ),
            "common_flow_label": "12 Total final consumption",
            "common_product_label": "17 Electricity",
        },
    ])

    totals = renderer._mixed_coverage_domestic_tfc_totals(
        demand_df,
        overview_flow_df,
        primary_source="LEAP",
        base_year=2022,
    )

    values = totals.set_index(["source_system", "scenario", "year"])["value"]
    assert values.loc[("LEAP", "Target", 2030)] == 210.0
    assert values.loc[("NINTH", "Target", 2030)] == 200.0


def test_combined_other_placeholder_drops_nonenergy_projection_fallback() -> None:
    demand_rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "16.03-16.05", 30.0),
        _demand_frontier_row("NINTH", "17", 20.0),
    ])

    selected = renderer._drop_nonenergy_fallback_covered_by_combined_other(
        demand_rows,
        demand_rows,
        "LEAP",
        "Target",
    )

    assert selected[["source_system", "common_flow_code"]].to_dict("records") == [
        {"source_system": "LEAP", "common_flow_code": "16.03-16.05"}
    ]


def test_combined_other_placeholder_keeps_historical_esto_nonenergy() -> None:
    demand_rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "16.03-16.05", 30.0),
        _demand_frontier_row("ESTO_EXTENDED", "17", 20.0),
        _demand_frontier_row("NINTH", "17", 20.0),
    ])

    selected = renderer._drop_nonenergy_fallback_covered_by_combined_other(
        demand_rows,
        demand_rows,
        "LEAP",
        "Target",
    )

    assert selected[["source_system", "common_flow_code"]].to_dict("records") == [
        {"source_system": "LEAP", "common_flow_code": "16.03-16.05"},
        {"source_system": "ESTO_EXTENDED", "common_flow_code": "17"},
    ]


def test_separate_leap_nonenergy_keeps_flow_17_projection() -> None:
    demand_rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "16.03-16.05", 30.0),
        _demand_frontier_row("LEAP", "17", 20.0),
    ])

    selected = renderer._drop_nonenergy_fallback_covered_by_combined_other(
        demand_rows,
        demand_rows,
        "LEAP",
        "Target",
    )

    assert set(selected["common_flow_code"]) == {"16.03-16.05", "17"}


def test_combined_other_placeholder_is_split_and_conserves_leap_total() -> None:
    rows = pd.DataFrame([
        {
            **_area_product_row("LEAP", "target", 2030, "16.03-16.05", "08.01", 30.0),
            "common_row_id": "leap-combined",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "16.03-16.04", "08.01", 8.0),
            "common_row_id": "ninth-other-a",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "16.05", "08.01", 2.0),
            "common_row_id": "ninth-other-b",
        },
        {
            **_area_product_row("NINTH", "Target", 2030, "17", "08.01", 20.0),
            "common_row_id": "ninth-nonenergy",
            "common_flow_label": "17 Non-energy use",
        },
        {
            **_area_product_row("LEAP", "target", 2030, "17", "08.01", 0.0),
            "common_row_id": "zero-filled-leap-nonenergy",
            "common_flow_label": "17 Non-energy use",
        },
    ])

    split = renderer.split_combined_other_nonenergy_placeholder(
        rows,
        primary_source="LEAP",
        ninth_source="NINTH",
    )
    leap = split[split["source_system"].eq("LEAP")]
    values = leap.groupby("common_flow_code")["value"].sum().to_dict()

    assert values == {
        "16.03-16.05": pytest.approx(10.0),
        "17": pytest.approx(20.0),
    }
    assert leap["value"].sum() == pytest.approx(30.0)
    assert set(leap["_other_nonenergy_estimation_method"].dropna()) == {
        "ninth_product_year_sector_share_of_combined_leap_placeholder"
    }


def test_road_history_uses_leap_base_year_fuel_shares_not_equal_splits() -> None:
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2021, "15.02", "07.01", 80.0
            ),
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 100.0
            ),
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "15.02.01", "07.01", 50.0
            ),
            "common_flow_label": "15.02.01 Freight road",
        },
        {
            **_area_product_row(
                "ESTO_EXTENDED", "historical", 2022, "15.02.02", "07.01", 50.0
            ),
            "common_flow_label": "15.02.02 Passenger road",
        },
        _area_product_row("LEAP", "Target", 2022, "15.02", "07.01", 100.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 10.0),
            "common_flow_label": "15.02.01 Freight road",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.02", "07.01", 90.0),
            "common_flow_label": "15.02.02 Passenger road",
        },
    ])

    fixed = renderer.estimate_esto_road_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    estimated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].isin(["15.02.01", "15.02.02"])
    ]
    values = estimated.set_index(["year", "common_flow_code"])["value"].to_dict()

    assert values == {
        (2021, "15.02.01"): pytest.approx(8.0),
        (2021, "15.02.02"): pytest.approx(72.0),
        (2022, "15.02.01"): pytest.approx(10.0),
        (2022, "15.02.02"): pytest.approx(90.0),
    }
    assert set(estimated["_historical_estimation_method"]) == {
        "estimated_from_leap_base_year_share"
    }


def test_detailed_demand_allocation_conserves_parent_and_preserves_zero_share() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2021, "14", "07.01", 80.0),
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "14", "07.01", 100.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "14.01", "07.01", 30.0),
            "common_flow_label": "14.01 Iron and steel",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "14.02", "07.01", 10.0),
            "common_flow_label": "14.02 Chemicals",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "14.03", "07.01", 0.0),
            "common_flow_label": "14.03 Other industry",
        },
    ])

    fixed = renderer.estimate_esto_demand_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
        component_specs=[{
            "component": "Industry",
            "flow_boundary": "14",
            "flow_prefixes": ["14"],
            "label": "14 Industry sector",
        }],
    )
    estimated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].isin(["14.01", "14.02", "14.03"])
    ]
    values = estimated.set_index(["year", "common_flow_code"])["value"].to_dict()

    assert values[(2021, "14.01")] == pytest.approx(60.0)
    assert values[(2021, "14.02")] == pytest.approx(20.0)
    assert values[(2021, "14.03")] == pytest.approx(0.0)
    assert values[(2022, "14.01")] == pytest.approx(75.0)
    assert values[(2022, "14.02")] == pytest.approx(25.0)
    assert values[(2022, "14.03")] == pytest.approx(0.0)
    assert estimated.groupby("year")["value"].sum().to_dict() == {
        2021: pytest.approx(80.0),
        2022: pytest.approx(100.0),
    }
    assert set(estimated["common_row_basis"]) == {
        "estimated_from_leap_base_year_share"
    }


def test_detailed_demand_allocation_uses_deepest_nonoverlapping_flow_frontier() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 100.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 100.0),
            "common_flow_label": "15.02.01 Freight road",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01.01", "07.01", 25.0),
            "common_flow_label": "15.02.01.01 Light vehicles",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01.02", "07.01", 75.0),
            "common_flow_label": "15.02.01.02 Trucks",
        },
    ])

    fixed = renderer.estimate_esto_road_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    estimated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].astype(str).str.startswith("15.02.")
    ]

    assert estimated.set_index("common_flow_code")["value"].to_dict() == {
        "15.02.01.01": pytest.approx(25.0),
        "15.02.01.02": pytest.approx(75.0),
    }


def test_detailed_demand_allocation_keeps_duplicate_deepest_rows() -> None:
    """Duplicate source contexts do not make a leaf look like its own parent."""
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 100.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 100.0),
            "common_flow_label": "15.02.01 Freight road",
            "comparison_scope": "esto_extended_leap",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 100.0),
            "common_flow_label": "15.02.01 Freight road",
            "comparison_scope": "esto_extended_leap_ninth",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.02", "07.01", 100.0),
            "common_flow_label": "15.02.02 Passenger road",
            "comparison_scope": "esto_extended_leap",
        },
    ])

    fixed = renderer.estimate_esto_road_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    estimated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].isin(["15.02.01", "15.02.02"])
    ]

    assert estimated.groupby("common_flow_code")["value"].sum().to_dict() == {
        "15.02.01": pytest.approx(200.0 / 3.0),
        "15.02.02": pytest.approx(100.0 / 3.0),
    }


def test_road_by_flow_keeps_same_named_leaves_after_child_grouping() -> None:
    """A synthesized Passenger-road group must retain every detailed branch."""
    rows = pd.DataFrame([
        _area_product_row(
            "ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 100.0
        ),
        {
            **_area_product_row(
                "LEAP", "Target", 2022, "15.02.01.01.02", "07.01", 30.0
            ),
            "common_flow_label": "15.02.01.01.02 ICE",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2022, "15.02.02.01.03", "07.01", 20.0
            ),
            "common_flow_label": "15.02.02.01.03 ICE",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2022, "15.02.02.02.12", "07.01", 50.0
            ),
            "common_flow_label": "15.02.02.02.12 ICE small",
        },
    ])

    fixed = renderer.estimate_esto_road_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    nodes = renderer.get_existing_flow_nodes(fixed)
    area_spec = {
        "aggregate_flow_prefix": "15.02",
        "aggregate_flow_label": "15.02 Road",
        "source_flow_labels": fixed["common_flow_label"].astype(str).tolist(),
    }
    child_rows = renderer.immediate_child_flow_rows(
        renderer.area_spec_rows(fixed, area_spec),
        nodes,
        "15.02",
    )
    selected = renderer.resolved_area_chart_rows(
        child_rows,
        area_spec,
        group_col="_child_flow_label",
    )
    historical = selected[selected["source_system"].eq("ESTO_EXTENDED")]

    child_totals = historical.groupby("_child_flow_code")["value"].sum().to_dict()
    assert child_totals == {
        "15.02.01": pytest.approx(30.0),
        "15.02.02": pytest.approx(70.0),
    }
    assert historical["value"].sum() == pytest.approx(100.0)


def test_detailed_demand_allocation_uses_visible_unallocated_without_denominator() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "16.01-16.02", "07.01", 50.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "16.01", "07.01", 0.0),
            "common_flow_label": "16.01 Services",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "16.02", "07.01", 0.0),
            "common_flow_label": "16.02 Residential",
        },
    ])

    fixed = renderer.estimate_esto_demand_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
        component_specs=[{
            "component": "Buildings",
            "flow_boundary": "16.01-16.02",
            "flow_prefixes": ["16.01", "16.02"],
            "label": "16 Buildings",
        }],
    )
    unallocated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_label"].eq("Unallocated within 16 Buildings")
    ]

    assert unallocated["value"].tolist() == [pytest.approx(50.0)]
    assert unallocated["common_row_basis"].tolist() == [
        "unallocated_no_leap_base_year_share"
    ]
    assert not fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].isin(["16.01", "16.02"])
    ].shape[0]


def test_detailed_demand_allocation_is_component_local_for_hybrid_upload() -> None:
    rows = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 90.0),
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.01,15.03-15.06", "07.01", 20.0),
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 30.0),
            "common_flow_label": "15.02.01 Freight road",
        },
        _area_product_row("LEAP", "Target", 2022, "15.01,15.03-15.06", "07.01", 20.0),
    ])
    specs = [
        {"component": "Road", "flow_boundary": "15.02", "flow_prefixes": ["15.02"], "label": "15.02 Road"},
        {"component": "Transport non road", "flow_boundary": "15.01,15.03-15.06", "flow_prefixes": ["15.01", "15.03", "15.04", "15.05", "15.06"], "label": "Transport non-road"},
    ]

    fixed = renderer.estimate_esto_demand_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
        component_specs=specs,
    )

    assert fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].eq("15.02.01")
    ]["value"].tolist() == [pytest.approx(90.0)]
    assert fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].eq("15.01,15.03-15.06")
    ]["value"].tolist() == [pytest.approx(20.0)]
    assert not fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_label"].str.contains("Unallocated", na=False)
    ].shape[0]


def test_non_energy_is_not_configured_for_child_allocation() -> None:
    template = {
        "leap_demand_sector_coverage": {
            "placeholder_component_product_sections": {
                "Industry": {"flow_code": "14", "label": "Industry"},
                "Non Energy Use": {"flow_code": "17", "label": "Non-energy use"},
            },
            "placeholder_component_flow_prefixes": {
                "Industry": ["14"],
                "Non Energy Use": ["17"],
            },
            "page_placeholder_components": {
                "industry": ["Industry", "Non Energy Use"],
            },
        }
    }

    specs = renderer.demand_detail_component_specs_for_page(template, "industry")

    assert [spec["component"] for spec in specs] == ["Industry"]


def test_transport_area_can_use_hybrid_demand_frontier() -> None:
    rows = pd.DataFrame([
        _demand_frontier_row("LEAP", "15", 100.0),
        _demand_frontier_row("LEAP", "15.02", 100.0),
        _demand_frontier_row("LEAP", "15.01,15.03-15.06", 25.0),
    ])
    area_spec = {
        "aggregate_flow_prefix": "15",
        "aggregate_flow_label": "15 Transport sector",
        "use_demand_coverage_frontier": True,
    }

    selected = renderer.resolved_area_chart_rows(rows, area_spec)

    assert set(selected["common_flow_code"]) == {
        "15.02", "15.01,15.03-15.06"
    }
    assert selected["value"].sum() == 125.0


def test_technology_stack_uses_authoritative_road_total_lines() -> None:
    detail = pd.DataFrame([
        {
            **_area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02.01", "07.01", 60.0),
            "common_flow_label": "Technology A",
        },
        {
            **_area_product_row("LEAP", "Target", 2022, "15.02.01", "07.01", 60.0),
            "common_flow_label": "Technology A",
        },
        {
            **_area_product_row("LEAP", "Target", 2030, "15.02.01", "07.01", 55.0),
            "common_flow_label": "Technology A",
        },
    ])
    totals = pd.DataFrame([
        _area_product_row("ESTO_EXTENDED", "historical", 2022, "15.02", "07.01", 100.0),
        _area_product_row("LEAP", "Target", 2022, "15.02", "07.01", 100.0),
        _area_product_row("LEAP", "Target", 2030, "15.02", "07.01", 95.0),
        _area_product_row("NINTH", "Target", 2022, "15.02", "07.01", 101.0),
        _area_product_row("NINTH", "Target", 2030, "15.02", "07.01", 90.0),
    ])
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "base_year": 2022,
        }
    }
    figure = renderer.build_area_chart(
        detail,
        {
            "aggregate_flow_prefix": "15.02",
            "aggregate_flow_label": "15.02 Road — detailed model by technology",
            "source_flow_labels": ["Technology A"],
            "authoritative_total_flow_boundary": "15.02",
        },
        {"LEAP|Target": "LEAP Target", "NINTH|Target": "9th Target"},
        template,
        group_col="common_flow_label",
        authoritative_total_df=totals,
    )
    traces = {trace.name: list(trace.y) for trace in figure.data}

    assert traces["LEAP Target total"] == [100.0, 95.0]
    assert traces["9th Target total"] == [101.0, 90.0]
    assert traces["15.02 Road — unallocated technology residual"] == [40.0, 40.0]
    assert "maximum absolute residual 40.00" in figure.layout.meta[
        "stacked_area_note"
    ]


def test_technology_stack_preserves_same_named_distinct_coded_branches() -> None:
    rows = pd.DataFrame([
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.01.02.02", "07.01", 10.0
            ),
            "common_flow_label": "15.02.01.02.02 BEV medium",
        },
        {
            **_area_product_row(
                "LEAP", "Target", 2030, "15.02.02.02.02", "07.01", 20.0
            ),
            "common_flow_label": "15.02.02.02.02 BEV medium",
        },
    ])
    selected = renderer.resolved_area_chart_rows(
        rows,
        {
            "aggregate_flow_prefix": "15.02",
            "aggregate_flow_label": "Road technology",
            "source_flow_labels": rows["common_flow_label"].tolist(),
            "preserve_distinct_flow_labels": True,
        },
        group_col="common_flow_label",
    )

    assert selected["value"].sum() == 30.0
    assert set(selected["common_flow_label"]) == {
        "15.02.01.02.02 BEV medium",
        "15.02.02.02.02 BEV medium",
    }


