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


def test_index_and_chart_guides_have_different_steps() -> None:
    chart_script = build_guide_fragments("chart", "supply", "Supply")["script"]
    index_script = build_guide_fragments("index", "index", "Common ESTO Dashboard")["script"]

    assert "Compare projection scenarios" in chart_script
    assert "Compare projection scenarios" not in index_script
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

    assert "Review the conversion story" in power_script
    assert "Power review sequence" in power_script
    assert "These emissions are derived" not in power_script
    assert "These emissions are derived" in emissions_script
    assert "Included and excluded boundaries" in emissions_script


def test_chart_guide_explains_the_overview_first_review_strategy() -> None:
    chart_script = build_guide_fragments("chart", "industry", "Industry")["script"]

    assert "Start with the summaries, not every chart" in chart_script
    assert "every valid flow-product pair" in chart_script
    assert "Recommended way to use a dense page" in chart_script
    assert chart_script.index("Start with the summaries") < chart_script.index("Read like with like")


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
