#%%
"""Render read-only mapping and hierarchy diagnostics beside the dashboard.

This module deliberately reads QA artifacts produced by leap_mappings. It does
not infer mappings, modify workbooks, or change validation status semantics.
"""

from __future__ import annotations

from html import escape
from math import floor, log10
from pathlib import Path

import pandas as pd


#%%
DIAGNOSTIC_PAGE_NAME = "mapping_diagnostics.html"
MAX_TABLE_ROWS = 30
MAX_TREE_CHILDREN = 10
MAX_TREE_DEPTH = 3

SCOPE_PRIORITY = {
    "esto_leap_ninth": 0,
    "esto_leap": 1,
    "leap_vs_ninth": 2,
    "esto_only": 3,
}


def _read_csv(path: Path) -> pd.DataFrame:
    """Read an optional diagnostic artifact as text-friendly values."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False).fillna("")


def _table_html(frame: pd.DataFrame, columns: list[str], *, limit: int = MAX_TABLE_ROWS) -> str:
    """Return a compact, escaped HTML table for available columns only."""
    available = [column for column in columns if column in frame.columns]
    if frame.empty or not available:
        return '<p class="empty-state">No rows in the current artifact.</p>'
    display = frame.loc[:, available].head(limit).copy()
    header = "".join(f"<th>{escape(column.replace('_', ' '))}</th>" for column in available)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>"
        for row in display.itertuples(index=False, name=None)
    )
    suffix = "" if len(frame) <= limit else f"<p class=\"table-note\">Showing {limit:,} of {len(frame):,} rows.</p>"
    return f"<div class=\"table-scroll\"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>{suffix}"


def _failure_summary(frame: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    if frame.empty or "status" not in frame.columns:
        return pd.DataFrame(columns=group_columns + ["rows"])
    failures = frame[frame["status"].astype(str).eq("failed")].copy()
    if failures.empty:
        return pd.DataFrame(columns=group_columns + ["rows"])
    available = [column for column in group_columns if column in failures.columns]
    return (
        failures.groupby(available, dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values("rows", ascending=False, kind="mergesort")
    )


def _three_significant_figures(value: float) -> str:
    """Format a number to three significant figures without unnecessary scientific notation."""
    if pd.isna(value) or value == 0:
        return "0"
    decimals = 2 - floor(log10(abs(value)))
    rounded = round(value, decimals)
    if decimals <= 0:
        return f"{rounded:,.0f}"
    return f"{rounded:,.{decimals}f}"


def _anchor_value_summary(anchor: pd.DataFrame) -> pd.DataFrame:
    """Sum failed parent/child comparisons across all economies, scenarios, and years."""
    required = {"status", "source_system", "validation_axis", "parent_code"}
    if anchor.empty or not required.issubset(anchor.columns):
        return pd.DataFrame()
    failures = anchor[anchor["status"].astype(str).eq("failed")].copy()
    if failures.empty:
        return pd.DataFrame()
    context_columns = [
        "source_system", "validation_axis", "economy", "scenario", "year",
        "other_axis_value", "parent_code",
    ]
    context_columns = [column for column in context_columns if column in failures.columns]
    if "comparison_scope" in failures.columns:
        failures["_scope_priority"] = failures["comparison_scope"].map(SCOPE_PRIORITY).fillna(99)
        failures = (
            failures.sort_values("_scope_priority", kind="mergesort")
            .drop_duplicates(context_columns, keep="first")
        )
    value_columns = ["parent_value", "frontier_sum", "difference", "abs_error"]
    for column in value_columns:
        failures[column] = pd.to_numeric(failures.get(column, 0), errors="coerce").fillna(0.0)
    summary = (
        failures.groupby(["source_system", "validation_axis", "parent_code"], dropna=False)
        .agg(
            failed_checks=("status", "size"),
            parent_total=("parent_value", "sum"),
            children_total=("frontier_sum", "sum"),
            net_difference=("difference", "sum"),
            absolute_mismatch_total=("abs_error", "sum"),
        )
        .reset_index()
        .sort_values("absolute_mismatch_total", ascending=False, kind="mergesort")
    )
    return summary


def _anchor_child_value_summary(child_values: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Choose the broadest available scope and sum raw values by tree edge."""
    required = {"source_system", "validation_axis", "parent_code", "child_code", "raw_child_total"}
    if child_values.empty or not required.issubset(child_values.columns):
        return {}
    working = child_values.copy()
    if "comparison_scope" in working.columns:
        working["_scope_priority"] = working["comparison_scope"].map(SCOPE_PRIORITY).fillna(99)
        group_columns = ["source_system", "validation_axis", "parent_code", "child_code"]
        preferred_scope = (
            working.groupby(group_columns, dropna=False)["_scope_priority"].transform("min")
        )
        working = working[working["_scope_priority"].eq(preferred_scope)]
    working["raw_child_total"] = pd.to_numeric(working["raw_child_total"], errors="coerce").fillna(0.0)
    grouped = working.groupby(["parent_code", "child_code"], dropna=False)["raw_child_total"].sum()
    return {(str(parent), str(child)): float(value) for (parent, child), value in grouped.items()}


