#%%
"""Supply-boundary configuration checks for international transport."""

import json
from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_renderer import (
    assign_pages,
    code_expression_matches_prefix,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"


def _template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_international_transport_routes_to_supply_and_supply_total() -> None:
    template = _template()
    rows = pd.DataFrame([
        {
            "common_flow_code": "04-05",
            "common_flow_label": "04-05 International transport (bunkers)",
            "common_product_code": "07.05",
            "common_product_label": "07.05 Kerosene type jet fuel",
        }
    ])

    assigned = assign_pages(rows, template["sector_pages"], template.get("routing_special_cases", []))

    assert assigned.iloc[0]["_page_key"] == "supply"
    assert template["total_demand_page"]["supply_codes"] == ["01", "02", "03", "04-05"]
    assert "bunkers" not in {
        page["page_key"] for page in template["sector_pages"]
    }

    assert template["secondary_pages"]["enabled"] is False
    assert template["secondary_pages"]["pages"] == []
    assert assigned.iloc[0]["_page_key"] == "supply"


def test_exact_compound_code_can_be_selected_without_selecting_its_children() -> None:
    assert code_expression_matches_prefix("04-05", "04-05")
    assert not code_expression_matches_prefix("04", "04-05")
    assert not code_expression_matches_prefix("05", "04-05")


#%%
