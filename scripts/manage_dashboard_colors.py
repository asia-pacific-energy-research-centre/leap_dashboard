#%%
"""Export and import the non-technical Excel editor for dashboard colours.

The workbook is a human editing surface. Production continues to read
``code_colors.json``; importing a returned workbook writes a complete custom
colour layer and applies it to that production file.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from colorsys import hls_to_rgb, rgb_to_hls
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.styles.colors import COLOR_INDEX
from openpyxl.worksheet.table import Table, TableStyleInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.dashboard_color_config import (
    build_common_rollup_colors,
    load_common_rollup_memberships,
    normalize_hex,
)


# --- Stable paths and workbook contract -----------------------------------

CONFIG_DIR = REPO_ROOT / "config" / "common_esto_dashboard"
CODE_COLORS_PATH = CONFIG_DIR / "code_colors.json"
CUSTOM_COLORS_PATH = CONFIG_DIR / "code_colors_custom.json"
DEFAULT_WORKBOOK_PATH = REPO_ROOT / "outputs" / "dashboard_color_mapping" / "dashboard_color_mapping.xlsx"
UPSTREAM_AXIS_NODES_PATH = (
    REPO_ROOT.parent
    / "leap_mappings"
    / "results"
    / "hierarchy_subtotal_contract"
    / "current"
    / "axis_nodes.csv"
)
FALLBACK_COMMON_ROWS_PATH = REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard" / "common_esto_rows.csv"
UPSTREAM_COMMON_ROWS_PATH = REPO_ROOT.parent / "leap_mappings" / "results" / "common_esto" / "common_esto_rows.csv"
DEFAULT_COMMON_ROWS_PATH = UPSTREAM_COMMON_ROWS_PATH if UPSTREAM_COMMON_ROWS_PATH.exists() else FALLBACK_COMMON_ROWS_PATH

WORKBOOK_SCHEMA_VERSION = "2"
COMMON_KEY_PREFIX = "common::"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SUBHEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
LOCKED_FILL = PatternFill("solid", fgColor="F2F2F2")
ROLLUP_FILL = PatternFill("solid", fgColor="D9EAF7")
WHITE_FONT = Font(color="FFFFFF")
BLACK_FONT = Font(color="000000")

SHEET_SPECS = (
    ("Products", "product"),
    ("Flows", "flow"),
)


# --- Colour and label helpers ---------------------------------------------

def _cell_fill_hex(cell: object) -> str:
    """Read an ordinary solid Excel fill as #RRGGBB, or return blank."""
    fill = getattr(cell, "fill", None)
    foreground = getattr(fill, "fgColor", None)
    if getattr(fill, "fill_type", None) != "solid" or foreground is None:
        return ""
    color_type = getattr(foreground, "type", "")
    if color_type == "rgb" and isinstance(foreground.rgb, str):
        rgb = foreground.rgb[-6:]
        return f"#{rgb.upper()}" if re.fullmatch(r"[0-9A-Fa-f]{6}", rgb) else ""
    if color_type == "indexed" and isinstance(foreground.indexed, int):
        if 0 <= foreground.indexed < len(COLOR_INDEX):
            return f"#{COLOR_INDEX[foreground.indexed][-6:].upper()}"
    if color_type == "theme" and isinstance(foreground.theme, int):
        return _theme_fill_hex(cell, foreground.theme, float(foreground.tint or 0))
    return ""


def _theme_fill_hex(cell: object, theme_index: int, tint: float) -> str:
    """Resolve an Excel theme fill, including its light/dark tint."""
    workbook = getattr(getattr(cell, "parent", None), "parent", None)
    theme_xml = getattr(workbook, "loaded_theme", None)
    if not theme_xml:
        return ""
    root = ElementTree.fromstring(theme_xml)
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    scheme = root.find(f".//{namespace}clrScheme")
    if scheme is None or not 0 <= theme_index < len(scheme):
        return ""
    color_node = next(iter(scheme[theme_index]), None)
    if color_node is None:
        return ""
    rgb = color_node.attrib.get("val") or color_node.attrib.get("lastClr") or ""
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", rgb):
        return ""
    red, green, blue = (int(rgb[index:index + 2], 16) / 255 for index in (0, 2, 4))
    hue, lightness, saturation = rgb_to_hls(red, green, blue)
    lightness = lightness * (1 + tint) if tint < 0 else lightness * (1 - tint) + tint
    tinted = hls_to_rgb(hue, max(0, min(1, lightness)), saturation)
    return "#{:02X}{:02X}{:02X}".format(*(round(channel * 255) for channel in tinted))