def _ninth_raw_context_summary(context_values: pd.DataFrame) -> pd.DataFrame:
    """Build a context-level raw NINTH parent/child reconciliation table."""
    required = {
        "source_system", "validation_axis", "comparison_scope", "economy", "scenario", "year",
        "other_axis_value", "parent_code", "child_code", "parent_value", "frontier_sum",
        "raw_child_value",
    }
    if context_values.empty or not required.issubset(context_values.columns):
        return pd.DataFrame()
    working = context_values[context_values["source_system"].astype(str).eq("NINTH")].copy()
    if working.empty:
        return pd.DataFrame()
    context_columns = [
        "validation_axis", "economy", "scenario", "year", "other_axis_value", "parent_code",
    ]
    working["_scope_priority"] = working["comparison_scope"].map(SCOPE_PRIORITY).fillna(99)
    preferred_scope = working.groupby(context_columns, dropna=False)["_scope_priority"].transform("min")
    working = working[working["_scope_priority"].eq(preferred_scope)]
    for column in ["parent_value", "frontier_sum", "raw_child_value"]:
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)
    group_columns = context_columns
    rows: list[dict[str, object]] = []
    for context, group in working.groupby(group_columns, dropna=False, sort=False):
        child_values = group.sort_values("child_code", kind="mergesort")
        raw_children_total = float(child_values["raw_child_value"].sum())
        parent_value = float(child_values["parent_value"].iloc[0])
        mapped_frontier = float(child_values["frontier_sum"].iloc[0])
        child_breakdown = "; ".join(
            f"{str(row.child_code).split('/')[-1]}: {_three_significant_figures(float(row.raw_child_value))}"
            for row in child_values.itertuples(index=False)
        )
        rows.append({
            "validation_axis": context[0],
            "economy": context[1],
            "scenario": context[2],
            "year": context[3],
            "other_axis_value": context[4],
            "parent_code": context[5],
            "raw_parent": _three_significant_figures(parent_value),
            "raw_children_sum": _three_significant_figures(raw_children_total),
            "raw_residual": _three_significant_figures(parent_value - raw_children_total),
            "absolute_raw_residual": abs(parent_value - raw_children_total),
            "mapped_frontier": _three_significant_figures(mapped_frontier),
            "raw_child_values": child_breakdown,
        })
    return pd.DataFrame(rows).sort_values("absolute_raw_residual", ascending=False, kind="mergesort")


