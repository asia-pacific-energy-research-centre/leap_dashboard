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


def _source_raw_context_summary(
    context_values: pd.DataFrame,
    anchor_value_summary: pd.DataFrame,
    source_system: str,
) -> pd.DataFrame:
    """Build a context drilldown joined to each branch's summed mismatch rank."""
    required = {
        "source_system", "validation_axis", "comparison_scope", "economy", "scenario", "year",
        "other_axis_value", "parent_code", "child_code", "parent_value", "frontier_sum",
        "raw_child_value",
    }
    if context_values.empty or not required.issubset(context_values.columns):
        return pd.DataFrame()
    working = context_values[context_values["source_system"].astype(str).eq(source_system)].copy()
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
    branch_values = anchor_value_summary[
        anchor_value_summary["source_system"].astype(str).eq(source_system)
    ].copy()
    branch_values = branch_values.sort_values("absolute_mismatch_total", ascending=False, kind="mergesort")
    branch_values["branch_mismatch_rank"] = range(1, len(branch_values) + 1)
    branch_lookup = {
        (str(row.validation_axis), str(row.parent_code)): row
        for row in branch_values.itertuples(index=False)
    }

    rows: list[dict[str, object]] = []
    for context, group in working.groupby(group_columns, dropna=False, sort=False):
        child_values = group.sort_values("child_code", kind="mergesort")
        raw_children_total = float(child_values["raw_child_value"].sum())
        parent_value = float(child_values["parent_value"].iloc[0])
        mapped_frontier = float(child_values["frontier_sum"].iloc[0])
        branch = branch_lookup.get((str(context[0]), str(context[5])))
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
            "branch_mismatch_rank": int(branch.branch_mismatch_rank) if branch else "",
            "branch_absolute_mismatch": _three_significant_figures(float(branch.absolute_mismatch_total)) if branch else "",
            "branch_parent_total": _three_significant_figures(float(branch.parent_total)) if branch else "",
            "branch_mapped_frontier_total": _three_significant_figures(float(branch.children_total)) if branch else "",
            "raw_child_values": child_breakdown,
        })
    return pd.DataFrame(rows).sort_values("absolute_raw_residual", ascending=False, kind="mergesort")


def _paired_anchor_aggregate_summary(
    context_values: pd.DataFrame,
    source_system: str,
    economy: str,
) -> pd.DataFrame:
    """Aggregate failed raw-tree contexts for one displayed source/economy.

    The mapped frontier is deliberately one total, rather than being assigned
    back to raw children: one Common ESTO row can legitimately represent more
    than one raw child.  Showing a made-up per-child split would make the
    comparison look additive when the validator specifically avoids that.
    """
    required = {
        "source_system", "validation_axis", "comparison_scope", "economy", "scenario", "year",
        "other_axis_value", "parent_code", "child_code", "parent_value", "frontier_sum",
        "raw_child_value",
    }
    if context_values.empty or not required.issubset(context_values.columns):
        return pd.DataFrame()
    working = context_values[
        context_values["source_system"].astype(str).eq(source_system)
        & context_values["economy"].astype(str).str.replace("_", "", regex=False).eq(economy)
    ].copy()
    if working.empty:
        return pd.DataFrame()
    context_keys = [
        "validation_axis", "economy", "scenario", "year", "other_axis_value", "parent_code",
    ]
    working["_scope_priority"] = working["comparison_scope"].map(SCOPE_PRIORITY).fillna(99)
    working = working[
        working["_scope_priority"].eq(
            working.groupby(context_keys, dropna=False)["_scope_priority"].transform("min")
        )
    ]
    for column in ["parent_value", "frontier_sum", "raw_child_value"]:
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)
    group_keys = ["validation_axis", "other_axis_value", "parent_code"]
    rows: list[dict[str, object]] = []
    for group_key, group in working.groupby(group_keys, dropna=False, sort=False):
        contexts = group.drop_duplicates(context_keys)
        child_totals = group.groupby("child_code", dropna=False)["raw_child_value"].sum()
        parent_total = float(contexts["parent_value"].sum())
        frontier_total = float(contexts["frontier_sum"].sum())
        children_total = float(child_totals.sum())
        rows.append({
            "validation_axis": group_key[0],
            "other_axis_value": group_key[1],
            "parent_code": group_key[2],
            "parent_total": parent_total,
            "children_total": children_total,
            "raw_residual": parent_total - children_total,
            "mapped_frontier_total": frontier_total,
            "mapped_difference": parent_total - frontier_total,
            "absolute_mismatch": abs(parent_total - frontier_total),
            "child_totals": child_totals.to_dict(),
            "scenarios": ", ".join(sorted(contexts["scenario"].astype(str).unique())),
            "years": ", ".join(str(year) for year in sorted(pd.to_numeric(contexts["year"]).dropna().astype(int).unique())),
        })
    return pd.DataFrame(rows).sort_values("absolute_mismatch", ascending=False, kind="mergesort")


