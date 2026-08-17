"""Tests for perceptual Common ESTO colour calculation."""
from __future__ import annotations

import csv
from pathlib import Path

from codebase.dashboard_color_config import (
    average_oklab,
    build_common_rollup_colors,
    load_common_rollup_memberships,
)


def test_oklab_average_is_equal_weight_and_order_independent() -> None:
    colors = ["#A6A6A6", "#C4C4C4", "#7D7D7D"]
    assert average_oklab(colors) == average_oklab(list(reversed(colors)))
    assert average_oklab(["#123456", "#123456"]) == "#123456"
    assert average_oklab(colors) not in colors


def test_common_rollup_membership_comes_from_published_components(tmp_path: Path) -> None:
    common_rows = tmp_path / "common_rows.csv"
    fieldnames = [
        "comparison_scope",
        "common_product_code",
        "common_product_label",
        "component_product_code",
        "common_flow_code",
        "common_flow_label",
        "component_flow_code",
    ]
    with common_rows.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for component in ("01.02", "01.03", "01.04"):
            writer.writerow({
                "comparison_scope": "esto_leap_ninth",
                "common_product_code": "01.02-01.04",
                "common_product_label": "01.02-01.04 Coal",
                "component_product_code": component,
                "common_flow_code": "01",
                "common_flow_label": "01 Production",
                "component_flow_code": "01",
            })

    memberships = load_common_rollup_memberships(common_rows)
    assert memberships["product"]["01.02-01.04"]["components"] == ["01.02", "01.03", "01.04"]
    resolved = build_common_rollup_colors(
        {"product": {"01.02": "#A6A6A6", "01.03": "#C4C4C4", "01.04": "#7D7D7D"}, "flow": {}},
        memberships,
    )
    assert resolved["product"]["01.02-01.04"] == average_oklab(["#A6A6A6", "#C4C4C4", "#7D7D7D"])