def _font_for_fill(hex_color: str) -> Font:
    """Use white text on dark fills and black text on light fills."""
    color = normalize_hex(hex_color)
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
    return WHITE_FONT if luminance < 0.46 else BLACK_FONT


def _load_axis_labels() -> dict[str, dict[str, str]]:
    """Load display labels from mapping-owned outputs without deriving hierarchy."""
    import csv

    labels: dict[str, dict[str, str]] = {"product": {}, "flow": {}}
    if UPSTREAM_AXIS_NODES_PATH.exists():
        with UPSTREAM_AXIS_NODES_PATH.open(encoding="utf-8-sig", newline="") as handle:
            axis_rows = list(csv.DictReader(handle))
        # Native ESTO/extended nodes supply friendly names for configured
        # parent or extension codes absent from the current common hierarchy.
        # Common ESTO labels then overwrite them where the contract has one.
        for dataset_id in ("esto_extended", "esto", "common_esto"):
            for row in axis_rows:
                if row.get("dataset_id") != dataset_id or row.get("axis_role") not in labels:
                    continue
                node_label = str(row.get("node_label", "")).strip()
                code, _, name = node_label.partition(" ")
                if code:
                    labels[str(row["axis_role"])][code] = name or node_label
        return labels

    if FALLBACK_COMMON_ROWS_PATH.exists():
        with FALLBACK_COMMON_ROWS_PATH.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                for axis in ("product", "flow"):
                    code = str(row.get(f"component_{axis}_code", "")).strip()
                    name = str(row.get(f"component_{axis}_name", "")).strip()
                    if code and name:
                        labels[axis].setdefault(code, name)
    return labels


def _config_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


# --- Workbook export ------------------------------------------------------

