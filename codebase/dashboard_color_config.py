"""Shared helpers for deterministic Common ESTO dashboard colours."""
from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from pathlib import Path


HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_hex(value: object) -> str:
    """Return an uppercase #RRGGBB colour or raise a useful error."""
    text = str(value or "").strip()
    if not HEX_PATTERN.fullmatch(text):
        raise ValueError(f"Expected a colour like #1F77B4, received {value!r}")
    return text.upper()


def _srgb_channel_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_channel_to_srgb(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def hex_to_oklab(hex_color: str) -> tuple[float, float, float]:
    """Convert an sRGB hex colour to OKLab."""
    color = normalize_hex(hex_color)
    red, green, blue = (
        _srgb_channel_to_linear(int(color[index:index + 2], 16) / 255)
        for index in (1, 3, 5)
    )
    long = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    long_root = math.copysign(abs(long) ** (1 / 3), long)
    medium_root = math.copysign(abs(medium) ** (1 / 3), medium)
    short_root = math.copysign(abs(short) ** (1 / 3), short)
    return (
        0.2104542553 * long_root + 0.7936177850 * medium_root - 0.0040720468 * short_root,
        1.9779984951 * long_root - 2.4285922050 * medium_root + 0.4505937099 * short_root,
        0.0259040371 * long_root + 0.7827717662 * medium_root - 0.8086757660 * short_root,
    )


def _oklab_to_linear_rgb(lightness: float, green_red: float, blue_yellow: float) -> tuple[float, float, float]:
    long_root = lightness + 0.3963377774 * green_red + 0.2158037573 * blue_yellow
    medium_root = lightness - 0.1055613458 * green_red - 0.0638541728 * blue_yellow
    short_root = lightness - 0.0894841775 * green_red - 1.2914855480 * blue_yellow
    long, medium, short = long_root ** 3, medium_root ** 3, short_root ** 3
    return (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )


def oklab_to_hex(lightness: float, green_red: float, blue_yellow: float) -> str:
    """Convert OKLab to an in-gamut sRGB hex using chroma reduction."""
    linear_rgb = _oklab_to_linear_rgb(lightness, green_red, blue_yellow)
    if not all(0 <= channel <= 1 for channel in linear_rgb):
        low, high = 0.0, 1.0
        for _ in range(24):
            scale = (low + high) / 2
            candidate = _oklab_to_linear_rgb(lightness, green_red * scale, blue_yellow * scale)
            if all(0 <= channel <= 1 for channel in candidate):
                low = scale
                linear_rgb = candidate
            else:
                high = scale
    srgb = [max(0, min(1, _linear_channel_to_srgb(channel))) for channel in linear_rgb]
    return "#{:02X}{:02X}{:02X}".format(*(round(channel * 255) for channel in srgb))


def average_oklab(hex_colors: list[str]) -> str:
    """Return the equal-weight perceptual average of one or more colours."""
    if not hex_colors:
        raise ValueError("At least one colour is required for an OKLab average")
    values = [hex_to_oklab(color) for color in hex_colors]
    count = len(values)
    averaged = tuple(sum(value[index] for value in values) / count for index in range(3))
    return oklab_to_hex(*averaged)


def resolve_component_color(code: str, colors: dict[str, str]) -> str:
    """Resolve an exact component colour, inheriting from its nearest parent."""
    candidate = str(code).strip()
    while candidate:
        if candidate in colors:
            return normalize_hex(colors[candidate])
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    return ""


def load_common_rollup_memberships(common_rows_path: Path) -> dict[str, dict[str, dict[str, object]]]:
    """Load multi-component Common ESTO axis membership from the published rows."""
    by_axis: dict[str, dict[str, dict[str, object]]] = {"product": {}, "flow": {}}
    scope_members: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    labels: dict[tuple[str, str], str] = {}
    with common_rows_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            scope = str(row.get("comparison_scope", "")).strip()
            for axis in ("product", "flow"):
                expression = str(row.get(f"common_{axis}_code", "")).strip()
                label = str(row.get(f"common_{axis}_label", "")).strip()
                component = str(row.get(f"component_{axis}_code", "")).strip()
                if expression and label and component:
                    scope_members[(axis, expression, scope)].add(component)
                    labels[(axis, expression)] = label

    grouped: dict[tuple[str, str], list[set[str]]] = defaultdict(list)
    for (axis, expression, _scope), members in scope_members.items():
        grouped[(axis, expression)].append(members)
    for (axis, expression), membership_sets in grouped.items():
        distinct = {tuple(sorted(members)) for members in membership_sets}
        if len(distinct) > 1:
            raise ValueError(f"Common ESTO {axis} {expression} has conflicting scope memberships: {sorted(distinct)}")
        components = list(next(iter(distinct)))
        if len(components) > 1:
            by_axis[axis][expression] = {
                "label": labels[(axis, expression)],
                "components": components,
            }
    return by_axis


def build_common_rollup_colors(
    base_colors: dict[str, dict[str, str]],
    memberships: dict[str, dict[str, dict[str, object]]],
    overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Calculate equal-weight OKLab colours for mapping-owned rollups."""
    result: dict[str, dict[str, str]] = {"product": {}, "flow": {}}
    for axis in ("product", "flow"):
        for expression, details in memberships.get(axis, {}).items():
            components = [str(code) for code in details["components"]]
            component_colors = [resolve_component_color(code, base_colors.get(axis, {})) for code in components]
            missing = [code for code, color in zip(components, component_colors) if not color]
            if missing:
                raise ValueError(f"Missing {axis} colours for Common ESTO {expression}: {missing}")
            result[axis][expression] = average_oklab(component_colors)
        for expression, color in dict((overrides or {}).get(axis, {})).items():
            if expression in result[axis]:
                result[axis][expression] = normalize_hex(color)
    return result
