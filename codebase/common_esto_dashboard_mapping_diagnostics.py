#%%
"""Render read-only mapping and hierarchy diagnostics beside the dashboard.

This module deliberately reads QA artifacts produced by leap_mappings. It does
not infer mappings, modify workbooks, or change validation status semantics.
"""

from __future__ import annotations

from html import escape
import json
from math import floor, log10
from pathlib import Path

import pandas as pd

from codebase.mapping_diagnostics_contract import (
    load_mapping_diagnostics_contract,
)


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


def prefer_compressed_csv_path(path: Path) -> Path:
    """Prefer a gzip CSV and fall back to the legacy plain CSV when needed."""
    candidate = Path(path)
    if candidate.name.lower().endswith(".csv.gz"):
        if candidate.exists():
            return candidate
        plain_path = candidate.with_suffix("")
        if plain_path.exists():
            return plain_path
    elif candidate.name.lower().endswith(".csv"):
        compressed_path = candidate.with_name(f"{candidate.name}.gz")
        if compressed_path.exists():
            return compressed_path
    return candidate


def load_esto_exact_values_for_economy(
    esto_exact_rows_path: Path,
    economy: str,
    min_year: int | None = None,
    max_year: int | None = None,
    source_system: str = "ESTO_RAW",
) -> pd.DataFrame:
    """Read one raw ESTO slice needed to explain rollup components."""
    esto_exact_rows_path = prefer_compressed_csv_path(esto_exact_rows_path)
    columns = ["economy", "esto_flow", "year", "value", "scenario"]
    economy_key = str(economy).replace("_", "")
    selected_chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(esto_exact_rows_path, usecols=columns, chunksize=250_000):
        selected = chunk[chunk["economy"].astype(str).str.replace("_", "", regex=False).eq(economy_key)].copy()
        if min_year is not None:
            selected = selected[selected["year"] >= min_year]
        if max_year is not None:
            selected = selected[selected["year"] <= max_year]
        if not selected.empty:
            selected_chunks.append(selected)
    if not selected_chunks:
        return pd.DataFrame(columns=["source_system", "scenario", "year", "common_flow_label", "value"])
    result = pd.concat(selected_chunks, ignore_index=True).rename(columns={"esto_flow": "common_flow_label"})
    result["source_system"] = source_system
    return result[["source_system", "scenario", "year", "common_flow_label", "value"]]


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

    ordinary_child_codes = ordinary_children["code"].astype(str).tolist()
    ordinary_html = "".join(
        f'<li><span class="solid-edge">→</span>{escape(str(row.code))} '
        f'<strong class="rollup-value" data-rollup-flow="{escape(str(row.code))}">—</strong></li>'
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
            f'<li>{escape(contributor)} <span class="dashed-edge">⋯→</span> '
            f'<strong class="rollup-value" data-rollup-flow="{escape(contributor)}">—</strong></li>'
            for contributor in contributors
        )
        mode_explanation = (
            "This boundary is not folded back into an ordinary ancestor total."
            if mode == "DETACHED"
            else "This boundary can support ordinary ancestor/frontier resolution."
        )
        boundary_cards.append(
            f'<article class="rollup-boundary {escape(mode.lower())}" '
            f'data-rollup-target="{escape(label)}" data-rollup-inputs="{escape("|".join(contributors))}">'
            f'<h3><span class="mode-pill">{escape(mode)}</span> {escape(label)} '
            f'<strong class="rollup-value" data-rollup-flow="{escape(label)}">—</strong></h3>'
            '<div class="boundary-columns"><div><h4>Dashed composition inputs</h4>'
            f'<ul>{contributor_html}</ul></div><div><h4>Solid registered children</h4>'
            f'<ul>{children_html}</ul></div></div>'
            f'<p class="helper-note">{escape(mode_explanation)}</p>'
            f'<p class="artifact-id">{escape(str(boundary_id))}</p></article>'
        )
    return (
        '<div class="transformation-diagram">'
        '<section class="ordinary-hierarchy"><h3>Ordinary hierarchy</h3>'
        f'<div class="tree-root rollup-check" data-rollup-target="{escape(ordinary_parent)}" '
        f'data-rollup-inputs="{escape("|".join(ordinary_child_codes))}">{escape(ordinary_parent)} '
        f'<strong class="rollup-value" data-rollup-flow="{escape(ordinary_parent)}">—</strong></div><ul>{ordinary_html}</ul></section>'
        '<section class="rollup-boundaries"><h3>Registered rollup boundaries</h3>'
        '<p class="subtle">Solid arrows are ordinary tree edges. Dotted arrows are rollup composition, not additive tree edges.</p>'
        f'{"".join(boundary_cards)}</section></div>'
    )


def _rollup_boundary_register_html(rollup_catalogue: pd.DataFrame) -> str:
    """Render every ESTO rollup as a collapsible diagnostic register."""
    required = {"source_system", "rollup_mode", "rolled_flow_label", "input_flow"}
    if rollup_catalogue.empty or not required.issubset(rollup_catalogue.columns):
        return '<p class="empty-state">No compiled rollup-edge catalogue is available.</p>'
    catalogue = rollup_catalogue[rollup_catalogue["source_system"].astype(str).eq("ESTO")].copy()
    id_column = "rollup_id" if "rollup_id" in catalogue.columns else "non_expanding_rollup_id"
    cards: list[str] = []
    for rollup_id, group in catalogue.groupby(id_column, dropna=False, sort=True):
        first = group.iloc[0]
        label = str(first["rolled_flow_label"])
        mode = str(first["rollup_mode"])
        contributors = sorted(set(group["input_flow"].dropna().astype(str)) - {"", "nan"})
        inputs_html = "".join(
            f'<li>{escape(flow)} <span class="dashed-edge">⋯→</span> '
            f'<strong class="rollup-value" data-rollup-flow="{escape(flow)}">—</strong></li>'
            for flow in contributors
        )
        cards.append(
            f'<article class="rollup-boundary {escape(mode.lower())}" '
            f'data-rollup-target="{escape(label)}" data-rollup-inputs="{escape("|".join(contributors))}">'
            f'<h3><span class="mode-pill">{escape(mode)}</span> {escape(label)} '
            f'<strong class="rollup-value" data-rollup-flow="{escape(label)}">—</strong></h3>'
            f'<ul>{inputs_html}</ul><p class="artifact-id">{escape(str(rollup_id))}</p></article>'
        )
    return '<div class="rollup-register">' + "".join(cards) + "</div>"


def _rollup_boundary_details_html(
    rollup_catalogue: pd.DataFrame,
    common_esto_tree: pd.DataFrame | None = None,
) -> str:
    """Render each ESTO rollup with its ordinary and composition relationships."""
    required = {"source_system", "rollup_mode", "rolled_flow_label", "input_flow"}
    if rollup_catalogue.empty or not required.issubset(rollup_catalogue.columns):
        return '<p class="empty-state">No compiled rollup-edge catalogue is available.</p>'
    catalogue = rollup_catalogue[rollup_catalogue["source_system"].astype(str).eq("ESTO")].copy()
    flow_tree = pd.DataFrame(columns=["code", "parent_code"])
    if common_esto_tree is not None and {"axis", "code", "parent_code"}.issubset(common_esto_tree.columns):
        flow_tree = common_esto_tree[common_esto_tree["axis"].astype(str).eq("flow")][["code", "parent_code"]].copy()
        flow_tree["code"] = flow_tree["code"].astype(str)
        flow_tree["parent_code"] = flow_tree["parent_code"].fillna("").astype(str)
    parent_by_code = dict(zip(flow_tree["code"], flow_tree["parent_code"]))
    id_column = "rollup_id" if "rollup_id" in catalogue.columns else "non_expanding_rollup_id"
    explanations = {
        "EXPANDING": "An ordinary combined category: its registered children remain part of the hierarchy, so this boundary may expand through them.",
        "NON_EXPANDING": "An inclusive comparison boundary: it can support the ordinary parent/frontier check, but is not an additional additive hierarchy expansion.",
        "DETACHED": "A separate comparison boundary: it is deliberately not folded into an ordinary ancestor total, even where its label resembles an ordinary sector.",
    }
    cards: list[str] = []
    for rollup_id, group in catalogue.groupby(id_column, dropna=False, sort=True):
        first = group.iloc[0]
        label = str(first["rolled_flow_label"])
        mode = str(first["rollup_mode"])
        contributors = sorted(set(group["input_flow"].dropna().astype(str)) - {"", "nan"})
        parents = sorted(set(group.get("parent_flow_label", pd.Series(dtype=str)).dropna().astype(str)) - {"", "nan"})
        ordinary_base = label.replace(" (including own use)", "")
        if ordinary_base not in parent_by_code:
            ordinary_base = next((flow for flow in contributors if flow in parent_by_code), "")
        if not parents and ordinary_base:
            inferred_parent = parent_by_code.get(ordinary_base, "")
            if inferred_parent:
                parents = [inferred_parent]
        siblings = sorted(
            set(flow_tree[flow_tree["parent_code"].isin(parents)]["code"].astype(str)) - {ordinary_base, label}
        )
        children = sorted({
            child.strip()
            for value in group.get("child_flow_labels", pd.Series(dtype=str)).dropna().astype(str)
            for child in value.split(";")
            if child.strip()
        })
        def _value_items(items: list[str], empty_message: str) -> str:
            return "".join(
                f'<li>{escape(item)} <strong class="rollup-value" data-rollup-flow="{escape(item)}">â€”</strong></li>'
                for item in items
            ) or f'<li class="muted">{escape(empty_message)}</li>'

        parent_html = _value_items(parents, "No ordinary parent.")
        child_html = _value_items(children, "No ordinary children.")
        sibling_html = _value_items(siblings, "No ordinary siblings.")
        component_html = _value_items(contributors, "No composition components.")
        note = str(first.get("note", "")).strip()
        cards.append(
            f'<article class="rollup-boundary {escape(mode.lower())}" data-rollup-target="{escape(label)}" data-rollup-inputs="{escape("|".join(contributors))}">'
            f'<h3>{escape(label)} <strong class="rollup-value" data-rollup-flow="{escape(label)}">â€”</strong></h3>'
            '<div class="boundary-columns"><div><h4>Ordinary hierarchy</h4><strong>Parent</strong>'
            f'<ul>{parent_html}</ul><strong>Children</strong><ul>{child_html}</ul><strong>Siblings</strong><ul>{sibling_html}</ul></div>'
            f'<div><h4>Composition components</h4><ul>{component_html}</ul></div></div>'
            f'<p class="helper-note"><span class="mode-pill">{escape(mode)}</span> {escape(explanations.get(mode, "Defined by the mapping workbook."))}</p>'
            f'<p class="artifact-id">{escape(note)}<br>{escape(str(rollup_id))}</p></article>'
        )
    return '<div class="rollup-register">' + "".join(cards) + "</div>"


