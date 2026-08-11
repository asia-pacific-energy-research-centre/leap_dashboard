import json
from pathlib import Path

import pytest

from codebase.common_esto_dashboard_guide import (
    DEFAULT_GUIDE_CONFIG_PATH,
    build_guide_fragments,
    validate_guide_config,
)


def test_guide_config_is_valid_and_page_copy_is_resolved() -> None:
    config = json.loads(DEFAULT_GUIDE_CONFIG_PATH.read_text(encoding="utf-8"))
    validate_guide_config(config)

    fragments = build_guide_fragments("chart", "power", "Power")

    assert "Use Power to review electricity and heat generation" in fragments["script"]
    assert "{page_purpose}" not in fragments["script"]
    assert 'id="dashboard-guide-launch"' in fragments["launch_button_html"]
    assert 'role="dialog"' in fragments["dialog_html"]
    assert ".dashboard-guide-highlight" in fragments["css"]


def test_industry_purpose_warns_about_possible_mapping_errors() -> None:
    fragments = build_guide_fragments("chart", "industry", "Industry")

    assert "Occasional mapping errors can make a chart show something unexpected" in fragments["script"]
    assert "please let the dashboard developer know" in fragments["script"]
    assert "white-space:pre-line" in fragments["css"]


def test_index_and_chart_guides_have_different_steps() -> None:
    chart_script = build_guide_fragments("chart", "supply", "Supply")["script"]
    index_script = build_guide_fragments("index", "index", "Common ESTO Dashboard")["script"]

    assert "Choose what you are viewing" in chart_script
    assert "Choose what you are viewing" not in index_script
    assert "Choose where to begin" in index_script
    assert "What mapping diagnostics are for" in build_guide_fragments(
        "diagnostics", "mapping_diagnostics", "Mapping diagnostics"
    )["script"]
    assert "What the mapping tree shows" in build_guide_fragments(
        "tree", "mapping_tree_explorer", "Full mapping tree explorer"
    )["script"]


def test_chart_guide_adds_only_the_current_pages_review_content() -> None:
    power_script = build_guide_fragments("chart", "power", "Power")["script"]
    emissions_script = build_guide_fragments("chart", "emissions", "Emissions")["script"]

    assert "do not measure power-sector own use or losses" in power_script
    assert "Review the conversion story" not in power_script
    assert "Power review sequence" not in power_script
    assert "These emissions are derived" not in power_script
    assert "These emissions are derived" in emissions_script
    assert "Included and excluded boundaries" in emissions_script


def test_routed_chart_pages_use_mapping_backed_contents_tables() -> None:
    config = json.loads(DEFAULT_GUIDE_CONFIG_PATH.read_text(encoding="utf-8"))
    routed_pages = {
        "supply",
        "power",
        "refining",
        "other_transformation",
        "industry",
        "transport",
        "buildings",
        "others",
        "non_energy",
        "transport_leap_vs_ninth",
        "datacentres_leap_vs_ninth",
    }

    for page_key in routed_pages:
        scope_step = config["page_steps"][page_key][0]
        assert scope_step["dynamic_content"] == "page_mapping_table"

    assert "dynamic_content" not in config["page_steps"]["total_demand"][0]
    assert "dynamic_content" not in config["page_steps"]["emissions"][0]


@pytest.mark.parametrize(
    ("page_key", "page_label", "scope_title"),
    [
        ("total_demand", "Energy balance overview", "What appears on the Energy balance overview"),
        ("supply", "Supply", "What appears on Supply"),
        ("power", "Power", "What appears on Power"),
        ("refining", "Refining", "What appears on Refining"),
        ("other_transformation", "Other transformation", "What appears on Other transformation"),
        ("industry", "Industry", "What appears on Industry"),
        ("transport", "Transport", "What appears on Transport"),
        ("buildings", "Buildings", "What appears on Buildings"),
        ("others", "Other demand", "What appears on Other demand"),
        ("non_energy", "Non-energy use", "What appears on Non-energy use"),
        ("emissions", "Emissions", "What appears on Emissions"),
        ("transport_leap_vs_ninth", "Diagnostic transport", "What appears on diagnostic Transport"),
        ("datacentres_leap_vs_ninth", "Diagnostic datacentres", "What appears on diagnostic Datacentres"),
    ],
)
def test_each_chart_page_has_unique_scope_guidance(
    page_key: str,
    page_label: str,
    scope_title: str,
) -> None:
    script = build_guide_fragments("chart", page_key, page_label)["script"]

    assert scope_title in script


def test_refining_scope_explains_the_inclusive_own_use_boundary() -> None:
    script = build_guide_fragments("chart", "refining", "Refining")["script"]

    assert "LEAP does not publish refinery own use separately" in script
    assert "Standalone 10.01.11 is therefore suppressed" in script
    assert "Other transformation &gt; Transfers" not in script
    assert "Other transformation > Transfers" in script


def test_energy_balance_scope_records_tfec_as_temporarily_disabled() -> None:
    script = build_guide_fragments(
        "chart", "total_demand", "Energy balance overview"
    )["script"]

    assert "TFEC" in script
    assert "Not currently displayed" in script
    assert "temporarily disabled" in script


def test_chart_guide_explains_the_overview_first_review_strategy() -> None:
    chart_script = build_guide_fragments("chart", "industry", "Industry")["script"]

    assert "Start with the summaries, not every chart" in chart_script
    assert "Start with the summary charts at the top" in chart_script
    assert "then open the detailed charts only" in chart_script
    assert "Recommended way to use a dense page" not in chart_script
    assert chart_script.index("How common categories make comparison possible") < chart_script.index(
        "Start with the summaries"
    )


