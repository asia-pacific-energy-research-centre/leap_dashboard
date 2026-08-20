#%%
"""Render dashboard-native, source-proximate checks for seeded supply results."""

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
    charts = json.loads(bundle_path.read_text(encoding="utf-8"))["charts"]
    return go.Figure(charts[chart_key]), charts[chart_key]


def _target_total(raw_figure: dict) -> pd.DataFrame:
    for trace, meta in zip(raw_figure["data"], raw_figure["layout"]["meta"]["trace_meta"]):
        if trace.get("name") == "LEAP Target total" and meta.get("source_system") == "LEAP" and meta.get("tag") == "tgt":
            return pd.DataFrame({"year": _decode(trace["x"]), "leap_total": _decode(trace["y"])})
    raise ValueError("LEAP Target total trace was not found.")


def _sum_workbook_variable(workbook_path: Path, variable: str, scenario: str, sign: float) -> pd.DataFrame:
    workbook = pd.read_excel(workbook_path, sheet_name="FOR_VIEWING", header=2)
    year_columns = [column for column in workbook.columns if str(column).isdigit()]
    rows = workbook.loc[workbook["Scenario"].astype(str).eq(scenario) & workbook["Variable"].astype(str).eq(variable), year_columns]
    if rows.empty:
        raise ValueError(f"No {variable} rows in {workbook_path}.")
    expected = rows.apply(pd.to_numeric, errors="coerce").sum().mul(sign).rename("expected_total").reset_index()
    expected.columns = ["year", "expected_total"]
    expected["year"] = expected["year"].astype(int)
    # Reference/Target supply settings begin in the first projection year.
    # Their base-year zeros are placeholders, not expected historical results.
    return expected.loc[expected["year"].ge(2023)].sort_values("year")


def _international_bunkers_expected(workbook_path: Path, scenario: str) -> pd.DataFrame:
    """Return signed bunker supply from the emitted aggregate-demand fuel leaves."""
    workbook = pd.read_excel(workbook_path, sheet_name="FOR_VIEWING", header=2)
    year_columns = [column for column in workbook.columns if str(column).isdigit()]
    prefix = "Demand\\All demand aggregated\\International transport\\"
    rows = workbook.loc[
        workbook["Scenario"].astype(str).eq(scenario)
        & workbook["Branch Path"].astype(str).str.startswith(prefix)
        & workbook["Variable"].astype(str).isin(["Activity Level", "Final Energy Intensity"])
    ]
    values = rows.pivot(index="Branch Path", columns="Variable", values=year_columns)
    activity = values.xs("Activity Level", axis=1, level=1)
    intensity = values.xs("Final Energy Intensity", axis=1, level=1)
    expected = activity.mul(intensity).sum(axis=0).mul(-1.0).rename("expected_total").reset_index()
    expected.columns = ["year", "expected_total"]
    expected["year"] = expected["year"].astype(int)
    return expected.sort_values("year")


def _add_expected_trace(figure: go.Figure, expected: pd.DataFrame) -> None:
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
    figure.update_layout(meta=meta)


