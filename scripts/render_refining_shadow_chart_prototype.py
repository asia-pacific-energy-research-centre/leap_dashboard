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
    build_product_chart,
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
    """Return all mapped LEAP Target fuel rows for a stacked transformation chart."""
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
    return scoped


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
    area_chart_title: str = "LEAP Target refinery fuel mix",
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
    series_labels = {
        "LEAP|Target": "LEAP Target",
        "ESTIMATION_EXPECTATION|Target": "Expected output",
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
    figure.update_layout(
        title=(
            f"Shadow comparison review ({first_year}–{last_year}): "
            f"{flow_label} — {product_label}"
        ),
        meta={
            **dict(figure.layout.meta or {}),
            "prototype_status": "diagnostic_expected_series_reviewed_boundary",
        },
    )
    area_figure = build_area_chart(
        area_rows,
        {
            "aggregate_flow_label": flow_label,
            "source_flow_labels": [flow_label],
        },
        series_labels,
        template,
        title_prefix=area_chart_title,
    )
    layout = {
        "dashboards": output_root / "dashboards",
        "chart_bundles": output_root / "chart_bundles",
        "supporting": output_root / "supporting_files",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    chart_key = f"chart__line__{review_key}__{product_label.split(' ', maxsplit=1)[0].replace('.', '_')}"
    bundle_name = f"{review_key}__charts"
    area_chart_key = f"chart__area__{review_key}__fuel_mix"
    write_chart_bundle(
        {area_chart_key: area_figure, chart_key: figure},
        layout["chart_bundles"] / bundle_name,
    )
    chart_rows = [{
        "chart_key": area_chart_key,
        "chart_type": "stacked_area",
        "title": area_chart_title,
        "product_label": "All transformation fuels",
        "section_label": review_label,
        "flow_group_label": flow_label,
        "datasets": chart_dataset_tokens_from_figure(area_figure),
        "total_abs_value": float(area_rows["value"].abs().sum()),
        "abs_diff": 0.0,
        "pct_diff": 0.0,
    }, {
        "chart_key": chart_key,
        "chart_type": "line",
        "title": f"{flow_label} — {product_label}",
        "product_label": product_label,
        "section_label": review_label,
        "flow_group_label": flow_label,
        "datasets": chart_dataset_tokens_from_figure(figure),
        "total_abs_value": float(comparison_rows["source_value_pj"].abs().sum()),
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
            "Read-only review: estimated expectation uses the maintained "
            f"comparison boundary ({first_year}–{last_year})."
        ),
        dataset_filter_options=["LEAP", "ESTIMATION_EXPECTATION"],
    )
    (layout["supporting"] / "shadow_chart_manifest.json").write_text(
        json.dumps(
            {
                "chart_key": chart_key,
                "review_key": review_key,
                "diagnostic_path": str(diagnostic_path),
                "boundary": flow_label,
                "product": product_label,
                "figure_layout": figure.to_plotly_json()["layout"],
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