def _tree_html(
    tree: pd.DataFrame,
    parent_code: str,
    value_summary: dict[str, dict[str, float]],
    child_values: dict[tuple[str, str], float],
    *,
    depth: int = 0,
) -> str:
    """Render a bounded subtree with aggregated parent/child mismatch values."""
    node = tree[tree["code"].astype(str).eq(parent_code)]
    label = str(node.iloc[0].get("label", parent_code)) if not node.empty else parent_code
    values = value_summary.get(parent_code, {})
    badge = ""
    if values:
        badge = (
            '<span class="value-badge">'
            f"parent {_three_significant_figures(values['parent_total'])}; "
            f"mapped frontier {_three_significant_figures(values['children_total'])}; "
            f"absolute mismatch {_three_significant_figures(values['absolute_mismatch_total'])}"
            "</span>"
        )
    children = tree[tree["parent_code"].astype(str).eq(parent_code)].copy()
    children = children.sort_values(["level", "code"], kind="mergesort").head(MAX_TREE_CHILDREN)
    code_detail = "" if label == parent_code else f'<code class="tree-code">{escape(parent_code)}</code>'
    raw_child_badge = ""
    if depth:
        raw_child_value = child_values.get((str(tree[tree["code"].astype(str).eq(parent_code)].iloc[0].get("parent_code", "")), parent_code)) if not node.empty else None
        if raw_child_value is not None:
            raw_child_badge = f'<span class="child-value">raw child {_three_significant_figures(raw_child_value)}</span>'
    title = f'<span class="tree-label">{escape(label)}</span>{code_detail}{badge}{raw_child_badge}'
    if children.empty or depth >= MAX_TREE_DEPTH:
        return f"<li><span class=\"tree-node\">{title}</span></li>"
    child_html = "".join(
        _tree_html(tree, str(row.code), value_summary, child_values, depth=depth + 1)
        for row in children.itertuples()
    )
    more = "" if len(tree[tree["parent_code"].astype(str).eq(parent_code)]) <= MAX_TREE_CHILDREN else "<li>… additional children omitted</li>"
    return f"<li><details open><summary>{title}</summary><ul>{child_html}{more}</ul></details></li>"


def _issue_tree_section(
    tree: pd.DataFrame,
    value_summary: pd.DataFrame,
    child_values: dict[tuple[str, str], float],
    source_system: str,
) -> str:
    """Render the branches with the largest summed anchor mismatch for one source system."""
    if tree.empty or value_summary.empty:
        return '<p class="empty-state">No tree or failed-anchor value data is available.</p>'
    values = value_summary[value_summary["source_system"].astype(str).eq(source_system)].copy()
    if values.empty:
        return '<p class="empty-state">No failed anchor rows for this source system.</p>'
    tree_codes = set(tree["code"].astype(str))
    roots = [str(code) for code in values["parent_code"] if str(code) in tree_codes][:4]
    if not roots:
        return '<p class="empty-state">The current failed parent labels do not resolve to this exported tree.</p>'
    value_lookup = {
        str(row.parent_code): {
            "parent_total": float(row.parent_total),
            "children_total": float(row.children_total),
            "absolute_mismatch_total": float(row.absolute_mismatch_total),
        }
        for row in values.itertuples(index=False)
    }
    return "<ul class=\"tree\">" + "".join(
        _tree_html(tree, root, value_lookup, child_values) for root in roots
    ) + "</ul>"


def _artifact_note(path: Path) -> str:
    if not path.exists():
        return f"Missing artifact: {path.name}"
    timestamp = pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")
    return f"{path.name} (updated {timestamp})"