def render_supply_shadow_chart_prototype(
    output_root: Path,
    template_path: Path,
    supply_workbook_path: Path,
    aggregated_demand_workbook_path: Path,
    dashboard_root: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
) -> Path:
    """Write safe direct-setting checks for exports and international bunkers."""
    load_json(template_path)
    layout = {"dashboards": output_root / "dashboards", "chart_bundles": output_root / "chart_bundles", "supporting": output_root / "supporting_files"}
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)

    reviews = [
        {
            "label": "03 Exports",
            "chart_key": "chart__area__03__03_exports",
            "expected": _sum_workbook_variable(supply_workbook_path, "Exports", scenario, sign=-1.0),
            "source_stage": "Emitted Resources Exports rows",
        },
        {
            "label": "04-05 International transport (bunkers)",
            "chart_key": "chart__area__04__04_05_international_transport_bunkers",
            "expected": _international_bunkers_expected(aggregated_demand_workbook_path, scenario),
            "source_stage": "Emitted All demand aggregated/International transport fuel leaves",
        },
    ]
    bundle_path = dashboard_root / "chart_bundles" / "supply__charts.json"
    review_key = "supply_shadow_review"
    figures: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_cards: list[dict] = []
    for review in reviews:
        figure, raw_figure = _load_chart(bundle_path, review["chart_key"])
        observed = _target_total(raw_figure)
        comparison = review["expected"].merge(observed, on="year", how="inner")
        comparison["difference"] = comparison["expected_total"] - comparison["leap_total"]
        projected = comparison.loc[comparison["year"].ge(2023)]
        if projected.empty:
            raise ValueError(f"No projected comparison years for {review['label']}.")
        _add_expected_trace(figure, review["expected"])
        figure.update_layout(title=f"LEAP Target stack, code expectation, and source totals: {review['label']}")

        output_chart_key = f"chart__area__{review_key}__{review['chart_key'].split('__')[-1]}"
        figures[output_chart_key] = figure
        max_gap = float(projected["difference"].abs().max())
        chart_rows.append({
            "chart_key": output_chart_key,
            "chart_type": "stacked_area",
            "title": figure.layout.title.text,
            "product_label": "All supply fuels",
            "section_label": "Supply shadow review",
            "flow_group_label": review["label"],
            "datasets": chart_dataset_tokens_from_figure(figure),
            "total_abs_value": 0.0,
            "abs_diff": max_gap,
            "pct_diff": 0.0,
        })
        manifest_cards.append({"label": review["label"], "source_stage": review["source_stage"], "max_code_to_leap_gap_pj": max_gap})

    bundle_name = f"{review_key}__charts"
    write_chart_bundle(figures, layout["chart_bundles"] / bundle_name)
    output_path = layout["dashboards"] / f"{review_key}.html"
    write_dashboard_page(
        page_config={"page_key": review_key, "page_label": "Supply shadow review"},
        chart_rows=chart_rows,
        bundle_js_name=f"{bundle_name}.js",
        output_path=output_path,
        economy_label=economy,
        page_note="Read-only review: expected totals use the closest safe emitted code values. Production is omitted because Maximum Production is a ceiling; imports are omitted because LEAP calculates them as the balancing residual.",
        dataset_filter_options=["LEAP", "ESTIMATION_CODE_EXPECTATION"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(json.dumps({
        "review_key": review_key,
        "classification": "direct_supply_setting",
        "withheld": {"01 Production": "Maximum Production is a capacity ceiling, not realised production.", "02 Imports": "Imports are intentionally zeroed in the seed and calculated by LEAP."},
        "cards": manifest_cards,
    }, indent=2), encoding="utf-8")
    return output_path


#%%
RUN_PROTOTYPE = False
TEMPLATE_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json"
RUN_ROOT = REPO_ROOT.parent / "leap_initialisation" / "outputs" / "leap_exports" / "supply_reconciliation" / "baseline_seed" / "runs" / "SEED_AUS_CONSOLIDATED_20260820_R2"
SUPPLY_WORKBOOK_PATH = RUN_ROOT / "workbooks" / "supply_leap_imports_01_AUS_Target_Reference_CurrentAccounts.xlsx"
AGGREGATED_DEMAND_WORKBOOK_PATH = RUN_ROOT / "workbooks" / "aggregated_demand_01_AUS_Target_Reference_CurrentAccounts_by_sector.xlsx"
DASHBOARD_ROOT = REPO_ROOT / "outputs" / "common_esto_dashboard" / "01AUS"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "shadow_estimation_review" / "01_AUS_supply_target_variable_output_review"

if RUN_PROTOTYPE:
    print(render_supply_shadow_chart_prototype(OUTPUT_ROOT, TEMPLATE_PATH, SUPPLY_WORKBOOK_PATH, AGGREGATED_DEMAND_WORKBOOK_PATH, DASHBOARD_ROOT))

#%%