def _write_instructions(workbook: Workbook) -> None:
    sheet = workbook.active
    sheet.title = "START HERE"
    sheet.sheet_view.showGridLines = False
    sheet.merge_cells("A1:F1")
    sheet["A1"] = "LEAP dashboard colour editor"
    sheet["A1"].fill = HEADER_FILL
    sheet["A1"].font = Font(color="FFFFFF", bold=True, size=16)
    sheet["A1"].alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 30

    instructions = [
        ("What to do", "Open Products or Flows and edit only cells under Colour — EDIT."),
        ("Easiest method", "Select a colour cell and use Excel's paint bucket (Fill Color)."),
        ("Exact method", "Type a six-digit hex colour such as #1F77B4 into the colour cell."),
        ("Common rollups", "Blue Common rollup rows are automatic OKLab averages. Leave them unchanged unless you want an override."),
        ("Important", "If you change both the text and the fill in one cell, make them the same colour."),
        ("When finished", "Save the workbook and send this same .xlsx file back. Do not delete rows or rename tabs."),
    ]
    sheet.append([])
    for heading, explanation in instructions:
        sheet.append([heading, explanation])
    sheet["A10"] = "Tip"
    sheet["B10"] = "Avoid very pale colours on white charts, and avoid giving neighbouring categories nearly identical colours."
    sheet["A10"].fill = SUBHEADER_FILL
    sheet["A10"].font = Font(bold=True)
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 100
    for row in range(3, 11):
        sheet[f"A{row}"].font = Font(bold=True)
        sheet[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[row].height = 34


def _write_colour_sheet(
    workbook: Workbook,
    sheet_name: str,
    rows: list[tuple[str, str, str, str, str]],
) -> None:
    sheet = workbook.create_sheet(sheet_name)
    sheet.sheet_view.showGridLines = False
    # Column A is the stable machine identifier used during import. It stays
    # hidden so the reviewer sees one uncomplicated combined Category column.
    sheet.append(["_internal_key", "Category", "Colour — EDIT", "Note"])
    for identifier, label, color, note, automatic_color in rows:
        row_number = sheet.max_row + 1
        sheet.append([identifier, label, color, note])
        color_cell = sheet.cell(row=row_number, column=3)
        color_cell.fill = PatternFill("solid", fgColor=color.lstrip("#"))
        color_cell.font = _font_for_fill(color)
        color_cell.alignment = Alignment(horizontal="center")
        sheet.cell(row=row_number, column=1).fill = LOCKED_FILL
        sheet.cell(row=row_number, column=2).fill = LOCKED_FILL
        sheet.cell(row=row_number, column=1).number_format = "@"
        if identifier.startswith(COMMON_KEY_PREFIX):
            sheet.cell(row=row_number, column=2).fill = ROLLUP_FILL
            sheet.cell(row=row_number, column=2).font = Font(bold=True, color="1F4E78")
            sheet.cell(row=row_number, column=4).fill = ROLLUP_FILL
            sheet.cell(row=row_number, column=4).alignment = Alignment(wrap_text=True)

    header = sheet[1]
    for cell in header:
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    header[2].fill = PatternFill("solid", fgColor="BF9000")
    sheet.row_dimensions[1].height = 34
    sheet.freeze_panes = "C2"
    # The Excel table below owns the filter. Adding a second worksheet-level
    # AutoFilter over the same cells creates conflicting OOXML that desktop
    # Excel repairs by removing the table.
    sheet.column_dimensions["A"].hidden = True
    sheet.column_dimensions["A"].width = 2
    sheet.column_dimensions["B"].width = 55
    sheet.column_dimensions["C"].width = 22
    sheet.column_dimensions["D"].width = 60
    if sheet.max_row > 1:
        sheet.conditional_formatting.add(
            f"C2:C{sheet.max_row}",
            FormulaRule(formula=["NOT(AND(LEFT(C2,1)=\"#\",LEN(C2)=7))"], fill=PatternFill("solid", fgColor="F4CCCC")),
        )
        table_name = re.sub(r"[^A-Za-z0-9]", "", sheet_name) + "Colours"
        table = Table(displayName=table_name, ref=f"A1:D{sheet.max_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False)
        sheet.add_table(table)


def export_color_workbook(
    output_path: Path = DEFAULT_WORKBOOK_PATH,
    code_colors_path: Path = CODE_COLORS_PATH,
    common_rows_path: Path = DEFAULT_COMMON_ROWS_PATH,
) -> Path:
    """Create the workbook that can be sent directly to a colleague."""
    payload = json.loads(code_colors_path.read_text(encoding="utf-8"))
    labels = _load_axis_labels()
    memberships = load_common_rollup_memberships(common_rows_path)
    automatic_common = build_common_rollup_colors(
        {axis: dict(payload.get(axis, {})) for axis in ("product", "flow")},
        memberships,
    )
    configured_common = dict(payload.get("common", {}))
    workbook = Workbook()
    _write_instructions(workbook)
    workbook_metadata_rows: list[tuple[str, str, str, str]] = []

    for sheet_name, axis in SHEET_SPECS:
        mapping = dict(payload.get(axis, {}))
        rows = [
            (
                code,
                f"{code} {labels.get(axis, {}).get(code, 'Category not in the current common hierarchy')}",
                normalize_hex(color),
                "",
                normalize_hex(color),
            )
            for code, color in sorted(mapping.items())
        ]
        for expression, details in sorted(memberships[axis].items()):
            automatic_color = automatic_common[axis][expression]
            current_color = normalize_hex(dict(configured_common.get(axis, {})).get(expression, automatic_color))
            components = ", ".join(str(code) for code in details["components"])
            rows.append((
                f"{COMMON_KEY_PREFIX}{expression}",
                f"Common rollup: {details['label']}",
                current_color,
                f"Automatic OKLab average of {components}: {automatic_color}. Edit to override.",
                automatic_color,
            ))
        _write_colour_sheet(workbook, sheet_name, rows)
        workbook_metadata_rows.extend(
            (sheet_name, identifier, color, automatic_color)
            for identifier, _label, color, _note, automatic_color in rows
        )

    metadata = workbook.create_sheet("_metadata")
    metadata.sheet_state = "hidden"
    metadata.append(["schema_version", WORKBOOK_SCHEMA_VERSION])
    metadata.append(["source_config_sha256", _config_hash(payload)])
    metadata.append(["source_config", str(code_colors_path)])
    metadata.append([])
    metadata.append(["sheet", "key", "current_color", "automatic_color"])
    for metadata_row in workbook_metadata_rows:
        metadata.append(list(metadata_row))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    print(f"Wrote colleague colour workbook: {output_path}")
    return output_path


# --- Workbook import ------------------------------------------------------

def _chosen_colour(current_value: object, proposed_cell: object, location: str) -> str:
    current = normalize_hex(current_value)
    proposed_text = normalize_hex(getattr(proposed_cell, "value", None))
    proposed_fill = _cell_fill_hex(proposed_cell) or current
    text_changed = proposed_text != current
    fill_changed = proposed_fill != current
    if text_changed and fill_changed and proposed_text != proposed_fill:
        raise ValueError(
            f"{location}: typed colour {proposed_text} and fill colour {proposed_fill} disagree. "
            "Make them match or change only one."
        )
    return proposed_text if text_changed else proposed_fill


def _read_colour_sheet(
    workbook: object,
    sheet_name: str,
    workbook_metadata: dict[tuple[str, str], tuple[str, str]],
) -> dict[str, dict[str, object]]:
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Required sheet {sheet_name!r} is missing or was renamed")
    sheet = workbook[sheet_name]
    expected_headers = ["Category", "Colour — EDIT", "Note"]
    actual_headers = [sheet.cell(row=1, column=column).value for column in (2, 3, 4)]
    if actual_headers != expected_headers:
        raise ValueError(f"{sheet_name}: headings were changed; expected {expected_headers!r}")
    colors: dict[str, dict[str, object]] = {}
    for row_number in range(2, sheet.max_row + 1):
        identifier = str(sheet.cell(row=row_number, column=1).value or "").strip()
        if not identifier:
            continue
        if identifier in colors:
            raise ValueError(f"{sheet_name}: duplicate identifier {identifier!r}")
        metadata_key = (sheet_name, identifier)
        if metadata_key not in workbook_metadata:
            raise ValueError(f"{sheet_name}: internal metadata is missing for {identifier!r}")
        current, automatic = workbook_metadata[metadata_key]
        current = normalize_hex(current)
        chosen = _chosen_colour(
            current,
            sheet.cell(row=row_number, column=3),
            f"{sheet_name}!C{row_number}",
        )
        colors[identifier] = {
            "color": chosen,
            "changed": chosen != current,
            "current": current,
            "automatic": normalize_hex(automatic),
        }
    return colors


def _read_workbook_metadata(workbook: object) -> dict[tuple[str, str], tuple[str, str]]:
    """Read stable keys and comparison colours from the hidden metadata sheet."""
    sheet = workbook["_metadata"]
    metadata: dict[tuple[str, str], tuple[str, str]] = {}
    for row_number in range(6, sheet.max_row + 1):
        sheet_name = str(sheet.cell(row=row_number, column=1).value or "").strip()
        identifier = str(sheet.cell(row=row_number, column=2).value or "").strip()
        if sheet_name and identifier:
            metadata[(sheet_name, identifier)] = (
                normalize_hex(sheet.cell(row=row_number, column=3).value),
                normalize_hex(sheet.cell(row=row_number, column=4).value),
            )
    return metadata


def import_color_workbook(
    workbook_path: Path,
    code_colors_path: Path = CODE_COLORS_PATH,
    custom_colors_path: Path = CUSTOM_COLORS_PATH,
    common_rows_path: Path = DEFAULT_COMMON_ROWS_PATH,
) -> Path:
    """Validate a returned workbook, save its scheme, and apply it to config."""
    workbook = load_workbook(workbook_path, data_only=False)
    if "_metadata" not in workbook.sheetnames:
        raise ValueError("This is not a dashboard colour workbook: hidden _metadata sheet is missing")
    schema_version = str(workbook["_metadata"]["B1"].value or "")
    if schema_version != WORKBOOK_SCHEMA_VERSION:
        raise ValueError(f"Unsupported workbook schema {schema_version!r}; expected {WORKBOOK_SCHEMA_VERSION!r}")
    workbook_metadata = _read_workbook_metadata(workbook)

    custom_payload: dict[str, object] = {
        "_generated_by": "scripts/manage_dashboard_colors.py from a colleague-edited workbook",
        "_workbook": workbook_path.name,
        "product": {},
        "flow": {},
        "common_overrides": {"product": {}, "flow": {}},
    }
    production_payload = json.loads(code_colors_path.read_text(encoding="utf-8"))
    memberships = load_common_rollup_memberships(common_rows_path)
    entries_by_axis: dict[str, dict[str, dict[str, object]]] = {}
    for sheet_name, axis in SHEET_SPECS:
        entries = _read_colour_sheet(workbook, sheet_name, workbook_metadata)
        entries_by_axis[axis] = entries
        base_colors = {
            key: str(details["color"])
            for key, details in entries.items()
            if not key.startswith(COMMON_KEY_PREFIX)
        }
        expected = set(dict(production_payload.get(axis, {})))
        received = set(base_colors)
        if expected != received:
            raise ValueError(f"{axis.title()} rows changed: missing={sorted(expected - received)}, extra={sorted(received - expected)}")
        rollup_expressions = {
            key.removeprefix(COMMON_KEY_PREFIX)
            for key in entries
            if key.startswith(COMMON_KEY_PREFIX)
        }
        if rollup_expressions != set(memberships[axis]):
            raise ValueError(f"{axis.title()} Common rollup rows were added or removed")
        custom_payload[axis] = base_colors

    base_by_axis = {axis: dict(custom_payload[axis]) for axis in ("product", "flow")}
    automatic_common = build_common_rollup_colors(base_by_axis, memberships)
    for axis in ("product", "flow"):
        for expression in memberships[axis]:
            details = entries_by_axis[axis][f"{COMMON_KEY_PREFIX}{expression}"]
            chosen = normalize_hex(details["color"])
            was_override = normalize_hex(details["current"]) != normalize_hex(details["automatic"])
            if bool(details["changed"]) or was_override:
                if chosen != automatic_common[axis][expression]:
                    custom_payload["common_overrides"][axis][expression] = chosen

    resolved_common = build_common_rollup_colors(
        base_by_axis,
        memberships,
        overrides=dict(custom_payload["common_overrides"]),
    )
    production_payload["product"] = dict(custom_payload["product"])
    production_payload["flow"] = dict(custom_payload["flow"])
    production_payload["common"] = resolved_common
    production_payload["_common_color_method"] = "equal-weight OKLab average of mapping-owned ESTO components"
    production_payload["_common_color_overrides"] = dict(custom_payload["common_overrides"])
    production_payload["_custom_color_source"] = custom_colors_path.name

    custom_colors_path.write_text(json.dumps(custom_payload, indent=2) + "\n", encoding="utf-8")
    code_colors_path.write_text(json.dumps(production_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Applied workbook colours to: {code_colors_path}")
    print(f"Saved reusable custom colour layer: {custom_colors_path}")
    return custom_colors_path


# --- Frequently changed notebook-style controls --------------------------

EXPORT_WORKBOOK = False
IMPORT_WORKBOOK = False
WORKBOOK_PATH = DEFAULT_WORKBOOK_PATH


#%%
if EXPORT_WORKBOOK:
    export_color_workbook(output_path=WORKBOOK_PATH)

if IMPORT_WORKBOOK:
    import_color_workbook(workbook_path=WORKBOOK_PATH)

#%%
