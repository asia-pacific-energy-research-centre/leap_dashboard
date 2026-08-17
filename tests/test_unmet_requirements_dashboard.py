from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_data import load_unmet_requirements_data
from codebase.common_esto_dashboard_renderer import build_unmet_requirements_chart


def test_unmet_requirements_use_scope_specific_common_fuels_and_keep_unknowns(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "raw_leap_results.csv"
    pd.DataFrame(
        [
            ["20_USA", "Target", 2030, "Unmet Requirements", "Natural gas", 4.0],
            ["20_USA", "Target", 2030, "Unmet Requirements", "Mystery fuel", -2.0],
            ["20_USA", "Target", 2031, "Unmet Requirements", "Natural gas", 0.0],
            ["20_USA", "Target", 2030, "Unmet Requirements", "Total", 2.0],
            ["20_USA", "Target", 2030, "Production", "Natural gas", 100.0],
            ["02_BD", "Target", 2030, "Unmet Requirements", "Natural gas", 9.0],
        ],
        columns=["economy", "scenario", "year", "leap_flow", "leap_product", "value"],
    ).to_csv(raw_path, index=False)
    map_path = tmp_path / "source_to_common_esto_map.csv"
    pd.DataFrame(
        [
            ["esto_leap_ninth", "LEAP", "Natural gas", "08.01 Natural gas"],
            ["esto_leap", "LEAP", "Natural gas", "08 Gas"],
        ],
        columns=["scope", "system", "source_product", "common_product_label"],
    ).to_csv(map_path, index=False)

    result = load_unmet_requirements_data(
        raw_path,
        map_path,
        comparison_scope="esto_leap_ninth",
        economy="20USA",
        min_year=2023,
        max_year=2060,
    )

    assert set(result["leap_product"]) == {"Mystery fuel", "Natural gas"}
    assert set(result["common_product_label"]) == {
        "08.01 Natural gas",
        "Unmapped LEAP fuel: Mystery fuel",
    }
    assert set(result["fuel_mapping_status"]) == {"mapped", "unmapped"}
    assert result["value"].sum() == 2.0


def test_unmet_requirements_chart_explains_shortage_and_surplus() -> None:
    rows = pd.DataFrame(
        [
            ["LEAP", "Reference", 2030, "08.01 Natural gas", -3.0],
            ["LEAP", "Reference", 2030, "17 Electricity", 5.0],
        ],
        columns=["source_system", "scenario", "year", "common_product_label", "value"],
    )

    fig = build_unmet_requirements_chart(
        rows,
        {"LEAP Reference": "LEAP Reference"},
        primary_scenario="Target",
        base_year=2022,
    )

    note = fig.layout.meta["stacked_area_note"]
    assert "Positive values show an energy shortage" in note
    assert "negative values show surplus energy" in note
    assert any(float(value) > 0 for trace in fig.data for value in trace.y)
    assert any(float(value) < 0 for trace in fig.data for value in trace.y)
    assert all(trace.visible is None or trace.visible is True for trace in fig.data)
    assert not any("net unmet requirements" in str(trace.name).casefold() for trace in fig.data)
