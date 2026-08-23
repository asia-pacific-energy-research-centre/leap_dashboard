"""Tests for the narrow, packageable Common ESTO dashboard render entry point."""

import json
from pathlib import Path

import pandas as pd
import pytest

from codebase import common_esto_dashboard_portable as portable
from codebase.common_esto_dashboard_portable import (
    OPTIONAL_DASHBOARD_INPUTS,
    REQUIRED_DASHBOARD_INPUTS,
    configured_comparison_scopes,
    normalize_dashboard_economy_key,
    render_common_esto_dashboard,
    render_common_esto_dashboard_variants,
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
        "power_interim_audit_path",
        "source_to_common_map_path",
        "esto_to_common_map_path",
    }


def test_configured_comparison_scopes_use_maintained_selector() -> None:
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    definitions = configured_comparison_scopes(template)

    assert [item["comparison_scope"] for item in definitions] == [
        "esto_extended_leap_ninth",
        "esto_extended_leap",
    ]
    assert [item["output_suffix"] for item in definitions] == [
        "",
        "__esto_extended_leap",
    ]
    assert [item["is_default"] for item in definitions] == [True, False]


def test_variant_render_forwards_basis_options_and_writes_export_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_render(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        key = str(kwargs["dashboard_key"])
        root = Path(str(kwargs["output_root"])) / key
        dashboard = root / "dashboards" / "index.html"
        dashboard.parent.mkdir(parents=True, exist_ok=True)
        dashboard.write_text("<html></html>", encoding="utf-8")
        return {
            "economy": "20USA",
            "output_root": str(root),
            "dashboard_index": str(dashboard),
            "chart_manifest": str(root / "supporting_files" / "chart_manifest.csv"),
            "sign_semantics_summary": str(root / "supporting_files" / "sign.csv"),
            "chart_count": 2,
        }

    monkeypatch.setattr(portable, "render_common_esto_dashboard", fake_render)
    monkeypatch.setattr(
        portable,
        "load_source_category_map",
        lambda *_args, **_kwargs: pd.DataFrame([
            {
                "comparison_scope": "esto_leap_ninth",
                "source_system": "LEAP",
                "source_flow": "Supply",
                "source_product": "Coal",
                "common_flow_label": "Supply",
                "common_product_label": "Coal",
            }
        ]),
    )

    result = render_common_esto_dashboard_variants(
        economy="20_USA",
        comparison_data_path=COMPARISON_FIXTURE,
        common_rows_path=ROWS_FIXTURE,
        template_path=TEMPLATE_PATH,
        series_config_path=SERIES_CONFIG_PATH,
        source_to_common_map_path=tmp_path / "source.csv",
        esto_to_common_map_path=tmp_path / "esto.csv",
        output_root=tmp_path / "outputs",
        dashboard_updated_label="test",
    )

    assert [call["comparison_scope"] for call in calls] == [
        "esto_extended_leap_ninth",
        "esto_extended_leap",
    ]
    assert calls[0]["category_basis_options"] == [
        {
            "comparison_scope": "esto_extended_leap_ninth",
            "label": "LEAP + ESTO Extended + Ninth",
            "dashboard_key": "20USA",
        },
        {
            "comparison_scope": "esto_extended_leap",
            "label": "LEAP + ESTO Extended",
            "dashboard_key": "20USA__esto_extended_leap",
        },
    ]
    assert calls[0]["additional_pages"] == [{
        "page_key": "mapping_diagnostics",
        "page_label": "Mapping diagnostics",
        "file": "../../diagnostics/dashboards/mapping_diagnostics.html",
    }]
    assert result["chart_count"] == 4
    assert result["mapping_diagnostics"]["unmapped_branch_count"] == 0
    assert (tmp_path / "outputs" / "diagnostics" / "dashboards" / "mapping_diagnostics.html").is_file()


def test_portable_mapping_diagnostics_shows_unmapped_categories(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa_nonzero_unmapped_leap_branches.csv"
    pd.DataFrame([{
        "leap_flow": "Freight road",
        "leap_product": "Gas and diesel oil",
        "indirect_esto_flow": "",
        "indirect_esto_product": "",
        "qa_status": "nonzero_unmapped_leap_branch_without_esto_pair",
    }]).to_csv(qa_path, index=False)

    result = portable.write_portable_mapping_diagnostics_page(
        output_root=tmp_path / "output",
        economy="20_USA",
        unmapped_branches_path=qa_path,
    )

    html = Path(str(result["page"])).read_text(encoding="utf-8")
    assert "Imported LEAP category recognition" in html
    assert "Freight road" in html
    assert "fully imported into the main LEAP areas" in html


def test_extended_scope_renders_ordinary_history_under_extended_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison = pd.read_csv(COMPARISON_FIXTURE)
    comparison = comparison[
        comparison["comparison_scope"].eq("esto_leap_ninth")
    ].copy()
    comparison["comparison_scope"] = "esto_extended_leap_ninth"
    comparison.loc[
        comparison["source_system"].eq("ESTO"), "source_system"
    ] = "ESTO_EXTENDED"
    comparison_path = tmp_path / "extended_comparison.csv"
    comparison.to_csv(comparison_path, index=False)
    captured: dict[str, object] = {}

    def fake_render_dashboard(df: pd.DataFrame, template: dict, *args: object, **kwargs: object) -> pd.DataFrame:
        captured["sources"] = set(df["source_system"].astype(str))
        captured["comparison_source"] = template["chart_generation"][
            "comparison_source_system"
        ]
        return pd.DataFrame()

    monkeypatch.setattr(portable, "render_dashboard", fake_render_dashboard)
    render_common_esto_dashboard(
        economy="20_USA",
        comparison_data_path=comparison_path,
        common_rows_path=ROWS_FIXTURE,
        template_path=TEMPLATE_PATH,
        series_config_path=SERIES_CONFIG_PATH,
        output_root=tmp_path / "outputs",
        comparison_scope="esto_extended_leap_ninth",
        active_dataset_filter_options=["LEAP", "ESTO_EXTENDED", "NINTH"],
        min_year=2020,
        max_year=2022,
    )

    assert "ESTO_EXTENDED" in captured["sources"]
    assert captured["comparison_source"] == "ESTO_EXTENDED"


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


def test_placeholder_metadata_does_not_hide_sector_pages(tmp_path: Path) -> None:
    baseline = _render(tmp_path / "baseline")
    restricted = _render(
        tmp_path / "restricted",
        representation_status_df=pd.DataFrame(
            [{
                "component_branch": "Road",
                "detailed_branches": "Freight road;Passenger road",
                "representation_status": "placeholder_only_retained",
            }]
        ),
    )
    assert restricted["leap_demand_representation_status_rows"] == 1
    assert int(restricted["chart_count"]) == int(baseline["chart_count"])


def test_power_interim_audit_adds_placeholder_note(tmp_path: Path) -> None:
    audit_path = tmp_path / "leap_source_branch_fallback_audit.csv"
    pd.DataFrame(
        [
            {
                "economy": "20_USA",
                "year": 2025,
                "status": "interim_only_retained",
                "interim_branch": "Electricity interim",
            },
            {
                "economy": "20_USA",
                "year": 2025,
                "status": "interim_zeroed",
                "interim_branch": "CHP interim",
            },
        ]
    ).to_csv(audit_path, index=False)

    result = _render(tmp_path, power_interim_audit_path=audit_path)

    assert result["power_interim_placeholder_branches"] == ["Electricity interim"]
    power_html = Path(str(result["dashboard_index"])).with_name("power.html")
    assert "LEAP placeholder in use" in power_html.read_text(encoding="utf-8")