def _tree_label_lookup(tree: pd.DataFrame) -> dict[str, str]:
    if tree.empty or not {"code", "label"}.issubset(tree.columns):
        return {}
    return {
        str(row.code): str(row.label) if str(row.label).strip() else str(row.code)
        for row in tree[["code", "label"]].drop_duplicates("code").itertuples(index=False)
    }


def _paired_tree_html(
    summary: pd.DataFrame,
    tree: pd.DataFrame,
    source_system: str,
    mapped_components: pd.DataFrame,
    economy: str,
) -> str:
    """Render original raw tree beside its de-duplicated mapped frontier."""
    if summary.empty:
        return '<p class="empty-state">No failed anchor contexts for this dashboard economy.</p>'
    labels = _tree_label_lookup(tree)
    cards: list[str] = []
    for row in summary.head(12).itertuples(index=False):
        parent_label = labels.get(str(row.parent_code), str(row.parent_code))
        raw_children = "".join(
            '<li class="optional-zero" data-zero-child="true">' if float(value) == 0 else "<li>"
            + "<span>child: " + escape(labels.get(str(child), str(child))) + "</span>"
            f"<strong>{_three_significant_figures(float(value))}</strong></li>"
            for child, value in sorted(row.child_totals.items())
        )
        component_rows = mapped_components[
            (mapped_components["validation_axis"].astype(str) == str(row.validation_axis))
            & (mapped_components["other_axis_value"].astype(str) == str(row.other_axis_value))
            & (mapped_components["parent_code"].astype(str) == str(row.parent_code))
            & (mapped_components["economy"].astype(str).str.replace("_", "", regex=False) == economy)
        ].copy() if not mapped_components.empty else pd.DataFrame()
        if not component_rows.empty:
            component_rows["mapped_value"] = pd.to_numeric(component_rows["mapped_value"], errors="coerce").fillna(0.0)
            mapped_branches = []
            for component_key, group in component_rows.groupby(
                ["raw_child_code", "component_esto_flow", "component_esto_product", "common_row_id", "mapping_status"],
                dropna=False,
            ):
                raw_child, flow, product, common_id, status = component_key
                if str(status).startswith("missing_source_mapping"):
                    mapping_label = f"Missing source mapping: {labels.get(str(raw_child), str(raw_child))}"
                elif str(status) == "component_not_registered_in_common_esto":
                    mapping_label = f"Unregistered Common ESTO component: {flow} / {product}"
                else:
                    mapping_label = f"{labels.get(str(raw_child), str(raw_child))} → {flow} / {product}"
                mapped_value = float(group["mapped_value"].sum())
                optional_zero = ' class="optional-zero" data-zero-child="true"' if mapped_value == 0 and str(status).startswith("mapped") else ""
                mapped_branches.append(
                    f'<li{optional_zero}><span>{escape(mapping_label)}</span><strong>{_three_significant_figures(mapped_value)}</strong></li>'
                )
            mapped_branch_html = "".join(mapped_branches)
        else:
            mapped_branch_html = '<li><span>No resolved component detail is available.</span><strong>—</strong></li>'
        cards.append(
            f'<article class="paired-case"><h3>{escape(source_system)} | {escape(str(row.validation_axis))} | '
            f'{escape(str(row.other_axis_value))}</h3><p class="subtle">{escape(str(row.scenarios))}; checked years: '
            f'{escape(str(row.years))}. Values are signed sums; display rounding is 1–3 significant figures.</p>'
            '<div class="paired-trees">'
            '<section><h4>Original raw tree</h4><ul class="value-tree">'
            f'<li><span>Parent: {escape(parent_label)}</span><strong>{_three_significant_figures(float(row.parent_total))}</strong></li>'
            f'{raw_children}'
            f'<li class="tree-total"><span>Children sum</span><strong>{_three_significant_figures(float(row.children_total))}</strong></li>'
            f'<li class="tree-residual"><span>Raw residual (parent − children)</span><strong>{_three_significant_figures(float(row.raw_residual))}</strong></li>'
            '</ul></section>'
            '<section><h4>Same branch represented through mappings</h4><ul class="value-tree">'
            f'<li><span>Raw parent reference</span><strong>{_three_significant_figures(float(row.parent_total))}</strong></li>'
            f'{mapped_branch_html}'
            f'<li><span>Mapped Common ESTO frontier (de-duplicated)</span><strong>{_three_significant_figures(float(row.mapped_frontier_total))}</strong></li>'
            f'<li class="tree-residual"><span>Anchor difference (parent − frontier)</span><strong>{_three_significant_figures(float(row.mapped_difference))}</strong></li>'
            '</ul></section></div></article>'
        )
    return "".join(cards)


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
    economy: str = "",
) -> dict[str, str]:
    """Write one self-contained mapping diagnostics page and summary CSV."""
    results_root = mappings_root / "results"
    tree_root = results_root / "tree_structure"
    anchor_path = tree_root / "source_parent_anchor_validation.csv"
    anchor_child_values_path = tree_root / "source_parent_anchor_child_values.csv"
    anchor_child_context_values_path = tree_root / "source_parent_anchor_child_context_values.csv"
    anchor_mapped_component_context_values_path = tree_root / "source_parent_anchor_mapped_component_context_values.csv"
    stage_path = tree_root / "common_esto_validation.csv"
    partial_path = results_root / "common_esto" / "qa_common_esto_unresolved_partial_coverage.csv"
    unmapped_path = results_root / "common_esto" / "qa_nonzero_unmapped_leap_branches.csv"
    conflicts_path = results_root / "maintenance" / "leap_source_presence_conflicts.csv"
    coverage_path = results_root / "source_coverage" / "all_demand_aggregated_coverage_gaps.csv"

    anchor = _read_csv(anchor_path)
    anchor_child_values = _read_csv(anchor_child_values_path)
    anchor_child_context_values = _read_csv(anchor_child_context_values_path)
    anchor_mapped_component_context_values = _read_csv(anchor_mapped_component_context_values_path)
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
    dashboard_economy = str(economy).replace("_", "").strip()
    ninth_paired_summary = _paired_anchor_aggregate_summary(
        anchor_child_context_values, "NINTH", dashboard_economy
    )
    leap_paired_summary = _paired_anchor_aggregate_summary(
        anchor_child_context_values, "LEAP", dashboard_economy
    )
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
.paired-case {{ border-top:1px solid #d9e1ea; padding:18px 0; }} .paired-case:first-child {{ border-top:0; padding-top:0; }} .paired-trees {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }} .paired-trees section {{ background:#f7fafc; border:1px solid #d9e1ea; border-radius:8px; padding:12px; }} .paired-trees h4 {{ margin:0 0 8px; }} .value-tree {{ list-style:none; padding:0; margin:0; }} .value-tree li {{ display:flex; gap:12px; justify-content:space-between; padding:5px 0; border-bottom:1px solid #e5ebf1; }} .value-tree li:last-child {{ border-bottom:0; }} .value-tree strong {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} .tree-total {{ font-weight:600; }} .tree-residual {{ color:#9b1c1c; }} .optional-zero {{ display:none; }} body.show-zero-children .optional-zero {{ display:flex; }} .zero-toggle {{ display:block; margin:12px 0; }} @media (max-width:760px) {{ .paired-trees {{ grid-template-columns:1fr; }} }}
.table-scroll {{ overflow:auto; max-height:480px; }} table {{ border-collapse:collapse; width:100%; font-size:12px; }} th {{ position:sticky; top:0; background:#e8f0fa; }} th,td {{ border:1px solid #d9e1ea; padding:6px 8px; text-align:left; vertical-align:top; }} .table-note,.empty-state {{ color:#5f6b7a; font-size:13px; }} footer {{ margin:22px 0; font-size:12px; color:#5f6b7a; }} a {{ color:#1b5e9a; }}
</style></head><body><div class="shell"><header><a href="index.html">← Dashboard overview</a><h1>Mapping diagnostics</h1><p class="subtle">Read-only inspection of hierarchy/anchor validation and direct mapping coverage. Updated: {escape(dashboard_updated_label)}</p></header>
<div class="metrics">{cards}</div>
<section class="panel"><h2>How the anchor validator connects the hierarchies</h2><div class="flow"><div>Raw source parent</div><span class="arrow">→</span><div>Raw source child tree</div><span class="arrow">→</span><div>Mapped Common ESTO frontier</div><span class="arrow">→</span><div>Comparison values</div><span class="arrow">→</span><div>Passed / failed / skipped reason</div></div><p class="subtle">The tables below match each raw parent/children context to its branch-level summed absolute mismatch and rank. This makes the materiality ranking and the exact source evidence visible together.</p></section>
<section class="panel"><h2>Stage 3 hierarchy failures</h2>{_table_html(stage_summary, ['source_system','validation_axis','parent_code','rows'])}</section>
<section class="panel"><h2>Largest summed anchor mismatches</h2><p class="subtle">Parent and children totals are sums across all failed rows; net difference is parent minus children, while absolute mismatch does not allow opposite signs to cancel.</p>{_table_html(anchor_value_display, ['source_system','validation_axis','parent_code','failed_checks','parent_total','children_total','net_difference','absolute_mismatch_total'])}<h3>Failure reasons</h3>{_table_html(anchor_summary, ['source_system','validation_axis','reason','parent_code','rows'])}</section>
<label class="zero-toggle"><input id="show-zero-children" type="checkbox"> Show zero-value children and mapped components</label>
<section class="panel"><h2>NINTH: original tree vs mapped representation</h2><p class="subtle">Each case aggregates the validator's failed contexts across Reference and Target. The raw residual identifies a contradiction within the source tree; the right-hand tree lists the actual resolved Common ESTO components and visibly retains any missing mapping paths.</p>{_paired_tree_html(ninth_paired_summary, ninth_tree, 'NINTH', anchor_mapped_component_context_values, dashboard_economy)}</section>
<section class="panel"><h2>LEAP: original tree vs mapped representation</h2><p class="subtle">Each case aggregates the validator's failed contexts across its checked scenarios and years.</p>{_paired_tree_html(leap_paired_summary, leap_tree, 'LEAP', anchor_mapped_component_context_values, dashboard_economy)}</section>
<section class="panel"><h2>Direct mapping coverage review</h2><h3>Actionable partial coverage</h3>{_table_html(partial, ['source_system','comparison_scope','common_row_id','missing_component_pairs','relevance_evidence','mapping_action','mapping_sheet_to_review'])}<h3>Non-zero unmapped LEAP branches</h3>{_table_html(unmapped, ['leap_flow','leap_product','indirect_esto_flow','indirect_esto_product','qa_status'])}<h3>LEAP source-presence conflicts</h3>{_table_html(conflicts, ['leap_sector_name_full_path','raw_leap_fuel_name','presence_status','in_leap_combined_esto','in_leap_combined_ninth'])}<h3>Source-coverage audit summary</h3>{_table_html(coverage_summary, ['coverage_status','mapping_status','rows'])}</section>
<footer><strong>Artifact provenance</strong><br>{artifact_notes}<br>{escape(_artifact_note(anchor_child_values_path))}<br>{escape(_artifact_note(anchor_child_context_values_path))}<br>{escape(_artifact_note(anchor_mapped_component_context_values_path))}</footer></div><script>document.getElementById('show-zero-children').addEventListener('change', function () {{ document.body.classList.toggle('show-zero-children', this.checked); }});</script></body></html>"""
    output_path = layout["dashboards"] / DIAGNOSTIC_PAGE_NAME
    output_path.write_text(html, encoding="utf-8")
    return {"page": str(output_path), "summary": str(layout["supporting"] / "mapping_diagnostics_summary.csv")}


#%%
