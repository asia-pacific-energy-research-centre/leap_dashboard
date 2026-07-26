#%%
"""Render a read-only prototype for inspecting three anchor-tree contexts.

The page deliberately reads generated leap_mappings artifacts.  It does not
infer or persist mappings, and it does not alter anchor-validator semantics.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

import pandas as pd


#%%
REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
OUTPUT_PATH = REPO_ROOT / "outputs" / "prototypes" / "mapping_tree_explorer_prototype.html"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required prototype input is missing: {path}")
    return pd.read_csv(path, low_memory=False)


def _normalise_economy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.replace("_", "", regex=False)


def _selected_rows(frame: pd.DataFrame, criteria: dict[str, object]) -> pd.DataFrame:
    selected = frame.copy()
    for column, value in criteria.items():
        if column == "economy":
            selected = selected[_normalise_economy(selected[column]).eq(str(value).replace("_", ""))]
        else:
            selected = selected[selected[column].astype(str).eq(str(value))]
    return selected.copy()


def _number(value: object) -> float:
    return float(pd.to_numeric(value, errors="coerce") if pd.notna(value) else 0.0)


def _scale(values: list[float]) -> tuple[float, str]:
    largest = max((abs(value) for value in values), default=0.0)
    if largest >= 1_000_000:
        return 1_000_000.0, "Values in millions (×1,000,000 PJ)"
    if largest >= 1_000:
        return 1_000.0, "Values in thousands (×1,000 PJ)"
    return 1.0, "Values in PJ"


def _target_nodes(component_rows: pd.DataFrame, esto_tree: pd.DataFrame) -> tuple[list[dict[str, object]], bool]:
    component_rows = component_rows.copy()
    if "mapped_value" not in component_rows.columns and "value" in component_rows.columns:
        component_rows = component_rows.rename(columns={"value": "mapped_value"})
    mapped = component_rows[component_rows["mapping_status"].astype(str).str.startswith("mapped")].copy()
    mapped = mapped[mapped["common_row_id"].notna()].copy()
    mapped["common_row_id"] = mapped["common_row_id"].astype(str)
    mapped = mapped[~mapped["common_row_id"].isin(["", "nan"])]
    if mapped.empty:
        return [], False
    nodes = (
        mapped.sort_values(["common_row_id", "component_esto_flow"], kind="mergesort")
        .drop_duplicates("common_row_id")
        [["common_row_id", "component_esto_flow", "component_esto_product", "mapped_value"]]
        .rename(columns={"mapped_value": "value"})
        .to_dict("records")
    )
    for node in nodes:
        node["value"] = _number(node["value"])
    parent_by_flow = dict(zip(esto_tree["code"].astype(str), esto_tree["parent_code"].fillna("").astype(str)))
    target_pairs = {(str(node["component_esto_flow"]), str(node["component_esto_product"])) for node in nodes}
    has_target_edge = any(
        (parent_by_flow.get(flow, ""), product) in target_pairs
        for flow, product in target_pairs
    )
    for node in nodes:
        node["parent_flow"] = parent_by_flow.get(str(node["component_esto_flow"]), "")
        node["is_target_child"] = (
            str(node["parent_flow"]), str(node["component_esto_product"])
        ) in target_pairs
    return nodes, has_target_edge


def _case_from_failed_artifacts(
    name: str,
    description: str,
    criteria: dict[str, object],
    anchors: pd.DataFrame,
    children: pd.DataFrame,
    components: pd.DataFrame,
    esto_tree: pd.DataFrame,
) -> dict[str, object]:
    anchor = _selected_rows(anchors, criteria).iloc[0]
    child_rows = _selected_rows(children, criteria)
    component_rows = _selected_rows(components, criteria)
    targets, has_target_edge = _target_nodes(component_rows, esto_tree)
    routes = component_rows[["raw_node_role", "raw_child_code", "component_esto_flow", "component_esto_product", "common_row_id", "mapping_status"]].fillna("").to_dict("records")
    raw_children = child_rows[["child_code", "raw_child_value"]].rename(columns={"raw_child_value": "value"}).to_dict("records")
    return {
        "name": name,
        "description": description,
        "context": {column: anchor[column] for column in ["source_system", "comparison_scope", "economy", "scenario", "year", "other_axis_value", "parent_code"]},
        "status": str(anchor["status"]), "reason": str(anchor["reason"]),
        "raw_parent": _number(anchor["parent_value"]), "normalised_parent": _number(anchor["parent_value"]),
        "frontier_total": _number(anchor["frontier_sum"]), "difference": _number(anchor["difference"]),
        "children": raw_children, "targets": targets, "routes": routes,
        "has_target_edge": has_target_edge,
        "warning": "Incomplete frontier / missing-route entries are shown in the route drawer." if any("missing" in str(route["mapping_status"]) for route in routes) else "",
    }


def _direct_fanout_case(
    anchors: pd.DataFrame,
    raw_leap: pd.DataFrame,
    structural: pd.DataFrame,
    comparison: pd.DataFrame,
    esto_tree: pd.DataFrame,
) -> dict[str, object]:
    criteria = {"source_system": "LEAP", "comparison_scope": "esto_leap", "economy": "20USA", "scenario": "Reference", "year": 2060, "other_axis_value": "Natural gas", "parent_code": "Other loss and own use"}
    anchor = _selected_rows(anchors, criteria).iloc[0]
    raw = raw_leap[
        _normalise_economy(raw_leap["economy"]).eq("20USA")
        & raw_leap["scenario"].astype(str).eq("Reference")
        & raw_leap["year"].astype(str).eq("2060")
        & raw_leap["leap_product"].astype(str).eq("Natural gas")
        & raw_leap["leap_flow"].astype(str).str.startswith("Other loss and own use/")
    ][["leap_flow", "value"]].rename(columns={"leap_flow": "child_code"})
    structural_rows = structural[
        structural["source_system"].astype(str).eq("LEAP")
        & structural["comparison_scope"].astype(str).eq("leap_vs_esto")
        & structural["original_source_product"].astype(str).eq("Natural gas")
        & structural["original_source_flow"].astype(str).str.startswith("Other loss and own use/")
    ].copy()
    values = comparison[
        comparison["source_system"].astype(str).eq("LEAP")
        & comparison["comparison_scope"].astype(str).eq("esto_leap")
        & _normalise_economy(comparison["economy"]).eq("20USA")
        & comparison["scenario"].astype(str).eq("Reference")
        & comparison["year"].astype(str).eq("2060")
    ][["common_row_id", "value"]]
    routes_frame = structural_rows.merge(values, on="common_row_id", how="left")
    routes_frame["mapping_status"] = "mapped"
    routes_frame["raw_node_role"] = "child"
    routes_frame = routes_frame.rename(columns={"original_source_flow": "raw_child_code"})
    targets, has_target_edge = _target_nodes(routes_frame, esto_tree)
    return {
        "name": "LEAP direct fan-out (passed)",
        "description": "A raw parent fans out to target siblings. The target rows are not a hierarchy under the source parent.",
        "context": criteria,
        "status": str(anchor["status"]), "reason": str(anchor["reason"]),
        "raw_parent": _number(raw_leap[
            _normalise_economy(raw_leap["economy"]).eq("20USA") & raw_leap["scenario"].astype(str).eq("Reference") & raw_leap["year"].astype(str).eq("2060") & raw_leap["leap_flow"].astype(str).eq("Other loss and own use") & raw_leap["leap_product"].astype(str).eq("Natural gas")
        ]["value"].iloc[0]),
        "normalised_parent": _number(anchor["parent_value"]), "frontier_total": _number(anchor["frontier_sum"]), "difference": _number(anchor["difference"]),
        "children": raw.to_dict("records"), "targets": targets,
        "routes": routes_frame[["raw_node_role", "raw_child_code", "component_esto_flow", "component_esto_product", "common_row_id", "mapping_status"]].fillna("").to_dict("records"),
        "has_target_edge": has_target_edge,
        "warning": "The raw LEAP sign is converted only for the validator comparison; calculations retain unrounded values.",
    }


def _case_html(case: dict[str, object]) -> str:
    numbers = [case["raw_parent"], case["normalised_parent"], case["frontier_total"], case["difference"]] + [float(row["value"]) for row in case["children"]] + [float(row.get("value", 0) or 0) for row in case["targets"]]
    divisor, scale_label = _scale(numbers)
    def value(number: object) -> str:
        return f"{float(number) / divisor:,.6f}".rstrip("0").rstrip(".")
    raw_sum = sum(float(row["value"]) for row in case["children"])
    source_rows = "".join(f"<li><span>{escape(str(row['child_code']).split('/')[-1])}</span><b>{value(row['value'])}</b></li>" for row in case["children"])
    target_rows = "".join(f"<li><span>{'↳ ' if row.get('is_target_child') else ''}{escape(str(row['component_esto_flow']))} / {escape(str(row['component_esto_product']))}<small>{escape(str(row['common_row_id']))}</small></span><b>{value(row.get('value', 0) or 0)}</b></li>" for row in case["targets"])
    route_rows = "".join(f"<tr><td>{escape(str(row['raw_node_role']))}</td><td>{escape(str(row['raw_child_code']))}</td><td>{escape(str(row['component_esto_flow']))} / {escape(str(row['component_esto_product']))}</td><td>{escape(str(row['common_row_id']))}</td><td>{escape(str(row['mapping_status']))}</td></tr>" for row in case["routes"])
    target_heading = "Genuine target hierarchy edge available" if case["has_target_edge"] else "Direct mapping fan-out — no target parent/child roll-up"
    context = " · ".join(f"{key}: {value_}" for key, value_ in case["context"].items())
    return f'''<article class="case"><h2>{escape(str(case['name']))}</h2><p>{escape(str(case['description']))}</p><p class="context">{escape(context)}</p><p class="scale">{scale_label}; calculations use unrounded values.</p><div class="columns"><section><h3>Original source tree</h3><ul><li><span>Parent: {escape(str(case['context']['parent_code']))}</span><b>{value(case['raw_parent'])}</b></li><li class="total"><span>Raw children sum</span><b>{value(raw_sum)}</b></li><li class="residual"><span>Raw residual</span><b>{value(float(case['raw_parent']) - raw_sum)}</b></li>{source_rows}</ul></section><section><h3>Mapped Common ESTO tree</h3><p class="target-note">{target_heading}</p><ul>{target_rows}</ul></section></div><div class="comparison"><span>Source (raw): <b>{value(case['raw_parent'])}</b></span><span>Source (validator normalised): <b>{value(case['normalised_parent'])}</b></span><span>Unique Common ESTO total: <b>{value(case['frontier_total'])}</b></span><span>Difference: <b>{value(case['difference'])}</b></span></div><p class="status"><b>{escape(str(case['status']))}</b> — {escape(str(case['reason']))}. {escape(str(case['warning']))}</p><details><summary>Show mapping routes ({len(case['routes'])})</summary><table><thead><tr><th>Raw role</th><th>Raw node</th><th>ESTO component</th><th>Common row ID</th><th>Route status</th></tr></thead><tbody>{route_rows}</tbody></table><p>Routes may repeat a Common ESTO row. The comparison total counts each row ID once, so it is not the sum of every displayed route.</p></details></article>'''


def render_prototype() -> Path:
    tree_root = MAPPINGS_ROOT / "results" / "tree_structure"
    anchors = _read_csv(tree_root / "source_parent_anchor_validation.csv")
    children = _read_csv(tree_root / "source_parent_anchor_child_context_values.csv")
    components = _read_csv(tree_root / "source_parent_anchor_mapped_component_context_values.csv")
    esto_tree = _read_csv(tree_root / "esto_tree.csv")
    cases = [
        _direct_fanout_case(anchors, _read_csv(MAPPINGS_ROOT / "results" / "mapping_relationships" / "raw_leap_results.csv"), _read_csv(MAPPINGS_ROOT / "results" / "common_esto" / "structural_artifacts" / "source_pair_to_common_row.csv"), _read_csv(MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_comparison_data.csv"), esto_tree),
        _case_from_failed_artifacts("NINTH source-tree contradiction", "A mapped total cannot repair a raw source hierarchy contradiction.", {"source_system": "NINTH", "comparison_scope": "esto_leap_ninth", "economy": "20USA", "scenario": "target", "year": 2070, "other_axis_value": "08_gas/08_02_lng", "parent_code": "09_total_transformation_sector"}, anchors, children, components, esto_tree),
        _case_from_failed_artifacts("ESTO genuine target hierarchy", "The right-side edge exists in the actual ESTO tree, so it is safe to draw.", {"source_system": "ESTO", "comparison_scope": "esto_leap", "economy": "20USA", "scenario": "historical", "year": 2023, "other_axis_value": "02.03 Coke oven gas", "parent_code": "09 Total transformation sector"}, anchors, children, components, esto_tree),
    ]
    page = "".join(_case_html(case) for case in cases)
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Mapping tree explorer prototype</title><style>body{{font:15px system-ui,sans-serif;background:#f4f7fa;color:#17212b;margin:0}}main{{max-width:1200px;margin:auto;padding:28px}}article{{background:white;border:1px solid #d5dee8;border-radius:10px;padding:20px;margin:18px 0}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}section{{border:1px solid #d5dee8;padding:12px;border-radius:7px}}ul{{list-style:none;padding:0}}li{{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid #eef2f5;padding:7px 0}}small{{display:block;color:#64748b;font-family:monospace}}.total,.comparison{{font-weight:600}}.residual,.status{{color:#9b1c1c}}.comparison{{display:flex;gap:15px;flex-wrap:wrap;background:#eaf1f8;padding:12px;margin-top:14px}}.context,.scale,.target-note{{color:#526273;font-size:13px}}table{{width:100%;border-collapse:collapse;font-size:12px}}td,th{{border:1px solid #d5dee8;padding:6px;text-align:left;vertical-align:top}}@media(max-width:760px){{.columns{{grid-template-columns:1fr}}}}</style><main><h1>Interactive anchor-tree explorer — prototype</h1><p>Read-only prototype using generated mapping artifacts. Solid source/tree relationships and dashed conceptual mapping routes are kept distinct; displayed Common ESTO IDs are de-duplicated for the validator total.</p>{page}</main></html>'''
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return OUTPUT_PATH


#%%
if __name__ == "__main__":
    print(render_prototype())

#%%
