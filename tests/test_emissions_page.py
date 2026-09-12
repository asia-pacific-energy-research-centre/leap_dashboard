from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from codebase import common_esto_dashboard_emissions as emissions

FACTOR_CSV = """fuels,subfuels,CO2e emissions factor,Unit,Gas
01_coal,01_01_coking_coal,0.0946,Mt/PJ,CARBON DIOXIDE
01_coal,01_x_thermal_coal,0.0946,Mt/PJ,CARBON DIOXIDE
01_coal,x,0.094,Mt/PJ,CARBON DIOXIDE
15_solid_biomass,15_05_other_biomass,0.1,Mt/PJ,CARBON DIOXIDE
15_solid_biomass,15_solid_biomass_unallocated,0.1,Mt/PJ,CARBON DIOXIDE
15_solid_biomass,x,0.1115,Mt/PJ,CARBON DIOXIDE
17_electricity,x,,Mt/PJ,CARBON DIOXIDE
19_total,x,,Mt/PJ,CARBON DIOXIDE
"""

NINTH_TO_ESTO = pd.DataFrame(
    [
        {"ninth_fuel": "01_01_coking_coal", "esto_product": "01.01 Coking coal"},
        {"ninth_fuel": "01_x_thermal_coal", "esto_product": "01.02 Other bituminous coal"},
        {"ninth_fuel": "01_x_thermal_coal", "esto_product": "01.04 Anthracite"},
        {"ninth_fuel": "01_coal_unallocated", "esto_product": "01.99 Coal nonspecified"},
        {"ninth_fuel": "15_05_other_biomass", "esto_product": "15.05 Other biomass"},
        {"ninth_fuel": "15_solid_biomass_unallocated", "esto_product": "15.05 Other biomass"},
        {"ninth_fuel": "17_electricity", "esto_product": "17 Electricity"},
    ]
)

ESTO_TO_COMMON = pd.DataFrame(
    [
        ("14 Industry sector", "01.01 Coking coal", "14 Industry sector", "01.01 Coking coal"),
        ("14 Industry sector", "01.02 Other bituminous coal", "14 Industry sector", "01.02-01.04 Coal"),
        ("14 Industry sector", "01.04 Anthracite", "14 Industry sector", "01.02-01.04 Coal"),
        ("14 Industry sector", "01.99 Coal nonspecified", "14 Industry sector", "01.99 Coal nonspecified"),
        ("14 Industry sector", "15.05 Other biomass", "14 Industry sector", "15.05 Other biomass"),
        ("14 Industry sector", "17 Electricity", "14 Industry sector", "17 Electricity"),
    ],
    columns=[
        "component_esto_flow",
        "component_esto_product",
        "common_flow_label",
        "common_product_label",
    ],
).assign(comparison_scope="esto_leap_ninth")