def write_mapping_diagnostics_page(
    layout: dict[str, Path],
    mappings_root: Path,
    *,
    dashboard_updated_label: str,
) -> dict[str, str]:
    """Write one self-contained mapping diagnostics page and summary CSV."""
    results_root = mappings_root / "results"
    tree_root = results_root / "tree_structure"
    anchor_path = tree_root / "source_parent_anchor_validation.csv"
    anchor_child_values_path = tree_root / "source_parent_anchor_child_values.csv"
    anchor_child_context_values_path = tree_root / "source_parent_anchor_child_context_values.csv"
    stage_path = tree_root / "common_esto_validation.csv"
    partial_path = results_root / "common_esto" / "qa_common_esto_unresolved_partial_coverage.csv"
    unmapped_path = results_root / "common_esto" / "qa_nonzero_unmapped_leap_branches.csv"
    conflicts_path = results_root / "maintenance" / "leap_source_presence_conflicts.csv"
    coverage_path = results_root / "source_coverage" / "all_demand_aggregated_coverage_gaps.csv"

    anchor = _read_csv(anchor_path)
    anchor_child_values = _read_csv(anchor_child_values_path)
    anchor_child_context_values = _read_csv(anchor_child_context_values_path)
    stage = _read_csv(stage_path)
    ninth_tree = _read_csv(tree_root / "ninth_tree.csv")
    leap_tree = _read_csv(tree_root / "leap_tree.csv")
    partial = _read_csv(partial_path)
    unmapped = _read_csv(unmapped_path)
    conflicts = _read_csv(conflicts_path)
    coverage = _read_csv(coverage_path)

    stage_summary = _failure_summary(stage, ["source_system", "validation_axis", "parent_code"])
    anchor_summary = _failure_summary(anchor, ["source_system", "validation_axis", "reason", "parent_code"])
    anchor_value_summary = _anchor_value_summary(anchor)
    anchor_child_value_lookup = _anchor_child_value_summary(anchor_child_values)
    ninth_raw_context_summary = _ninth_raw_context_summary(anchor_child_context_values)
    anchor_value_display = anchor_value_summary.copy()
    for column in ["parent_total", "children_total", "net_difference", "absolute_mismatch_total"]:
        if column in anchor_value_display.columns:
            anchor_value_display[column] = anchor_value_display[column].map(_three_significant_figures)
    coverage_summary = (
        coverage.groupby([column for column in ["coverage_status", "mapping_status"] if column in coverage.columns], dropna=False)
        .size().reset_index(name="rows").sort_values("rows", ascending=False, kind="mergesort")
        if not coverage.empty else pd.DataFrame(columns=["coverage_status", "mapping_status", "rows"])
    )
    summary = pd.DataFrame([
        {"metric": "Stage 3 failed hierarchy checks", "rows": int(len(stage[stage.get("status", "").astype(str).eq("failed")])) if not stage.empty else 0},
        {"metric": "Failed anchor checks", "rows": int(len(anchor[anchor.get("status", "").astype(str).eq("failed")])) if not anchor.empty else 0},
        {"metric": "Actionable partial-coverage rows", "rows": int(len(partial))},
        {"metric": "Non-zero unmapped LEAP branches", "rows": int(len(unmapped))},
        {"metric": "LEAP source-presence conflicts", "rows": int(len(conflicts))},
        {"metric": "Source-coverage gaps", "rows": int(len(coverage))},
    ])
    summary.to_csv(layout["supporting"] / "mapping_diagnostics_summary.csv", index=False)

    cards = "".join(
        f'<div class="metric-card"><span>{escape(str(row.metric))}</span><strong>{int(row.rows):,}</strong></div>'
        for row in summary.itertuples(index=False)
    )
    artifact_notes = "<br>".join(escape(_artifact_note(path)) for path in [anchor_path, stage_path, partial_path, unmapped_path, conflicts_path, coverage_path])
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapping diagnostics</title><style>
body {{ font-family: Inter,Segoe UI,Arial,sans-serif; margin:0; background:#f4f6f8; color:#172033; }}
.shell {{ max-width:1600px; margin:auto; padding:20px; }} header {{ background:white; border:1px solid #d9e1ea; border-radius:12px; padding:18px 22px; }}
h1,h2,h3 {{ margin:0 0 10px; }} h2 {{ margin-top:28px; }} .subtle {{ color:#5f6b7a; }} .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:16px 0; }}
.metric-card,.panel {{ background:white; border:1px solid #d9e1ea; border-radius:10px; padding:14px; }} .metric-card span {{ display:block; color:#5f6b7a; font-size:13px; }} .metric-card strong {{ font-size:28px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(480px,1fr)); gap:16px; }} .flow {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:12px 0; }} .flow div {{ background:#e8f0fa; border:1px solid #adc4df; border-radius:8px; padding:10px; font-size:13px; }} .arrow {{ color:#53718f; font-size:22px; }}
.tree {{ padding-left:18px; }} .tree ul {{ padding-left:22px; }} summary,.tree-node {{ line-height:1.7; }} code {{ color:#254b75; }} .tree-label {{ color:#102a43; font-weight:600; }} .tree-code {{ color:#4b6378; display:block; font-size:.72rem; margin:.08rem 0 .16rem; overflow-wrap:anywhere; }} .value-badge {{ background:#fde8e7; color:#9b1c1c; border-radius:999px; padding:2px 7px; font-size:12px; margin-left:5px; }} .child-value {{ color:#5f6b7a; font-size:12px; margin-left:7px; }}
.table-scroll {{ overflow:auto; max-height:480px; }} table {{ border-collapse:collapse; width:100%; font-size:12px; }} th {{ position:sticky; top:0; background:#e8f0fa; }} th,td {{ border:1px solid #d9e1ea; padding:6px 8px; text-align:left; vertical-align:top; }} .table-note,.empty-state {{ color:#5f6b7a; font-size:13px; }} footer {{ margin:22px 0; font-size:12px; color:#5f6b7a; }} a {{ color:#1b5e9a; }}
</style></head><body><div class="shell"><header><a href="index.html">← Dashboard overview</a><h1>Mapping diagnostics</h1><p class="subtle">Read-only inspection of hierarchy/anchor validation and direct mapping coverage. Updated: {escape(dashboard_updated_label)}</p></header>
<div class="metrics">{cards}</div>
<section class="panel"><h2>How the anchor validator connects the trees</h2><div class="flow"><div>Raw source parent</div><span class="arrow">→</span><div>Raw source child tree</div><span class="arrow">→</span><div>Mapped Common ESTO frontier</div><span class="arrow">→</span><div>Comparison values</div><span class="arrow">→</span><div>Passed / failed / skipped reason</div></div><p class="subtle">Tree badges sum failed values across economies, scenarios, and years. Each failed parent shows its raw parent total, mapped-frontier total, and absolute mismatch. Each listed direct child shows its raw source total for the same failed contexts.</p></section>
<div class="grid"><section class="panel"><h2>NINTH branches with largest summed mismatch</h2>{_issue_tree_section(ninth_tree[ninth_tree.get('axis', '').astype(str).eq('sector')] if not ninth_tree.empty else ninth_tree, anchor_value_summary, anchor_child_value_lookup, 'NINTH')}</section><section class="panel"><h2>LEAP branches with largest summed mismatch</h2>{_issue_tree_section(leap_tree[leap_tree.get('axis', '').astype(str).eq('sector')] if not leap_tree.empty else leap_tree, anchor_value_summary, anchor_child_value_lookup, 'LEAP')}</section></div>
<section class="panel"><h2>Stage 3 hierarchy failures</h2>{_table_html(stage_summary, ['source_system','validation_axis','parent_code','rows'])}</section>
<section class="panel"><h2>Largest summed anchor mismatches</h2><p class="subtle">Parent and children totals are sums across all failed rows; net difference is parent minus children, while absolute mismatch does not allow opposite signs to cancel.</p>{_table_html(anchor_value_display, ['source_system','validation_axis','parent_code','failed_checks','parent_total','children_total','net_difference','absolute_mismatch_total'])}<h3>Failure reasons</h3>{_table_html(anchor_summary, ['source_system','validation_axis','reason','parent_code','rows'])}</section>
<section class="panel"><h2>Raw NINTH hierarchy drilldown</h2><p class="subtle">Each row is one economy, scenario, year, and other-axis context before mapping. Raw residual is raw parent minus the sum of its immediate raw children. This separates source-hierarchy contradictions from mapped-frontier differences.</p>{_table_html(ninth_raw_context_summary, ['economy','scenario','year','validation_axis','other_axis_value','parent_code','raw_parent','raw_children_sum','raw_residual','mapped_frontier','raw_child_values'])}</section>
<section class="panel"><h2>Direct mapping coverage review</h2><h3>Actionable partial coverage</h3>{_table_html(partial, ['source_system','comparison_scope','common_row_id','missing_component_pairs','relevance_evidence','mapping_action','mapping_sheet_to_review'])}<h3>Non-zero unmapped LEAP branches</h3>{_table_html(unmapped, ['leap_flow','leap_product','indirect_esto_flow','indirect_esto_product','qa_status'])}<h3>LEAP source-presence conflicts</h3>{_table_html(conflicts, ['leap_sector_name_full_path','raw_leap_fuel_name','presence_status','in_leap_combined_esto','in_leap_combined_ninth'])}<h3>Source-coverage audit summary</h3>{_table_html(coverage_summary, ['coverage_status','mapping_status','rows'])}</section>
<footer><strong>Artifact provenance</strong><br>{artifact_notes}<br>{escape(_artifact_note(anchor_child_values_path))}<br>{escape(_artifact_note(anchor_child_context_values_path))}</footer></div></body></html>"""
    output_path = layout["dashboards"] / DIAGNOSTIC_PAGE_NAME
    output_path.write_text(html, encoding="utf-8")
    return {"page": str(output_path), "summary": str(layout["supporting"] / "mapping_diagnostics_summary.csv")}


#%%
