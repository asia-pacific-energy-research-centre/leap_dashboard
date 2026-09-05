"""Focused ESTO Extended frontier contract tests for Buildings."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_common_esto_dashboard_frontier import _area_product_row  # noqa: E402
from codebase import common_esto_dashboard_renderer as renderer  # noqa: E402


BUILDINGS_BOUNDARY = "16.01-16.02"
BUILDINGS_LABEL = "16.01-16.02 Buildings"
CHILD_LABELS = {
    "16.01": "16.01 Commercial and public services",
    "16.02": "16.02 Residential",
}
PRODUCT_LABELS = {
    "07.01": "07.01 Motor gasoline",
    "07.07": "07.07 Gas/diesel oil",
}


def _building_row(
    source: str,
    scenario: str,
    economy: str,
    year: int,
    flow: str,
    product: str,
    value: float,
    *,
    exact_native: bool = False,
) -> dict[str, object]:
    row = _area_product_row(source, scenario, year, flow, product, value)
    row.update(
        {
            "economy": economy,
            "common_flow_label": (
                BUILDINGS_LABEL if flow == BUILDINGS_BOUNDARY else CHILD_LABELS[flow]
            ),
            "common_product_label": PRODUCT_LABELS[product],
        }
    )
    if exact_native:
        row.update({"is_exact_row": True, "common_row_basis": "exact_esto_row"})
    return row


def _china_buildings_rows() -> pd.DataFrame:
    """Two economies and two fuels with deliberately different LEAP shares."""
    rows: list[dict[str, object]] = []
    parents = {
        "05_PRC": {"07.01": {2021: 80.0, 2022: 100.0}, "07.07": {2021: 40.0, 2022: 50.0}},
        "06_IND": {"07.01": {2021: 60.0, 2022: 90.0}, "07.07": {2021: 30.0, 2022: 45.0}},
    }
    leap_shares = {
        "05_PRC": {"07.01": (80.0, 20.0), "07.07": (60.0, 40.0)},
        "06_IND": {"07.01": (20.0, 80.0), "07.07": (30.0, 70.0)},
    }
    for economy, products in parents.items():
        for product, yearly_values in products.items():
            for year, value in yearly_values.items():
                rows.append(
                    _building_row(
                        "ESTO_EXTENDED",
                        "historical",
                        economy,
                        year,
                        BUILDINGS_BOUNDARY,
                        product,
                        value,
                    )
                )
            services, residential = leap_shares[economy][product]
            rows.extend(
                [
                    _building_row(
                        "LEAP", "Target", economy, 2022, "16.01", product, services
                    ),
                    _building_row(
                        "LEAP", "Target", economy, 2022, "16.02", product, residential
                    ),
                ]
            )
    return pd.DataFrame(rows)


def _buildings_component_spec() -> dict[str, object]:
    return {
        "component": "Buildings",
        "flow_boundary": BUILDINGS_BOUNDARY,
        "flow_prefixes": ["16.01", "16.02"],
        "label": "16 Buildings",
    }


def _allocate(
    rows: pd.DataFrame,
    *,
    audit_rows: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    return renderer.estimate_esto_demand_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
        component_specs=[_buildings_component_spec()],
        audit_rows=audit_rows,
    )


def test_buildings_allocation_is_scoped_by_economy_year_and_fuel() -> None:
    fixed = _allocate(_china_buildings_rows())
    estimated = fixed[fixed["source_system"].eq("ESTO_EXTENDED")]
    estimated = estimated[estimated["common_flow_code"].isin(["16.01", "16.02"])]

    def values(economy: str, year: int, product: str, flow: str) -> list[float]:
        return estimated.loc[
            estimated["economy"].eq(economy)
            & estimated["year"].eq(year)
            & estimated["common_product_code"].eq(product)
            & estimated["common_flow_code"].eq(flow),
            "value",
        ].tolist()

    assert values("05_PRC", 2021, "07.01", "16.01") == [pytest.approx(64.0)]
    assert values("05_PRC", 2021, "07.01", "16.02") == [pytest.approx(16.0)]
    assert values("06_IND", 2021, "07.01", "16.01") == [pytest.approx(12.0)]
    assert values("06_IND", 2021, "07.01", "16.02") == [pytest.approx(48.0)]
    assert values("05_PRC", 2021, "07.07", "16.01") == [pytest.approx(24.0)]
    assert values("06_IND", 2021, "07.07", "16.02") == [pytest.approx(21.0)]


def test_native_extended_children_are_preserved_while_missing_children_are_allocated() -> None:
    """An exact child owns its value; only the missing child receives the remainder."""
    rows = pd.DataFrame(
        [
            _building_row(
                "ESTO_EXTENDED", "historical", "05_PRC", 2022,
                BUILDINGS_BOUNDARY, "07.01", 120.0, exact_native=True,
            ),
            _building_row(
                "ESTO_EXTENDED", "historical", "05_PRC", 2022,
                "16.01", "07.01", 45.0, exact_native=True,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2022,
                "16.01", "07.01", 20.0,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2022,
                "16.02", "07.01", 40.0,
            ),
        ]
    )

    fixed = _allocate(rows)
    native = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["economy"].eq("05_PRC")
        & fixed["common_flow_code"].isin(["16.01", "16.02"])
    ]

    assert native.set_index("common_flow_code")["value"].to_dict() == {
        "16.01": pytest.approx(45.0),
        "16.02": pytest.approx(75.0),
    }
    assert native.loc[native["common_flow_code"].eq("16.01"), "value"].tolist() == [
        pytest.approx(45.0)
    ]
    assert not fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].eq(BUILDINGS_BOUNDARY)
    ].shape[0]


def test_estimated_buildings_children_conserve_each_parent_by_economy_year_and_fuel() -> None:
    source = _china_buildings_rows()
    fixed = _allocate(source)
    estimated = fixed[
        fixed["source_system"].eq("ESTO_EXTENDED")
        & fixed["common_flow_code"].isin(["16.01", "16.02"])
    ]
    expected = source[source["source_system"].eq("ESTO_EXTENDED")].groupby(
        ["economy", "year", "common_product_code"], dropna=False
    )["value"].sum()
    actual = estimated.groupby(
        ["economy", "year", "common_product_code"], dropna=False
    )["value"].sum()

    pd.testing.assert_series_equal(
        actual.sort_index(), expected.sort_index(), check_names=True
    )


def test_buildings_by_flow_surface_exposes_estimated_children() -> None:
    fixed = _allocate(_china_buildings_rows())
    grouped = renderer.configured_flow_group_rows(
        fixed,
        [
            {"flow_boundary": "16.01", "label": "16.01 Services"},
            {"flow_boundary": "16.02", "label": "16.02 Residential"},
        ],
    )
    history = grouped[
        grouped["source_system"].eq("ESTO_EXTENDED")
        & grouped["economy"].eq("05_PRC")
        & grouped["year"].eq(2021)
        & grouped["common_product_code"].eq("07.01")
    ]

    assert set(history["_configured_flow_group_label"]) == {
        "16.01 Services",
        "16.02 Residential",
    }
    assert history.set_index("_configured_flow_group_label")["value"].to_dict() == {
        "16.01 Services": pytest.approx(64.0),
        "16.02 Residential": pytest.approx(16.0),
    }
    assert set(history["common_row_basis"]) == {
        "estimated_from_leap_base_year_share"
    }


def test_buildings_by_product_chart_matches_ordinary_esto_historical_frontier() -> None:
    input_rows = pd.DataFrame(
        [
            _building_row(
                "ESTO_EXTENDED", "historical", "05_PRC", 2022,
                BUILDINGS_BOUNDARY, "07.01", 100.0,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2022,
                "16.01", "07.01", 80.0,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2022,
                "16.02", "07.01", 20.0,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2023,
                BUILDINGS_BOUNDARY, "07.01", 120.0,
            ),
        ]
    )
    extended = _allocate(input_rows)
    ordinary = input_rows.copy()
    ordinary.loc[ordinary["source_system"].eq("ESTO_EXTENDED"), "source_system"] = "ESTO"
    spec = {
        "aggregate_flow_prefix": BUILDINGS_BOUNDARY,
        "aggregate_flow_label": BUILDINGS_LABEL,
        "preferred_detail_flow_boundaries": ["16.01", "16.02"],
        "explicit_flow_boundary": True,
    }
    template = {
        "chart_generation": {
            "comparison_source_system": "ESTO_EXTENDED",
            "primary_area_source_system": "LEAP",
            "primary_area_scenario": "Target",
            "base_year": 2022,
        }
    }
    labels = {
        "ESTO_EXTENDED|historical": "ESTO Extended Historical",
        "LEAP|Target": "LEAP Target",
    }

    extended_figure = renderer.build_area_chart(
        extended, spec, labels, template, group_col="common_product_label"
    )
    ordinary_template = {
        "chart_generation": {
            **template["chart_generation"],
            "comparison_source_system": "ESTO",
        }
    }
    ordinary_figure = renderer.build_area_chart(
        ordinary, spec, {**labels, "ESTO|historical": "ESTO Historical"}, ordinary_template,
        group_col="common_product_label",
    )

    extended_traces = {trace.name: list(trace.y) for trace in extended_figure.data}
    ordinary_traces = {trace.name: list(trace.y) for trace in ordinary_figure.data}
    assert extended_traces["ESTO Extended Historical total"] == [100.0]
    assert ordinary_traces["ESTO Historical total"] == [100.0]
    assert extended_traces["07.01 Motor gasoline"] == ordinary_traces["07.01 Motor gasoline"]


def test_buildings_without_leap_child_basis_keeps_parent_without_synthetic_residual() -> None:
    rows = pd.DataFrame(
        [
            _building_row(
                "ESTO_EXTENDED", "historical", "05_PRC", 2022,
                BUILDINGS_BOUNDARY, "07.01", 100.0, exact_native=True,
            ),
            _building_row(
                "ESTO_EXTENDED", "historical", "05_PRC", 2022,
                "16.01", "07.01", 20.0,
            ),
            _building_row(
                "LEAP", "Target", "05_PRC", 2022,
                BUILDINGS_BOUNDARY, "07.01", 100.0,
            ),
        ]
    )
    audit_rows: list[dict[str, object]] = []
    fixed = _allocate(rows, audit_rows=audit_rows)
    historical = fixed[fixed["source_system"].eq("ESTO_EXTENDED")]

    assert historical["common_flow_code"].tolist() == [BUILDINGS_BOUNDARY]
    assert historical["value"].tolist() == [pytest.approx(100.0)]
    assert not historical["common_flow_label"].str.contains(
        "Unallocated|residual", case=False, regex=True
    ).any()
    assert historical["common_row_basis"].tolist() == ["exact_esto_row"]
    assert len(audit_rows) == 1
    audit = audit_rows[0]
    expected_audit = {
        "comparison_scope": "esto_extended_leap_ninth",
        "economy": "05_PRC",
        "source_system": "ESTO_EXTENDED",
        "scenario": "historical",
        "year": 2022,
        "parent_flow_code": BUILDINGS_BOUNDARY,
        "product_code": "07.01",
        "product_label": PRODUCT_LABELS["07.01"],
        "parent_value": 100.0,
            "preserved_native_child_value": 0.0,
            "uncovered_parent_value": 100.0,
            "leap_basis_value": 0.0,
            "estimated_child_count": 0,
        "qa_status": "FAIL",
        "allocation_status": "failed_parent_retained",
        "allocation_method": "",
        "failure_reason": "no_nonzero_leap_base_year_share_for_missing_children",
    }
    assert all(audit[key] == value for key, value in expected_audit.items())

    figure = renderer.build_area_chart(
        fixed,
        {
            "aggregate_flow_prefix": BUILDINGS_BOUNDARY,
            "aggregate_flow_label": BUILDINGS_LABEL,
            "preferred_detail_flow_boundaries": ["16.01", "16.02"],
            "explicit_flow_boundary": True,
        },
        {
            "ESTO_EXTENDED|historical": "ESTO Extended Historical",
            "LEAP|Target": "LEAP Target",
        },
        {
            "chart_generation": {
                "comparison_source_system": "ESTO_EXTENDED",
                "primary_area_source_system": "LEAP",
                "primary_area_scenario": "Target",
                "base_year": 2022,
            }
        },
    )
    traces = {trace.name: list(trace.y) for trace in figure.data}
    assert traces["ESTO Extended Historical total"] == [100.0]
    assert not any("residual" in str(name).casefold() for name in traces)
