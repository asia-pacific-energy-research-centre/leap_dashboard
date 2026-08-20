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


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
MODULE_ROOT = REPO_ROOT / "codebase"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_renderer import (
    build_area_chart,
    chart_dataset_tokens_from_figure,
    load_json,
    write_chart_bundle,
    write_dashboard_page,
)


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
        sign_status="valid_positive",
        sign_interpretation="transformation output",
        common_flow_code=common_flow_code,
        common_flow_label=flow_label,
        common_product_code=common_product_code,
        common_product_label=product_label,
    )
    expected = scoped.assign(
        source_system="ESTIMATION_EXPECTATION",
        value=scoped["source_value_pj"],
        sign_status="valid_positive",
        sign_interpretation="transformation output",
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


def _load_target_area_rows(
    diagnostic_path: Path,
    economy: str,
    scenario: str,
    flow_label: str,
) -> pd.DataFrame:
    """Return mapped positive LEAP Target outputs for a stacked fuel chart."""
    source = pd.read_csv(diagnostic_path)
    scoped = source.loc[
        source["economy"].astype(str).eq(economy)
        & source["scenario"].astype(str).eq(scenario)
        & source["esto_flow"].astype(str).eq(flow_label)
        & source["leap_value_pj"].notna()
    ].copy()
    if scoped.empty:
        raise ValueError("No mapped LEAP Target rows were found for the area chart.")
    product_parts = scoped["esto_product"].astype(str).str.split(" ", n=1, expand=True)
    scoped["source_system"] = "LEAP"
    scoped["value"] = scoped["leap_value_pj"]
    scoped["common_flow_code"] = flow_label.split(" ", maxsplit=1)[0]
    scoped["common_flow_label"] = flow_label
    scoped["common_product_code"] = product_parts[0]
    scoped["common_product_label"] = scoped["esto_product"].astype(str)
    return scoped.loc[scoped["value"] > 0].copy()


def _load_variable_expected_rows(
    transformation_workbook_path: Path,
    product_label: str,
    output_fuel_label: str,
    flow_label: str,
    economy: str,
    scenario: str,
) -> pd.DataFrame:
    """Derive expected output from the pre-seed capacity and output-share variables."""
    workbook = pd.read_excel(transformation_workbook_path, header=2)
    process_path = "Transformation\\Oil Refining\\Processes\\Oil Refining"
    capacity = workbook.loc[
        workbook["Branch Path"].astype(str).eq(process_path)
        & workbook["Variable"].astype(str).eq("Exogenous Capacity")
        & workbook["Scenario"].astype(str).eq(scenario)
    ].iloc[0]
    share = workbook.loc[
        workbook["Branch Path"].astype(str).eq(
            f"Transformation\\Oil Refining\\Output Fuels\\{output_fuel_label}"
        )
        & workbook["Variable"].astype(str).eq("Output Share")
        & workbook["Scenario"].astype(str).eq(scenario)
    ].iloc[0]
    year_columns = [column for column in workbook.columns if str(column).isdigit()]
    values = []
    for column in year_columns:
        capacity_value = pd.to_numeric(capacity[column], errors="coerce")
        share_value = pd.to_numeric(share[column], errors="coerce")
        if pd.isna(capacity_value) or pd.isna(share_value):
            continue
        share_fraction = share_value / 100.0 if abs(share_value) > 1 else share_value
        values.append({"year": int(column), "value": capacity_value * share_fraction})
    result = pd.DataFrame(values)
    result["source_system"] = "ESTIMATION_CODE"
    result["scenario"] = scenario
    result["economy"] = economy
    result["common_flow_code"] = flow_label.split(" ", maxsplit=1)[0]
    result["common_flow_label"] = flow_label
    result["common_product_code"] = product_label.split(" ", maxsplit=1)[0]
    result["common_product_label"] = product_label
    return result


def _load_esto_history_rows(
    esto_data_path: Path, flow_label: str, product_label: str, economy: str, scenario: str
) -> pd.DataFrame:
    """Load the historical source amount without inventing a projection comparator."""
    source = pd.read_csv(esto_data_path)
    esto_economy = economy.replace("_", "")
    selected = source.loc[
        source["economy"].astype(str).eq(esto_economy)
        & source["flows"].astype(str).eq("09.07 Oil refineries")
        & source["products"].astype(str).eq(product_label)
    ]
    if selected.empty:
        return pd.DataFrame()
    row = selected.iloc[0]
    values = [
        {"year": int(column), "value": pd.to_numeric(row[column], errors="coerce")}
        for column in source.columns if str(column).isdigit() and pd.notna(row[column])
    ]
    result = pd.DataFrame(values)
    result["source_system"] = "ESTO"
    result["scenario"] = scenario
    result["economy"] = economy
    result["common_flow_code"] = flow_label.split(" ", maxsplit=1)[0]
    result["common_flow_label"] = flow_label
    result["common_product_code"] = product_label.split(" ", maxsplit=1)[0]
    result["common_product_label"] = product_label
    return result


def render_refining_shadow_chart_prototype(
    diagnostic_path: Path,
    output_root: Path,
    template_path: Path,
    economy: str = "01_AUS",
    scenario: str = "Target",
    flow_label: str = "09.07 Oil refineries (including own use)",
    product_label: str = "07.07 Gas/diesel oil",
    review_key: str = "refining_shadow_review",
    review_label: str = "Refining shadow review",
    area_chart_title: str = "LEAP Target fuels, code expectation, and source references",
    transformation_workbook_path: Path | None = None,
    esto_data_path: Path | None = None,
    output_fuel_label: str = "Gas and diesel oil",
) -> Path:
    """Render a production-style refining diagnostic through page/bundle writers."""
    template = load_json(template_path)
    rows = _load_refining_diagnostic_rows(
        diagnostic_path=diagnostic_path,
        economy=economy,
        scenario=scenario,
        flow_label=flow_label,
        product_label=product_label,
    )
    area_rows = _load_target_area_rows(
        diagnostic_path=diagnostic_path,
        economy=economy,
        scenario=scenario,
        flow_label=flow_label,
    )
    if transformation_workbook_path is None:
        transformation_workbook_path = (
            REPO_ROOT.parent / "leap_initialisation" / "outputs" / "leap_exports"
            / "supply_reconciliation" / "baseline_seed" / "runs"
            / "SEED_AUS_CONSOLIDATED_20260820" / "workbooks"
            / "transformation_leap_imports_01_AUS_Target.xlsx"
        )
    if esto_data_path is None:
        esto_data_path = REPO_ROOT.parent / "leap_initialisation" / "data" / "00APEC_2024_low_with_subtotals.csv"
    code_expected_rows = _load_variable_expected_rows(
        transformation_workbook_path, product_label, output_fuel_label,
        flow_label, economy, scenario,
    )
    esto_rows = _load_esto_history_rows(
        esto_data_path, flow_label, product_label, economy, scenario,
    )
    series_labels = {
        "LEAP|Target": "LEAP Target",
        "LEAP_OUTPUT|Target": "LEAP Target diesel output",
        "ESTIMATION_CODE|Target": "Expected output (transformation settings)",
        "NINTH|Target": "9th Target output",
        "ESTO|Target": "ESTO historical output",
    }
    comparison_rows = rows.loc[
        rows["source_system"].eq("ESTIMATION_EXPECTATION")
    ].copy()
    comparison_rows["absolute_difference_pj"] = (
        comparison_rows["source_value_pj"] - comparison_rows["leap_value_pj"]
    ).abs()
    comparison_rows["absolute_percentage_difference"] = (
        comparison_rows["absolute_difference_pj"]
        / comparison_rows["source_value_pj"].abs()
    )
    first_year = int(comparison_rows["year"].min())
    last_year = int(comparison_rows["year"].max())
    comparison_rows["source_system"] = "NINTH"
    leap_output_rows = area_rows.loc[
        area_rows["common_product_label"].eq(product_label)
    ].copy()
    leap_output_rows["source_system"] = "LEAP_OUTPUT"
    area_chart_rows = pd.concat(
        [area_rows, leap_output_rows, code_expected_rows, comparison_rows, esto_rows],
        ignore_index=True,
    )
    area_figure = build_area_chart(
        area_chart_rows,
        {
            "aggregate_flow_label": flow_label,
            "source_flow_labels": [flow_label],
        },
        series_labels,
        template,
        title_prefix=area_chart_title,
    )
    trace_meta = list((area_figure.layout.meta or {}).get("trace_meta", []))
    for index, trace in enumerate(area_figure.data):
        source_system = (
            str(trace_meta[index].get("source_system", ""))
            if index < len(trace_meta) else ""
        )
        if source_system == "ESTO" and str(trace.name) == product_label:
            trace.update(visible=False, showlegend=False)
        if str(trace.name).startswith("Expected output (transformation settings)"):
            trace.update(
                name="Expected output (transformation settings)",
                line={"dash": "dash", "color": "#8c55b8"},
            )
        elif str(trace.name).startswith("9th Target output"):
            trace.update(name="9th Target output", line={"dash": "dot", "color": "#4f6d7a"})
        elif str(trace.name).startswith("ESTO historical output"):
            trace.update(name="ESTO historical output", line={"dash": "solid", "color": "#333333"})
        elif str(trace.name).startswith("LEAP Target diesel output"):
            trace.update(name="LEAP Target diesel output", line={"dash": "solid", "color": "#D55E00"})
    area_figure.update_layout(
        title=(
            f"{area_chart_title} ({first_year}–{last_year}): {flow_label}"
        ),
        meta={
            **dict(area_figure.layout.meta or {}),
            "prototype_status": "pre_seed_variable_expected_output_review",
            "expected_output_source": "transformation workbook capacity times output share",
        },
    )
    layout = {
        "dashboards": output_root / "dashboards",
        "chart_bundles": output_root / "chart_bundles",
        "supporting": output_root / "supporting_files",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    bundle_name = f"{review_key}__charts"
    area_chart_key = f"chart__area__{review_key}__fuel_mix"
    write_chart_bundle(
        {area_chart_key: area_figure},
        layout["chart_bundles"] / bundle_name,
    )
    chart_rows = [{
        "chart_key": area_chart_key,
        "chart_type": "stacked_area",
        "title": f"{area_chart_title} ({first_year}–{last_year})",
        "product_label": "All transformation fuels",
        "section_label": review_label,
        "flow_group_label": flow_label,
        "datasets": chart_dataset_tokens_from_figure(area_figure),
        "total_abs_value": float(area_chart_rows["value"].abs().sum()),
        "abs_diff": float(comparison_rows["absolute_difference_pj"].max()),
        "pct_diff": float(
            comparison_rows["absolute_percentage_difference"].max()
        ),
    }]
    output_path = layout["dashboards"] / f"{review_key}.html"
    write_dashboard_page(
        page_config={
            "page_key": review_key,
            "page_label": review_label,
        },
        chart_rows=chart_rows,
        bundle_js_name=f"{bundle_name}.js",
        output_path=output_path,
        economy_label=economy,
        page_note=(
            "Read-only review: stacked areas and total are positive LEAP refinery "
            "outputs only. The diesel-output lines compare LEAP, pre-seed capacity "
            "× output share, 9th Target, and ESTO history on the same product basis."
        ),
        dataset_filter_options=["LEAP", "ESTIMATION_EXPECTATION"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(
        json.dumps(
            {
                "review_key": review_key,
                "diagnostic_path": str(diagnostic_path),
                "transformation_workbook_path": str(transformation_workbook_path),
                "esto_data_path": str(esto_data_path),
                "boundary": flow_label,
                "product": product_label,
                "figure_layout": area_figure.to_plotly_json()["layout"],
                "area_chart_key": area_chart_key,
                "area_chart_product_count": int(
                    area_rows["common_product_label"].nunique()
                ),
            },
            default=str,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


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
OUTPUT_ROOT = REPO_ROOT / "outputs" / "shadow_estimation_review" / "01_AUS_refining_target_2023"

if RUN_PROTOTYPE:
    RESULT_PATH = render_refining_shadow_chart_prototype(
        diagnostic_path=DIAGNOSTIC_PATH,
        output_root=OUTPUT_ROOT,
        template_path=TEMPLATE_PATH,
    )
    print(f"[OK] Renderer-backed prototype written to {RESULT_PATH}")

#%%
