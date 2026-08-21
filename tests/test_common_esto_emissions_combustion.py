#%%
"""Regression tests for the dashboard combustion-emissions boundary."""

import pandas as pd

from codebase.common_esto_dashboard_emissions import (
    apply_emissions_flow_policy,
    load_emissions_flow_policy,
    select_emissions_component_rows,
)


COMBUSTION_CONFIG = {
    "demand_page_keys": ["industry", "transport", "buildings", "others"],
    "aggregate_flow_code": "13",
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
        "component_flow_code": flow_code,
        "common_flow_label": flow_label,
        "common_product_label": "08.01 Natural gas",
        "source_system": "LEAP",
        "scenario": "Target",
        "year": 2023,
        "value": value,
    }


def test_flow_policy_excludes_conversion_feedstocks_and_losses() -> None:
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

    selected, resolution = apply_emissions_flow_policy(
        rows,
        load_emissions_flow_policy(),
        "test",
    )

    assert set(selected["common_flow_code"]) == {
        "09.01.01,09.02.01",
        "10.01.03",
    }
    assert set(resolution["policy_status"]) == {"included", "excluded"}


def test_extended_and_compound_codes_inherit_original_esto_policy() -> None:
    rows = pd.DataFrame([
        _row("transport", "15.02.02.02.01", "BEV large", 10.0),
        _row("power", "09.01.01,09.02.01", "Electricity plants", -20.0),
        _row("others", "16.03-17", "Other sector including non-energy", 30.0),
    ])

    selected, resolution = apply_emissions_flow_policy(
        rows,
        load_emissions_flow_policy(),
        "test",
    )

    assert set(selected["common_flow_code"]) == {
        "15.02.02.02.01",
        "09.01.01,09.02.01",
    }
    mixed = resolution[resolution["common_flow_code"].eq("16.03-17")].iloc[0]
    assert mixed["policy_status"] == "excluded"
    assert mixed["resolved_esto_flow_codes"] == "16.03; 17"


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

    selected, coverage, selection, resolution = select_emissions_component_rows(
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
    lng_feedstock = resolution[
        resolution["common_flow_code"].eq("09.06.02.01")
    ]
    assert set(lng_feedstock["policy_status"]) == {"excluded"}


def test_original_esto_policy_is_complete_and_explicit() -> None:
    policy = load_emissions_flow_policy()

    assert len(policy) == 116
    assert policy["esto_flow_code"].is_unique
    assert policy["notes"].ne("").all()
    measured = policy.set_index("esto_flow_code")["measured_in_dashboard"]
    assert bool(measured.loc["09.01.01"])
    assert not bool(measured.loc["09.06.02"])
    assert bool(measured.loc["10.01.03"])
    assert not bool(measured.loc["10.02"])
    assert not bool(measured.loc["12"])
    assert bool(measured.loc["13"])
    assert not bool(measured.loc["17"])


#%%
