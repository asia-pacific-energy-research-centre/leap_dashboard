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
from colorsys import hls_to_rgb, rgb_to_hls
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.styles.colors import COLOR_INDEX
from openpyxl.worksheet.table import Table, TableStyleInfo


# --- Stable paths and workbook contract -----------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
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

WORKBOOK_SCHEMA_VERSION = "1"
HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
EDIT_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SUBHEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
LOCKED_FILL = PatternFill("solid", fgColor="F2F2F2")
WHITE_FONT = Font(color="FFFFFF")
BLACK_FONT = Font(color="000000")

SHEET_SPECS = (
    ("Products", "product", "code"),
    ("Flows", "flow", "code"),
    ("Product labels", "product", "plotting"),
    ("Flow labels", "flow", "plotting"),
    ("Capacity labels", "capacity", "plotting"),
)


# --- Colour and label helpers ---------------------------------------------

def normalize_hex(value: object) -> str:
    """Return an uppercase #RRGGBB colour or raise a useful error."""
    text = str(value or "").strip()
    if not HEX_PATTERN.fullmatch(text):
        raise ValueError(f"Expected a colour like #1F77B4, received {value!r}")
    return text.upper()


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
        ("What to do", "Open the Products and Flows tabs. The yellow-column heading marks the cells you may edit."),
        ("Option 1 — easiest", "Select a Proposed colour cell and use Excel's paint bucket (Fill Color) to choose a colour."),
        ("Option 2 — exact", "Type a six-digit hex colour such as #1F77B4 into a Proposed colour cell."),
        ("Important", "If you change both the text and the fill in one cell, make them the same colour."),
        ("When finished", "Save the workbook and send this same .xlsx file back. Do not delete rows or rename tabs."),
        ("Helpful notes", "Use the Notes column to explain choices. Do not edit the Category column or delete rows."),
        ("Special labels", "The three label tabs are optional and cover special chart labels outside the main Common ESTO code hierarchy."),
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
    rows: list[tuple[str, str, str]],
) -> None:
    sheet = workbook.create_sheet(sheet_name)
    sheet.sheet_view.showGridLines = False
    # Column A is the stable machine identifier used during import. It stays
    # hidden so the reviewer sees one uncomplicated combined Category column.
    sheet.append(["_internal_key", "Category", "Current colour", "Proposed colour — EDIT", "Notes (optional)"])
    for identifier, label, color in rows:
        row_number = sheet.max_row + 1
        sheet.append([identifier, label, color, color, ""])
        for column in (3, 4):
            cell = sheet.cell(row=row_number, column=column)
            cell.fill = PatternFill("solid", fgColor=color.lstrip("#"))
            cell.font = _font_for_fill(color)
            cell.alignment = Alignment(horizontal="center")
        sheet.cell(row=row_number, column=1).fill = LOCKED_FILL
        sheet.cell(row=row_number, column=2).fill = LOCKED_FILL
        sheet.cell(row=row_number, column=1).number_format = "@"

    header = sheet[1]
    for cell in header:
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    header[3].fill = PatternFill("solid", fgColor="BF9000")
    sheet.row_dimensions[1].height = 34
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = f"A1:E{sheet.max_row}"
    sheet.column_dimensions["A"].hidden = True
    sheet.column_dimensions["A"].width = 2
    sheet.column_dimensions["B"].width = 55
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 24
    sheet.column_dimensions["E"].width = 44
    if sheet.max_row > 1:
        sheet.conditional_formatting.add(
            f"D2:D{sheet.max_row}",
            FormulaRule(formula=["NOT(AND(LEFT(D2,1)=\"#\",LEN(D2)=7))"], fill=PatternFill("solid", fgColor="F4CCCC")),
        )
        table_name = re.sub(r"[^A-Za-z0-9]", "", sheet_name) + "Colours"
        table = Table(displayName=table_name, ref=f"A1:E{sheet.max_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False)
        sheet.add_table(table)


def export_color_workbook(
    output_path: Path = DEFAULT_WORKBOOK_PATH,
    code_colors_path: Path = CODE_COLORS_PATH,
) -> Path:
    """Create the workbook that can be sent directly to a colleague."""
    payload = json.loads(code_colors_path.read_text(encoding="utf-8"))
    labels = _load_axis_labels()
    workbook = Workbook()
    _write_instructions(workbook)

    for sheet_name, axis, mapping_kind in SHEET_SPECS:
        if mapping_kind == "code":
            mapping = dict(payload.get(axis, {}))
            rows = [
                (
                    code,
                    f"{code} {labels.get(axis, {}).get(code, 'Category not in the current common hierarchy')}",
                    normalize_hex(color),
                )
                for code, color in sorted(mapping.items())
            ]
            _write_colour_sheet(workbook, sheet_name, rows)
        else:
            mapping = dict(payload.get("plotting", {}).get(axis, {}))
            rows = [
                (name, name.replace("_", " "), normalize_hex(color))
                for name, color in sorted(mapping.items(), key=lambda item: item[0].casefold())
            ]
            _write_colour_sheet(workbook, sheet_name, rows)

    metadata = workbook.create_sheet("_metadata")
    metadata.sheet_state = "hidden"
    metadata.append(["schema_version", WORKBOOK_SCHEMA_VERSION])
    metadata.append(["source_config_sha256", _config_hash(payload)])
    metadata.append(["source_config", str(code_colors_path)])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    print(f"Wrote colleague colour workbook: {output_path}")
    return output_path


# --- Workbook import ------------------------------------------------------

def _chosen_colour(current_cell: object, proposed_cell: object, location: str) -> str:
    current = normalize_hex(getattr(current_cell, "value", None))
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


def _read_colour_sheet(workbook: object, sheet_name: str) -> dict[str, str]:
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Required sheet {sheet_name!r} is missing or was renamed")
    sheet = workbook[sheet_name]
    expected_headers = ["Category", "Current colour", "Proposed colour — EDIT"]
    actual_headers = [sheet.cell(row=1, column=column).value for column in (2, 3, 4)]
    if actual_headers != expected_headers:
        raise ValueError(f"{sheet_name}: headings were changed; expected {expected_headers!r}")
    colors: dict[str, str] = {}
    for row_number in range(2, sheet.max_row + 1):
        identifier = str(sheet.cell(row=row_number, column=1).value or "").strip()
        if not identifier:
            continue
        if identifier in colors:
            raise ValueError(f"{sheet_name}: duplicate identifier {identifier!r}")
        colors[identifier] = _chosen_colour(
            sheet.cell(row=row_number, column=3),
            sheet.cell(row=row_number, column=4),
            f"{sheet_name}!D{row_number}",
        )
    return colors


def import_color_workbook(
    workbook_path: Path,
    code_colors_path: Path = CODE_COLORS_PATH,
    custom_colors_path: Path = CUSTOM_COLORS_PATH,
) -> Path:
    """Validate a returned workbook, save its scheme, and apply it to config."""
    workbook = load_workbook(workbook_path, data_only=False)
    if "_metadata" not in workbook.sheetnames:
        raise ValueError("This is not a dashboard colour workbook: hidden _metadata sheet is missing")
    schema_version = str(workbook["_metadata"]["B1"].value or "")
    if schema_version != WORKBOOK_SCHEMA_VERSION:
        raise ValueError(f"Unsupported workbook schema {schema_version!r}; expected {WORKBOOK_SCHEMA_VERSION!r}")

    custom_payload: dict[str, object] = {
        "_generated_by": "scripts/manage_dashboard_colors.py from a colleague-edited workbook",
        "_workbook": workbook_path.name,
        "product": {},
        "flow": {},
        "plotting": {},
    }
    for sheet_name, axis, mapping_kind in SHEET_SPECS:
        colors = _read_colour_sheet(workbook, sheet_name)
        if mapping_kind == "code":
            custom_payload[axis] = colors
        else:
            custom_payload["plotting"][axis] = colors

    production_payload = json.loads(code_colors_path.read_text(encoding="utf-8"))
    for axis in ("product", "flow"):
        expected = set(dict(production_payload.get(axis, {})))
        received = set(dict(custom_payload[axis]))
        if expected != received:
            raise ValueError(f"{axis.title()} rows changed: missing={sorted(expected - received)}, extra={sorted(received - expected)}")
        production_payload[axis] = dict(custom_payload[axis])
    for axis, colors in dict(custom_payload["plotting"]).items():
        expected = set(dict(production_payload.get("plotting", {}).get(axis, {})))
        if expected != set(colors):
            raise ValueError(f"{axis.title()} plotting-label rows were added or removed")
        production_payload.setdefault("plotting", {})[axis] = colors
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
