#%%
"""Render a maintained refining diagnostic through the production chart builder.

This is a read-only prototype. The expected series comes from the maintained
baseline-seed balance diagnostic, which already applies the reviewed inclusive
refinery/own-use comparison boundary.
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
def _load_refining_diagnostic_rows(
    diagnostic_path: Path,
    economy: str,
    scenario: str,
    flow_label: str,
    product_label: str,
) -> pd.DataFrame:
    """Return a safe actual/expectation pair from the diagnostic evidence."""
    source = pd.read_csv(diagnostic_path)
    scoped = source.loc[
        source["economy"].astype(str).eq(economy)
        & source["scenario"].astype(str).eq(scenario)
        & source["esto_flow"].astype(str).eq(flow_label)
        & source["esto_product"].astype(str).eq(product_label)
        & source["source_value_pj"].notna()
        & source["leap_value_pj"].notna()
        & source["status"].astype(str).isin({"match", "value_mismatch"})
        & source["comparison_grain"].astype(str).eq(
            "canonical_allocated_ninth_to_esto_pair"
        )
    ].copy()
    common_flow_code = flow_label.split(" ", maxsplit=1)[0]
    common_product_code = product_label.split(" ", maxsplit=1)[0]
    actual = scoped.assign(
        source_system="LEAP",
        value=scoped["leap_value_pj"],
        common_flow_code=common_flow_code,
        common_flow_label=flow_label,
        common_product_code=common_product_code,
        common_product_label=product_label,
    )
    expected = scoped.assign(
        source_system="ESTIMATION_EXPECTATION",
        value=scoped["source_value_pj"],
        common_flow_code=common_flow_code,
        common_flow_label=flow_label,
        common_product_code=common_product_code,
        common_product_label=product_label,
    )
    result = pd.concat([actual, expected], ignore_index=True)
    if result.empty:
        raise ValueError(
            "No safe actual/expected rows matched the selected refining case. "
            "Run the maintained diagnostic first, or select a supported boundary."
        )
    return result


def render_refining_shadow_chart_prototype(
    diagnostic_path: Path,
    output_html_path: Path,
    template_path: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
    flow_label: str = "09.07 Oil refineries (including own use)",
    product_label: str = "07.07 Gas/diesel oil",
) -> Path:
    """Render a production-style refining diagnostic to a standalone HTML file."""
    template = load_json(template_path)
    rows = _load_refining_diagnostic_rows(
        diagnostic_path=diagnostic_path,
        economy=economy,
        scenario=scenario,
        flow_label=flow_label,
        product_label=product_label,
    )
    series_labels = {
        "LEAP|Target": "LEAP Target (actual output)",
        "ESTIMATION_EXPECTATION|Target": "Estimated expectation (reviewed boundary)",
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
        if str(trace.name).startswith("Estimated expectation"):
            trace.update(line={"dash": "dash", "color": "#8c55b8"})
    figure.update_layout(
        title=f"Shadow comparison prototype: {flow_label} — {product_label}",
        meta={
            **dict(figure.layout.meta or {}),
            "prototype_status": "diagnostic_expected_series_reviewed_boundary",
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
DIAGNOSTIC_PATH = (
    REPO_ROOT.parent
    / "leap_initialisation"
    / "outputs"
    / "diagnostics"
    / "ah72_investigation_20260818"
    / "leap_balance_source_differences.csv"
)
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
OUTPUT_HTML_PATH = REPO_ROOT / "outputs" / "prototypes" / "refining_shadow_comparison.html"

if RUN_PROTOTYPE:
    RESULT_PATH = render_refining_shadow_chart_prototype(
        diagnostic_path=DIAGNOSTIC_PATH,
        output_html_path=OUTPUT_HTML_PATH,
        template_path=TEMPLATE_PATH,
    )
    print(f"[OK] Renderer-backed prototype written to {RESULT_PATH}")

#%%