def _rollup_graph_data(
    common_esto_tree: pd.DataFrame,
    rollup_catalogue: pd.DataFrame,
    validation: pd.DataFrame | None = None,
    economy: str = "",
) -> dict[str, object]:
    """Return mapping-owned hierarchy, rollup, and read-only QA metadata."""
    if common_esto_tree.empty or "axis" not in common_esto_tree.columns:
        return {"sectors": [], "boundaries": [], "parent": "", "children": []}
    tree = common_esto_tree[common_esto_tree["axis"].astype(str).eq("flow")].copy()
    if "level" not in tree.columns:
        tree["level"] = tree["parent_code"].fillna("").astype(str).ne("").map({False: 1, True: 2})
    if "label" not in tree.columns:
        tree["label"] = tree["code"]
    tree["level"] = pd.to_numeric(tree["level"], errors="coerce").fillna(0).astype(int)
    duplicate_codes = set(tree.loc[tree["code"].astype(str).duplicated(keep=False), "code"].astype(str))
    tree_codes = set(tree["code"].astype(str))
    validation_by_code: dict[str, dict[str, dict[str, object]]] = {}
    if validation is not None and not validation.empty:
        required = {"validation_axis", "source_system", "parent_code", "status"}
        if required.issubset(validation.columns):
            validation_rows = validation[
                validation["validation_axis"].astype(str).eq("flow")
            ].copy()
            economy_key = str(economy).replace("_", "")
            if economy_key and "economy" in validation_rows.columns:
                validation_rows = validation_rows[
                    validation_rows["economy"].astype(str).str.replace("_", "", regex=False).eq(economy_key)
                ]
            for (code, source), group in validation_rows.groupby(
                ["parent_code", "source_system"], dropna=False, sort=False
            ):
                statuses = group["status"].astype(str)
                reasons = sorted(
                    set(group.get("reason", pd.Series(dtype=str)).dropna().astype(str)) - {"", "nan"}
                )
                validation_by_code.setdefault(str(code), {})[str(source)] = {
                    "failed": int(statuses.eq("failed").sum()),
                    "passed": int(statuses.eq("passed").sum()),
                    "reasons": reasons[:4],
                }
    nodes = tree.sort_values(["level", "code"], kind="mergesort")[["code", "label", "parent_code", "level"]].assign(
        parent_code=lambda frame: frame["parent_code"].fillna("").astype(str),
        code=lambda frame: frame["code"].astype(str),
        label=lambda frame: frame["label"].fillna("").astype(str),
    ).to_dict("records")
    for node in nodes:
        display_value = node["label"] or node["code"]
        display_parts = display_value.split(" ", 1)
        node["flow_code"] = display_parts[0]
        node["flow_label"] = display_parts[1] if len(display_parts) > 1 else ""
        node["is_ordinary_hierarchy"] = node["level"] > 0
        flags = []
        if node["code"] in duplicate_codes:
            flags.append("DUPLICATE_FLOW_CODE")
        if node["parent_code"] and node["parent_code"] not in tree_codes:
            flags.append("ORPHAN_PARENT")
        if node["level"] > 1 and not node["parent_code"]:
            flags.append("ORPHANED_HIERARCHY_ROW")
        node["structural_flags"] = flags
        node["validation"] = validation_by_code.get(node["code"], {})
    roots = tree[
        tree["parent_code"].fillna("").astype(str).eq("")
        & tree["level"].eq(1)
    ]["code"].astype(str).tolist()
    sectors = []
    for root in roots:
        children = tree[tree["parent_code"].fillna("").astype(str).eq(root)]["code"].astype(str).tolist()
        sectors.append({"root": root, "children": children})
    legacy_sector = next((sector for sector in sectors if sector["root"] == "09 Total transformation sector"), {"root": "", "children": []})
    if rollup_catalogue.empty or not {"source_system", "rolled_flow_label"}.issubset(rollup_catalogue.columns):
        return {"sectors": sectors, "nodes": nodes, "boundaries": [], "all_boundaries": [], "parent": legacy_sector["root"], "children": legacy_sector["children"]}
    catalogue = rollup_catalogue[rollup_catalogue["source_system"].astype(str).eq("ESTO")].copy()
    id_column = "rollup_id" if "rollup_id" in catalogue.columns else "non_expanding_rollup_id"
    boundaries = []
    for rollup_id, group in catalogue.groupby(id_column, dropna=False, sort=True):
        first = group.iloc[0]
        modes = sorted(set(group["rollup_mode"].dropna().astype(str)) - {"", "nan"})
        labels = sorted(set(group["rolled_flow_label"].dropna().astype(str)) - {"", "nan"})
        inputs = [value for value in group["input_flow"].dropna().astype(str) if value not in {"", "nan"}]
        flags = []
        if len(modes) != 1:
            flags.append("INCONSISTENT_ROLLUP_MODE")
        if len(labels) != 1:
            flags.append("INCONSISTENT_ROLLUP_TARGET")
        if len(inputs) != len(set(inputs)):
            flags.append("DUPLICATE_ROLLUP_INPUT")
        if not labels or not inputs:
            flags.append("INCOMPLETE_ROLLUP")
        parent_values = set(group.get("parent_flow_label", pd.Series(dtype=str)).dropna().astype(str))
        boundaries.append({
            "id": str(rollup_id),
            "label": str(first["rolled_flow_label"]),
            "mode": str(first["rollup_mode"]),
            "inputs": sorted(set(inputs)),
            "parent": sorted(parent_values - {"", "nan"})[0] if parent_values - {"", "nan"} else "",
            "children": sorted({
                child.strip()
                for value in group.get("child_flow_labels", pd.Series(dtype=str)).dropna().astype(str)
                for child in value.split(";")
                if child.strip()
            }),
            "structural_flags": flags,
        })
    legacy_boundaries = [boundary for boundary in boundaries if boundary["label"].startswith("09")]
    return {
        "sectors": sectors,
        "nodes": nodes,
        "all_boundaries": boundaries,
        "boundaries": legacy_boundaries,
        # Retained while the older inline renderer remains in the generated page.
        "parent": legacy_sector["root"],
        "children": legacy_sector["children"],
    }


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
    comparison_data: pd.DataFrame | None = None,
    esto_exact_values: pd.DataFrame | None = None,
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
    contract_selection = load_mapping_diagnostics_contract(mappings_root)
    contract_note = "Legacy tree artifacts (no canonical contract selected)"
    if contract_selection is not None:
        common_esto_tree = contract_selection["tree"]
        stage = contract_selection["validation"]
        contract_note = (
            "Canonical hierarchy contract build: "
            f"{str(contract_selection['build_id'])[:16]}"
        )
    source_tree = _read_csv(tree_root / "all_dataset_trees.csv")
    partial = _read_csv(partial_path)
    unmapped = _read_csv(unmapped_path)
    conflicts = _read_csv(conflicts_path)
    coverage = _read_csv(coverage_path)
    source_to_common = _read_csv(source_to_common_path)
    many_to_many = _read_csv(many_to_many_path)
    rollup_catalogue = _read_csv(rollup_catalogue_path)
    if (
        contract_selection is not None
        and not contract_selection["rollups"].empty
    ):
        rollup_catalogue = contract_selection["rollups"]
    rollup_boundary_register = _rollup_boundary_details_html(rollup_catalogue, common_esto_tree)
    rollup_graph_data = _rollup_graph_data(
        common_esto_tree,
        rollup_catalogue,
        validation=stage,
        economy=economy,
    )
    transformation_graph_json = json.dumps(rollup_graph_data, ensure_ascii=False).replace("</", "<\\/")
    displayed_rollup_flows = {
        str(node.get("code", "")).strip()
        for node in rollup_graph_data.get("nodes", [])
        if str(node.get("code", "")).strip()
    }
    for boundary in rollup_graph_data.get("all_boundaries", []):
        displayed_rollup_flows.add(str(boundary.get("label", "")).strip())
        displayed_rollup_flows.update(
            str(value).strip()
            for value in boundary.get("inputs", [])
            if str(value).strip()
        )
    rollup_value_records: list[dict[str, object]] = []
    if comparison_data is not None and not comparison_data.empty:
        required_value_columns = {"source_system", "scenario", "year", "common_flow_label", "value"}
        if required_value_columns.issubset(comparison_data.columns):
            value_rows = comparison_data.copy()
            value_rows["value"] = pd.to_numeric(value_rows["value"], errors="coerce").fillna(0.0)
            value_rows = value_rows[
                value_rows["common_flow_label"].astype(str).isin(displayed_rollup_flows)
            ]
            rollup_value_records = value_rows.groupby(
                ["source_system", "scenario", "year", "common_flow_label"], dropna=False
            )["value"].sum().reset_index().to_dict("records")
    if esto_exact_values is not None and not esto_exact_values.empty:
        required_value_columns = {"source_system", "scenario", "year", "common_flow_label", "value"}
        if required_value_columns.issubset(esto_exact_values.columns):
            exact_rows = esto_exact_values.copy()
            exact_rows["value"] = pd.to_numeric(exact_rows["value"], errors="coerce").fillna(0.0)
            exact_rows = exact_rows[
                exact_rows["common_flow_label"].astype(str).isin(displayed_rollup_flows)
            ]
            rollup_value_records.extend(exact_rows.groupby(
                ["source_system", "scenario", "year", "common_flow_label"], dropna=False
            )["value"].sum().reset_index().to_dict("records"))
    rollup_value_json = json.dumps(rollup_value_records, ensure_ascii=False).replace("</", "<\\/")

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
.transformation-diagram {{ display:grid; grid-template-columns:minmax(260px,0.8fr) minmax(520px,2fr); gap:16px; }} .ordinary-hierarchy,.rollup-boundaries {{ background:#f7fafc; border:1px solid #d9e1ea; border-radius:8px; padding:12px; }} .ordinary-hierarchy h3,.rollup-boundaries h3,.rollup-boundary h3,.rollup-boundary h4 {{ margin:0 0 8px; }} .tree-root {{ background:#dceaf8; border:1px solid #8eb2d4; border-radius:6px; font-weight:600; padding:8px; }} .ordinary-hierarchy ul,.rollup-boundary ul {{ list-style:none; padding-left:12px; margin:8px 0; }} .ordinary-hierarchy li,.rollup-boundary li {{ margin:5px 0; }} .solid-edge {{ color:#2d6a9f; font-weight:700; margin-right:4px; }} .dashed-edge {{ color:#7c5b00; font-weight:700; margin-left:6px; }} .rollup-boundary {{ border:1px solid #d9e1ea; border-left:5px solid #3d7fb1; border-radius:8px; padding:10px; margin-top:10px; background:#fff; }} .rollup-boundary.detached {{ border-left-color:#9b5c00; background:#fffaf0; }} .mode-pill {{ display:inline-block; font-size:11px; padding:2px 6px; border-radius:999px; background:#dceaf8; color:#174b73; }} .detached .mode-pill {{ background:#ffe7ba; color:#754300; }} .boundary-columns {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; font-size:13px; }} .artifact-id {{ margin:8px 0 0; color:#5f6b7a; font-family:ui-monospace,monospace; font-size:11px; }} .rollup-controls {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; margin:12px 0; }} .rollup-controls label {{ display:grid; gap:3px; color:#5f6b7a; font-size:12px; }} .rollup-controls select {{ min-width:140px; padding:6px; }} .rollup-value {{ float:right; font-variant-numeric:tabular-nums; color:#5f6b7a; }} .rollup-check.value-pass,.rollup-boundary.value-pass {{ background:#ecf8ef; border-color:#5dae70; }} .rollup-check.value-fail,.rollup-boundary.value-fail {{ background:#fff0f0; border-color:#c95d5d; }} .rollup-check.value-pass .rollup-value,.rollup-boundary.value-pass .rollup-value {{ color:#176b35; }} .rollup-check.value-fail .rollup-value,.rollup-boundary.value-fail .rollup-value {{ color:#9b1c1c; }} @media (max-width:760px) {{ .paired-trees,.transformation-diagram,.boundary-columns {{ grid-template-columns:1fr; }} }}
.rollup-explainer {{ display:grid; grid-template-columns:repeat(4,minmax(180px,1fr)); gap:8px; margin:10px 0 14px; }} .rollup-explainer div {{ border:1px solid #d9e1ea; border-radius:7px; padding:9px; font-size:12px; line-height:1.4; }} .rollup-explainer strong {{ display:block; margin-bottom:3px; }} .rollup-filter-grid {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; margin:8px 0; }} .rollup-filter-grid label {{ display:grid; gap:3px; color:#5f6b7a; font-size:12px; }} .rollup-filter-grid select,.rollup-filter-grid input {{ min-width:150px; padding:6px; }} .rollup-filter-grid input {{ min-width:230px; }} .basis-state {{ align-self:center; border-radius:999px; background:#e8f0fa; color:#174b73; font-size:12px; font-weight:700; padding:6px 10px; }} .rollup-legend {{ display:flex; flex-wrap:wrap; gap:12px; margin:8px 0; color:#445266; font-size:12px; }} .legend-line {{ display:inline-block; width:28px; border-top:3px solid #53718f; margin-right:5px; vertical-align:middle; }} .legend-line.rollup {{ border-color:#987216; border-top-style:dotted; }} .legend-line.detached {{ border-color:#9b5c00; border-top-style:dashed; }} .rollup-graph-toolbar {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:10px 0 8px; }} .rollup-graph-toolbar button {{ padding:5px 10px; cursor:pointer; }} .rollup-graph-help {{ color:#5f6b7a; font-size:12px; }} .rollup-graph-wrap {{ height:620px; overflow:auto; border:1px solid #d9e1ea; border-radius:8px; background:#fbfdff; }} #rollup-graph {{ min-height:200px; }} #rollup-graph svg {{ display:block; }} #rollup-graph text {{ font-family:Inter,Segoe UI,Arial,sans-serif; font-size:13px; fill:#172033; pointer-events:none; }} #rollup-graph .node {{ cursor:pointer; }} #rollup-graph .node rect {{ fill:#fff; stroke:#8eb2d4; stroke-width:1.6; rx:8; }} #rollup-graph .node.root rect {{ fill:#edf5fc; stroke:#3d7fb1; }} #rollup-graph .node.extended-only rect {{ fill:#f1edff; stroke:#7656b5; }} #rollup-graph .node.boundary rect {{ fill:#edf5fc; stroke-width:2.2; }} #rollup-graph .node.expanding rect {{ fill:#e9f6ee; stroke:#438a5b; }} #rollup-graph .node.non_expanding rect {{ fill:#eaf3ff; stroke:#356c9b; stroke-dasharray:5 3; }} #rollup-graph .node.detached rect {{ fill:#fff5df; stroke:#b77b13; stroke-dasharray:2 3; }} #rollup-graph .node.selected rect {{ stroke:#13233a; stroke-width:4; }} #rollup-graph .node.neighbour rect {{ stroke-width:3; }} #rollup-graph .node.issue rect {{ fill:#fff0f0; stroke:#c95d5d; }} #rollup-graph .node.value-pass rect {{ filter:drop-shadow(0 0 2px #5dae70); }} #rollup-graph .node.value-fail rect {{ fill:#fff0f0; stroke:#c95d5d; }} #rollup-graph .edge {{ fill:none; stroke:#53718f; stroke-width:1.8; marker-end:url(#hierarchy-arrow); }} #rollup-graph .edge.rollup {{ stroke:#987216; stroke-width:2.2; stroke-dasharray:3 5; marker-end:url(#rollup-arrow); }} #rollup-graph .edge.detached {{ stroke:#9b5c00; stroke-dasharray:10 5; }} #rollup-graph .edge.dimmed,.node.dimmed {{ opacity:.16; }} #rollup-graph .mode {{ font-size:10px; font-weight:800; letter-spacing:.4px; fill:#335b7d; }} #rollup-graph .value {{ font-size:11px; font-weight:700; fill:#5f6b7a; }} #rollup-graph .origin {{ font-size:10px; fill:#7656b5; }} .graph-empty {{ padding:34px; color:#5f6b7a; text-align:center; }} .rollup-summary {{ margin-top:14px; }} .rollup-summary h3 {{ margin-bottom:6px; }} .rollup-summary-status {{ color:#5f6b7a; font-size:12px; margin:0 0 8px; }} #rollup-summary-table tr.issue-row td {{ background:#fff4f4; }} #rollup-summary-table tr.detached-row td {{ background:#fffaf0; }} @media (max-width:900px) {{ .rollup-explainer {{ grid-template-columns:1fr 1fr; }} }} @media (max-width:620px) {{ .rollup-explainer {{ grid-template-columns:1fr; }} }}
.table-scroll {{ overflow:auto; max-height:480px; }} table {{ border-collapse:collapse; width:100%; font-size:12px; }} th {{ position:sticky; top:0; background:#e8f0fa; }} th,td {{ border:1px solid #d9e1ea; padding:6px 8px; text-align:left; vertical-align:top; }} .table-note,.empty-state {{ color:#5f6b7a; font-size:13px; }} footer {{ margin:22px 0; font-size:12px; color:#5f6b7a; }} a {{ color:#1b5e9a; }}
</style></head><body><div class="shell"><header><a href="index.html">← Dashboard overview</a><h1>Mapping diagnostics</h1><p class="subtle">Read-only inspection of hierarchy/anchor validation and direct mapping coverage. Updated: {escape(dashboard_updated_label)}<br>{escape(contract_note)}</p></header>
<section class="panel"><h2>How to read a hierarchy case</h2><div class="guide-grid"><div class="guide-card guide-good"><strong>Manual LEAP roll-up</strong>Only constructed LEAP subtotal branches receive this label; they are compared with their immediate source-tree children.</div><div class="guide-card guide-good"><strong>One-to-many fan-out</strong>One raw parent can reach several ESTO components. Those routes are not additional source-tree parents.</div><div class="guide-card guide-neutral"><strong>De-duplicated frontier</strong>Mapped component rows can overlap. The frontier counts each Common ESTO row once, so do not add the displayed component rows.</div><div class="guide-card guide-warning"><strong>Raw source contradiction</strong>If a raw parent is 0 while its children are non-zero, the original source hierarchy disagrees with itself. It is not, by itself, a missing mapping.</div></div></section>
<div class="metrics">{cards}</div>
<section class="panel"><h2>How the anchor validator connects the hierarchies</h2><div class="flow"><div>Raw source parent</div><span class="arrow">→</span><div>Raw source child tree</div><span class="arrow">→</span><div>Mapped Common ESTO frontier</div><span class="arrow">→</span><div>Comparison values</div><span class="arrow">→</span><div>Passed / failed / skipped reason</div></div><p class="subtle">The tables below match each raw parent/children context to its branch-level summed absolute mismatch and rank. This makes the materiality ranking and the exact source evidence visible together.</p></section>
<details class="panel collapsed-panel"><summary><h2>All rollup boundaries</h2><span></span></summary><div><p class="subtle">Mapping-owned rollup edges across every ESTO flow. Green means a rolled value equals its contributors within tolerance; red means it does not. Values aggregate all products for the chosen source, scenario, and year.</p><div class="rollup-controls"><label>Dataset<select id="rollup-source"></select></label><label>Scenario<select id="rollup-scenario"></select></label><label>Year<select id="rollup-year"></select></label></div>{rollup_boundary_register}</div></details>
<section class="panel"><h2>All sector rollup structure</h2><p class="subtle">Start with the collapsed major-sector overview, choose a sector, or search for a flow. The graph never treats rollup composition as an ordinary hierarchy branch.</p><div class="rollup-explainer"><div><strong>Normal hierarchy</strong>A solid blue arrow means the child has the displayed parent in the ESTO flow tree.</div><div><strong>Registered rollup</strong>A dotted ochre arrow means the input contributes to a compiled comparison boundary; it is not another parent-child edge.</div><div><strong>NON_EXPANDING vs DETACHED</strong>NON_EXPANDING replaces a comparison frontier without adding another hierarchy branch. DETACHED remains outside ordinary ancestor totals and is intentional, not an orphan.</div><div><strong>ESTO Extended</strong>Extended-only rows are purple. “ESTO + Extended” makes both datasets selectable; “Compare” shows both values side by side without adding them.</div></div><div class="rollup-filter-grid"><label>ESTO basis<select id="rollup-basis"><option value="original">Original ESTO only</option><option value="plus">ESTO + ESTO Extended</option><option value="compare">Compare ESTO vs Extended</option></select></label><label>Major sector<select id="rollup-sector"></select></label><label>Rollup type<select id="rollup-mode"><option value="NONE" selected>Hierarchy only</option><option value="ALL">All rollup types</option><option value="EXPANDING">EXPANDING</option><option value="NON_EXPANDING">NON_EXPANDING</option><option value="DETACHED">DETACHED</option></select></label><label>Validation/status<select id="rollup-status"><option value="ALL">All statuses</option><option value="ISSUES">Issues only</option><option value="PASS">Reconciled only</option><option value="UNAVAILABLE">Unavailable only</option></select></label><label>Search for a flow<input id="rollup-search" type="search" placeholder="Code or label" autocomplete="off"></label><span class="basis-state" id="rollup-basis-state">Showing original ESTO only</span></div><div class="rollup-legend"><span><i class="legend-line"></i>normal hierarchy</span><span><i class="legend-line rollup"></i>rollup composition</span><span><i class="legend-line detached"></i>intentional DETACHED boundary</span><span>Purple node = Extended-only addition; red = orphan, duplicate, inconsistency, or failed validation.</span></div><div class="rollup-graph-toolbar"><button type="button" id="rollup-fit">Fit width</button><button type="button" id="rollup-zoom-out">−</button><button type="button" id="rollup-zoom-reset">100%</button><button type="button" id="rollup-zoom-in">+</button><button type="button" id="rollup-clear-selection">Clear selection</button><span class="rollup-graph-help">Click a node to highlight its parent, children, and rollup relationships. Choose a major sector (or click one) to expand it.</span></div><div class="rollup-graph-wrap"><div id="rollup-graph"></div></div><div class="rollup-summary"><h3>Rows in the current graph</h3><p class="rollup-summary-status" id="rollup-summary-status"></p><div class="table-scroll"><table id="rollup-summary-table"><thead><tr><th>Flow code</th><th>Flow label</th><th>Parent flow</th><th>Relationship type</th><th>Rollup type</th><th>Original / Extended</th><th>Child count</th><th>Rollup membership</th><th>Validation / status</th></tr></thead><tbody></tbody></table></div></div></section>
<details class="panel collapsed-panel"><summary><h2>Stage 3 hierarchy failures</h2><span></span></summary><div>{_table_html(stage_summary, ['source_system','validation_axis','parent_code','rows'])}</div></details>
<details class="panel collapsed-panel"><summary><h2>Largest summed anchor mismatches</h2><span></span></summary><div><p class="subtle">Parent and children totals are sums across all failed rows; net difference is parent minus children, while absolute mismatch does not allow opposite signs to cancel.</p>{_table_html(anchor_value_display, ['source_system','validation_axis','parent_code','failed_checks','parent_total','children_total','net_difference','absolute_mismatch_total'])}<h3>Failure reasons</h3>{_table_html(anchor_summary, ['source_system','validation_axis','reason','parent_code','rows'])}</div></details>
<details class="panel collapsed-panel"><summary><h2>Reviewed source-hierarchy exceptions</h2><span></span></summary><div><p class="subtle">These are known source-data conditions from the exception workbook. They are skipped from actionable anchor failures but remain visible here with their review notes.</p>{_table_html(reviewed_anchor_exceptions, ['source_system','validation_axis','parent_code','other_axis_value','economy','scenario','year','parent_value','reason','exception_resolution','data_quality_exception_notes'])}<h3>Leaf-reconciliation candidates awaiting review</h3><p class="subtle">These are not exceptions yet. Their immediate children do not reconcile, while their descendant leaves do; review before copying an enabled row into <code>source_mismatch_allowed</code>.</p>{_table_html(leaf_reconciliation_candidates, ['source_system','validation_axis','parent_code','other_axis_value','economy','scenario','year','parent_value','direct_children_sum','leaf_descendants_sum','candidate_classification','notes'])}</div></details>
<label class="zero-toggle"><input id="show-zero-children" type="checkbox" autocomplete="off" onchange="document.body.classList.toggle('show-zero-children', this.checked)"> Show zero-value children and mapped components</label>
<section class="panel"><h2>NINTH flow tree: original vs mapped representation</h2><p class="subtle">The right side uses the Common ESTO hierarchy, including structure-only ancestors where needed; otherwise it shows a direct fan-out.</p>{_paired_tree_html(ninth_paired_summary, ninth_tree, common_esto_tree, 'NINTH', anchor_mapped_component_context_values, dashboard_economy)}</section>
<section class="panel"><h2>LEAP flow tree: original vs mapped representation</h2><p class="subtle">The right side uses the Common ESTO hierarchy, including structure-only ancestors where needed; otherwise it shows a direct fan-out.</p>{_paired_tree_html(leap_paired_summary, leap_tree, common_esto_tree, 'LEAP', anchor_mapped_component_context_values, dashboard_economy)}</section>
<details class="panel collapsed-panel"><summary><h2>Direct mapping coverage review</h2><span></span></summary><div><h3>Actionable partial coverage</h3>{_table_html(partial, ['source_system','comparison_scope','common_row_id','missing_component_pairs','relevance_evidence','mapping_action','mapping_sheet_to_review'])}<h3>Non-zero unmapped LEAP branches</h3>{_table_html(unmapped, ['leap_flow','leap_product','indirect_esto_flow','indirect_esto_product','qa_status'])}<h3>LEAP source-presence conflicts</h3>{_table_html(conflicts, ['leap_sector_name_full_path','raw_leap_fuel_name','presence_status','in_leap_combined_esto','in_leap_combined_ninth'])}<h3>Source-coverage audit summary</h3>{_table_html(coverage_summary, ['coverage_status','mapping_status','rows'])}{cardinality_sections}</div></details>
<footer><strong>Artifact provenance</strong><br>{artifact_notes}<br>{escape(_artifact_note(anchor_child_values_path))}<br>{escape(_artifact_note(anchor_child_context_values_path))}<br>{escape(_artifact_note(anchor_mapped_component_context_values_path))}<br>{escape(_artifact_note(leaf_reconciliation_candidates_path))}</footer></div><script>const ROLLUP_GRAPH={transformation_graph_json},ROLLUP_VALUES={rollup_value_json};const rs=document.querySelector('#rollup-source'),rc=document.querySelector('#rollup-scenario'),ry=document.querySelector('#rollup-year');const unique=a=>[...new Set(a)].sort();const fill=(el,items,selected)=>{{el.innerHTML='';items.forEach(x=>el.add(new Option(x,x,false,String(x)===String(selected)));}};function esc(s){{return String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));}}function drawGraph(){{let h=230+ROLLUP_GRAPH.boundaries.length*150,w=1300,kids=ROLLUP_GRAPH.children;let childX=i=>70+i*(1160/Math.max(kids.length-1,1));let svg=`<svg viewBox="0 0 ${{w}} ${{h}}" width="100%" height="${{h}}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#53718f"/></marker></defs>`;svg+=`<g class="node rollup-check" data-rollup-target="${{esc(ROLLUP_GRAPH.parent)}}" data-rollup-inputs="${{esc(kids.join('|'))}}"><rect x="510" y="20" width="280" height="48"/><text x="525" y="43">${{esc(ROLLUP_GRAPH.parent)}}</text><text class="value" data-rollup-flow="${{esc(ROLLUP_GRAPH.parent)}}" x="525" y="59">—</text></g>`;kids.forEach((x,i)=>{{let cx=childX(i);svg+=`<line class="edge" x1="650" y1="68" x2="${{cx}}" y2="118"/><g class="node"><rect x="${{cx-62}}" y="118" width="124" height="48"/><text x="${{cx-54}}" y="140">${{esc(x).replace(' plants','')}}</text><text class="value" data-rollup-flow="${{esc(x)}}" x="${{cx-54}}" y="157">—</text></g>`;}});ROLLUP_GRAPH.boundaries.forEach((b,i)=>{{let y=210+i*150,targetX=850;svg+=`<g class="node boundary ${{b.mode==='DETACHED'?'detached':''}} rollup-check" data-rollup-target="${{esc(b.label)}}" data-rollup-inputs="${{esc(b.inputs.join('|'))}}"><rect x="${{targetX}}" y="${{y}}" width="350" height="58"/><text class="mode" x="${{targetX+12}}" y="${{y+18}}">${{esc(b.mode)}}</text><text x="${{targetX+12}}" y="${{y+35}}">${{esc(b.label)}}</text><text class="value" data-rollup-flow="${{esc(b.label)}}" x="${{targetX+12}}" y="${{y+51}}">—</text></g>`;b.inputs.forEach((x,j)=>{{let iy=y+j*28,ix=110+j*250;svg+=`<line class="edge dashed" x1="${{ix+175}}" y1="${{iy+12}}" x2="${{targetX}}" y2="${{y+29}}"/><g class="node"><rect x="${{ix}}" y="${{iy}}" width="175" height="25"/><text x="${{ix+7}}" y="${{iy+12}}">${{esc(x)}}</text><text class="value" data-rollup-flow="${{esc(x)}}" x="${{ix+7}}" y="${{iy+22}}">—</text></g>`;}});}});document.querySelector('#rollup-graph').innerHTML=svg+'</svg>';}}function refreshScenarios(){{let rows=ROLLUP_VALUES.filter(r=>r.source_system===rs.value);fill(rc,unique(rows.map(r=>r.scenario)),rc.value||unique(rows.map(r=>r.scenario))[0]);refreshYears();}}function refreshYears(){{let rows=ROLLUP_VALUES.filter(r=>r.source_system===rs.value&&r.scenario===rc.value);let years=unique(rows.map(r=>r.year)).sort((a,b)=>Number(a)-Number(b));fill(ry,years,years.at(-1));paint();}}function paint(){{let rows=ROLLUP_VALUES.filter(r=>r.source_system===rs.value&&r.scenario===rc.value&&String(r.year)===String(ry.value)),values=new Map();rows.forEach(r=>values.set(r.common_flow_label,(values.get(r.common_flow_label)||0)+Number(r.value)));document.querySelectorAll('[data-rollup-flow]').forEach(el=>{{let v=values.get(el.dataset.rollupFlow);el.textContent=v===undefined?'—':v.toLocaleString(undefined,{{maximumFractionDigits:2}});}});document.querySelectorAll('[data-rollup-target]').forEach(el=>{{let target=values.get(el.dataset.rollupTarget),inputs=el.dataset.rollupInputs.split('|').filter(Boolean),sum=inputs.reduce((s,x)=>s+(values.get(x)||0),0),ok=target!==undefined&&Math.abs(target-sum)<=0.01*Math.max(Math.abs(target),1);el.classList.toggle('value-pass',ok);el.classList.toggle('value-fail',target!==undefined&&!ok);}});}}drawGraph();if(ROLLUP_VALUES.length){{fill(rs,unique(ROLLUP_VALUES.map(r=>r.source_system)),unique(ROLLUP_VALUES.map(r=>r.source_system)).includes('ESTO')?'ESTO':unique(ROLLUP_VALUES.map(r=>r.source_system))[0]);refreshScenarios();rs.onchange=refreshScenarios;rc.onchange=refreshYears;ry.onchange=paint;}}else{{document.querySelector('.rollup-controls').innerHTML='<span class="empty-state">No comparison values were supplied for this dashboard render.</span>';}}</script></body></html>"""
    # The dashboard template predates the graph and emits one compact inline
    # script. Correct its option-construction parenthesis while it remains
    # embedded, then move the selectors from the register to the SVG panel.
    existing_rollup_controls_html = (
        '<div class="rollup-controls"><label>Dataset<select id="rollup-source"></select></label>'
        '<label>Scenario<select id="rollup-scenario"></select></label>'
        '<label>Year<select id="rollup-year"></select></label></div>'
    )
    rollup_controls_html = (
        '<div class="rollup-controls"><label>Dataset<select id="rollup-source"></select></label>'
        '<label>Scenario<select id="rollup-scenario"></select></label>'
        '<label>Year<select id="rollup-year"></select></label></div>'
    )
    graph_heading_html = '<section class="panel"><h2>All sector rollup structure</h2>'
    html = html.replace('String(x)===String(selected)));', 'String(x)===String(selected))));')
    html = html.replace(
        'unique(ROLLUP_VALUES.map(r=>r.source_system))',
        "unique(ROLLUP_VALUES.filter(r=>r.source_system!=='ESTO_RAW').map(r=>r.source_system))",
    )
    html = html.replace(
        "Start with the collapsed major-sector overview, choose a sector, or search for a flow. "
        "The graph never treats rollup composition as an ordinary hierarchy branch.",
        "Start with the collapsed major-sector overview, choose a sector, or search for a flow. "
        "All rollup types appear in the hierarchy view with their mode labelled inside the target "
        "box; detailed rule definitions remain in the tables on this page.",
    )
    html = html.replace(
        '<label>Rollup type<select id="rollup-mode"><option value="NONE" selected>Hierarchy only</option>'
        '<option value="ALL">All rollup types</option><option value="EXPANDING">EXPANDING</option>'
        '<option value="NON_EXPANDING">NON_EXPANDING</option><option value="DETACHED">DETACHED</option>'
        '</select></label>',
        "",
    )
    html = html.replace(
        "A dotted ochre arrow means the input contributes to a compiled comparison boundary; "
        "it is not another parent-child edge.",
        "A dotted ochre arrow shows display membership in a compiled comparison boundary; "
        "the target box identifies its rollup mode.",
    )
    html = html.replace("rollup composition</span>", "rollup display relationship</span>")
    html = html.replace("<th>Parent flow</th>", "<th>Displayed parent</th>")
    html = html.replace("<th>Child count</th>", "<th>Displayed children</th>")
    html = html.replace(existing_rollup_controls_html, "", 1)
    html = html.replace(graph_heading_html, graph_heading_html + rollup_controls_html, 1)

    # Replace the early 09-only SVG with the complete sector/rollup graph after
    # the shared selector and value-painting code has initialised.
    all_sector_graph_script = """
<script>
(() => {
  function escGraph(value) {
    return String(value).replace(/[&<>]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[char]));
  }
  function shortLabel(value, limit = 34) {
    const label = String(value);
    return label.length > limit ? `${label.slice(0, limit - 1)}…` : label;
  }
  function drawAllSectorGraph() {
    const graph = ROLLUP_GRAPH;
    const sectors = [];
    const nodes = graph.nodes || [];
    const nodesByLevel = new Map();
    nodes.forEach(node => {
      const level = Number(node.level || 0);
      nodesByLevel.set(level, [...(nodesByLevel.get(level) || []), node]);
    });
    const hierarchyLevels = [...nodesByLevel.keys()].sort((a, b) => a - b);
    const boundaries = graph.all_boundaries || graph.boundaries || [];
    const maxOrdinaryChildren = Math.max(1, ...[...nodesByLevel.values()].map(levelNodes => levelNodes.length));
    const maxBoundaryInputs = Math.max(1, ...boundaries.map(boundary => (boundary.inputs || []).length));
    const width = Math.max(1660, 405 + maxOrdinaryChildren * 230, 380 + maxBoundaryInputs * 260 + 360);
    let cursorY = 24;
    let svg = `<svg viewBox="0 0 ${width} 100" width="${width}" height="100"><defs><marker id="all-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#53718f"/></marker></defs>`;
    const edge = (x1, y1, x2, y2, dashed = false) => `<line class="edge${dashed ? ' dashed' : ''}" marker-end="url(#all-arrow)" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    const renderFullHierarchy = () => {
      const positions = new Map();
      hierarchyLevels.forEach((level, levelIndex) => {
        (nodesByLevel.get(level) || []).forEach((node, index) => {
          positions.set(node.code, {x: 30 + index * 230, y: cursorY + 18 + levelIndex * 82});
        });
      });
      svg += `<text class="mode" x="30" y="${cursorY}">FULL ESTO FLOW HIERARCHY — EVERY LEVEL</text>`;
      positions.forEach((position, code) => {
        const parentCode = nodes.find(node => node.code === code)?.parent_code || '';
        const parentPosition = positions.get(parentCode);
        if (parentPosition) svg += edge(parentPosition.x + 102, parentPosition.y + 48, position.x + 102, position.y);
      });
      positions.forEach((position, code) => {
        const childCodes = nodes.filter(node => node.parent_code === code).map(node => node.code);
        const checkAttributes = childCodes.length
          ? ` rollup-check" data-rollup-target="${escGraph(code)}" data-rollup-inputs="${escGraph(childCodes.join('|'))}`
          : '';
        svg += `<g class="node${checkAttributes}"><rect x="${position.x}" y="${position.y}" width="205" height="48"/><text x="${position.x + 10}" y="${position.y + 21}">${escGraph(shortLabel(code, 34))}</text><text class="value" data-rollup-flow="${escGraph(code)}" x="${position.x + 10}" y="${position.y + 40}">—</text></g>`;
      });
      cursorY += hierarchyLevels.length * 82 + 42;
    };
    const node = (x, y, widthValue, height, label, extraClass = '', mode = '') => `<g class="node ${extraClass}"><rect x="${x}" y="${y}" width="${widthValue}" height="${height}"/><text${mode ? ' class="mode"' : ''} x="${x + 10}" y="${y + (mode ? 16 : 21)}">${escGraph(mode || shortLabel(label))}</text><text x="${x + 10}" y="${y + (mode ? 34 : 37)}">${mode ? escGraph(shortLabel(label)) : ''}</text><text class="value" data-rollup-flow="${escGraph(label)}" x="${x + 10}" y="${y + height - 8}">—</text></g>`;
    svg += `<text class="mode" x="30" y="${cursorY}">ORDINARY ESTO FLOW HIERARCHY — ALL ROOT SECTORS</text>`;
    cursorY += 14;
    sectors.forEach(sector => {
      const children = sector.children || [];
      const blockHeight = 70;
      const rootY = cursorY + blockHeight / 2 - 24;
      svg += `<g class="node rollup-check" data-rollup-target="${escGraph(sector.root)}" data-rollup-inputs="${escGraph(children.join('|'))}"><rect x="30" y="${rootY}" width="265" height="48"/><text x="40" y="${rootY + 20}">${escGraph(shortLabel(sector.root, 42))}</text><text class="value" data-rollup-flow="${escGraph(sector.root)}" x="40" y="${rootY + 40}">—</text></g>`;
      children.forEach((child, index) => {
        const x = 345 + index * 230;
        const y = cursorY;
        svg += edge(295, rootY + 24, x, y + 24);
        svg += node(x, y, 205, 48, child);
      });
      cursorY += blockHeight + 14;
    });
    cursorY += 12;
    svg += `<text class="mode" x="30" y="${cursorY}">REGISTERED ESTO ROLLUP BOUNDARIES — ALL MODES</text>`;
    cursorY += 16;
    boundaries.forEach(boundary => {
      const inputs = boundary.inputs || [];
      const blockHeight = 72;
      const targetY = cursorY + blockHeight / 2 - 29;
      const modeClass = String(boundary.mode || '').toLowerCase();
      const targetX = Math.max(980, 65 + inputs.length * 260);
      svg += `<g class="node boundary ${modeClass} rollup-check" data-rollup-target="${escGraph(boundary.label)}" data-rollup-inputs="${escGraph(inputs.join('|'))}"><rect x="980" y="${targetY}" width="300" height="58"/><text class="mode" x="992" y="${targetY + 16}">${escGraph(boundary.mode)}</text><text x="992" y="${targetY + 34}">${escGraph(shortLabel(boundary.label, 42))}</text><text class="value" data-rollup-flow="${escGraph(boundary.label)}" x="992" y="${targetY + 51}">—</text></g>`;
      inputs.forEach((input, index) => {
        const x = 45 + index * 260;
        const y = cursorY;
        svg += edge(x + 230, y + 22, targetX, targetY + 29, true);
        svg += node(x, y, 230, 44, input);
      });
      cursorY += blockHeight + 14;
    });
    const height = cursorY + 20;
    svg = svg.replace('0 0 1320 100', `0 0 ${width} ${height}`).replace('height="100"', `height="${height}"`);
    document.querySelector('#rollup-graph').innerHTML = svg + '</svg>';
    paint();
  }
  function enableMapNavigation() {
    const viewport = document.querySelector('.rollup-graph-wrap');
    const canvas = document.querySelector('#rollup-graph');
    let scale = 0.55;
    let translateX = 20;
    let translateY = 12;
    let dragStart = null;
    const applyView = () => {
      canvas.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    };
    const zoom = factor => {
      scale = Math.max(0.2, Math.min(2.5, scale * factor));
      applyView();
    };
    viewport.addEventListener('wheel', event => {
      event.preventDefault();
      zoom(event.deltaY < 0 ? 1.12 : 1 / 1.12);
    }, {passive:false});
    viewport.addEventListener('pointerdown', event => {
      dragStart = {x:event.clientX, y:event.clientY, translateX, translateY};
      viewport.classList.add('dragging');
      viewport.setPointerCapture(event.pointerId);
    });
    viewport.addEventListener('pointermove', event => {
      if (!dragStart) return;
      translateX = dragStart.translateX + event.clientX - dragStart.x;
      translateY = dragStart.translateY + event.clientY - dragStart.y;
      applyView();
    });
    const finishDrag = () => {
      dragStart = null;
      viewport.classList.remove('dragging');
    };
    viewport.addEventListener('pointerup', finishDrag);
    viewport.addEventListener('pointercancel', finishDrag);
    document.querySelector('#rollup-zoom-in').onclick = () => zoom(1.25);
    document.querySelector('#rollup-zoom-out').onclick = () => zoom(1 / 1.25);
    document.querySelector('#rollup-zoom-reset').onclick = () => {
      scale = 0.55;
      translateX = 20;
      translateY = 12;
      applyView();
    };
    applyView();
  }
  drawAllSectorGraph();
  enableMapNavigation();
})();
</script>
"""
    all_sector_graph_script = all_sector_graph_script.replace(
        '<rect x="980" y="${targetY}"', '<rect x="${targetX}" y="${targetY}"'
    ).replace(
        'x="992" y="${targetY + 16}"', 'x="${targetX + 12}" y="${targetY + 16}"'
    ).replace(
        'x="992" y="${targetY + 34}"', 'x="${targetX + 12}" y="${targetY + 34}"'
    ).replace(
        'x="992" y="${targetY + 51}"', 'x="${targetX + 12}" y="${targetY + 51}"'
    ).replace(
        '    svg += `<text class="mode" x="30" y="${cursorY}">ORDINARY ESTO FLOW HIERARCHY',
        '    renderFullHierarchy();\n    svg += `<text class="mode" x="30" y="${cursorY}">ORDINARY ESTO FLOW HIERARCHY',
    )
    # The first graph renderer is retained above only while the surrounding
    # legacy inline page template is progressively split up. This focused
    # renderer replaces its output and deliberately keeps hierarchy and rollup
    # composition as separate visual layers.
    all_sector_graph_script = """
<script>
(() => {
  const graph = ROLLUP_GRAPH;
  const nodes = graph.nodes || [];
  const ordinaryNodes = nodes.filter(node => node.is_ordinary_hierarchy);
  const boundaries = graph.all_boundaries || [];
  const nodeByCode = new Map(nodes.map(node => [node.code, node]));
  const boundariesByTarget = new Map();
  boundaries.forEach(boundary => {
    boundariesByTarget.set(
      boundary.label,
      [...(boundariesByTarget.get(boundary.label) || []), boundary]
    );
  });
  const rollupModesFor = code => uniqueSorted(
    (boundariesByTarget.get(code) || []).map(boundary => boundary.mode)
  );
  const displayParentFor = code => {
    const ordinaryParent = nodeByCode.get(code)?.parent_code || '';
    if (ordinaryParent) return ordinaryParent;
    const inputBoundary = boundaries.find(boundary => boundary.inputs.includes(code));
    if (inputBoundary) return inputBoundary.label;
    const targetBoundary = (boundariesByTarget.get(code) || [])
      .find(boundary => boundary.parent);
    return targetBoundary?.parent || '';
  };
  const displayChildrenByCode = new Map();
  nodes.forEach(node => {
    const parent = displayParentFor(node.code);
    if (!parent || parent === node.code) return;
    displayChildrenByCode.set(
      parent,
      [...(displayChildrenByCode.get(parent) || []), node.code]
    );
  });
  const roots = ordinaryNodes
    .filter(node => !node.parent_code && Number(node.level) === 1)
    .map(node => node.code)
    .sort();
  const basis = document.querySelector('#rollup-basis');
  const sector = document.querySelector('#rollup-sector');
  const status = document.querySelector('#rollup-status');
  const search = document.querySelector('#rollup-search');
  const basisState = document.querySelector('#rollup-basis-state');
  const viewport = document.querySelector('.rollup-graph-wrap');
  const canvas = document.querySelector('#rollup-graph');
  const tableBody = document.querySelector('#rollup-summary-table tbody');
  const tableStatus = document.querySelector('#rollup-summary-status');
  let selectedCode = '';
  let zoom = 1;
  let naturalSize = {width: 1260, height: 400};

  const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[char]));
  const uniqueSorted = values => [...new Set(values)].filter(Boolean).sort();
  const sourceOptions = () => uniqueSorted(
    ROLLUP_VALUES
      .filter(row => !['ESTO_RAW', 'ESTO_EXTENDED_RAW'].includes(row.source_system))
      .map(row => row.source_system)
  );
  const rowsForSource = source => ROLLUP_VALUES.filter(row =>
    row.source_system === source
    && row.scenario === rc.value
    && String(row.year) === String(ry.value)
  );
  const valuesForSource = source => {
    const values = new Map();
    rowsForSource(source).forEach(row => {
      values.set(row.common_flow_label, (values.get(row.common_flow_label) || 0) + Number(row.value));
    });
    const rawSource = source === 'ESTO'
      ? 'ESTO_RAW'
      : source === 'ESTO_EXTENDED' ? 'ESTO_EXTENDED_RAW' : '';
    if (rawSource) {
      rowsForSource(rawSource).forEach(row => {
        if (!values.has(row.common_flow_label)) {
          values.set(row.common_flow_label, Number(row.value));
        }
      });
    }
    return values;
  };
  const commonRowsForSource = source => {
    const result = new Set();
    rowsForSource(source).forEach(row => result.add(row.common_flow_label));
    return result;
  };
  const formatValue = value => value === undefined
    ? '—'
    : Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
  const displayedValue = code => {
    if (basis.value === 'compare') {
      const esto = valuesForSource('ESTO').get(code);
      const extended = valuesForSource('ESTO_EXTENDED').get(code);
      return `E ${formatValue(esto)} | X ${formatValue(extended)}`;
    }
    return formatValue(valuesForSource(rs.value).get(code));
  };
  const originFor = code => {
    const inEsto = commonRowsForSource('ESTO').has(code);
    const inExtended = commonRowsForSource('ESTO_EXTENDED').has(code);
    if (inEsto && inExtended) return 'Original ESTO + Extended';
    if (inEsto) return 'Original ESTO';
    if (inExtended) return 'ESTO Extended addition';
    return 'No selected-period ESTO row';
  };
  const validationSources = () => basis.value === 'compare'
    ? ['ESTO', 'ESTO_EXTENDED']
    : [rs.value];
  const nodeStatus = node => {
    const flags = [...(node.structural_flags || [])].filter(flag =>
      flag !== 'ORPHANED_HIERARCHY_ROW' || !displayParentFor(node.code)
    );
    let failed = 0;
    let passed = 0;
    const reasons = [];
    validationSources().forEach(source => {
      const result = (node.validation || {})[source];
      if (!result) return;
      failed += Number(result.failed || 0);
      passed += Number(result.passed || 0);
      (result.reasons || []).forEach(reason => reasons.push(reason));
    });
    if (failed) flags.push(`FAILED_HIERARCHY_CHECKS:${failed}`);
    if (flags.length) return {kind:'issue', label:uniqueSorted([...flags, ...reasons]).join('; ')};
    if (passed) return {kind:'pass', label:`Passed hierarchy checks: ${passed}`};
    const hasValue = basis.value === 'compare'
      ? valuesForSource('ESTO').has(node.code) || valuesForSource('ESTO_EXTENDED').has(node.code)
      : valuesForSource(rs.value).has(node.code);
    return hasValue
      ? {kind:'info', label:'No parent-boundary validation for this row'}
      : {kind:'unavailable', label:'Value / validation unavailable'};
  };
  const boundaryStatus = boundary => {
    const flags = [...(boundary.structural_flags || [])];
    const sources = basis.value === 'compare' ? ['ESTO', 'ESTO_EXTENDED'] : [rs.value];
    let anyAvailable = false;
    let anyFailure = false;
    sources.forEach(source => {
      const values = valuesForSource(source);
      const target = values.get(boundary.label);
      const inputs = boundary.inputs.map(input => values.get(input));
      if (target === undefined || inputs.some(value => value === undefined)) return;
      anyAvailable = true;
      const sum = inputs.reduce((total, value) => total + value, 0);
      if (Math.abs(target - sum) > 0.01 * Math.max(Math.abs(target), 1)) anyFailure = true;
    });
    if (flags.length || anyFailure) {
      return {kind:'issue', label:uniqueSorted([
        ...flags,
        ...(anyFailure ? ['ROLLUP_RECONCILIATION_MISMATCH'] : []),
      ]).join('; ')};
    }
    if (anyAvailable) {
      return {
        kind:'pass',
        label:boundary.mode === 'DETACHED'
          ? 'Reconciled; intentional DETACHED boundary'
          : 'Rollup reconciled',
      };
    }
    return {
      kind:'unavailable',
      label:boundary.mode === 'DETACHED'
        ? 'Intentional DETACHED boundary; values unavailable'
        : 'Rollup values unavailable',
    };
  };
  const statusMatches = itemStatus => (
    status.value === 'ALL'
    || (status.value === 'ISSUES' && itemStatus.kind === 'issue')
    || (status.value === 'PASS' && itemStatus.kind === 'pass')
    || (status.value === 'UNAVAILABLE' && itemStatus.kind === 'unavailable')
  );
  const descendants = root => {
    const result = new Set();
    const visit = code => {
      if (result.has(code)) return;
      result.add(code);
      (displayChildrenByCode.get(code) || []).forEach(visit);
    };
    visit(root);
    return result;
  };
  const ancestors = code => {
    const result = [];
    let parent = displayParentFor(code);
    while (parent && nodeByCode.has(parent)) {
      result.push(parent);
      parent = displayParentFor(parent);
    }
    return result;
  };
  const rollupMembership = code => boundaries.filter(
    boundary => boundary.label === code || boundary.inputs.includes(code)
  );
  const visibleSets = () => {
    let visibleCodes = sector.value === 'ALL'
      ? new Set(status.value === 'ALL' ? roots : ordinaryNodes.map(node => node.code))
      : new Set([...descendants(sector.value)].filter(code => nodeByCode.has(code)));
    if (basis.value === 'original') {
      visibleCodes = new Set([...visibleCodes].filter(code => originFor(code) !== 'ESTO Extended addition'));
    }
    const query = search.value.trim().toLowerCase();
    if (query) {
      const matches = nodes
        .filter(node => node.code.toLowerCase().includes(query))
        .map(node => node.code);
      const neighbourhood = new Set();
      matches.forEach(code => {
        neighbourhood.add(code);
        ancestors(code).forEach(parent => neighbourhood.add(parent));
        (displayChildrenByCode.get(code) || []).forEach(child => neighbourhood.add(child));
        rollupMembership(code).forEach(boundary => {
          neighbourhood.add(boundary.label);
          boundary.inputs.forEach(input => neighbourhood.add(input));
        });
      });
      visibleCodes = new Set([...neighbourhood].filter(code =>
        nodeByCode.has(code)
        && (basis.value !== 'original' || originFor(code) !== 'ESTO Extended addition')
      ));
      if (!selectedCode && matches.length) selectedCode = matches[0];
    }
    visibleCodes = new Set([...visibleCodes].filter(code => statusMatches(nodeStatus(nodeByCode.get(code)))));
    const filteredBoundaries = boundaries.filter(boundary => {
      if (basis.value === 'original' && originFor(boundary.label) === 'ESTO Extended addition') return false;
      if (!statusMatches(boundaryStatus(boundary))) return false;
      if (query) {
        return boundary.label.toLowerCase().includes(query)
          || boundary.inputs.some(input => input.toLowerCase().includes(query))
          || boundary.inputs.some(input => visibleCodes.has(input));
      }
      if (sector.value !== 'ALL') {
        const sectorCodes = descendants(sector.value);
        return sectorCodes.has(boundary.label) || boundary.inputs.some(input => sectorCodes.has(input));
      }
      return true;
    });
    return {visibleCodes, filteredBoundaries};
  };
  const wrapText = (label, x, y, width = 29) => {
    const words = String(label).split(' ');
    const lines = [];
    let line = '';
    words.forEach(word => {
      if (`${line} ${word}`.trim().length > width && line) {
        lines.push(line);
        line = word;
      } else {
        line = `${line} ${word}`.trim();
      }
    });
    if (line) lines.push(line);
    const shown = lines.slice(0, 2);
    if (lines.length > 2) shown[1] = `${shown[1].slice(0, Math.max(0, width - 1))}…`;
    return shown.map((text, index) =>
      `<tspan x="${x}" y="${y + index * 15}">${escapeHtml(text)}</tspan>`
    ).join('');
  };
  const nodeSvg = (code, x, y, extraClass = '', subtitle = '') => {
    const node = nodeByCode.get(code);
    const origin = originFor(code);
    const statusResult = node ? nodeStatus(node) : {kind:'info', label:''};
    const classes = [
      'node',
      extraClass,
      rollupModesFor(code).map(value => value.toLowerCase()).join(' '),
      roots.includes(code) ? 'root' : '',
      origin === 'ESTO Extended addition' ? 'extended-only' : '',
      statusResult.kind === 'issue' ? 'issue' : '',
    ].filter(Boolean).join(' ');
    return `<g class="${classes}" data-code="${escapeHtml(code)}" transform="translate(${x} ${y})">
      <rect width="250" height="72"/>
      <text>${wrapText(code, 11, 19)}</text>
      ${subtitle ? `<text class="mode" x="11" y="49">${escapeHtml(subtitle)}</text>` : ''}
      <text class="value" x="11" y="64">${escapeHtml(displayedValue(code))}</text>
    </g>`;
  };
  const renderGraph = () => {
    const {visibleCodes, filteredBoundaries} = visibleSets();
    const positions = new Map();
    let hierarchyHeight = 70;
    if (sector.value === 'ALL' && !search.value.trim()) {
      [...visibleCodes].sort().forEach((code, index) => {
        positions.set(code, {x:30 + (index % 4) * 300, y:42 + Math.floor(index / 4) * 92});
      });
      hierarchyHeight = 65 + Math.ceil(Math.max(visibleCodes.size, 1) / 4) * 92;
    } else {
      const depthFor = code => {
        if (sector.value !== 'ALL' && descendants(sector.value).has(code)) {
          let depth = 0;
          let cursor = code;
          while (cursor !== sector.value && displayParentFor(cursor)) {
            depth += 1;
            cursor = displayParentFor(cursor);
          }
          return depth;
        }
        return ancestors(code).length;
      };
      const byDepth = new Map();
      [...visibleCodes].sort().forEach(code => {
        const depth = depthFor(code);
        byDepth.set(depth, [...(byDepth.get(depth) || []), code]);
      });
      [...byDepth.keys()].sort((a, b) => a - b).forEach(depth => {
        byDepth.get(depth).forEach((code, index) => {
          positions.set(code, {x:30 + depth * 290, y:42 + index * 92});
        });
      });
      hierarchyHeight = 75 + Math.max(1, ...[...byDepth.values()].map(values => values.length)) * 92;
    }
    let width = Math.max(1260, ...[...positions.values()].map(position => position.x + 280), 1260);
    const height = Math.max(230, hierarchyHeight + 35);
    naturalSize = {width, height};
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
      <defs>
        <marker id="hierarchy-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#53718f"/></marker>
        <marker id="rollup-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#987216"/></marker>
      </defs>
      <text class="mode" x="30" y="22">${sector.value === 'ALL' ? 'MAJOR SECTORS — COLLAPSED' : 'NORMAL ESTO HIERARCHY — SOLID BLUE EDGES'}</text>`;
    positions.forEach((position, code) => {
      const parent = displayParentFor(code);
      if (positions.has(parent)) {
        const parentPosition = positions.get(parent);
        const relationshipClass = nodeByCode.get(code)?.parent_code === parent ? '' : ' rollup';
        svg += `<path class="edge${relationshipClass}" data-a="${escapeHtml(parent)}" data-b="${escapeHtml(code)}" d="M${parentPosition.x + 250} ${parentPosition.y + 36} C${parentPosition.x + 270} ${parentPosition.y + 36},${position.x - 20} ${position.y + 36},${position.x} ${position.y + 36}"/>`;
      }
    });
    positions.forEach((position, code) => {
      svg += nodeSvg(code, position.x, position.y, '', rollupModesFor(code).join(', '));
    });
    svg += '</svg>';
    canvas.innerHTML = visibleCodes.size || filteredBoundaries.length
      ? svg
      : '<div class="graph-empty">No hierarchy rows or rollups match the selected filters.</div>';
    applyZoom();
    bindNodeSelection();
    renderTable(visibleCodes, filteredBoundaries);
    applySelectionHighlight();
  };
  const tableCell = value => `<td>${escapeHtml(value || '—')}</td>`;
  const splitFlow = value => {
    const parts = String(value || '').split(/ (.+)/);
    return {code:parts[0] || '', label:parts[1] || ''};
  };
  const renderTable = (visibleCodes, filteredBoundaries) => {
    const rows = [];
    [...visibleCodes].sort().forEach(code => {
      const node = nodeByCode.get(code);
      const memberships = rollupMembership(code);
      const result = nodeStatus(node);
      rows.push({
        code:node.flow_code,
        label:node.flow_label,
        parent:displayParentFor(code),
        relationship:node.parent_code
          ? 'Normal hierarchy child'
          : (displayParentFor(code) ? 'Rollup display child' : 'Hierarchy root'),
        rollupType:uniqueSorted(memberships.map(item => item.mode)).join(', '),
        origin:originFor(code),
        childCount:(displayChildrenByCode.get(code) || []).length,
        membership:memberships.map(item => `${item.id} (${item.label === code ? 'target' : 'input'})`).join('; '),
        validation:result.label,
        kind:result.kind,
        detached:false,
      });
    });
    filteredBoundaries.forEach(boundary => {
      const result = boundaryStatus(boundary);
      const boundaryFlow = splitFlow(boundary.label);
      rows.push({
        code:boundaryFlow.code,
        label:boundaryFlow.label,
        parent:boundary.parent,
        relationship:'Registered rollup composition target',
        rollupType:boundary.mode,
        origin:originFor(boundary.label),
        childCount:boundary.children.length,
        membership:`${boundary.id}; inputs: ${boundary.inputs.join(', ')}`,
        validation:result.label,
        kind:result.kind,
        detached:boundary.mode === 'DETACHED',
      });
      boundary.inputs
        .filter(input => !visibleCodes.has(input))
        .forEach(input => {
          const inputFlow = splitFlow(input);
          rows.push({
            code:inputFlow.code,
            label:inputFlow.label,
            parent:'',
            relationship:'Registered rollup input',
            rollupType:boundary.mode,
            origin:originFor(input),
            childCount:0,
            membership:`${boundary.id} (input to ${boundary.label})`,
            validation:result.kind === 'issue'
              ? `Related rollup issue: ${result.label}`
              : (boundary.mode === 'DETACHED' ? 'Intentional DETACHED input' : 'Registered rollup input'),
            kind:result.kind,
            detached:boundary.mode === 'DETACHED',
          });
        });
    });
    tableBody.innerHTML = rows.map(row =>
      `<tr class="${row.kind === 'issue' ? 'issue-row' : ''} ${row.detached ? 'detached-row' : ''}">`
      + tableCell(row.code) + tableCell(row.label) + tableCell(row.parent)
      + tableCell(row.relationship) + tableCell(row.rollupType) + tableCell(row.origin)
      + tableCell(String(row.childCount)) + tableCell(row.membership) + tableCell(row.validation)
      + '</tr>'
    ).join('');
    const issueCount = rows.filter(row => row.kind === 'issue').length;
    const detachedCount = rows.filter(row => row.detached).length;
    tableStatus.textContent = `${rows.length} rows; ${issueCount} genuine issue flags; ${detachedCount} intentional DETACHED boundaries.`;
  };
  const relatedCodes = code => {
    const related = new Set([code]);
    const displayedParent = displayParentFor(code);
    if (displayedParent) related.add(displayedParent);
    (displayChildrenByCode.get(code) || []).forEach(child => related.add(child));
    rollupMembership(code).forEach(boundary => {
      related.add(boundary.label);
      boundary.inputs.forEach(input => related.add(input));
    });
    return related;
  };
  const applySelectionHighlight = () => {
    const elements = canvas.querySelectorAll('[data-code]');
    const edges = canvas.querySelectorAll('.edge');
    if (!selectedCode) {
      elements.forEach(element => element.classList.remove('selected', 'neighbour', 'dimmed'));
      edges.forEach(edge => edge.classList.remove('dimmed'));
      return;
    }
    const related = relatedCodes(selectedCode);
    elements.forEach(element => {
      const code = element.dataset.code;
      element.classList.toggle('selected', code === selectedCode);
      element.classList.toggle('neighbour', code !== selectedCode && related.has(code));
      element.classList.toggle('dimmed', !related.has(code));
    });
    edges.forEach(edge => {
      edge.classList.toggle('dimmed', !related.has(edge.dataset.a) || !related.has(edge.dataset.b));
    });
  };
  const bindNodeSelection = () => {
    canvas.querySelectorAll('[data-code]').forEach(element => {
      element.addEventListener('click', event => {
        event.stopPropagation();
        const code = element.dataset.code;
        if (roots.includes(code) && sector.value === 'ALL' && !search.value.trim()) {
          sector.value = code;
          selectedCode = code;
          renderGraph();
          return;
        }
        if (roots.includes(code) && sector.value === code && selectedCode === code) {
          sector.value = 'ALL';
          selectedCode = '';
          renderGraph();
          return;
        }
        selectedCode = selectedCode === code ? '' : code;
        applySelectionHighlight();
      });
    });
  };
  const applyZoom = () => {
    const svg = canvas.querySelector('svg');
    if (!svg) return;
    svg.style.width = `${naturalSize.width * zoom}px`;
    svg.style.height = `${naturalSize.height * zoom}px`;
  };
  const fitWidth = () => {
    zoom = Math.min(1, Math.max(0.45, (viewport.clientWidth - 20) / naturalSize.width));
    applyZoom();
    viewport.scrollTo({left:0, top:0});
  };
  const refreshSelectors = () => {
    const allSources = sourceOptions();
    const availableSources = basis.value === 'original'
      ? allSources.filter(source => source !== 'ESTO_EXTENDED')
      : allSources;
    if (basis.value === 'compare') {
      rs.disabled = true;
      fill(rs, ['ESTO vs ESTO_EXTENDED'], 'ESTO vs ESTO_EXTENDED');
    } else {
      const selectedSource = availableSources.includes(rs.value)
        ? rs.value
        : (availableSources.includes('ESTO') ? 'ESTO' : availableSources[0]);
      rs.disabled = false;
      fill(rs, availableSources, selectedSource);
    }
    const selectedSources = basis.value === 'compare' ? ['ESTO', 'ESTO_EXTENDED'] : [rs.value];
    const sourceRows = ROLLUP_VALUES.filter(row => selectedSources.includes(row.source_system));
    const scenarios = uniqueSorted(sourceRows.map(row => row.scenario));
    const selectedScenario = scenarios.includes(rc.value) ? rc.value : scenarios[0];
    fill(rc, scenarios, selectedScenario);
    const years = uniqueSorted(
      sourceRows.filter(row => row.scenario === rc.value).map(row => row.year)
    ).sort((a, b) => Number(a) - Number(b));
    const selectedYear = years.some(year => String(year) === String(ry.value)) ? ry.value : years.at(-1);
    fill(ry, years, selectedYear);
    basisState.textContent = basis.value === 'original'
      ? 'Showing original ESTO only'
      : basis.value === 'plus'
        ? 'Showing ESTO plus ESTO Extended (one selected dataset at a time)'
        : 'Comparing ESTO with ESTO Extended (values are not added)';
    renderGraph();
  };

  fill(sector, ['ALL', ...roots], 'ALL');
  sector.options[0].text = 'All major sectors (collapsed)';
  basis.addEventListener('change', refreshSelectors);
  rs.addEventListener('change', refreshSelectors);
  rc.addEventListener('change', refreshSelectors);
  ry.addEventListener('change', renderGraph);
  sector.addEventListener('change', () => { selectedCode = ''; renderGraph(); });
  status.addEventListener('change', renderGraph);
  search.addEventListener('input', renderGraph);
  document.querySelector('#rollup-clear-selection').onclick = () => {
    selectedCode = '';
    search.value = '';
    applySelectionHighlight();
    renderGraph();
  };
  document.querySelector('#rollup-zoom-in').onclick = () => { zoom = Math.min(1.8, zoom * 1.15); applyZoom(); };
  document.querySelector('#rollup-zoom-out').onclick = () => { zoom = Math.max(0.4, zoom / 1.15); applyZoom(); };
  document.querySelector('#rollup-zoom-reset').onclick = () => { zoom = 1; applyZoom(); };
  document.querySelector('#rollup-fit').onclick = fitWidth;
  refreshSelectors();
  fitWidth();
})();
</script>
"""
    raw_esto_context_script = """
<script>
(() => {
  const paintWithRawEsto = () => {
    const commonRows = ROLLUP_VALUES.filter(row => row.source_system === rs.value && row.scenario === rc.value && String(row.year) === String(ry.value));
    const rawSource = rs.value === 'ESTO'
      ? 'ESTO_RAW'
      : rs.value === 'ESTO_EXTENDED'
        ? 'ESTO_EXTENDED_RAW'
        : '';
    const rawRows = rawSource
      ? ROLLUP_VALUES.filter(row => row.source_system === rawSource && row.scenario === rc.value && String(row.year) === String(ry.value))
      : [];
    const commonValues = new Map();
    const rawValues = new Map();
    commonRows.forEach(row => commonValues.set(row.common_flow_label, (commonValues.get(row.common_flow_label) || 0) + Number(row.value)));
    rawRows.forEach(row => rawValues.set(row.common_flow_label, (rawValues.get(row.common_flow_label) || 0) + Number(row.value)));
    const valueFor = flow => commonValues.has(flow) ? commonValues.get(flow) : rawValues.get(flow);
    document.querySelectorAll('[data-rollup-flow]').forEach(element => {
      const value = valueFor(element.dataset.rollupFlow);
      element.textContent = value === undefined ? '—' : value.toLocaleString(undefined, {maximumFractionDigits:2});
    });
    document.querySelectorAll('[data-rollup-target]').forEach(element => {
      const target = valueFor(element.dataset.rollupTarget);
      const inputs = element.dataset.rollupInputs.split('|').filter(Boolean);
      const inputValues = inputs.map(valueFor);
      const unavailable = inputValues.some(value => value === undefined);
      const sum = inputValues.reduce((total, value) => total + (value || 0), 0);
      const ok = !unavailable && target !== undefined && Math.abs(target - sum) <= 0.01 * Math.max(Math.abs(target), 1);
      element.classList.toggle('value-pass', ok);
      element.classList.toggle('value-fail', !unavailable && target !== undefined && !ok);
      element.classList.toggle('value-unavailable', unavailable);
    });
  };
  ry.addEventListener('change', paintWithRawEsto);
  rc.addEventListener('change', paintWithRawEsto);
  rs.addEventListener('change', paintWithRawEsto);
  paintWithRawEsto();
})();
</script>
"""
    extended_source_control_script = """
<script>
(() => {
  const extendedToggle = document.querySelector('#include-esto-extended');
  const extendedControl = document.querySelector('#include-esto-extended-control');
  if (!extendedToggle || !extendedControl) return;
  const sourceOptions = () => unique(
    ROLLUP_VALUES
      .filter(row => row.source_system !== 'ESTO_RAW' && row.source_system !== 'ESTO_EXTENDED_RAW')
      .map(row => row.source_system)
  );
  const hasExtended = sourceOptions().includes('ESTO_EXTENDED');
  if (!hasExtended) {
    extendedControl.hidden = true;
    return;
  }
  const refreshSourceOptions = () => {
    const available = sourceOptions().filter(source => extendedToggle.checked || source !== 'ESTO_EXTENDED');
    const selected = available.includes(rs.value)
      ? rs.value
      : (available.includes('ESTO') ? 'ESTO' : available[0]);
    fill(rs, available, selected);
    refreshScenarios();
    rs.dispatchEvent(new Event('change'));
  };
  extendedToggle.addEventListener('change', refreshSourceOptions);
  refreshSourceOptions();
})();
</script>
"""
    # Value painting and Extended-source selection are handled together by the
    # focused renderer so graph and table cannot drift onto different filters.
    raw_esto_context_script = ""
    extended_source_control_script = ""
    html = html.replace(
        "</body></html>",
        all_sector_graph_script + raw_esto_context_script + extended_source_control_script + "</body></html>",
    )
    output_path = layout["dashboards"] / DIAGNOSTIC_PAGE_NAME
    output_path.write_text(html, encoding="utf-8")
    return {"page": str(output_path), "summary": str(layout["supporting"] / "mapping_diagnostics_summary.csv")}


#%%
