#%%
"""Render dashboard-native code-expectation reviews for aggregated demand sectors."""

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
SECTOR_REVIEWS = [
    {
        "sector": "Industry",
        "page": "industry",
        "chart_key": "chart__area__14__14_industry_sector",
        "flow_label": "14 Industry sector",
    },
    {
        "sector": "Transport non road",
        "page": "transport",
        "chart_key": "chart__area__flowgroup__transport__15_01_15_03_15_06_transport_non_road__product",
        "flow_label": "15.01,15.03-15.06 Transport non-road",
    },
    {
        "sector": "Other sector",
        "page": "others",
        "chart_key": "chart__area__flowgroup__others__16_03_16_05_17_other_sector_including_non_energy_all_demand_aggregate__product",
        "flow_label": "16.03-16.05,17 Other sector including non-energy (all demand aggregate)",
    },
]


def _decode(values: object) -> list[float | int]:
    if isinstance(values, dict) and "bdata" in values:
        return np.frombuffer(base64.b64decode(values["bdata"]), np.dtype(values["dtype"])).tolist()
    return list(values or [])


def _load_chart(bundle_path: Path, chart_key: str) -> tuple[go.Figure, dict]:
    charts = json.loads(bundle_path.read_text(encoding="utf-8"))["charts"]
    return go.Figure(charts[chart_key]), charts[chart_key]


def _target_total(raw_figure: dict) -> pd.DataFrame:
    trace_meta = raw_figure["layout"]["meta"]["trace_meta"]
    for trace, meta in zip(raw_figure["data"], trace_meta):
        if trace.get("name") == "LEAP Target total" and meta.get("source_system") == "LEAP" and meta.get("tag") == "tgt":
            return pd.DataFrame({"year": _decode(trace["x"]), "leap_total": _decode(trace["y"])})
    raise ValueError("LEAP Target total trace was not found.")


def _code_expected_total(workbook_path: Path, sector: str, scenario: str) -> pd.DataFrame:
    """Sum the emitted Activity Level × Final Energy Intensity fuel leaves."""
    workbook = pd.read_excel(workbook_path, sheet_name="FOR_VIEWING", header=2)
    branch_prefix = f"Demand\\All demand aggregated\\{sector}\\"
    scoped = workbook.loc[
        workbook["Scenario"].astype(str).eq(scenario)
        & workbook["Branch Path"].astype(str).str.startswith(branch_prefix)
        & workbook["Variable"].astype(str).isin(["Activity Level", "Final Energy Intensity"])
    ].copy()
    year_columns = [column for column in scoped.columns if str(column).isdigit()]
    if scoped.empty or not year_columns:
        raise ValueError(f"No emitted {sector} activity/intensity rows in {workbook_path}.")

    values = scoped.pivot(index="Branch Path", columns="Variable", values=year_columns)
    activity = values.xs("Activity Level", axis=1, level=1)
    intensity = values.xs("Final Energy Intensity", axis=1, level=1)
    expected = activity.mul(intensity).sum(axis=0).rename("expected_total").reset_index()
    expected.columns = ["year", "expected_total"]
    expected["year"] = expected["year"].astype(int)
    return expected.sort_values("year")


