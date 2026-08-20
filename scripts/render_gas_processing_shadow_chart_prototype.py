#%%
"""Render a dashboard-native gas-processing shadow review from active variables.

This read-only prototype deliberately classifies each dashboard card before
adding an expected-net line. Only AUS Gas works is currently process-resolved:
the 09.06 and liquefaction/regasification parent cards retain their ordinary
dashboard figures until their mixed source and own-use boundaries are proved.
"""

#%%
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
MODULE_ROOT = REPO_ROOT / "codebase"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_renderer import (
    chart_dataset_tokens_from_figure,
    load_json,
    write_chart_bundle,
    write_dashboard_page,
)


#%%
def _load_bundle_figures(bundle_path: Path) -> dict[str, go.Figure]:
    """Load existing dashboard figures without rebuilding mapping rollups."""
    prefix = "window.COMMON_ESTO_CHART_BUNDLE_DATA="
    text = bundle_path.read_text(encoding="utf-8")
    if not text.startswith(prefix):
        raise ValueError(f"Not a dashboard chart bundle: {bundle_path}")
    charts = json.loads(text[len(prefix):].rstrip(";\n"))["charts"]
    return {key: go.Figure(value) for key, value in charts.items()}


def _decode_plotly_values(values: object) -> list[float | int]:
    """Decode Plotly's compact typed-array representation when present."""
    if isinstance(values, dict) and "bdata" in values:
        return np.frombuffer(
            base64.b64decode(values["bdata"]), dtype=np.dtype(values["dtype"])
        ).tolist()
    return list(values or [])


def _target_total_at_year(bundle_path: Path, chart_key: str, trace_name: str, year: int) -> float:
    """Read a dashboard total directly for a one-year reconstruction check."""
    prefix = "window.COMMON_ESTO_CHART_BUNDLE_DATA="
    charts = json.loads(bundle_path.read_text(encoding="utf-8")[len(prefix):].rstrip(";\n"))["charts"]
    for trace in charts[chart_key]["data"]:
        if trace.get("name") == trace_name:
            years = _decode_plotly_values(trace.get("x"))
            values = _decode_plotly_values(trace.get("y"))
            return float(values[years.index(year)])
    raise ValueError(f"{trace_name} was not found on {chart_key}.")


def _gas_works_expected_net(workbook_path: Path, scenario: str) -> pd.DataFrame:
    """Reconstruct Gas works net from its gross-capacity process variables.

    The active writer uses gross output for non-refinery capacity. Gas works'
    auxiliary variables are direct per-unit-of-gross-output ratios, not percent
    values, so they must not be divided by 100. This is validated against the
    mapped 9th total before the review line is emitted.
    """
    workbook = pd.read_excel(workbook_path, header=2)
    process_path = "Transformation\\Gas works plants\\Processes\\Gas works plants"
    selected = workbook.loc[workbook["Scenario"].astype(str).eq(scenario)].copy()
    capacity = selected.loc[
        selected["Branch Path"].astype(str).eq(process_path)
        & selected["Variable"].astype(str).eq("Exogenous Capacity")
    ].iloc[0]
    efficiency = selected.loc[
        selected["Branch Path"].astype(str).eq(process_path)
        & selected["Variable"].astype(str).eq("Process Efficiency")
    ].iloc[0]
    auxiliary = selected.loc[
        selected["Branch Path"].astype(str).str.startswith(process_path + "\\Auxiliary Fuels\\")
        & selected["Variable"].astype(str).eq("Auxiliary Fuel Use")
    ]
    values = []
    for column in [value for value in workbook.columns if str(value).isdigit()]:
        gross_output = pd.to_numeric(capacity[column], errors="coerce")
        efficiency_value = pd.to_numeric(efficiency[column], errors="coerce")
        auxiliary_ratio = pd.to_numeric(auxiliary[column], errors="coerce").fillna(0.0).sum()
        if pd.isna(gross_output) or pd.isna(efficiency_value) or efficiency_value == 0:
            continue
        efficiency_fraction = efficiency_value / 100.0 if efficiency_value > 1 else efficiency_value
        feedstock_input = -gross_output / efficiency_fraction
        auxiliary_use = -gross_output * auxiliary_ratio
        values.append(
            {
                "year": int(column),
                "value": gross_output + feedstock_input + auxiliary_use,
                "gross_output": gross_output,
                "feedstock_input": feedstock_input,
                "auxiliary_use": auxiliary_use,
            }
        )
    return pd.DataFrame(values)


def _append_expected_line(figure: go.Figure, expected: pd.DataFrame) -> go.Figure:
    """Add the one safe expected series while preserving dashboard styling."""
    figure.add_trace(
        go.Scatter(
            x=expected["year"],
            y=expected["value"],
            mode="lines+markers",
            name="Expected net total (transformation settings)",
            line={"dash": "dash", "color": "#8c55b8", "width": 4},
            marker={"size": 9, "symbol": "diamond"},
            hovertemplate=(
                "%{x}<br>Expected net total: %{y:,.3f} PJ"
                "<extra>Gas works transformation settings</extra>"
            ),
        )
    )
    meta = dict(figure.layout.meta or {})
    meta["trace_meta"] = list(meta.get("trace_meta", [])) + [
        {"source_system": "ESTIMATION_CODE_NET", "tag": "tgt", "metric": "both", "active_visible": True}
    ]
    figure.update_layout(meta=meta)
    return figure


