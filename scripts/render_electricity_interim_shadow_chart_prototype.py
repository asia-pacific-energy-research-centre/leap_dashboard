#%%
"""Render a dashboard-native capacity-dispatch review for Electricity interim."""

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
def _decode(values: object) -> list[float | int]:
    if isinstance(values, dict) and "bdata" in values:
        return np.frombuffer(base64.b64decode(values["bdata"]), np.dtype(values["dtype"])).tolist()
    return list(values or [])


def _load_chart(bundle_path: Path, chart_key: str) -> tuple[go.Figure, dict]:
    text = bundle_path.read_text(encoding="utf-8")
    charts = json.loads(text.split("=", maxsplit=1)[1].rstrip(";\n"))["charts"]
    return go.Figure(charts[chart_key]), charts[chart_key]


def _target_trace(raw_figure: dict, name: str) -> tuple[list[int], list[float]]:
    trace_meta = raw_figure["layout"]["meta"]["trace_meta"]
    for trace, meta in zip(raw_figure["data"], trace_meta):
        if trace.get("name") == name and meta.get("source_system") == "LEAP" and meta.get("tag") == "tgt":
            return _decode(trace.get("x")), _decode(trace.get("y"))
    raise ValueError(f"Target trace not found: {name}")


def _capacity_and_efficiency(workbook_path: Path, scenario: str) -> pd.DataFrame:
    workbook = pd.read_excel(workbook_path, header=2)
    path = "Transformation\\Electricity interim\\Processes\\Electricity interim"
    scoped = workbook.loc[workbook["Scenario"].astype(str).eq(scenario)]
    capacity = scoped.loc[(scoped["Branch Path"].astype(str).eq(path)) & scoped["Variable"].astype(str).eq("Exogenous Capacity")].iloc[0]
    efficiency = scoped.loc[(scoped["Branch Path"].astype(str).eq(path)) & scoped["Variable"].astype(str).eq("Process Efficiency")].iloc[0]
    records = []
    for column in [value for value in workbook.columns if str(value).isdigit()]:
        cap = pd.to_numeric(capacity[column], errors="coerce")
        eff = pd.to_numeric(efficiency[column], errors="coerce")
        if pd.notna(cap) and pd.notna(eff) and eff > 0:
            records.append({"year": int(column), "capacity": float(cap), "efficiency": float(eff) / 100.0})
    return pd.DataFrame(records)


def render_electricity_interim_shadow_chart_prototype(
    output_root: Path,
    template_path: Path,
    workbook_path: Path,
    bundle_path: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
) -> Path:
    """Write a review that distinguishes a capacity envelope from dispatch."""
    load_json(template_path)
    chart_key = "chart__area__flowgroup__power__09_01_01_09_02_01_electricity_plants__product"
    figure, raw_figure = _load_chart(bundle_path, chart_key)
    settings = _capacity_and_efficiency(workbook_path, scenario)
    actual_years, actual_output = _target_trace(raw_figure, "17 Electricity")
    actual_output_by_year = dict(zip(actual_years, actual_output))
    settings["realised_output"] = settings["year"].map(actual_output_by_year)
    settings = settings.loc[settings["realised_output"].notna()].copy()
    settings["conditional_net"] = settings["realised_output"] - settings["realised_output"] / settings["efficiency"]
    total_years, target_total = _target_trace(raw_figure, "LEAP Target total")
    total_by_year = dict(zip(total_years, target_total))
    settings["leap_net"] = settings["year"].map(total_by_year)
    settings["capacity_utilisation"] = settings["realised_output"] / settings["capacity"]
    settings["response_gap"] = settings["conditional_net"] - settings["leap_net"]
    projected = settings.loc[settings["year"].ge(2023)]
    if projected.empty or (projected["realised_output"] - projected["capacity"] > 0.01).any():
        raise ValueError("Electricity interim dispatch exceeds the declared capacity envelope.")
    if projected["response_gap"].abs().max() > 0.01:
        raise ValueError("Electricity interim conditional response does not reproduce LEAP net.")

    figure.add_trace(go.Scatter(
        x=settings["year"], y=settings["conditional_net"], mode="lines",
        name="Expected total (code settings)",
        line={"dash": "dash", "color": "#8c55b8", "width": 4},
        hovertemplate="%{x}<br>Expected total: %{y:,.2f} PJ<extra>Code settings</extra>",
    ))
    meta = dict(figure.layout.meta or {})
    meta["trace_meta"] = list(meta.get("trace_meta", [])) + [
        {"source_system": "ESTIMATION_CODE_EXPECTATION", "tag": "tgt", "metric": "both", "active_visible": True},
    ]
    figure.update_layout(meta=meta, title="LEAP Target stack, 9th trajectory, and interim capacity-dispatch review")

    layout = {"dashboards": output_root / "dashboards", "chart_bundles": output_root / "chart_bundles", "supporting": output_root / "supporting_files"}
    for path in layout.values(): path.mkdir(parents=True, exist_ok=True)
    review_key = "electricity_interim_shadow_review"
    output_chart_key = f"chart__area__{review_key}__electricity"
    bundle_name = f"{review_key}__charts"
    write_chart_bundle({output_chart_key: figure}, layout["chart_bundles"] / bundle_name)
    output_path = layout["dashboards"] / f"{review_key}.html"
    write_dashboard_page(
        page_config={"page_key": review_key, "page_label": "Electricity interim shadow review"},
        chart_rows=[{"chart_key": output_chart_key, "chart_type": "stacked_area", "title": figure.layout.title.text, "product_label": "All transformation fuels", "section_label": "Electricity interim shadow review", "flow_group_label": "09.01.01,09.02.01 Electricity plants — capacity-dispatched", "datasets": chart_dataset_tokens_from_figure(figure), "total_abs_value": 0.0, "abs_diff": float(projected["response_gap"].abs().max()), "pct_diff": 0.0}],
        bundle_js_name=f"{bundle_name}.js", output_path=output_path, economy_label=economy,
        page_note="Read-only review: the purple expected-total line applies the emitted code settings to realised interim activity. The 9th line remains a separate source trajectory.",
        dataset_filter_options=["LEAP", "ESTIMATION_CODE_EXPECTATION"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(json.dumps({"review_key": review_key, "workbook_path": str(workbook_path), "bundle_path": str(bundle_path), "classification": "capacity_dispatched", "max_projected_utilisation": float(projected["capacity_utilisation"].max()), "max_conditional_response_gap_pj": float(projected["response_gap"].abs().max())}, indent=2), encoding="utf-8")
    return output_path


#%%
RUN_PROTOTYPE = False
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
WORKBOOK_PATH = REPO_ROOT.parent / "leap_initialisation" / "outputs" / "leap_exports" / "supply_reconciliation" / "baseline_seed" / "runs" / "SEED_AUS_CONSOLIDATED_20260820" / "workbooks" / "electricity_heat_interim_01_AUS_Target_Reference_Current_Accounts.xlsx"
BUNDLE_PATH = REPO_ROOT / "outputs" / "common_esto_dashboard" / "01AUS" / "chart_bundles" / "power__charts.js"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "shadow_estimation_review" / "01_AUS_electricity_interim_target_capacity_dispatch_review"

if RUN_PROTOTYPE:
    print(render_electricity_interim_shadow_chart_prototype(OUTPUT_ROOT, TEMPLATE_PATH, WORKBOOK_PATH, BUNDLE_PATH))

#%%
