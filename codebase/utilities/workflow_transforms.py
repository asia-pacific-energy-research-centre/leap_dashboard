"""Pure data-transform helpers for the LEAP balance dashboard workflow.

These functions operate only on DataFrames — no file I/O, no config side-effects.
"""
from __future__ import annotations

import pandas as pd

from codebase.utilities.leap_results_dashboard_balance import (
    _split_transformation_input_output_measures,
)


def normalize_base_scenario(comparison_long: pd.DataFrame) -> pd.DataFrame:
    """Rename all source=='base' rows to scenario='ESTO' and deduplicate.

    The base (ESTO) value is a single base-year lookup that gets duplicated once
    per LEAP scenario during comparison assembly. Renaming it to 'ESTO' and
    deduplicating ensures only one copy appears and the VISIBLE_COMPARISON_SERIES
    entry ("base", "ESTO") can match it.
    """
    if comparison_long.empty:
        return comparison_long.copy()
    out = comparison_long.copy()
    out["source"] = out["source"].fillna("").astype(str).str.strip()
    base_mask = out["source"] == "base"
    out.loc[base_mask, "scenario"] = "ESTO"
    key_cols = [c for c in out.columns if c != "value"]
    out = out.drop_duplicates(subset=key_cols, keep="first")
    return out.reset_index(drop=True)


def filter_visible_comparison_series(
    comparison_long: pd.DataFrame,
    visible_series: set[tuple[str, str]],
) -> pd.DataFrame:
    if comparison_long.empty or not visible_series:
        return comparison_long.copy()
    out = comparison_long.copy()
    out["source"] = out["source"].fillna("").astype(str).str.strip()
    out["scenario"] = out["scenario"].fillna("").astype(str).str.strip()
    allowed = {(str(s).strip(), str(sc).strip()) for s, sc in visible_series}
    mask = pd.Series(list(zip(out["source"], out["scenario"])), index=out.index).isin(allowed)
    return out.loc[mask].copy().reset_index(drop=True)


def apply_bunker_abs_values(
    comparison_long: pd.DataFrame,
    bunker_sheet_keys: set[str],
) -> pd.DataFrame:
    if comparison_long.empty:
        return comparison_long.copy()
    out = comparison_long.copy()
    out["sheet"] = out["sheet"].fillna("").astype(str).str.strip()
    if "chart_group_key" not in out.columns:
        out["chart_group_key"] = ""
    out["chart_group_key"] = out["chart_group_key"].fillna("").astype(str).str.strip()
    bunker_mask = out["chart_group_key"].isin(bunker_sheet_keys) | out["sheet"].isin(bunker_sheet_keys)
    if bunker_mask.any():
        out.loc[bunker_mask, "value"] = pd.to_numeric(out.loc[bunker_mask, "value"], errors="coerce").abs()
    return out


def comparison_wide_from_long(comparison_long: pd.DataFrame) -> pd.DataFrame:
    index_cols = [
        "economy", "scenario", "sheet", "page_key", "page_label",
        "chart_group_key", "chart_group_label", "measure", "fuel_label", "year",
    ]
    if comparison_long.empty:
        return pd.DataFrame(columns=index_cols)
    work = comparison_long.copy()
    for col in index_cols:
        if col not in work.columns:
            work[col] = ""
    return (
        work.pivot_table(index=index_cols, columns="source", values="value", aggfunc="sum")
        .reset_index()
        .rename_axis(columns=None)
        .sort_values(["scenario", "page_key", "chart_group_key", "measure", "fuel_label", "year"], kind="mergesort")
        .reset_index(drop=True)
    )


def chart_series_snapshot(chart_line_ledger: pd.DataFrame) -> pd.DataFrame:
    """Aggregate chart_line_mapping_ledger to one value row per series/year."""
    columns = ["dashboard_section_label", "esto_flow_group_label", "fuel_label", "source", "year", "value"]
    if chart_line_ledger.empty:
        return pd.DataFrame(columns=columns)
    work = chart_line_ledger.copy()
    for col in columns[:-1]:
        if col not in work.columns:
            work[col] = ""
    work["value"] = pd.to_numeric(work.get("value", pd.Series(dtype=float)), errors="coerce")
    return (
        work.groupby(columns[:-1], dropna=False)["value"]
        .sum()
        .reset_index()
        .sort_values(columns[:-1])
        .reset_index(drop=True)
    )


def split_directional_balance_rows_for_charts(
    comparison_long: pd.DataFrame,
    resolved_structure: dict,
) -> pd.DataFrame:
    """Split signed transformation and transfer rows before charting.

    The shared helper keys off dashboard structure. `08 Transfers` is routed
    under Other transformation, so it is split into input/output magnitudes
    before chart ledgers and rendered charts are built.
    """
    return _split_transformation_input_output_measures(
        comparison_long,
        resolved_structure.get("sheet_catalog", {}),
    )
