#%%
"""Render one shadow-comparison prototype through the production chart builder.

This is a read-only prototype. It deliberately uses a candidate expected series
from the published Common ESTO data so the visual can be assessed before the
upstream expected-output contract is implemented.
"""

#%%
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.io as pio


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
MODULE_ROOT = REPO_ROOT / "codebase"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_renderer import build_product_chart, load_json


#%%
def _load_refining_prototype_rows(
    comparison_data_path: Path,
    economy: str,
    comparison_scope: str,
    scenario: str,
    flow_code: str,
    product_code: str,
    min_year: int,
    max_year: int,
) -> pd.DataFrame:
    """Return LEAP output plus a candidate expected series at one common row.

    ``NINTH`` is renamed to ``SHADOW_EXPECTED`` only for this visual. The
    planned upstream contract will replace it with a LEAP-boundary-adjusted
    expected value after validating own-use and aggregation semantics.
    """
    columns = [
        "economy",
        "comparison_scope",
        "source_system",
        "scenario",
        "year",
        "common_flow_code",
        "common_flow_label",
        "common_product_code",
        "common_product_label",
        "value",
    ]
    source = pd.read_parquet(comparison_data_path, columns=columns)
    scoped = source.loc[
        source["economy"].astype(str).eq(economy)
        & source["comparison_scope"].astype(str).eq(comparison_scope)
        & source["common_flow_code"].astype(str).eq(flow_code)
        & source["common_product_code"].astype(str).eq(product_code)
        & source["year"].between(min_year, max_year)
    ].copy()
    actual = scoped.loc[
        scoped["source_system"].astype(str).eq("LEAP")
        & scoped["scenario"].astype(str).eq(scenario)
    ].copy()
    expected = scoped.loc[
        scoped["source_system"].astype(str).eq("NINTH")
        & scoped["scenario"].astype(str).str.casefold().eq(scenario.casefold())
    ].copy()
    expected["source_system"] = "SHADOW_EXPECTED"
    expected["scenario"] = scenario
    result = pd.concat([actual, expected], ignore_index=True)
    if result.empty:
        raise ValueError("No actual/expected prototype rows matched the selected refining case.")
    return result


def render_refining_shadow_chart_prototype(
    comparison_data_path: Path,
    output_html_path: Path,
    template_path: Path,
    economy: str = "01_AUS",
    comparison_scope: str = "esto_extended_leap_ninth",
    scenario: str = "Target",
    flow_code: str = "09.07",
    product_code: str = "07.07",
    min_year: int = 2022,
    max_year: int = 2030,
) -> Path:
    """Render a production-style refining shadow chart to a standalone HTML file."""
    template = load_json(template_path)
    rows = _load_refining_prototype_rows(
        comparison_data_path=comparison_data_path,
        economy=economy,
        comparison_scope=comparison_scope,
        scenario=scenario,
        flow_code=flow_code,
        product_code=product_code,
        min_year=min_year,
        max_year=max_year,
    )
    flow_label = str(rows["common_flow_label"].iloc[0])
    product_label = str(rows["common_product_label"].iloc[0])
    series_labels = {
        "LEAP|Target": "LEAP Target (actual output)",
        "SHADOW_EXPECTED|Target": "Expected LEAP boundary (candidate)",
    }
    figure = build_product_chart(
        rows,
        flow_label,
        product_label,
        series_labels,
        primary_source="LEAP",
        primary_scenario=scenario,
        comparison_source="ESTO_EXTENDED",
        base_year=int(template["chart_generation"]["base_year"]),
    )
    for trace in figure.data:
        if str(trace.name).startswith("Expected LEAP boundary"):
            trace.update(line={"dash": "dash", "color": "#8c55b8"})
    figure.update_layout(
        title=f"Shadow comparison prototype: {flow_label} — {product_label}",
        meta={
            **dict(figure.layout.meta or {}),
            "prototype_status": "candidate_expected_series_not_yet_boundary_validated",
        },
    )
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    output_html_path.write_text(
        pio.to_html(figure, include_plotlyjs="cdn", full_html=True),
        encoding="utf-8",
    )
    output_html_path.with_suffix(".json").write_text(
        json.dumps(figure.to_plotly_json(), default=str, indent=2),
        encoding="utf-8",
    )
    return output_html_path


#%%
RUN_PROTOTYPE = False
COMPARISON_DATA_PATH = (
    REPO_ROOT.parent
    / "leap_mappings"
    / "results"
    / "common_esto"
    / "common_esto_comparison_data.parquet"
)
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
OUTPUT_HTML_PATH = REPO_ROOT / "outputs" / "prototypes" / "refining_shadow_comparison.html"

if RUN_PROTOTYPE:
    RESULT_PATH = render_refining_shadow_chart_prototype(
        comparison_data_path=COMPARISON_DATA_PATH,
        output_html_path=OUTPUT_HTML_PATH,
        template_path=TEMPLATE_PATH,
    )
    print(f"[OK] Renderer-backed prototype written to {RESULT_PATH}")

#%%