def render_aggregated_demand_shadow_chart_prototype(
    output_root: Path,
    template_path: Path,
    workbook_path: Path,
    dashboard_root: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
) -> Path:
    """Write one normal-dashboard card per aggregate-demand sector."""
    load_json(template_path)
    layout = {"dashboards": output_root / "dashboards", "chart_bundles": output_root / "chart_bundles", "supporting": output_root / "supporting_files"}
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)

    review_key = "aggregated_demand_shadow_review"
    figures: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_cards: list[dict] = []
    for review in SECTOR_REVIEWS:
        bundle_path = dashboard_root / "chart_bundles" / f"{review['page']}__charts.json"
        figure, raw_figure = _load_chart(bundle_path, review["chart_key"])
        expected = _code_expected_total(workbook_path, review["sector"], scenario)
        observed = _target_total(raw_figure)
        comparison = expected.merge(observed, on="year", how="inner")
        comparison["difference"] = comparison["expected_total"] - comparison["leap_total"]
        projected = comparison.loc[comparison["year"].ge(2023)]
        if projected.empty:
            raise ValueError(f"No projected comparison years for {review['sector']}.")

        figure.add_trace(go.Scatter(
            x=expected["year"], y=expected["expected_total"], mode="lines",
            name="Expected total (code settings)",
            line={"dash": "dash", "color": "#8c55b8", "width": 4},
            hovertemplate="%{x}<br>Expected total: %{y:,.2f} PJ<extra>Code settings</extra>",
        ))
        meta = dict(figure.layout.meta or {})
        meta["trace_meta"] = list(meta.get("trace_meta", [])) + [
            {"source_system": "ESTIMATION_CODE_EXPECTATION", "tag": "tgt", "metric": "both", "active_visible": True},
        ]
        figure.update_layout(meta=meta, title=f"LEAP Target stack, code expectation, and source totals: {review['flow_label']}")

        output_chart_key = f"chart__area__{review_key}__{review['sector'].lower().replace(' ', '_')}"
        figures[output_chart_key] = figure
        max_gap = float(projected["difference"].abs().max())
        chart_rows.append({
            "chart_key": output_chart_key,
            "chart_type": "stacked_area",
            "title": figure.layout.title.text,
            "product_label": "All demand fuels",
            "section_label": "All demand aggregated shadow review",
            "flow_group_label": review["flow_label"],
            "datasets": chart_dataset_tokens_from_figure(figure),
            "total_abs_value": 0.0,
            "abs_diff": max_gap,
            "pct_diff": 0.0,
        })
        manifest_cards.append({
            "sector": review["sector"],
            "dashboard_chart_key": review["chart_key"],
            "max_code_to_leap_gap_pj": max_gap,
            "comparison_years": [int(year) for year in projected["year"]],
        })

    bundle_name = f"{review_key}__charts"
    write_chart_bundle(figures, layout["chart_bundles"] / bundle_name)
    output_path = layout["dashboards"] / f"{review_key}.html"
    write_dashboard_page(
        page_config={"page_key": review_key, "page_label": "All demand aggregated shadow review"},
        chart_rows=chart_rows,
        bundle_js_name=f"{bundle_name}.js",
        output_path=output_path,
        economy_label=economy,
        page_note="Read-only review: purple expected-total lines are calculated from the emitted All demand aggregated Activity Level × Final Energy Intensity fuel leaves. A visible gap identifies a dashboard-to-code boundary difference for investigation.",
        dataset_filter_options=["LEAP", "ESTIMATION_CODE_EXPECTATION"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(json.dumps({
        "review_key": review_key,
        "workbook_path": str(workbook_path),
        "classification": "direct_demand_energy",
        "formula": "sum(Activity Level × Final Energy Intensity) across emitted fuel leaves",
        "cards": manifest_cards,
    }, indent=2), encoding="utf-8")
    return output_path


#%%
RUN_PROTOTYPE = False
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
WORKBOOK_PATH = REPO_ROOT.parent / "leap_initialisation" / "outputs" / "leap_exports" / "supply_reconciliation" / "baseline_seed" / "runs" / "SEED_AUS_CONSOLIDATED_20260820_R2" / "workbooks" / "aggregated_demand_01_AUS_Target_Reference_CurrentAccounts_by_sector.xlsx"
DASHBOARD_ROOT = REPO_ROOT / "outputs" / "common_esto_dashboard" / "01AUS"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "shadow_estimation_review" / "01_AUS_aggregated_demand_target_variable_output_review"

if RUN_PROTOTYPE:
    print(render_aggregated_demand_shadow_chart_prototype(OUTPUT_ROOT, TEMPLATE_PATH, WORKBOOK_PATH, DASHBOARD_ROOT))

#%%