def test_transport_purpose_excludes_international_transport_without_extra_card() -> None:
    chart_script = build_guide_fragments("chart", "transport", "Transport")["script"]

    assert "International aviation and marine bunkers are not included here" in chart_script
    assert "review them on Supply" in chart_script
    assert "Separate domestic mode detail from total transport" not in chart_script


def test_buildings_guide_accepts_mapping_table_and_placeholder_context() -> None:
    context = {
        "page_mapping_table": {
            "caption": "Page categories and published source mappings",
            "headers": ["Common sector", "Common fuel", "LEAP sector"],
            "rows": [["16.02 Residential", "17 Electricity", "Buildings"]],
        },
        "placeholder_status": (
            "Placeholder in use: the LEAP 'All demand aggregated' branch supplies "
            "Buildings on this page."
        ),
    }

    script = build_guide_fragments("chart", "buildings", "Buildings", context)["script"]

    assert "16.02 Residential" in script
    assert "17 Electricity" in script
    assert "LEAP sector" in script
    assert "All demand aggregated" in script
    assert "dashboard-guide-table" in build_guide_fragments(
        "chart", "buildings", "Buildings", context
    )["dialog_html"]


def test_mapping_table_renders_optional_provenance_note() -> None:
    context = {
        "page_mapping_table": {
            "caption": "Page categories and published source mappings",
            "headers": ["Common sector", "Common fuel"],
            "rows": [["14 Industry sector", "17 Electricity"]],
            "note": "* Mapping inputs do not match.",
        }
    }

    fragments = build_guide_fragments("chart", "industry", "Industry", context)

    assert "Mapping inputs do not match" in fragments["script"]
    assert "dashboard-guide-table-note" in fragments["css"]


def test_shared_placeholder_step_is_omitted_when_page_has_no_placeholder() -> None:
    script = build_guide_fragments(
        "chart",
        "industry",
        "Industry",
        {
            "placeholder_status": "No aggregate LEAP placeholder is identified.",
            "placeholder_in_use": False,
        },
    )["script"]

    assert "What the placeholder warning means" not in script


def test_chart_guide_combines_top_controls_and_drops_review_action() -> None:
    script = build_guide_fragments("chart", "buildings", "Buildings")["script"]

    assert "change economy" in script
    assert "choose Reference or Target" in script
    assert "select which datasets define the comparison basis" in script
    assert "move between dashboard pages" in script
    assert "is explained later in this guide" not in script
    assert "correct it in the model or source data" in script
    assert "review surface, not the model itself" not in script
    assert "Work from sector total to subsector and fuel" not in build_guide_fragments(
        "chart", "industry", "Industry"
    )["script"]
    assert "Find material differences first" not in script
    assert "Confirm the economy and update" not in script
    assert "Compare projection scenarios" not in script
    assert "Move through the energy system" not in script
    assert "Turn a difference into a review action" not in script


def test_index_guide_includes_the_recommended_review_route() -> None:
    index_script = build_guide_fragments("index", "index", "Common ESTO Dashboard")["script"]

    assert "Recommended review route" in index_script
    assert "Mapping diagnostics" in index_script
    assert "does not allocate coarse values" in index_script
    assert "each routed flow is compared across every relevant product or fuel" in index_script


def test_guide_validation_rejects_duplicate_step_ids() -> None:
    step = {"id": "same", "target": "#target", "title": "Title", "copy": "Copy"}
    invalid = {
        "page_purposes": {"default": "Purpose"},
        "chart_steps": [step, dict(step)],
        "index_steps": [{"id": "index", "target": "#target", "title": "Title", "copy": "Copy"}],
        "diagnostics_steps": [{"id": "diagnostics", "target": "#target", "title": "Title", "copy": "Copy"}],
        "tree_steps": [{"id": "tree", "target": "#target", "title": "Title", "copy": "Copy"}],
    }

    with pytest.raises(ValueError, match="Duplicate guide step id"):
        validate_guide_config(invalid)


def test_guide_validation_rejects_invalid_page_steps() -> None:
    step = {"id": "step", "target": "#target", "title": "Title", "copy": "Copy"}
    invalid = {
        "page_purposes": {"default": "Purpose"},
        "chart_steps": [step],
        "index_steps": [step],
        "diagnostics_steps": [step],
        "tree_steps": [step],
        "page_steps": {"power": "not-a-list"},
    }

    with pytest.raises(ValueError, match="page_steps.power.*list"):
        validate_guide_config(invalid)


def test_guide_validation_rejects_malformed_rich_table() -> None:
    step = {"id": "step", "target": "#target", "title": "Title", "copy": "Copy"}
    invalid = {
        "page_purposes": {"default": "Purpose"},
        "chart_steps": [step],
        "index_steps": [
            {
                **step,
                "table": {"headers": ["One", "Two"], "rows": [["only one cell"]]},
            }
        ],
        "diagnostics_steps": [step],
        "tree_steps": [step],
    }

    with pytest.raises(ValueError, match="table rows must match the header count"):
        validate_guide_config(invalid)


def test_guide_config_path_is_repository_relative() -> None:
    assert DEFAULT_GUIDE_CONFIG_PATH == (
        Path(__file__).resolve().parents[1]
        / "config"
        / "common_esto_dashboard"
        / "guide_config.json"
    )
