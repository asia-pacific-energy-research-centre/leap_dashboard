#%%
"""Regression tests for the dashboard combustion-emissions boundary."""

import pandas as pd

from codebase.common_esto_dashboard_emissions import (
    _combustion_transformation_rows,
    select_emissions_component_rows,
)


COMBUSTION_CONFIG = {
    "demand_page_keys": ["industry", "transport", "buildings", "others"],
    "combustion_transformation_flow_code_prefixes": ["09.01", "09.02"],
    "combustion_own_use_flow_code_prefixes": ["10.01"],
}


def _row(
    page_key: str,
    flow_code: str,
    flow_label: str,
    value: float,
) -> dict[str, object]:
    return {
        "_page_key": page_key,
        "_page_label": page_key.replace("_", " ").title(),
        "common_flow_code": flow_code,
        "common_flow_label": flow_label,
        "common_product_label": "08.01 Natural gas",
        "source_system": "LEAP",
        "scenario": "Target",
        "year": 2023,
        "value": value,
    }


def test_combustion_boundary_excludes_conversion_feedstocks_and_losses() -> None:
    rows = pd.DataFrame([
        _row("power", "09.01.01,09.02.01", "Electricity plants", -100.0),
        _row("other_transformation", "09.06.02", "LNG liquefaction", -80.0),
        _row("refining", "09.07", "Oil refineries", -70.0),
        _row("other_transformation", "09.08.01", "Coke ovens", -60.0),
        _row("other_transformation", "09.09", "Petrochemical industry", -50.0),
        _row("other_transformation", "09.13.03", "SMR with CCS", -40.0),
        _row("other_transformation", "10.01.03", "LNG own use", -8.0),
        _row("other_transformation", "10.02", "Transmission losses", -7.0),
        _row("other_transformation", "08", "Transfers", -6.0),
    ])

    selected = _combustion_transformation_rows(rows, COMBUSTION_CONFIG)

    assert set(selected["common_flow_code"]) == {
        "09.01.01,09.02.01",
        "10.01.03",
    }


def test_lng_emissions_use_own_use_not_transformation_feedstock() -> None:
    rows = pd.DataFrame([
        _row("industry", "14", "Industry", 20.0),
        _row("power", "09.01.01,09.02.01", "Electricity plants", -100.0),
        _row("other_transformation", "09.06.02.01", "Liquefaction", -4220.411097),
        _row(
            "other_transformation",
            "09.06.02",
            "Liquefaction/regasification plants (including own use)",
            -4528.757899,
        ),
        _row(
            "other_transformation",
            "10.01.03",
            "Liquefaction/regasification plants own use",
            -308.346802,
        ),
    ])

    selected, coverage, selection = select_emissions_component_rows(
        rows,
        COMBUSTION_CONFIG,
    )

    assert coverage.empty
    transformation = selected[
        selected["_sector_label"].eq("Power generation and own use")
    ]
    assert set(transformation["common_flow_code"]) == {
        "09.01.01,09.02.01",
        "10.01.03",
    }
    assert transformation["value"].sum() == 408.346802
    assert set(selection["emissions_level"]) == {
        "detail",
        "combustion_leaf_frontier",
    }


#%%