@pytest.fixture()
def factor_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Build a self-contained factor set plus its two mapping inputs."""
    factor_path = tmp_path / "factors.csv"
    factor_path.write_text(FACTOR_CSV, encoding="utf-8")
    workbook_path = tmp_path / "single_axis.xlsx"
    NINTH_TO_ESTO.to_excel(workbook_path, sheet_name="ninth_fuel_to_esto", index=False)
    map_path = tmp_path / "esto_to_common.csv"
    ESTO_TO_COMMON.to_csv(map_path, index=False)

    monkeypatch.setattr(emissions, "_NINTH_FUEL_TO_ESTO_CACHE", {})
    factor_set = {
        "key": "test_set",
        "label": "Test factors",
        "path": str(factor_path),
        "mapping_axis": "ninth_fuel",
        "factor_column": "CO2e emissions factor",
        "gas_column": "Gas",
        "gases": ["CARBON DIOXIDE"],
        "emissions_unit": "Mt CO2e",
        "blank_factor_means": "zero",
        "ninth_fuel_axis": {
            "fuel_column": "fuels",
            "subfuel_column": "subfuels",
            "subfuel_placeholder": "x",
            "unallocated_suffix": "_unallocated",
        },
        "ninth_conflict_resolution": "prefer_specific_then_mean",
        "component_conflict_resolution": "mean",
    }
    return {
        "factor_set": factor_set,
        "mapping_sources": {
            "ninth_fuel_to_esto_workbook": str(workbook_path),
            "esto_to_common_map": str(map_path),
        },
    }


def test_subfuel_replaces_parent_fuel_and_placeholder_becomes_unallocated(factor_workspace):
    resolved, dropped = emissions.collapse_ninth_fuel_rows(
        pd.read_csv(factor_workspace["factor_set"]["path"]).rename(
            columns={"CO2e emissions factor": "emissions_factor"}
        ),
        factor_workspace["factor_set"],
        NINTH_TO_ESTO["ninth_fuel"].tolist(),
    )
    codes = set(resolved["ninth_fuel"])
    # A named subfuel replaces its parent fuel.
    assert "01_01_coking_coal" in codes
    # The placeholder row stands in for the unallocated code when nothing else does.
    assert "01_coal_unallocated" in codes
    # 15_solid_biomass already has an explicit unallocated subfuel, so its
    # placeholder row is a pure aggregate and must not be reused.
    assert "15_solid_biomass_unallocated" in codes
    assert set(dropped["ninth_fuel_key"]) == {"15_solid_biomass", "19_total"}


def test_factor_table_resolves_common_axis_with_blank_as_zero(factor_workspace):
    factors, diagnostics = emissions.build_factor_table(
        factor_workspace["factor_set"], factor_workspace["mapping_sources"]
    )
    by_label = factors.set_index("common_product_label")["emissions_factor"]
    assert by_label["01.01 Coking coal"] == pytest.approx(0.0946)
    # A rolled-up common fuel takes the factor its ESTO components share.
    assert by_label["01.02-01.04 Coal"] == pytest.approx(0.0946)
    assert by_label["01.99 Coal nonspecified"] == pytest.approx(0.094)
    # A blank factor means no emissions, not missing data.
    assert by_label["17 Electricity"] == pytest.approx(0.0)
    assert diagnostics["axis_values_without_factor"].empty


def test_factor_table_applies_esto_product_override(factor_workspace):
    factor_workspace["factor_set"]["esto_product_factor_overrides"] = {
        "15.05 Other biomass": 0.0,
    }
    factors, _ = emissions.build_factor_table(
        factor_workspace["factor_set"], factor_workspace["mapping_sources"]
    )
    by_label = factors.set_index("common_product_label")["emissions_factor"]
    assert by_label["15.05 Other biomass"] == pytest.approx(0.0)


def test_multiple_gases_in_one_factor_column_is_refused(factor_workspace, tmp_path):
    factor_set = dict(factor_workspace["factor_set"])
    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        FACTOR_CSV.replace(
            "01_coal,01_01_coking_coal,0.0946,Mt/PJ,CARBON DIOXIDE",
            "01_coal,01_01_coking_coal,0.0946,Mt/PJ,METHANE",
        ),
        encoding="utf-8",
    )
    factor_set["path"] = str(mixed)
    factor_set["gases"] = ["CARBON DIOXIDE", "METHANE"]
    with pytest.raises(ValueError, match="multiple gases"):
        emissions.build_factor_table(factor_set, factor_workspace["mapping_sources"])


def test_attach_emissions_multiplies_value_by_factor():
    factors = pd.DataFrame(
        [{"common_product_label": "01.01 Coking coal", "emissions_factor": 0.1, "emissions_unit": "Mt CO2e"}]
    )
    rows = pd.DataFrame(
        [
            {"common_product_label": "01.01 Coking coal", "value": 200.0},
            {"common_product_label": "17 Electricity", "value": 50.0},
        ]
    )
    result = emissions.attach_emissions(rows, factors)
    assert result.loc[0, emissions.EMISSIONS_COLUMN] == pytest.approx(20.0)
    # An unfactored fuel stays NaN so it can be reported, not silently zeroed.
    assert pd.isna(result.loc[1, emissions.EMISSIONS_COLUMN])


def test_unmatched_factor_rows_keep_full_source_observation_identity():
    rows = pd.DataFrame([{
        "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
        "source_system": "LEAP", "scenario": "Target", "year": 2023,
        "common_flow_code": "10.01.11", "common_flow_label": "10.01.11 Oil refineries",
        "common_product_code": "99", "common_product_label": "99 Unmapped fuel",
        "value": 12.0, "_emissions_component": "Power generation and own use",
    }])
    attached = emissions.attach_emissions(rows, pd.DataFrame([{
        "common_product_label": "01 Coal", "emissions_factor": 0.1, "emissions_unit": "Mt CO2e",
    }]))

    missing = emissions.unmatched_factor_rows(attached)

    assert missing.to_dict("records") == [{
        "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
        "source_system": "LEAP", "scenario": "Target", "year": 2023,
        "common_flow_code": "10.01.11", "common_flow_label": "10.01.11 Oil refineries",
        "common_product_code": "99", "common_product_label": "99 Unmapped fuel",
        "value": 12.0, "_emissions_component": "Power generation and own use",
    }]


def test_emissions_page_writes_and_shows_unmatched_factor_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    layout = {
        "supporting": tmp_path / "supporting_files",
        "chart_bundles": tmp_path / "chart_bundles",
        "dashboards": tmp_path / "dashboards",
    }
    for path in layout.values():
        path.mkdir()
    assigned = pd.DataFrame([
        {
            "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            "source_system": "LEAP", "scenario": "Target", "year": 2023,
            "_page_key": "industry", "_page_label": "Industry",
            "common_flow_code": "14", "common_flow_label": "14 Industry sector",
            "common_product_code": "99", "common_product_label": "99 Unmapped fuel", "value": 10.0,
        },
        {
            "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
            "source_system": "LEAP", "scenario": "Target", "year": 2023,
            "_page_key": "industry", "_page_label": "Industry",
            "common_flow_code": "14", "common_flow_label": "14 Industry sector",
            "common_product_code": "01", "common_product_label": "01 Coal", "value": 20.0,
        },
    ])
    template = {
        "emissions_page": {
            "enabled": True, "page_key": "emissions", "page_label": "Emissions",
            "demand_page_keys": ["industry"], "aggregate_flow_code": "13",
        },
        "chart_generation": {"base_year": 2022},
    }
    monkeypatch.setattr(emissions, "emissions_page_enabled", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(emissions, "load_factor_set_config", lambda _path: {})
    monkeypatch.setattr(emissions, "select_factor_set", lambda *_args: {
        "key": "test", "label": "Test factors", "emissions_unit": "Mt CO2e",
    })
    monkeypatch.setattr(emissions, "build_factor_table", lambda *_args, **_kwargs: (
        pd.DataFrame([{
            "common_product_label": "01 Coal", "emissions_factor": 0.1, "emissions_unit": "Mt CO2e",
        }]),
        {"factor_resolution": pd.DataFrame()},
    ))

    emissions.build_emissions_page(
        assigned, template, {"LEAP|Target": "LEAP Target"}, layout,
        [{"page_key": "emissions", "page_label": "Emissions", "file": "emissions.html"}],
        economy_label="United States of America",
    )

    warning_csv = layout["supporting"] / "emissions_unmatched_factor_rows.csv"
    assert warning_csv.exists()
    warning_rows = pd.read_csv(warning_csv)
    assert warning_rows[["source_system", "scenario", "year", "common_flow_label", "common_product_label"]].to_dict("records") == [{
        "source_system": "LEAP", "scenario": "Target", "year": 2023,
        "common_flow_label": "14 Industry sector", "common_product_label": "99 Unmapped fuel",
    }]
    page_html = (layout["dashboards"] / "emissions.html").read_text(encoding="utf-8")
    assert "WARNING: 1 selected row(s) have no emissions factor" in page_html
    assert "LEAP | Target | 2023 | 14 Industry sector | 99 Unmapped fuel" in page_html


def test_all_unmatched_emissions_rows_write_csv_and_explained_empty_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    layout = {
        "supporting": tmp_path / "supporting_files",
        "chart_bundles": tmp_path / "chart_bundles",
        "dashboards": tmp_path / "dashboards",
    }
    for path in layout.values():
        path.mkdir()
    assigned = pd.DataFrame([{
        "comparison_scope": "esto_leap_ninth", "economy": "20_USA",
        "source_system": "LEAP", "scenario": "Target", "year": 2023,
        "_page_key": "industry", "_page_label": "Industry",
        "common_flow_code": "14", "common_flow_label": "14 Industry sector",
        "common_product_code": "99", "common_product_label": "99 Unmapped fuel", "value": 10.0,
    }])
    template = {
        "emissions_page": {
            "enabled": True, "page_key": "emissions", "page_label": "Emissions",
            "demand_page_keys": ["industry"], "aggregate_flow_code": "13",
        },
        "chart_generation": {"base_year": 2022},
    }
    monkeypatch.setattr(emissions, "emissions_page_enabled", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(emissions, "load_factor_set_config", lambda _path: {})
    monkeypatch.setattr(emissions, "select_factor_set", lambda *_args: {
        "key": "test", "label": "Test factors", "emissions_unit": "Mt CO2e",
    })
    monkeypatch.setattr(emissions, "build_factor_table", lambda *_args, **_kwargs: (
        pd.DataFrame(columns=["common_product_label", "emissions_factor", "emissions_unit"]),
        {"factor_resolution": pd.DataFrame()},
    ))

    manifest_rows, page_row = emissions.build_emissions_page(
        assigned, template, {"LEAP|Target": "LEAP Target"}, layout,
        [{"page_key": "emissions", "page_label": "Emissions", "file": "emissions.html"}],
        economy_label="United States of America",
    )

    assert manifest_rows == []
    assert page_row["area_chart_count"] == 0
    warning_csv = layout["supporting"] / "emissions_unmatched_factor_rows.csv"
    assert warning_csv.exists()
    assert pd.read_csv(warning_csv)[["source_system", "scenario", "year", "common_flow_label", "common_product_label"]].to_dict("records") == [{
        "source_system": "LEAP", "scenario": "Target", "year": 2023,
        "common_flow_label": "14 Industry sector", "common_product_label": "99 Unmapped fuel",
    }]
    page_html = (layout["dashboards"] / "emissions.html").read_text(encoding="utf-8")
    assert "No emissions charts" in page_html
    assert "WARNING: 1 selected row(s) have no emissions factor" in page_html
    assert "LEAP | Target | 2023 | 14 Industry sector | 99 Unmapped fuel" in page_html


def _hierarchy_rows() -> pd.DataFrame:
    """One source reporting a sector total, its children, and a spanning rollup."""
    return pd.DataFrame(
        [
            ("NINTH", "reference", 2030, "16 Other sector", "08.01 Natural gas", 100.0),
            ("NINTH", "reference", 2030, "16.02 Residential", "08.01 Natural gas", 60.0),
            ("NINTH", "reference", 2030, "16.05 Non-specified others", "08.01 Natural gas", 40.0),
            ("NINTH", "reference", 2030, "17 Non-energy use", "08.01 Natural gas", 25.0),
            (
                "NINTH", "reference", 2030,
                "16.03-16.05,17 Other sector including non-energy", "08.01 Natural gas", 65.0,
            ),
        ],
        columns=["source_system", "scenario", "year", "common_flow_label", "common_product_label", "value"],
    )


def test_non_overlapping_frontier_keeps_detail_not_overlapping_aggregates():
    frontier = emissions.select_non_overlapping_rows(_hierarchy_rows())
    assert set(frontier["common_flow_label"]) == {
        "16.02 Residential",
        "16.05 Non-specified others",
        "17 Non-energy use",
    }
    # The two aggregates overlap on 16.05, so keeping either would double count.
    assert frontier["value"].sum() == pytest.approx(125.0)


def test_frontier_coverage_check_reports_missing_detail():
    rows = _hierarchy_rows()
    # Drop the detail that makes "16 Other sector" add up.
    rows = rows[rows["common_flow_label"] != "16.05 Non-specified others"]
    frontier = emissions.select_non_overlapping_rows(rows)
    check = emissions.frontier_coverage_check(rows, frontier)
    gap = check[check["common_flow_label"] == "16 Other sector"]["difference"]
    assert gap.iloc[0] == pytest.approx(40.0)


def test_emissions_uses_aggregate_tfc_when_sector_detail_is_absent():
    detail = pd.DataFrame([
        {"source_system": "NINTH", "scenario": "Target", "common_flow_label": "Industry", "common_product_label": "Gas", "value": 10.0},
    ])
    overview = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "common_flow_code": "12", "common_flow_label": "12 Total final consumption", "common_product_label": "Gas", "value": 25.0},
    ])

    selected, selection = emissions.select_emissions_demand_rows(detail, overview)

    assert set(selected["source_system"]) == {"LEAP", "NINTH"}
    assert selected.loc[selected["source_system"] == "LEAP", "value"].tolist() == [25.0]
    assert selection.set_index("source_system").loc["LEAP", "emissions_level"] == "aggregate"
    assert selection.set_index("source_system").loc["NINTH", "emissions_level"] == "detail"


def test_emissions_prefers_detail_over_aggregate_for_same_source():
    detail = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "common_flow_label": "Industry", "common_product_label": "Gas", "value": 10.0},
    ])
    overview = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "common_flow_code": "12", "common_flow_label": "12 Total final consumption", "common_product_label": "Gas", "value": 25.0},
    ])

    selected, selection = emissions.select_emissions_demand_rows(detail, overview)

    assert selected["value"].tolist() == [10.0]
    assert selection.loc[0, "emissions_level"] == "detail"


def test_emissions_keeps_major_sector_labels_from_aggregate_branch_rows():
    detail = pd.DataFrame([
        {"source_system": "LEAP", "scenario": "Target", "_page_label": "Industry", "common_flow_label": "All demand aggregated / Industry", "common_product_label": "Gas", "value": 10.0},
        {"source_system": "LEAP", "scenario": "Target", "_page_label": "Buildings", "common_flow_label": "All demand aggregated / Buildings", "common_product_label": "Gas", "value": 20.0},
    ])
    overview = pd.DataFrame(columns=[
        "source_system", "scenario", "common_flow_code", "common_flow_label",
        "common_product_label", "value",
    ])

    selected, _ = emissions.select_emissions_demand_rows(detail, overview)

    assert selected["_page_label"].tolist() == ["Industry", "Buildings"]


def _power_transformation_rows(*pairs: tuple[str, float]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "_page_key": "power",
            "_page_label": "Power",
            "common_flow_code": flow_code,
            "component_flow_code": flow_code,
            "common_flow_label": flow_code,
            "common_product_label": "08.01 Natural gas",
            "source_system": "NINTH",
            "scenario": "reference",
            "year": 2030,
            "value": value,
        }
        for flow_code, value in pairs
    ])


def test_transformation_frontier_keeps_reconciling_power_children() -> None:
    rows = _power_transformation_rows(
        ("09.01", -100.0),
        ("09.01.01", -40.0),
        ("09.01.02", -60.0),
    )

    frontier = emissions._lowest_transformation_frontier(rows)

    assert set(frontier["common_flow_code"]) == {"09.01.01", "09.01.02"}
    assert frontier["value"].sum() == pytest.approx(-100.0)


def test_transformation_frontier_retains_parent_when_power_children_mismatch() -> None:
    rows = _power_transformation_rows(
        ("09.01", -100.0),
        ("09.01.01", -40.0),
        ("09.01.02", -50.0),
    )

    frontier = emissions._lowest_transformation_frontier(rows)

    assert set(frontier["common_flow_code"]) == {"09.01"}
    assert frontier["value"].sum() == pytest.approx(-100.0)


def test_transformation_frontier_uses_active_scope_power_parent_per_year() -> None:
    rows = pd.concat([
        _power_transformation_rows(
            ("09.01-09.02", -100.0),
            ("09.01.01,09.02.01", -35.0),
            ("09.01.02,09.02.02", -45.0),
        ),
        _power_transformation_rows(
            ("09.01-09.02", -90.0),
            ("09.01.01,09.02.01", -30.0),
            ("09.01.02,09.02.02", -40.0),
        ).assign(year=2031),
    ], ignore_index=True)

    frontier = emissions._lowest_transformation_frontier(rows)

    assert frontier[["year", "common_flow_code", "value"]].to_dict("records") == [
        {"year": 2030, "common_flow_code": "09.01-09.02", "value": -100.0},
        {"year": 2031, "common_flow_code": "09.01-09.02", "value": -90.0},
    ]


def test_transformation_frontier_treats_compound_chp_as_an_additive_sibling() -> None:
    rows = _power_transformation_rows(
        ("09", 25.0),
        ("09.01-09.02", -100.0),
        ("09.01.01,09.02.01", -90.0),
        ("09.01.02,09.02.02,09.01.02.01,09.02.02.01", -10.0),
    )

    frontier = emissions._lowest_transformation_frontier(rows)

    assert set(frontier["common_flow_code"]) == {
        "09.01.01,09.02.01",
        "09.01.02,09.02.02,09.01.02.01,09.02.02.01",
    }
    assert frontier["value"].sum() == pytest.approx(-100.0)


def test_transformation_frontier_never_uses_total_transformation_as_power_fallback() -> None:
    rows = _power_transformation_rows(
        ("09", -200.0),
        ("09.01-09.02", -100.0),
        ("09.01.01,09.02.01", -90.0),
    )

    frontier = emissions._lowest_transformation_frontier(rows)

    assert set(frontier["common_flow_code"]) == {"09.01-09.02"}
    assert frontier["value"].sum() == pytest.approx(-100.0)


def test_transformation_frontier_emits_parent_child_reconciliation_qa() -> None:
    rows = _power_transformation_rows(
        ("09.01", -100.0),
        ("09.01.01", -40.0),
        ("09.01.02", -50.0),
    )

    selected, coverage, *_ = emissions.select_emissions_component_rows(
        rows,
        {"demand_page_keys": ["industry", "transport", "buildings", "others"]},
    )

    assert set(selected["common_flow_code"]) == {"09.01"}
    assert selected["value"].sum() == pytest.approx(100.0)
    qa = coverage[coverage["common_flow_label"].eq("09.01")]
    assert len(qa) == 1
    assert qa.iloc[0]["status"] == "failed"
    assert qa.iloc[0]["reconciliation_action"] == "parent_fallback"


def test_emissions_power_reconciliation_does_not_change_detailed_power_frontier() -> None:
    rows = _power_transformation_rows(
        ("09.01-09.02", -100.0),
        ("09.01.01,09.02.01", -40.0),
        ("09.01.03,09.02.03", -60.0),
    )

    selected, coverage, *_ = emissions.select_emissions_component_rows(
        rows,
        {"demand_page_keys": ["industry", "transport", "buildings", "others"]},
    )

    assert set(selected["common_flow_code"]) == {
        "09.01.01,09.02.01",
        "09.01.03,09.02.03",
    }
    assert selected["value"].sum() == pytest.approx(100.0)
    qa = coverage[coverage["common_flow_label"].eq("09.01-09.02")]
    assert len(qa) == 1
    assert qa.iloc[0]["status"] == "passed"
    assert qa.iloc[0]["reconciliation_action"] == "children"


def test_emissions_power_reconciliation_prefers_children_when_parent_incomplete() -> None:
    # DASH-037: Broad 09.01-09.02 parent contains only Heat plants (-10.0),
    # while detailed power processes report full generation (-100.0).
    # Detailed children must be retained so combustion is not erased.
    rows = _power_transformation_rows(
        ("09.01-09.02", -10.0),
        ("09.01.01.01,09.02.01.01", -90.0),
        ("09.01.03,09.02.03", -10.0),
    )

    selected, coverage, *_ = emissions.select_emissions_component_rows(
        rows,
        {"demand_page_keys": ["industry", "transport", "buildings", "others"]},
    )

    assert set(selected["common_flow_code"]) == {
        "09.01.01.01,09.02.01.01",
        "09.01.03,09.02.03",
    }
    assert selected["value"].sum() == pytest.approx(100.0)
    qa = coverage[coverage["common_flow_label"].eq("09.01-09.02")]
    assert len(qa) == 1
    assert qa.iloc[0]["status"] == "passed"
    assert qa.iloc[0]["reconciliation_action"] == "children"


def test_emissions_page_note_is_short_and_plain_language() -> None:
    assert emissions._page_note({}, "Mt CO2e", ["LEAP"]) == (
        "Emissions (Mt CO₂) are estimated from final demand, power generation and "
        "energy-sector own use, using energy-weighted 9th Edition CO₂e factors."
    )


def test_emissions_stacked_scenarios_keep_only_default_stack_visible() -> None:
    rows = pd.DataFrame([
        {
            "source_system": "ESTO_EXTENDED", "scenario": "historical", "year": 2022,
            "common_product_label": "08.01 Natural gas", "_sector_label": "Industry",
            "emissions_value": 10.0,
        },
        {
            "source_system": "LEAP", "scenario": "Target", "year": 2023,
            "common_product_label": "08.01 Natural gas", "_sector_label": "Industry",
            "emissions_value": 20.0,
        },
        {
            "source_system": "LEAP", "scenario": "Reference", "year": 2023,
            "common_product_label": "08.01 Natural gas", "_sector_label": "Industry",
            "emissions_value": 30.0,
        },
    ])

    figure = emissions._stacked_emissions_chart(
        rows,
        "_sector_label",
        "Emissions by sector",
        "Mt CO2e",
        {},
        "LEAP",
        "Target",
        2022,
    )

    stack_meta = [
        entry for entry in figure.layout.meta["trace_meta"]
        if entry["metric"] == "both"
    ]
    assert [entry["active_visible"] for entry in stack_meta[:2]] == [True, False]


def test_emissions_page_is_hidden_when_its_inputs_are_missing(tmp_path):
    template = {
        "emissions_page": {
            "enabled": True,
            "factor_sets_config_path": str(tmp_path / "does_not_exist.json"),
        }
    }
    assert emissions.emissions_page_enabled(template) is False


def test_emissions_page_is_hidden_when_no_demand_rows_are_assigned(monkeypatch):
    """A navigation chip must never outlive the page it points at.

    render_dashboard fixes the navigation inventory before any page is written,
    so the gate it consults has to agree with what build_emissions_page can
    actually produce.
    """
    template = {"emissions_page": {"enabled": True, "demand_page_keys": ["industry"]}}
    monkeypatch.setattr(emissions, "load_factor_set_config", lambda _path: {})
    empty_pages = pd.DataFrame({"_page_key": ["supply", "power"]})
    assert emissions.emissions_page_enabled(template, empty_pages) is False


def test_shipped_factor_set_config_is_loadable():
    config = emissions.load_factor_set_config(
        "config/common_esto_dashboard/emissions_factor_sets.json"
    )
    factor_set = emissions.select_factor_set(config)
    assert factor_set["mapping_axis"] in emissions.SUPPORTED_MAPPING_AXES
    assert emissions._resolve_repo_path(factor_set["path"]).exists()
    overrides = factor_set["esto_product_factor_overrides"]
    assert overrides["15.01 Fuelwood & woodwaste"] == 0.0
    assert overrides["16.03 Municipal solid waste (renewable)"] == 0.0
    assert "16.02 Industrial waste" not in overrides
    assert "16.04 Municipal solid waste (non-renewable)" not in overrides


def test_template_declares_the_emissions_page():
    template = json.loads(
        (Path("config/common_esto_dashboard/common_esto_dashboard_template.json")).read_text(
            encoding="utf-8"
        )
    )
    config = emissions.emissions_page_config(template)
    assert config["enabled"] is True
    declared_pages = {str(rule.get("page_key")) for rule in template["sector_pages"]}
    assert set(config["demand_page_keys"]) <= declared_pages
