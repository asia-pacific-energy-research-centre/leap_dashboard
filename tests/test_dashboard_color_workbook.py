"""Focused tests for the colleague-facing dashboard colour workbook."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.styles import Color, PatternFill

from scripts.manage_dashboard_colors import export_color_workbook, import_color_workbook


def _sample_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "plotting": {"product": {"Coal": "#111111"}, "flow": {}, "capacity": {}},
                "product": {"01": "#0D0D0D", "17": "#FFD757"},
                "flow": {"01": "#2F855A"},
            }
        ),
        encoding="utf-8",
    )


def test_export_and_import_accept_typed_and_fill_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    custom_path = tmp_path / "code_colors_custom.json"
    workbook_path = tmp_path / "colors.xlsx"
    _sample_config(config_path)

    export_color_workbook(output_path=workbook_path, code_colors_path=config_path)
    workbook = load_workbook(workbook_path)
    assert workbook["_metadata"].sheet_state == "hidden"
    assert workbook["Products"]["D2"].value == "#0D0D0D"
    assert workbook["Products"]["D2"].fill.fgColor.rgb.endswith("0D0D0D")
    workbook["Products"]["D2"] = "#123456"
    workbook["Flows"]["D2"].fill = PatternFill("solid", fgColor="ABCDEF")
    workbook.save(workbook_path)

    import_color_workbook(workbook_path, config_path, custom_path)
    custom = json.loads(custom_path.read_text(encoding="utf-8"))
    production = json.loads(config_path.read_text(encoding="utf-8"))
    assert custom["product"]["01"] == "#123456"
    assert custom["flow"]["01"] == "#ABCDEF"
    assert production["product"]["01"] == "#123456"
    assert production["flow"]["01"] == "#ABCDEF"


def test_import_rejects_conflicting_typed_and_fill_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    workbook_path = tmp_path / "colors.xlsx"
    _sample_config(config_path)
    export_color_workbook(output_path=workbook_path, code_colors_path=config_path)
    workbook = load_workbook(workbook_path)
    workbook["Products"]["D2"] = "#123456"
    workbook["Products"]["D2"].fill = PatternFill("solid", fgColor="654321")
    workbook.save(workbook_path)

    with pytest.raises(ValueError, match="disagree"):
        import_color_workbook(workbook_path, config_path, tmp_path / "custom.json")


def test_import_accepts_excel_theme_fill(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    workbook_path = tmp_path / "colors.xlsx"
    custom_path = tmp_path / "custom.json"
    _sample_config(config_path)
    export_color_workbook(output_path=workbook_path, code_colors_path=config_path)
    workbook = load_workbook(workbook_path)
    workbook["Products"]["D2"].fill = PatternFill("solid", fgColor=Color(theme=4))
    workbook.save(workbook_path)

    import_color_workbook(workbook_path, config_path, custom_path)
    custom = json.loads(custom_path.read_text(encoding="utf-8"))
    assert custom["product"]["01"] == "#4F81BD"
