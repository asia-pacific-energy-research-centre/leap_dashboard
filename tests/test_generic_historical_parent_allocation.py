"""Focused tests for native ESTO parent allocation to LEAP child frontiers."""

import pandas as pd
import pytest

from codebase import common_esto_dashboard_renderer as renderer


def _row(
    source: str,
    year: int,
    flow: str,
    product: str,
    value: float,
    *,
    scenario: str | None = None,
    exact: bool = False,
) -> dict[str, object]:
    return {
        "comparison_scope": "esto_extended_leap_ninth",
        "source_system": source,
        "economy": "01_AUS",
        "scenario": scenario or ("historical" if source == "ESTO_EXTENDED" else "Target"),
        "year": year,
        "common_flow_code": flow,
        "common_flow_label": flow,
        "common_product_code": product,
        "common_product_label": product,
        "common_row_basis": "exact_esto_row" if exact else "",
        "is_exact_row": exact,
        "value": value,
    }


def _automatic_allocate(rows: pd.DataFrame) -> pd.DataFrame:
    specs = renderer.automatic_historical_parent_allocation_specs(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    return renderer.allocate_historical_parent_by_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
        parent_specs=specs,
    )


def test_road_wrapper_still_allocates_by_leap_share() -> None:
    rows = pd.DataFrame([
        _row("ESTO_EXTENDED", 2021, "15.02", "07.01", 80.0),
        _row("ESTO_EXTENDED", 2022, "15.02", "07.01", 100.0),
        _row("LEAP", 2022, "15.02.01", "07.01", 10.0),
        _row("LEAP", 2022, "15.02.02", "07.01", 90.0),
    ])

    allocated = renderer.estimate_esto_road_detail_from_leap_base_year_shares(
        rows,
        comparison_source="ESTO_EXTENDED",
        primary_source="LEAP",
        primary_scenario="Target",
        base_year=2022,
    )
    history = allocated[allocated["source_system"].eq("ESTO_EXTENDED")]

    assert history.groupby("year")["value"].sum().to_dict() == {
        2021: pytest.approx(80.0),
        2022: pytest.approx(100.0),
    }
    assert history.set_index(["year", "common_flow_code"])["value"].to_dict() == {
        (2021, "15.02.01"): pytest.approx(8.0),
        (2021, "15.02.02"): pytest.approx(72.0),
        (2022, "15.02.01"): pytest.approx(10.0),
        (2022, "15.02.02"): pytest.approx(90.0),
    }


def test_power_compound_parent_is_automatically_allocated_and_conserved() -> None:
    parent = "09.01.01,09.02.01"
    rows = pd.DataFrame([
        _row("ESTO_EXTENDED", 2021, parent, "01.02", -60.0, exact=True),
        _row("ESTO_EXTENDED", 2022, parent, "01.02", -100.0, exact=True),
        _row("LEAP", 2022, "09.01.01.01,09.02.01.01", "01.02", -75.0),
        _row("LEAP", 2022, "09.01.01.04,09.02.01.04", "01.02", -25.0),
    ])

    allocated = _automatic_allocate(rows)
    history = allocated[allocated["source_system"].eq("ESTO_EXTENDED")]

    assert parent not in set(history["common_flow_code"])
    assert history.groupby("year")["value"].sum().to_dict() == {
        2021: pytest.approx(-60.0),
        2022: pytest.approx(-100.0),
    }
    assert set(history["_historical_estimation_method"]) == {
        "estimated_from_leap_base_year_share"
    }


def test_non_power_native_parent_is_automatically_allocated() -> None:
    rows = pd.DataFrame([
        _row("ESTO_EXTENDED", 2022, "14", "08.01", 120.0, exact=True),
        _row("LEAP", 2022, "14.01", "08.01", 20.0),
        _row("LEAP", 2022, "14.02", "08.01", 40.0),
    ])

    allocated = _automatic_allocate(rows)
    history = allocated[allocated["source_system"].eq("ESTO_EXTENDED")]

    assert history.set_index("common_flow_code")["value"].to_dict() == {
        "14.01": pytest.approx(40.0),
        "14.02": pytest.approx(80.0),
    }
    assert history["value"].sum() == pytest.approx(120.0)


def test_exact_native_child_is_preserved_and_missing_sibling_gets_remainder() -> None:
    rows = pd.DataFrame([
        _row("ESTO_EXTENDED", 2022, "14", "08.01", 120.0, exact=True),
        _row("ESTO_EXTENDED", 2022, "14.01", "08.01", 45.0, exact=True),
        _row("LEAP", 2022, "14.01", "08.01", 20.0),
        _row("LEAP", 2022, "14.02", "08.01", 40.0),
    ])

    allocated = _automatic_allocate(rows)
    history = allocated[allocated["source_system"].eq("ESTO_EXTENDED")]

    assert history.set_index("common_flow_code")["value"].to_dict() == {
        "14.01": pytest.approx(45.0),
        "14.02": pytest.approx(75.0),
    }
    assert history["value"].sum() == pytest.approx(120.0)
    assert history.loc[
        history["common_flow_code"].eq("14.02"),
        "_historical_estimation_method",
    ].tolist() == ["estimated_from_leap_base_year_share"]


@pytest.mark.parametrize(
    "leap_rows",
    [
        [],
        [_row("LEAP", 2022, "14.01", "17", 50.0)],
        [
            _row("LEAP", 2022, "14.01", "08.01", 0.0),
            _row("LEAP", 2022, "14.02", "08.01", 0.0),
        ],
    ],
)
def test_missing_mismatched_or_zero_basis_keeps_native_parent(
    leap_rows: list[dict[str, object]],
) -> None:
    parent = _row("ESTO_EXTENDED", 2022, "14", "08.01", 120.0, exact=True)
    rows = pd.DataFrame([parent, *leap_rows])

    allocated = _automatic_allocate(rows)
    history = allocated[allocated["source_system"].eq("ESTO_EXTENDED")]

    assert history[["common_flow_code", "value"]].to_dict("records") == [
        {"common_flow_code": "14", "value": 120.0}
    ]
