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
TREE_VALIDATION_AXIS = "flow"

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


def _mapping_cardinality_diagnostics(
    source_to_common: pd.DataFrame,
    target_tree: pd.DataFrame,
    source_tree: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return both directions of source/target hierarchy overlap.

    Both checks use the structural source-to-Common-ESTO map rather than the
    explanatory parent/child routes shown in an anchor card.  That avoids
    labelling a legitimate raw parent and raw child as a duplicate merely
    because each maps to its corresponding target hierarchy level.
    """
    source_columns = ["source_system", "original_source_flow", "original_source_product"]
    required = set(source_columns + ["common_row_id", "common_flow_label", "common_product_label"])
    if source_to_common.empty or not required.issubset(source_to_common.columns):
        return pd.DataFrame(), pd.DataFrame()

    relations = source_to_common.drop_duplicates(source_columns + ["common_row_id"]).copy()
    source_counts = (
        relations.groupby(source_columns, dropna=False)["common_row_id"].nunique()
        .rename("mapped_target_count").reset_index()
    )
    fanout_keys = source_counts[source_counts["mapped_target_count"].gt(1)]
    fanout_relations = relations.merge(fanout_keys, on=source_columns, how="inner")
    target_counts = (
        relations.groupby(["source_system", "common_row_id"], dropna=False).size()
        .rename("mapped_source_count").reset_index()
    )

    parent_by_flow = (
        target_tree.set_index("code")["parent_code"].fillna("").astype(str).to_dict()
        if {"code", "parent_code"}.issubset(target_tree.columns) else {}
    )
    overlap_rows: list[dict[str, object]] = []
    for key, group in fanout_relations.groupby(source_columns, dropna=False, sort=False):
        targets = {
            (str(row.common_flow_label), str(row.common_product_label), str(row.common_row_id))
            for row in group.itertuples(index=False)
        }
        for flow, product, row_id in targets:
            ancestor = parent_by_flow.get(flow, "")
            while ancestor:
                ancestor_match = next(
                    (candidate for candidate in targets if candidate[0] == ancestor and candidate[1] == product),
                    None,
                )
                if ancestor_match is not None:
                    overlap_rows.append({
                        "source_system": key[0],
                        "source_flow": key[1],
                        "source_product": key[2],
                        "ancestor_target": f"{ancestor_match[0]} / {ancestor_match[1]}",
                        "descendant_target": f"{flow} / {product}",
                        "ancestor_common_row_id": ancestor_match[2],
                        "descendant_common_row_id": row_id,
                    })
                    break
                ancestor = parent_by_flow.get(ancestor, "")
    overlaps = pd.DataFrame(overlap_rows).drop_duplicates() if overlap_rows else pd.DataFrame()

    source_parent_by_system: dict[str, dict[str, str]] = {}
    if {"dataset", "code", "parent_code"}.issubset(source_tree.columns):
        for system, group in source_tree.groupby(source_tree["dataset"].astype(str).str.upper(), sort=False):
            source_parent_by_system[str(system)] = (
                group.set_index("code")["parent_code"].fillna("").astype(str).to_dict()
            )
    reverse_rows: list[dict[str, object]] = []
    target_fanin = relations.merge(
        target_counts[target_counts["mapped_source_count"].gt(1)],
        on=["source_system", "common_row_id"], how="inner",
    )
    for key, group in target_fanin.groupby(
        ["source_system", "common_row_id", "original_source_product"], dropna=False, sort=False,
    ):
        system, common_row_id, source_product = key
        parent_by_source_flow = source_parent_by_system.get(str(system), {})
        source_flows = set(group["original_source_flow"].astype(str))
        for source_flow in source_flows:
            ancestor = parent_by_source_flow.get(source_flow, "")
            while ancestor:
                if ancestor in source_flows:
                    first = group.iloc[0]
                    reverse_rows.append({
                        "source_system": system,
                        "common_target": f"{first.common_flow_label} / {first.common_product_label}",
                        "common_row_id": common_row_id,
                        "source_product": source_product,
                        "source_parent": ancestor,
                        "source_descendant": source_flow,
                    })
                    break
                ancestor = parent_by_source_flow.get(ancestor, "")
    source_overlaps = pd.DataFrame(reverse_rows).drop_duplicates() if reverse_rows else pd.DataFrame()
    return overlaps, source_overlaps


def _three_significant_figures(value: float) -> str:
    """Format a number to three significant figures without unnecessary scientific notation."""
    if pd.isna(value) or value == 0:
        return "0"
    decimals = 2 - floor(log10(abs(value)))
    rounded = round(value, decimals)
    if decimals <= 0:
        return f"{rounded:,.0f}"
    return f"{rounded:,.{decimals}f}"


def _context_value_formatter(values: list[float]) -> tuple[str, callable]:
    """Return one readable scale for a whole anchor case, not per-value rounding.

    A shared scale keeps displayed siblings additive. Six decimal places after
    scaling preserve useful source precision while avoiding floating-point noise.
    """
    magnitude = max((abs(float(value)) for value in values), default=0.0)
    if magnitude >= 1_000_000:
        divisor, label = 1_000_000.0, "Values in millions (×1,000,000)"
    elif magnitude >= 1_000:
        divisor, label = 1_000.0, "Values in thousands (×1,000)"
    else:
        divisor, label = 1.0, "Values in original units"

    def format_value(value: float) -> str:
        scaled = float(value) / divisor
        if scaled == 0:
            return "0"
        return f"{scaled:,.6f}".rstrip("0").rstrip(".")

    return label, format_value


def _mapped_target_structure_html(
    component_rows: pd.DataFrame,
    target_tree: pd.DataFrame,
    source_parent_label: str,
    formatter: callable,
    expected_total: float,
) -> tuple[str, str, bool]:
    """Show a real target hierarchy or an honest direct fan-out.

    The target hierarchy is only drawn when mapped rows themselves have a real
    ESTO parent/child relationship. Mapping routes from source parent/children
    are deliberately not used as hierarchy edges.
    """
    mapped = component_rows[
        component_rows["mapping_status"].astype(str).str.startswith("mapped")
        & component_rows["common_row_id"].astype(str).ne("")
    ].copy()
    if mapped.empty:
        return (
            '<li><span>No mapped Common ESTO rows are available.</span><strong>—</strong></li>',
            "",
            expected_total == 0,
        )

    identity_columns = [
        "comparison_scope", "economy", "scenario", "year", "common_row_id",
        "component_esto_flow", "component_esto_product",
    ]
    mapped = mapped.drop_duplicates(identity_columns)
    targets = (
        mapped.groupby(["common_row_id", "component_esto_flow", "component_esto_product"], dropna=False)["mapped_value"]
        .sum()
        .reset_index()
    )
    targets["component_esto_flow"] = targets["component_esto_flow"].astype(str)
    targets["component_esto_product"] = targets["component_esto_product"].astype(str)
    target_keys = set(zip(targets["component_esto_flow"], targets["component_esto_product"]))
    parent_by_flow = (
        target_tree.set_index("code")["parent_code"].fillna("").astype(str).to_dict()
        if {"code", "parent_code"}.issubset(target_tree.columns) else {}
    )
    has_mapped_ancestor = False
    for flow, product in target_keys:
        ancestor = parent_by_flow.get(flow, "")
        while ancestor:
            if (ancestor, product) in target_keys:
                has_mapped_ancestor = True
                break
            ancestor = parent_by_flow.get(ancestor, "")
    display_keys = set(target_keys)
    structural_keys: set[tuple[str, str]] = set()
    if has_mapped_ancestor:
        for flow, product in target_keys:
            ancestor = parent_by_flow.get(flow, "")
            while ancestor and (ancestor, product) not in display_keys:
                display_keys.add((ancestor, product))
                structural_keys.add((ancestor, product))
                ancestor = parent_by_flow.get(ancestor, "")
    hierarchy_children: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for flow, product in display_keys:
        parent = parent_by_flow.get(flow, "")
        if (parent, product) in display_keys:
            hierarchy_children.setdefault((parent, product), []).append((flow, product))
    has_hierarchy = has_mapped_ancestor
    target_values = (
        targets.groupby(["component_esto_flow", "component_esto_product"], dropna=False)["mapped_value"]
        .sum().to_dict()
    )
    detail_matches_total = abs(sum(target_values.values()) - expected_total) <= 1e-6 * max(abs(expected_total), 1.0)

    def target_item(key: tuple[str, str], *, child: bool = False) -> str:
        flow, product = key
        prefix = "└─ " if child else ""
        if key in structural_keys:
            return (
                f'<li class="tree-structural"><span>{escape(prefix + flow + " / " + product + " (structure only)")}</span>'
                '<strong>—</strong></li>'
            )
        return (
            f'<li><span>{escape(prefix + flow + " / " + product)}</span>'
            f'<strong>{formatter(float(target_values[key]))}</strong></li>'
        )

    if has_hierarchy:
        roots = sorted(key for key in display_keys if key not in {child for children in hierarchy_children.values() for child in children})
        body = '<li class="tree-category"><span>Mapped Common ESTO hierarchy</span></li>'
        def render_node(key: tuple[str, str], depth: int = 0) -> str:
            item = target_item(key, child=depth > 0)
            return item + "".join(
                render_node(child, depth + 1)
                for child in sorted(hierarchy_children.get(key, []))
            )
        for root in roots:
            body += render_node(root)
        note = (
            '<p class="helper-note">Mapped target hierarchy: only Common ESTO parent/child relationships '
            'are shown. “Structure only” nodes provide context and are not included in the mapped total.</p>'
        )
        return body, note, detail_matches_total

    body = '<li class="tree-category"><span>Direct mapping fan-out</span></li>'
    for key in sorted(target_keys):
        body += target_item(key)
    note = (
        '<p class="helper-note">No mapped Common ESTO parent/child roll-up exists for this source parent. '
        f'{escape(source_parent_label)} maps directly to these target rows.</p>'
    )
    return body, note, detail_matches_total


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


def _reviewed_anchor_exceptions(anchor: pd.DataFrame, economy: str) -> pd.DataFrame:
    """Show reviewed source-data exceptions that were skipped, not hidden."""
    required = {"status", "known_data_quality_exception"}
    if anchor.empty or not required.issubset(anchor.columns):
        return pd.DataFrame()
    flagged = anchor[
        anchor["status"].astype(str).eq("skipped")
        & anchor["known_data_quality_exception"].astype(str).str.lower().eq("true")
    ].copy()
    if economy and "economy" in flagged.columns:
        flagged = flagged[
            flagged["economy"].astype(str).str.replace("_", "", regex=False).eq(economy)
        ]
    columns = [
        "source_system", "validation_axis", "parent_code", "other_axis_value", "economy",
        "scenario", "year", "parent_value", "reason", "exception_resolution",
        "data_quality_exception_notes",
    ]
    return flagged.loc[:, [column for column in columns if column in flagged.columns]]


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
        & context_values["validation_axis"].astype(str).eq(TREE_VALIDATION_AXIS)
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
    target_tree: pd.DataFrame,
    source_system: str,
    mapped_components: pd.DataFrame,
    economy: str,
) -> str:
    """Render a source tree beside a genuine Common ESTO hierarchy or fan-out."""
    if summary.empty:
        return '<p class="empty-state">No failed anchor contexts for this dashboard economy.</p>'
    labels = _tree_label_lookup(tree)
    manual_rollup_codes = (
        set(tree.loc[tree["is_subtotal"].astype(str).str.lower().eq("true"), "code"].astype(str))
        if source_system == "LEAP" and "is_subtotal" in tree.columns else set()
    )
    cards: list[str] = []
    for row in summary.head(12).itertuples(index=False):
        parent_label = labels.get(str(row.parent_code), str(row.parent_code))
        scale_label, format_value = _context_value_formatter([
            float(row.parent_total), float(row.children_total), float(row.raw_residual),
            float(row.mapped_frontier_total), float(row.mapped_difference),
            *[float(value) for value in row.child_totals.values()],
        ])
        raw_children = "".join(
            ('<li class="optional-zero" data-zero-child="true">' if float(value) == 0 else "<li>")
            + "<span>" + escape(labels.get(str(child), str(child))) + "</span>"
            + f"<strong>{format_value(float(value))}</strong></li>"
            for child, value in sorted(row.child_totals.items())
        )
        component_rows = mapped_components[
            (mapped_components["validation_axis"].astype(str) == str(row.validation_axis))
            & (mapped_components["other_axis_value"].astype(str) == str(row.other_axis_value))
            & (mapped_components["parent_code"].astype(str) == str(row.parent_code))
            & (mapped_components["economy"].astype(str).str.replace("_", "", regex=False) == economy)
        ].copy() if not mapped_components.empty else pd.DataFrame()
        if not component_rows.empty and "comparison_scope" in component_rows.columns:
            component_scope_keys = ["validation_axis", "economy", "scenario", "year", "other_axis_value", "parent_code"]
            component_rows["_scope_priority"] = component_rows["comparison_scope"].map(SCOPE_PRIORITY).fillna(99)
            component_rows = component_rows[
                component_rows["_scope_priority"].eq(
                    component_rows.groupby(component_scope_keys, dropna=False)["_scope_priority"].transform("min")
                )
            ].drop(columns="_scope_priority")
        if not component_rows.empty:
            component_rows["mapped_value"] = pd.to_numeric(component_rows["mapped_value"], errors="coerce").fillna(0.0)
            mapped_branch_html, mapped_structure_note, detail_matches_total = _mapped_target_structure_html(
                component_rows, target_tree, parent_label, format_value, float(row.mapped_frontier_total),
            )
        else:
            mapped_branch_html = '<li><span>No resolved component detail is available.</span><strong>—</strong></li>'
            mapped_structure_note = ""
            detail_matches_total = float(row.mapped_frontier_total) == 0
        displayed_mapped_total = 0.0
        if not component_rows.empty:
            displayed_rows = component_rows[
                component_rows["mapping_status"].astype(str).str.startswith("mapped")
                & component_rows["common_row_id"].astype(str).ne("")
            ].copy()
            if not displayed_rows.empty:
                identity_columns = [
                    "comparison_scope", "economy", "scenario", "year", "common_row_id",
                    "component_esto_flow", "component_esto_product",
                ]
                displayed_mapped_total = float(
                    displayed_rows.drop_duplicates(identity_columns)["mapped_value"].sum()
                )
        raw_rollup_note = (
            '<p class="helper-note">Manual LEAP roll-up: this constructed subtotal is compared with its immediate source-tree children.</p>'
            if str(row.parent_code) in manual_rollup_codes else ""
        )
        source_warning = (
            '<p class="source-warning">Source-data warning: the raw parent is 0 while its children sum to a non-zero value. '
            'This is a contradiction within the original source hierarchy, not evidence that a mapping row is missing.</p>'
            if float(row.parent_total) == 0 and float(row.children_total) != 0 else ""
        )
        cards.append(
            f'<article class="paired-case"><h3>{escape(source_system)} | {escape(str(row.validation_axis))} | '
            f'{escape(str(row.other_axis_value))}</h3><p class="subtle">{escape(str(row.scenarios))}; checked years: '
            f'{escape(str(row.years))}. {escape(scale_label)}. Calculations use unrounded values.</p>'
            '<div class="paired-trees">'
            '<section><h4>Original raw source tree</h4><ul class="value-tree">'
            '<li class="tree-category"><span>Original source parent</span></li>'
            f'<li><span>{escape(parent_label)}</span><strong>{format_value(float(row.parent_total))}</strong></li>'
            '<li class="tree-category"><span>Original source children</span></li>'
            f'{raw_children}'
            f'<li class="tree-total"><span>Children sum</span><strong>{format_value(float(row.children_total))}</strong></li>'
            f'<li class="tree-residual"><span>Raw residual (parent − children)</span><strong>{format_value(float(row.raw_residual))}</strong></li>'
            f'</ul>{raw_rollup_note}{source_warning}</section>'
            '<section><h4>Mapped Common ESTO representation</h4><ul class="value-tree">'
            f'{mapped_branch_html}'
            f'<li class="tree-total"><span>{"Unique mapped comparison total" if detail_matches_total else "Validator mapped total (detail incomplete)"}</span><strong>{format_value(float(row.mapped_frontier_total))}</strong></li>'
            f'<li class="tree-residual"><span>Anchor difference (parent − mapped total)</span><strong>{format_value(float(row.mapped_difference))}</strong></li>'
            f'</ul>{mapped_structure_note}{"" if detail_matches_total else f"<p class=\"source-warning\">The mapped rows shown above add to {format_value(displayed_mapped_total)}, but the validator used {format_value(float(row.mapped_frontier_total))}. The unshown contribution is {format_value(float(row.mapped_frontier_total) - displayed_mapped_total)}. Do not use this card to diagnose the anchor difference until that contribution is listed.</p>"}</section></div></article>'
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


def _transformation_rollup_diagram_html(
    common_esto_tree: pd.DataFrame,
    rollup_catalogue: pd.DataFrame,
) -> str:
    """Render mapping-owned 09 transformation tree and rollup boundaries."""
    required = {"source_system", "rollup_mode", "rolled_flow_label", "input_flow"}
    if common_esto_tree.empty or rollup_catalogue.empty or not required.issubset(rollup_catalogue.columns):
        return '<p class="empty-state">Current transformation-tree or rollup-catalogue artifacts are unavailable.</p>'

    tree = common_esto_tree[common_esto_tree["axis"].astype(str).eq("flow")].copy()
    ordinary_parent = "09 Total transformation sector"
    ordinary_children = tree[
        tree["parent_code"].fillna("").astype(str).eq(ordinary_parent)
    ].sort_values("code", kind="mergesort")
    catalogue = rollup_catalogue[
        rollup_catalogue["source_system"].astype(str).eq("ESTO")
        & rollup_catalogue["rolled_flow_label"].astype(str).str.startswith("09")
    ].copy()
    if ordinary_children.empty and catalogue.empty:
        return '<p class="empty-state">No ESTO 09-transformation rollup boundaries are registered.</p>'

    ordinary_html = "".join(
        f'<li><span class="solid-edge">→</span>{escape(str(row.code))}</li>'
        for row in ordinary_children.itertuples(index=False)
    ) or '<li class="empty-state">No ordinary children found.</li>'
    boundary_cards: list[str] = []
    boundary_id_column = "rollup_id" if "rollup_id" in catalogue.columns else "non_expanding_rollup_id"
    for boundary_id, group in catalogue.groupby(boundary_id_column, dropna=False, sort=True):
        first = group.iloc[0]
        label = str(first["rolled_flow_label"])
        mode = str(first["rollup_mode"])
        contributors = sorted(set(group["input_flow"].dropna().astype(str)) - {"", "nan"})
        registered_children = tree[
            tree["parent_code"].fillna("").astype(str).eq(label)
        ].sort_values("code", kind="mergesort")
        children_html = "".join(
            f'<li><span class="solid-edge">→</span>{escape(str(row.code))}</li>'
            for row in registered_children.itertuples(index=False)
        ) or '<li class="muted">No registered ordinary children.</li>'
        contributor_html = "".join(
            f'<li>{escape(contributor)} <span class="dashed-edge">⋯→</span></li>'
            for contributor in contributors
        )
        mode_explanation = (
            "This boundary is not folded back into an ordinary ancestor total."
            if mode == "DETACHED"
            else "This boundary can support ordinary ancestor/frontier resolution."
        )
        boundary_cards.append(
            f'<article class="rollup-boundary {escape(mode.lower())}">'
            f'<h3><span class="mode-pill">{escape(mode)}</span> {escape(label)}</h3>'
            '<div class="boundary-columns"><div><h4>Dashed composition inputs</h4>'
            f'<ul>{contributor_html}</ul></div><div><h4>Solid registered children</h4>'
            f'<ul>{children_html}</ul></div></div>'
            f'<p class="helper-note">{escape(mode_explanation)}</p>'
            f'<p class="artifact-id">{escape(str(boundary_id))}</p></article>'
        )
    return (
        '<div class="transformation-diagram">'
        '<section class="ordinary-hierarchy"><h3>Ordinary hierarchy</h3>'
        f'<div class="tree-root">{escape(ordinary_parent)}</div><ul>{ordinary_html}</ul></section>'
        '<section class="rollup-boundaries"><h3>Registered rollup boundaries</h3>'
        '<p class="subtle">Solid arrows are ordinary tree edges. Dotted arrows are rollup composition, not additive tree edges.</p>'
        f'{"".join(boundary_cards)}</section></div>'
    )


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
    leaf_reconciliation_candidates_path = tree_root / "source_parent_anchor_leaf_reconciliation_candidates.csv"
    stage_path = tree_root / "common_esto_validation.csv"
    partial_path = results_root / "common_esto" / "qa_common_esto_unresolved_partial_coverage.csv"
    unmapped_path = results_root / "common_esto" / "qa_nonzero_unmapped_leap_branches.csv"
    conflicts_path = results_root / "maintenance" / "leap_source_presence_conflicts.csv"
    coverage_path = results_root / "source_coverage" / "all_demand_aggregated_coverage_gaps.csv"
    source_to_common_path = results_root / "common_esto" / "structural_artifacts" / "source_pair_to_common_row.csv"
    many_to_many_path = results_root / "maintenance" / "many_to_many_conflicts.csv"
    rollup_catalogue_path = results_root / "mapping_relationships" / "rollup_edges.csv"
    if not rollup_catalogue_path.exists():
        rollup_catalogue_path = results_root / "mapping_relationships" / "non_expanding_rollups.csv"

    anchor = _read_csv(anchor_path)
    anchor_child_values = _read_csv(anchor_child_values_path)
    anchor_child_context_values = _read_csv(anchor_child_context_values_path)
    anchor_mapped_component_context_values = _read_csv(anchor_mapped_component_context_values_path)
    leaf_reconciliation_candidates = _read_csv(leaf_reconciliation_candidates_path)
    stage = _read_csv(stage_path)
    ninth_tree = _read_csv(tree_root / "ninth_tree.csv")
    leap_tree = _read_csv(tree_root / "leap_tree.csv")
    common_esto_tree = _read_csv(tree_root / "common_esto_tree.csv")
    source_tree = _read_csv(tree_root / "all_dataset_trees.csv")
    partial = _read_csv(partial_path)
    unmapped = _read_csv(unmapped_path)
    conflicts = _read_csv(conflicts_path)
    coverage = _read_csv(coverage_path)
    source_to_common = _read_csv(source_to_common_path)
    many_to_many = _read_csv(many_to_many_path)
    rollup_catalogue = _read_csv(rollup_catalogue_path)
    transformation_rollup_diagram = _transformation_rollup_diagram_html(
        common_esto_tree, rollup_catalogue
    )

    stage_summary = _failure_summary(stage, ["source_system", "validation_axis", "parent_code"])
    anchor_summary = _failure_summary(anchor, ["source_system", "validation_axis", "reason", "parent_code"])
    anchor_value_summary = _anchor_value_summary(anchor)
    dashboard_economy = str(economy).replace("_", "").strip()
    reviewed_anchor_exceptions = _reviewed_anchor_exceptions(anchor, dashboard_economy)
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
    target_ancestor_overlaps, source_ancestor_overlaps = _mapping_cardinality_diagnostics(
        source_to_common, common_esto_tree, source_tree,
    )
    cardinality_sections = ""
    if not target_ancestor_overlaps.empty:
        cardinality_sections += (
            '<h3>Mapped target ancestor overlaps</h3>'
            '<p class="subtle">A single source pair reaches both a Common ESTO target row and one of its '
            'descendants. Review these as potential double-counting routes.</p>'
            + _table_html(target_ancestor_overlaps, [
                "source_system", "source_flow", "source_product", "ancestor_target", "descendant_target",
            ])
        )
    if not source_ancestor_overlaps.empty:
        cardinality_sections += (
            '<h3>Source parent and child mapped to one target</h3>'
            '<p class="subtle">One Common ESTO target is reached by both a source parent and its descendant. '
            'This can be intentional aggregation, but review it before treating both routes as additive.</p>'
            + _table_html(source_ancestor_overlaps, [
                "source_system", "common_target", "source_product", "source_parent", "source_descendant",
            ])
        )
    if not many_to_many.empty:
        cardinality_sections += (
            '<h3>Active many-to-many mapping conflicts</h3>'
            '<p class="subtle">These active workbook mappings have multiple targets for a source and multiple '
            'sources for a target. They require an explicit modelling decision.</p>'
            + _table_html(many_to_many, [
                "sheet", "leap_sector_name_full_path", "raw_leap_fuel_name", "ninth_sector", "ninth_fuel",
                "n_targets_for_source", "n_sources_for_target", "cardinality",
            ])
        )
    summary = pd.DataFrame([
        {"metric": "Stage 3 failed hierarchy checks", "rows": int(len(stage[stage.get("status", "").astype(str).eq("failed")])) if not stage.empty else 0},
        {"metric": "Failed anchor checks", "rows": int(len(anchor[anchor.get("status", "").astype(str).eq("failed")])) if not anchor.empty else 0},
        {"metric": "Reviewed anchor exceptions (skipped but flagged)", "rows": int(len(reviewed_anchor_exceptions))},
        {"metric": "Leaf-reconciliation exception candidates", "rows": int(len(leaf_reconciliation_candidates))},
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
    artifact_notes = "<br>".join(escape(_artifact_note(path)) for path in [anchor_path, stage_path, partial_path, unmapped_path, conflicts_path, coverage_path, source_to_common_path, many_to_many_path])
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapping diagnostics</title><style>
body {{ font-family: Inter,Segoe UI,Arial,sans-serif; margin:0; background:#f4f6f8; color:#172033; }}
.shell {{ max-width:1600px; margin:auto; padding:20px; }} header {{ background:white; border:1px solid #d9e1ea; border-radius:12px; padding:18px 22px; }}
h1,h2,h3 {{ margin:0 0 10px; }} h2 {{ margin-top:28px; }} .subtle {{ color:#5f6b7a; }} .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:16px 0; }}
.metric-card,.panel {{ background:white; border:1px solid #d9e1ea; border-radius:10px; padding:14px; }} .metric-card span {{ display:block; color:#5f6b7a; font-size:13px; }} .metric-card strong {{ font-size:28px; }} .collapsed-panel summary {{ cursor:pointer; display:flex; align-items:center; justify-content:space-between; }} .collapsed-panel summary h2 {{ margin:0; }} .collapsed-panel summary span {{ color:#1b5e9a; font-size:0; }} .collapsed-panel[open] summary span::after {{ content:'Hide'; font-size:13px; }} .collapsed-panel:not([open]) summary span::after {{ content:'Show'; font-size:13px; }} .collapsed-panel > div {{ margin-top:14px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(480px,1fr)); gap:16px; }} .guide-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:10px; }} .guide-card {{ border-radius:8px; padding:10px; font-size:13px; line-height:1.4; }} .guide-card strong {{ display:block; margin-bottom:3px; }} .guide-good {{ background:#e8f5e9; color:#176b35; }} .guide-warning {{ background:#fff4e5; color:#8a4b08; }} .guide-neutral {{ background:#e8f0fa; color:#294f78; }} .flow {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:12px 0; }} .flow div {{ background:#e8f0fa; border:1px solid #adc4df; border-radius:8px; padding:10px; font-size:13px; }} .arrow {{ color:#53718f; font-size:22px; }}
.paired-case {{ border-top:1px solid #d9e1ea; padding:18px 0; }} .paired-case:first-child {{ border-top:0; padding-top:0; }} .paired-trees {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }} .paired-trees section {{ background:#f7fafc; border:1px solid #d9e1ea; border-radius:8px; padding:12px; }} .paired-trees h4 {{ margin:0 0 8px; }} .value-tree {{ list-style:none; padding:0; margin:0; }} .value-tree li {{ display:flex; gap:12px; justify-content:space-between; padding:5px 0; border-bottom:1px solid #e5ebf1; }} .value-tree li:last-child {{ border-bottom:0; }} .value-tree strong {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} .value-tree li.tree-category {{ display:block; border-bottom:0; color:#5f6b7a; font-size:12px; font-weight:600; padding-top:10px; }} .value-tree li.tree-structural {{ color:#5f6b7a; font-style:italic; }} .tree-total {{ font-weight:600; }} .tree-residual {{ color:#9b1c1c; }} .helper-note,.source-warning {{ font-size:12px; line-height:1.4; margin:10px 0 0; padding:8px; border-radius:6px; }} .helper-note {{ background:#e8f5e9; color:#176b35; }} .source-warning {{ background:#fff4e5; color:#8a4b08; }} .value-tree li.optional-zero {{ display:none; }} body.show-zero-children .value-tree li.optional-zero {{ display:flex; }} .zero-toggle {{ display:block; margin:12px 0; }} @media (max-width:760px) {{ .paired-trees {{ grid-template-columns:1fr; }} }}
.transformation-diagram {{ display:grid; grid-template-columns:minmax(260px,0.8fr) minmax(520px,2fr); gap:16px; }} .ordinary-hierarchy,.rollup-boundaries {{ background:#f7fafc; border:1px solid #d9e1ea; border-radius:8px; padding:12px; }} .ordinary-hierarchy h3,.rollup-boundaries h3,.rollup-boundary h3,.rollup-boundary h4 {{ margin:0 0 8px; }} .tree-root {{ background:#dceaf8; border:1px solid #8eb2d4; border-radius:6px; font-weight:600; padding:8px; }} .ordinary-hierarchy ul,.rollup-boundary ul {{ list-style:none; padding-left:12px; margin:8px 0; }} .ordinary-hierarchy li,.rollup-boundary li {{ margin:5px 0; }} .solid-edge {{ color:#2d6a9f; font-weight:700; margin-right:4px; }} .dashed-edge {{ color:#7c5b00; font-weight:700; margin-left:6px; }} .rollup-boundary {{ border:1px solid #d9e1ea; border-left:5px solid #3d7fb1; border-radius:8px; padding:10px; margin-top:10px; background:#fff; }} .rollup-boundary.detached {{ border-left-color:#9b5c00; background:#fffaf0; }} .mode-pill {{ display:inline-block; font-size:11px; padding:2px 6px; border-radius:999px; background:#dceaf8; color:#174b73; }} .detached .mode-pill {{ background:#ffe7ba; color:#754300; }} .boundary-columns {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; font-size:13px; }} .artifact-id {{ margin:8px 0 0; color:#5f6b7a; font-family:ui-monospace,monospace; font-size:11px; }} @media (max-width:760px) {{ .paired-trees,.transformation-diagram,.boundary-columns {{ grid-template-columns:1fr; }} }}
.table-scroll {{ overflow:auto; max-height:480px; }} table {{ border-collapse:collapse; width:100%; font-size:12px; }} th {{ position:sticky; top:0; background:#e8f0fa; }} th,td {{ border:1px solid #d9e1ea; padding:6px 8px; text-align:left; vertical-align:top; }} .table-note,.empty-state {{ color:#5f6b7a; font-size:13px; }} footer {{ margin:22px 0; font-size:12px; color:#5f6b7a; }} a {{ color:#1b5e9a; }}
</style></head><body><div class="shell"><header><a href="index.html">← Dashboard overview</a><h1>Mapping diagnostics</h1><p class="subtle">Read-only inspection of hierarchy/anchor validation and direct mapping coverage. Updated: {escape(dashboard_updated_label)}</p></header>
<section class="panel"><h2>How to read a hierarchy case</h2><div class="guide-grid"><div class="guide-card guide-good"><strong>Manual LEAP roll-up</strong>Only constructed LEAP subtotal branches receive this label; they are compared with their immediate source-tree children.</div><div class="guide-card guide-good"><strong>One-to-many fan-out</strong>One raw parent can reach several ESTO components. Those routes are not additional source-tree parents.</div><div class="guide-card guide-neutral"><strong>De-duplicated frontier</strong>Mapped component rows can overlap. The frontier counts each Common ESTO row once, so do not add the displayed component rows.</div><div class="guide-card guide-warning"><strong>Raw source contradiction</strong>If a raw parent is 0 while its children are non-zero, the original source hierarchy disagrees with itself. It is not, by itself, a missing mapping.</div></div></section>
<div class="metrics">{cards}</div>
<section class="panel"><h2>How the anchor validator connects the hierarchies</h2><div class="flow"><div>Raw source parent</div><span class="arrow">→</span><div>Raw source child tree</div><span class="arrow">→</span><div>Mapped Common ESTO frontier</div><span class="arrow">→</span><div>Comparison values</div><span class="arrow">→</span><div>Passed / failed / skipped reason</div></div><p class="subtle">The tables below match each raw parent/children context to its branch-level summed absolute mismatch and rank. This makes the materiality ranking and the exact source evidence visible together.</p></section>
<section class="panel"><h2>09 transformation rollup boundaries</h2><p class="subtle">Automatically rendered from the Common ESTO tree and the mapping-owned compiled non-expanding rollup catalogue. It keeps ordinary hierarchy edges and comparison-boundary composition visibly distinct.</p>{transformation_rollup_diagram}</section>
<details class="panel collapsed-panel"><summary><h2>Stage 3 hierarchy failures</h2><span></span></summary><div>{_table_html(stage_summary, ['source_system','validation_axis','parent_code','rows'])}</div></details>
<details class="panel collapsed-panel"><summary><h2>Largest summed anchor mismatches</h2><span></span></summary><div><p class="subtle">Parent and children totals are sums across all failed rows; net difference is parent minus children, while absolute mismatch does not allow opposite signs to cancel.</p>{_table_html(anchor_value_display, ['source_system','validation_axis','parent_code','failed_checks','parent_total','children_total','net_difference','absolute_mismatch_total'])}<h3>Failure reasons</h3>{_table_html(anchor_summary, ['source_system','validation_axis','reason','parent_code','rows'])}</div></details>
<details class="panel collapsed-panel"><summary><h2>Reviewed source-hierarchy exceptions</h2><span></span></summary><div><p class="subtle">These are known source-data conditions from the exception workbook. They are skipped from actionable anchor failures but remain visible here with their review notes.</p>{_table_html(reviewed_anchor_exceptions, ['source_system','validation_axis','parent_code','other_axis_value','economy','scenario','year','parent_value','reason','exception_resolution','data_quality_exception_notes'])}<h3>Leaf-reconciliation candidates awaiting review</h3><p class="subtle">These are not exceptions yet. Their immediate children do not reconcile, while their descendant leaves do; review before copying an enabled row into <code>source_mismatch_allowed</code>.</p>{_table_html(leaf_reconciliation_candidates, ['source_system','validation_axis','parent_code','other_axis_value','economy','scenario','year','parent_value','direct_children_sum','leaf_descendants_sum','candidate_classification','notes'])}</div></details>
<label class="zero-toggle"><input id="show-zero-children" type="checkbox" autocomplete="off" onchange="document.body.classList.toggle('show-zero-children', this.checked)"> Show zero-value children and mapped components</label>
<section class="panel"><h2>NINTH flow tree: original vs mapped representation</h2><p class="subtle">The right side uses the Common ESTO hierarchy, including structure-only ancestors where needed; otherwise it shows a direct fan-out.</p>{_paired_tree_html(ninth_paired_summary, ninth_tree, common_esto_tree, 'NINTH', anchor_mapped_component_context_values, dashboard_economy)}</section>
<section class="panel"><h2>LEAP flow tree: original vs mapped representation</h2><p class="subtle">The right side uses the Common ESTO hierarchy, including structure-only ancestors where needed; otherwise it shows a direct fan-out.</p>{_paired_tree_html(leap_paired_summary, leap_tree, common_esto_tree, 'LEAP', anchor_mapped_component_context_values, dashboard_economy)}</section>
<details class="panel collapsed-panel"><summary><h2>Direct mapping coverage review</h2><span></span></summary><div><h3>Actionable partial coverage</h3>{_table_html(partial, ['source_system','comparison_scope','common_row_id','missing_component_pairs','relevance_evidence','mapping_action','mapping_sheet_to_review'])}<h3>Non-zero unmapped LEAP branches</h3>{_table_html(unmapped, ['leap_flow','leap_product','indirect_esto_flow','indirect_esto_product','qa_status'])}<h3>LEAP source-presence conflicts</h3>{_table_html(conflicts, ['leap_sector_name_full_path','raw_leap_fuel_name','presence_status','in_leap_combined_esto','in_leap_combined_ninth'])}<h3>Source-coverage audit summary</h3>{_table_html(coverage_summary, ['coverage_status','mapping_status','rows'])}{cardinality_sections}</div></details>
<footer><strong>Artifact provenance</strong><br>{artifact_notes}<br>{escape(_artifact_note(anchor_child_values_path))}<br>{escape(_artifact_note(anchor_child_context_values_path))}<br>{escape(_artifact_note(anchor_mapped_component_context_values_path))}<br>{escape(_artifact_note(leaf_reconciliation_candidates_path))}</footer></div></body></html>"""
    output_path = layout["dashboards"] / DIAGNOSTIC_PAGE_NAME
    output_path.write_text(html, encoding="utf-8")
    return {"page": str(output_path), "summary": str(layout["supporting"] / "mapping_diagnostics_summary.csv")}


#%%
