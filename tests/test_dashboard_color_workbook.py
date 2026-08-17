"""Focused tests for the colleague-facing dashboard colour workbook."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.styles import Color, PatternFill

from codebase.dashboard_color_config import average_oklab
from scripts.manage_dashboard_colors import export_color_workbook, import_color_workbook


def _sample_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "plotting": {"product": {"Coal": "#111111"}, "flow": {}, "capacity": {}},
                "product": {
                    "01": "#0D0D0D",
                    "01.02": "#A6A6A6",
                    "01.03": "#C4C4C4",
                    "01.04": "#7D7D7D",
                    "17": "#FFD757",
                },
                "flow": {
                    "01": "#2F855A",
                    "18.01": "#362B4F",
                    "18.02": "#8A5DA7",
                    "18.03": "#0F266B",
                },
            }
        ),
        encoding="utf-8",
    )


def _sample_common_rows(path: Path) -> None:
    path.write_text(
        "comparison_scope,common_product_code,common_product_label,component_product_code,common_flow_code,common_flow_label,component_flow_code\n"
        "esto_leap_ninth,01.02-01.04,01.02-01.04 Coal,01.02,18.01-18.03,18.01-18.03 Electricity output in GWh,18.01\n"
        "esto_leap_ninth,01.02-01.04,01.02-01.04 Coal,01.03,18.01-18.03,18.01-18.03 Electricity output in GWh,18.02\n"
        "esto_leap_ninth,01.02-01.04,01.02-01.04 Coal,01.04,18.01-18.03,18.01-18.03 Electricity output in GWh,18.03\n",
        encoding="utf-8",
    )


def _row_for_key(sheet: object, key: str) -> int:
    return next(row for row in range(2, sheet.max_row + 1) if sheet.cell(row=row, column=1).value == key)


def test_export_and_import_accept_typed_and_fill_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    custom_path = tmp_path / "code_colors_custom.json"
    workbook_path = tmp_path / "colors.xlsx"
    common_rows_path = tmp_path / "common_rows.csv"
    _sample_config(config_path)
    _sample_common_rows(common_rows_path)

    export_color_workbook(output_path=workbook_path, code_colors_path=config_path, common_rows_path=common_rows_path)
    workbook = load_workbook(workbook_path)
    assert workbook["_metadata"].sheet_state == "hidden"
    assert workbook["Products"].column_dimensions["A"].hidden is True
    assert workbook["Products"]["B2"].value == "01 Coal"
    assert workbook["Products"]["C2"].value == "#0D0D0D"
    assert workbook["Products"]["C2"].fill.fgColor.rgb.endswith("0D0D0D")
    product_row = _row_for_key(workbook["Products"], "01.02")
    flow_row = _row_for_key(workbook["Flows"], "01")
    workbook["Products"].cell(product_row, 3).value = "#123456"
    workbook["Flows"].cell(flow_row, 3).fill = PatternFill("solid", fgColor="ABCDEF")
    workbook.save(workbook_path)

    import_color_workbook(workbook_path, config_path, custom_path, common_rows_path)
    custom = json.loads(custom_path.read_text(encoding="utf-8"))
    production = json.loads(config_path.read_text(encoding="utf-8"))
    assert custom["product"]["01.02"] == "#123456"
    assert custom["flow"]["01"] == "#ABCDEF"
    assert production["product"]["01.02"] == "#123456"
    assert production["flow"]["01"] == "#ABCDEF"
    assert production["common"]["product"]["01.02-01.04"] == average_oklab(["#123456", "#C4C4C4", "#7D7D7D"])
    assert set(workbook.sheetnames) == {"START HERE", "Products", "Flows", "_metadata"}


def test_import_rejects_conflicting_typed_and_fill_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    workbook_path = tmp_path / "colors.xlsx"
    common_rows_path = tmp_path / "common_rows.csv"
    _sample_config(config_path)
    _sample_common_rows(common_rows_path)
    export_color_workbook(output_path=workbook_path, code_colors_path=config_path, common_rows_path=common_rows_path)
    workbook = load_workbook(workbook_path)
    workbook["Products"]["C2"] = "#123456"
    workbook["Products"]["C2"].fill = PatternFill("solid", fgColor="654321")
    workbook.save(workbook_path)

    with pytest.raises(ValueError, match="disagree"):
        import_color_workbook(workbook_path, config_path, tmp_path / "custom.json", common_rows_path)


def test_import_accepts_excel_theme_fill(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    workbook_path = tmp_path / "colors.xlsx"
    custom_path = tmp_path / "custom.json"
    common_rows_path = tmp_path / "common_rows.csv"
    _sample_config(config_path)
    _sample_common_rows(common_rows_path)
    export_color_workbook(output_path=workbook_path, code_colors_path=config_path, common_rows_path=common_rows_path)
    workbook = load_workbook(workbook_path)
    workbook["Products"]["C2"].fill = PatternFill("solid", fgColor=Color(theme=4))
    workbook.save(workbook_path)

    import_color_workbook(workbook_path, config_path, custom_path, common_rows_path)
    custom = json.loads(custom_path.read_text(encoding="utf-8"))
    assert custom["product"]["01"] == "#4F81BD"


def test_import_preserves_explicit_common_rollup_override(tmp_path: Path) -> None:
    config_path = tmp_path / "code_colors.json"
    workbook_path = tmp_path / "colors.xlsx"
    custom_path = tmp_path / "custom.json"
    common_rows_path = tmp_path / "common_rows.csv"
    _sample_config(config_path)
    _sample_common_rows(common_rows_path)
    export_color_workbook(output_path=workbook_path, code_colors_path=config_path, common_rows_path=common_rows_path)
    workbook = load_workbook(workbook_path)
    rollup_row = _row_for_key(workbook["Products"], "common::01.02-01.04")
    workbook["Products"].cell(rollup_row, 3).value = "#445566"
    workbook.save(workbook_path)

    import_color_workbook(workbook_path, config_path, custom_path, common_rows_path)
    custom = json.loads(custom_path.read_text(encoding="utf-8"))
    production = json.loads(config_path.read_text(encoding="utf-8"))
    assert custom["common_overrides"]["product"]["01.02-01.04"] == "#445566"
    assert production["common"]["product"]["01.02-01.04"] == "#445566"