def render_gas_processing_shadow_chart_prototype(
    output_root: Path,
    template_path: Path,
    transformation_workbook_path: Path,
    base_dashboard_bundle_path: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
) -> Path:
    """Write an isolated review page containing gas processing and subsectors."""
    load_json(template_path)  # Keep the same template dependency as normal pages.
    figures = _load_bundle_figures(base_dashboard_bundle_path)
    cards = [
        ("09.06 Gas processing plants (including own use)", "chart__area__flowgroup_parent__other_transformation__09_06__product", "withheld: parent combines differently classified children"),
        ("09.06.01 Gas works plants (including own use)", "chart__area__flowgroup__other_transformation__09_06_01_gas_works_plants_including_own_use__product", "safe: gross capacity + feedstock + process-owned auxiliary use"),
        ("09.06.02 Liquefaction/regasification plants (including own use)", "chart__area__flowgroup_parent__other_transformation__09_06_02__product", "withheld: parent mixes liquefaction/regasification and demand-owned 10.01.03 use"),
        ("09.06.02.01 Liquefaction (including own use)", "chart__area__flowgroup__other_transformation__09_06_02_01_liquefaction_including_own_use__product", "withheld: no reviewed same-boundary 9th/ESTO comparator"),
    ]
    expected = _gas_works_expected_net(transformation_workbook_path, scenario)
    gas_key = cards[1][1]
    expected_2023 = float(expected.loc[expected["year"].eq(2023), "value"].iloc[0])
    ninth_2023 = _target_total_at_year(base_dashboard_bundle_path, gas_key, "9th Target total", 2023)
    reconstruction_gap = expected_2023 - ninth_2023
    if abs(reconstruction_gap) >= 0.002:
        raise ValueError(
            "Gas works source-to-process reconstruction did not pass: "
            f"expected={expected_2023:.6f}, ninth={ninth_2023:.6f}, gap={reconstruction_gap:.6f}."
        )
    figures[gas_key] = _append_expected_line(figures[gas_key], expected)

    layout = {
        "dashboards": output_root / "dashboards",
        "chart_bundles": output_root / "chart_bundles",
        "supporting": output_root / "supporting_files",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    review_key = "gas_processing_shadow_review"
    review_figures = {f"chart__area__{review_key}__{index + 1}": figures[key] for index, (_, key, _) in enumerate(cards)}
    bundle_name = f"{review_key}__charts"
    write_chart_bundle(review_figures, layout["chart_bundles"] / bundle_name)
    chart_rows = []
    for index, (label, _, classification) in enumerate(cards):
        chart_key = f"chart__area__{review_key}__{index + 1}"
        figure = review_figures[chart_key]
        chart_rows.append(
            {
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": figure.layout.title.text,
                "product_label": "All transformation fuels",
                "section_label": "Gas processing shadow review",
                "flow_group_label": f"{label} — {classification}",
                "datasets": chart_dataset_tokens_from_figure(figure),
                "total_abs_value": 0.0,
                "abs_diff": abs(reconstruction_gap) if index == 1 else 0.0,
                "pct_diff": abs(reconstruction_gap / ninth_2023) if index == 1 and ninth_2023 else 0.0,
            }
        )
    output_path = layout["dashboards"] / f"{review_key}.html"
    write_dashboard_page(
        page_config={"page_key": review_key, "page_label": "Gas processing shadow review"},
        chart_rows=chart_rows,
        bundle_js_name=f"{bundle_name}.js",
        output_path=output_path,
        economy_label=economy,
        page_note=(
            "Read-only review: every card reuses its normal dashboard stack and totals. "
            "Only Gas works has a dashed expected-net line because its exact gross-capacity, "
            "feedstock, and process-owned auxiliary formula reproduces the mapped 9th total. "
            "The parent and LNG cards are intentionally unclassified rather than assigned the refinery rule."
        ),
        dataset_filter_options=["LEAP", "ESTIMATION_CODE_NET"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(
        json.dumps(
            {
                "review_key": review_key,
                "economy": economy,
                "scenario": scenario,
                "base_dashboard_bundle_path": str(base_dashboard_bundle_path),
                "transformation_workbook_path": str(transformation_workbook_path),
                "classifications": [
                    {"boundary": label, "classification": classification, "expected_line_drawn": index == 1}
                    for index, (label, _, classification) in enumerate(cards)
                ],
                "gas_works_2023_reconstruction": {
                    "expected_net_pj": expected_2023,
                    "ninth_target_net_pj": ninth_2023,
                    "difference_pj": reconstruction_gap,
                    "formula": "gross output - gross output / efficiency - gross output * sum(auxiliary ratios)",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


#%%
RUN_PROTOTYPE = False
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
WORKBOOK_PATH = (
    REPO_ROOT.parent / "leap_initialisation" / "outputs" / "leap_exports"
    / "supply_reconciliation" / "baseline_seed" / "runs" / "SEED_AUS_CONSOLIDATED_20260820"
    / "workbooks" / "transformation_leap_imports_01_AUS_Target.xlsx"
)
BUNDLE_PATH = REPO_ROOT / "outputs" / "common_esto_dashboard" / "01AUS" / "chart_bundles" / "other_transformation__charts.js"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "shadow_estimation_review" / "01_AUS_gas_processing_target_variable_output_review"

if RUN_PROTOTYPE:
    RESULT_PATH = render_gas_processing_shadow_chart_prototype(
        output_root=OUTPUT_ROOT,
        template_path=TEMPLATE_PATH,
        transformation_workbook_path=WORKBOOK_PATH,
        base_dashboard_bundle_path=BUNDLE_PATH,
    )
    print(f"[OK] Renderer-backed prototype written to {RESULT_PATH}")

#%%
