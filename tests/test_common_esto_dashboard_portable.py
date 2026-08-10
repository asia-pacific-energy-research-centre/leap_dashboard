"""Tests for the narrow, packageable Common ESTO dashboard render entry point."""

import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.common_esto_dashboard_portable import (
    OPTIONAL_DASHBOARD_INPUTS,
    REQUIRED_DASHBOARD_INPUTS,
    normalize_dashboard_economy_key,
    render_common_esto_dashboard,
)
from codebase.common_esto_dashboard_renderer import (
    load_code_colors,
    set_code_colors_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard"
COMPARISON_FIXTURE = FIXTURE_DIR / "common_esto_comparison_data_sample.csv"
ROWS_FIXTURE = FIXTURE_DIR / "common_esto_rows.csv"
TEMPLATE_PATH = (
    REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
)
SERIES_CONFIG_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "series_config.json"


def _render(tmp_path: Path, **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "economy": "20_USA",
        "comparison_data_path": COMPARISON_FIXTURE,
        "common_rows_path": ROWS_FIXTURE,
        "template_path": TEMPLATE_PATH,
        "series_config_path": SERIES_CONFIG_PATH,
        "output_root": tmp_path / "outputs",
        "dashboard_updated_label": "fixed-label-for-tests",
        # A full 2010-2060 render of the USA fixture takes minutes. These tests
        # check the render contract, not chart content, so they use a short
        # window to stay usable as a focused check.
        "min_year": 2020,
        "max_year": 2030,
    }
    kwargs.update(overrides)
    return render_common_esto_dashboard(**kwargs)  # type: ignore[arg-type]


def test_normalize_dashboard_economy_key_accepts_both_forms() -> None:
    assert normalize_dashboard_economy_key("20_USA") == "20USA"
    assert normalize_dashboard_economy_key("20USA") == "20USA"
    assert normalize_dashboard_economy_key("  02_BD ") == "02BD"


def test_normalize_dashboard_economy_key_rejects_blank() -> None:
    with pytest.raises(ValueError, match="economy code is required"):
        normalize_dashboard_economy_key("   ")


def test_required_inputs_are_declared_for_every_path_argument() -> None:
    # Callers explain missing inputs from this mapping, so it must stay in step
    # with the render signature's required path arguments.
    assert set(REQUIRED_DASHBOARD_INPUTS) == {
        "comparison_data_path",
        "common_rows_path",
        "template_path",
        "series_config_path",
    }


def test_optional_inputs_are_declared() -> None:
    assert set(OPTIONAL_DASHBOARD_INPUTS) == {
        "code_colors_path",
        "source_to_common_map_path",
        "esto_to_common_map_path",
    }


def test_code_colors_path_can_be_redirected_and_restored(tmp_path: Path) -> None:
    # A distributed package keeps config/ outside the repository layout, so the
    # colour map must be locatable without a repo-relative path.
    default_colors = load_code_colors()
    custom = tmp_path / "code_colors.json"
    custom.write_text(
        json.dumps({"product": {"01.01": "#123456"}, "flow": {}, "plotting": {}}),
        encoding="utf-8",
    )
    try:
        assert set_code_colors_path(custom) == custom
        assert load_code_colors()["product"]["01.01"] == "#123456"
    finally:
        restored = set_code_colors_path(None)
    assert restored.name == "code_colors.json"
    assert load_code_colors() == default_colors


def test_render_writes_dashboard_index_and_manifest(tmp_path: Path) -> None:
    result = _render(tmp_path)

    assert result["economy"] == "20USA"
    index_path = Path(str(result["dashboard_index"]))
    manifest_path = Path(str(result["chart_manifest"]))
    sign_summary_path = Path(str(result["sign_semantics_summary"]))
    assert index_path.exists()
    assert manifest_path.exists()
    assert sign_summary_path.exists()
    assert int(result["chart_count"]) > 0

    manifest = pd.read_csv(manifest_path)
    assert len(manifest) == int(result["chart_count"])

    bundles = list((tmp_path / "outputs" / "20USA" / "chart_bundles").glob("*.js"))
    assert bundles, "expected at least one Plotly chart bundle"


def test_render_is_independent_of_the_current_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = _render(tmp_path)
    assert Path(str(result["dashboard_index"])).exists()


def test_render_rejects_an_economy_absent_from_the_data(tmp_path: Path) -> None:
    # The upstream scope filter names the economy and the scopes it does have,
    # which is the message a caller should surface; the render's own empty-frame
    # guard is only a backstop for data that passes the scope filter.
    with pytest.raises(ValueError, match="does not contain requested comparison scope"):
        _render(tmp_path, economy="99_ZZZ")


def test_missing_leap_demand_branches_hide_sector_pages(tmp_path: Path) -> None:
    baseline = _render(tmp_path / "baseline")
    restricted = _render(
        tmp_path / "restricted",
        missing_leap_demand_branches=["Transport"],
    )
    assert restricted["missing_leap_demand_branches"] == ["Transport"]
    # Hiding a sector page cannot increase the number of rendered charts.
    assert int(restricted["chart_count"]) <= int(baseline["chart_count"])
