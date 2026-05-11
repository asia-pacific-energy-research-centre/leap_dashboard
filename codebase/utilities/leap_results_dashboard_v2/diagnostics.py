from __future__ import annotations

from pathlib import Path

import pandas as pd

from codebase.utilities.leap_results_dashboard_utils import basic_checks
from codebase.utilities.leap_results_dashboard_v2.output_writer import _write_workbook_with_header_comments
from codebase.utilities.workflow_outputs import build_workflow_output_layout


def _write_gap_and_mapping_diagnostics(
    *,
    comparison_long: pd.DataFrame,
    mapping_status: pd.DataFrame,
    diagnostics_dir: Path,
    mapping_dir: Path,
    base_year: int,
    projection_probe_year: int = 2030,
) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    mapping_dir.mkdir(parents=True, exist_ok=True)

    gap_path = diagnostics_dir / "comparison_gap_diagnostics.csv"
    if not comparison_long.empty:
        comp = comparison_long.copy()
        comp["value"] = pd.to_numeric(comp["value"], errors="coerce")
        wide = (
            comp.pivot_table(
                index=["sheet", "fuel_label", "scenario", "year"],
                columns="source",
                values="value",
                aggfunc="first",
            )
            .reset_index()
        )
        for col in ["leap", "base", "projection", "esto_aggregated"]:
            if col not in wide.columns:
                wide[col] = pd.NA

        base_rows = wide[wide["year"] == base_year].copy()
        base_rows["gap_base"] = pd.to_numeric(base_rows["leap"], errors="coerce") - pd.to_numeric(base_rows["base"], errors="coerce")
        base_rows["abs_gap_base"] = base_rows["gap_base"].abs()
        base_rows["ratio_base_to_leap"] = pd.to_numeric(base_rows["base"], errors="coerce") / pd.to_numeric(base_rows["leap"], errors="coerce")

        proj_rows = wide[wide["year"] == projection_probe_year].copy()
        proj_rows["gap_projection"] = pd.to_numeric(proj_rows["leap"], errors="coerce") - pd.to_numeric(proj_rows["projection"], errors="coerce")
        proj_rows["abs_gap_projection"] = proj_rows["gap_projection"].abs()
        proj_rows["ratio_projection_to_leap"] = pd.to_numeric(proj_rows["projection"], errors="coerce") / pd.to_numeric(proj_rows["leap"], errors="coerce")

        key_cols = ["sheet", "fuel_label", "scenario"]
        merged = base_rows[key_cols + ["leap", "base", "gap_base", "abs_gap_base", "ratio_base_to_leap"]].rename(
            columns={"leap": f"leap_{base_year}", "base": f"base_{base_year}"}
        ).merge(
            proj_rows[key_cols + ["leap", "projection", "gap_projection", "abs_gap_projection", "ratio_projection_to_leap"]].rename(
                columns={"leap": f"leap_{projection_probe_year}", "projection": f"projection_{projection_probe_year}"}
            ),
            on=key_cols,
            how="outer",
        )

        proj_horizon = wide[wide["year"] > base_year].copy()
        proj_cov = (
            proj_horizon.assign(
                leap_present=pd.to_numeric(proj_horizon["leap"], errors="coerce").notna(),
                projection_present=pd.to_numeric(proj_horizon["projection"], errors="coerce").notna(),
            )
            .groupby(key_cols, as_index=False)[["leap_present", "projection_present"]]
            .sum()
            .rename(columns={"leap_present": "leap_year_points", "projection_present": "projection_year_points"})
        )
        merged = merged.merge(proj_cov, on=key_cols, how="left")
        merged["projection_missing_year_points"] = (
            merged["leap_year_points"].fillna(0) - merged["projection_year_points"].fillna(0)
        ).clip(lower=0)

        merged["diagnostic_flag"] = ""
        merged.loc[merged["projection_missing_year_points"] > 0, "diagnostic_flag"] = "missing_projection_points"
        merged.loc[
            (merged["diagnostic_flag"] == "") & (pd.to_numeric(merged["gap_projection"], errors="coerce").fillna(0) < 0),
            "diagnostic_flag",
        ] = "projection_above_leap"
        probe_col = f"leap_{projection_probe_year}"
        proj_col = f"projection_{projection_probe_year}"
        if probe_col in merged.columns and proj_col in merged.columns:
            merged.loc[
                (merged["diagnostic_flag"] == "")
                & (pd.to_numeric(merged[probe_col], errors="coerce") * pd.to_numeric(merged[proj_col], errors="coerce") < 0),
                "diagnostic_flag",
            ] = "sign_mismatch_projection"
        merged.loc[
            (merged["diagnostic_flag"] == "") & (pd.to_numeric(merged["abs_gap_base"], errors="coerce") > 0),
            "diagnostic_flag",
        ] = "base_gap_present"

        merged.sort_values(
            by=["projection_missing_year_points", "abs_gap_projection", "abs_gap_base"],
            ascending=[False, False, False],
            inplace=True,
        )
        merged.to_csv(gap_path, index=False)
        artifacts["gap_diagnostics"] = str(gap_path)

    if not mapping_status.empty:
        status = mapping_status.copy()
        bool_cols = {"has_any_mapping", "base_mapping_complete", "projection_mapping_complete", "partially_mapped", "mapped"}
        for col in [
            "ninth_fuel_code", "esto_flow", "esto_product", "mapping_note",
            "has_any_mapping", "base_mapping_complete", "projection_mapping_complete",
            "partially_mapped", "mapped",
        ]:
            if col not in status.columns:
                status[col] = ""
            if col in bool_cols:
                na_mask = status[col].isna()
                status.loc[na_mask, col] = False
                status[col] = status[col].astype(bool)
            else:
                status[col] = status[col].fillna("").astype(str).str.strip()

        status["missing_ninth_fuel"] = status["ninth_fuel_code"] == ""
        status["missing_esto_flow"] = status["esto_flow"] == ""
        status["missing_esto_product"] = status["esto_product"] == ""
        status["has_mapping_note"] = status["mapping_note"] != ""

        detail_path = mapping_dir / "mapping_rundown_details.xlsx"
        legacy_detail_csv_path = mapping_dir / "mapping_rundown_details.csv"
        try:
            _write_workbook_with_header_comments(status, detail_path, sheet_name="mapping_rundown_details")
        except PermissionError:
            print(
                "[WARN] Could not write mapping_rundown_details workbook because it is in use. "
                f"Close it and rerun if you need it refreshed: {detail_path}"
            )
        if legacy_detail_csv_path.exists():
            try:
                legacy_detail_csv_path.unlink()
            except PermissionError:
                print(
                    "[WARN] Could not remove legacy mapping_rundown_details CSV because it is in use. "
                    f"Close it and remove manually: {legacy_detail_csv_path}"
                )
        artifacts["mapping_rundown_details"] = str(detail_path)

        by_sheet = (
            status.groupby("sheet", as_index=False)
            .agg(
                rows=("sheet", "size"),
                fully_mapped=("mapped", "sum"),
                partially_mapped=("partially_mapped", "sum"),
                any_mapping=("has_any_mapping", "sum"),
                base_mapping_complete=("base_mapping_complete", "sum"),
                projection_mapping_complete=("projection_mapping_complete", "sum"),
                missing_ninth_fuel=("missing_ninth_fuel", "sum"),
                missing_esto_flow=("missing_esto_flow", "sum"),
                missing_esto_product=("missing_esto_product", "sum"),
                with_mapping_notes=("has_mapping_note", "sum"),
            )
            .sort_values(
                by=["fully_mapped", "partially_mapped", "missing_ninth_fuel", "missing_esto_flow", "missing_esto_product", "rows"],
                ascending=[True, False, False, False, False, False],
            )
        )
        by_sheet_path = mapping_dir / "mapping_rundown_by_sheet.csv"
        by_sheet.to_csv(by_sheet_path, index=False)
        artifacts["mapping_rundown_by_sheet"] = str(by_sheet_path)

        aggregate_fuel_audit = status.copy()
        aggregate_fuel_audit["ninth_fuel_code"] = aggregate_fuel_audit["ninth_fuel_code"].astype(str).str.strip()
        aggregate_fuel_audit = aggregate_fuel_audit[
            aggregate_fuel_audit["ninth_fuel_code"].str.contains("_x_", regex=False)
        ].copy()
        if not aggregate_fuel_audit.empty:
            aggregate_fuel_audit = (
                aggregate_fuel_audit.groupby(["sheet", "ninth_fuel_code"], as_index=False)
                .agg(
                    label_count=("fuel_label", "nunique"),
                    fuel_labels=(
                        "fuel_label",
                        lambda s: " | ".join(sorted({str(v).strip() for v in s if str(v).strip()})),
                    ),
                )
                .sort_values(["label_count", "sheet", "ninth_fuel_code"], ascending=[False, True, True])
            )
            aggregate_fuel_audit_path = mapping_dir / "shared_aggregate_fuel_mapping_audit.csv"
            aggregate_fuel_audit.to_csv(aggregate_fuel_audit_path, index=False)
            artifacts["shared_aggregate_fuel_mapping_audit"] = str(aggregate_fuel_audit_path)

    return artifacts


def _write_issue_summary(
    *,
    comparison_long: pd.DataFrame,
    mapping_status: pd.DataFrame,
    diagnostics_dir: Path,
    base_year: int,
    probe_year: int,
    top_n: int,
) -> str | None:
    if comparison_long.empty:
        return None

    comp = comparison_long.copy()
    comp["value"] = pd.to_numeric(comp["value"], errors="coerce")
    comp["year"] = pd.to_numeric(comp["year"], errors="coerce").astype("Int64")
    comp["source_compare"] = comp["source"].replace(
        {
            "base_estimated": "base",
            "base_mixed": "base",
            "projection_estimated": "projection",
            "projection_mixed": "projection",
        }
    )
    comp = comp[comp["source_compare"].isin(["leap", "base", "projection"])].copy()
    if comp.empty:
        return None

    wide = (
        comp.pivot_table(
            index=["sheet", "fuel_label", "scenario", "year"],
            columns="source_compare",
            values="value",
            aggfunc="first",
        )
        .reset_index()
    )
    for col in ["leap", "base", "projection"]:
        if col not in wide.columns:
            wide[col] = pd.NA

    base_rows = wide[wide["year"] == base_year].copy()
    if not base_rows.empty:
        base_rows["base_abs_gap"] = (
            pd.to_numeric(base_rows["leap"], errors="coerce") - pd.to_numeric(base_rows["base"], errors="coerce")
        ).abs()
        base_rows["base_gap_ratio"] = base_rows["base_abs_gap"] / pd.to_numeric(
            base_rows["leap"], errors="coerce"
        ).abs().where(lambda s: s > 1e-9)
    else:
        base_rows = pd.DataFrame(columns=["sheet", "fuel_label", "scenario", "base_abs_gap", "base_gap_ratio"])

    probe_rows = wide[wide["year"] == probe_year].copy()
    if not probe_rows.empty:
        probe_rows["projection_abs_gap"] = (
            pd.to_numeric(probe_rows["leap"], errors="coerce") - pd.to_numeric(probe_rows["projection"], errors="coerce")
        ).abs()
        probe_rows["projection_gap_ratio"] = probe_rows["projection_abs_gap"] / pd.to_numeric(
            probe_rows["leap"], errors="coerce"
        ).abs().where(lambda s: s > 1e-9)
    else:
        probe_rows = pd.DataFrame(
            columns=["sheet", "fuel_label", "scenario", "projection_abs_gap", "projection_gap_ratio"]
        )

    summary = base_rows[
        ["sheet", "fuel_label", "scenario", "base_abs_gap", "base_gap_ratio"]
    ].merge(
        probe_rows[
            ["sheet", "fuel_label", "scenario", "projection_abs_gap", "projection_gap_ratio"]
        ],
        on=["sheet", "fuel_label", "scenario"],
        how="outer",
    )

    status = mapping_status.copy()
    if not status.empty:
        keep_cols = [
            "sheet", "fuel_label", "ninth_fuel_code", "mapping_source",
            "flow_source", "fuel_source", "sector_match_method", "mapping_note",
        ]
        for col in ["comparator_scope", "uses_parent_flow", "allow_parent_estimate"]:
            if col in status.columns:
                keep_cols.append(col)
        status = status[keep_cols].drop_duplicates()
        summary = summary.merge(status, on=["sheet", "fuel_label"], how="left")

    def _as_bool(value: object) -> bool:
        if pd.isna(value):
            return False
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "yes"}

    def _classify_issue(row: pd.Series) -> str:
        mapping_note = str(row.get("mapping_note") or "").strip().lower()
        mapping_source = str(row.get("mapping_source") or "").strip().lower()
        comparator_scope = str(row.get("comparator_scope") or "").strip().lower()
        fuel_label = str(row.get("fuel_label") or "").strip().lower()
        uses_parent_flow = _as_bool(row.get("uses_parent_flow"))
        allow_parent_estimate = _as_bool(row.get("allow_parent_estimate"))
        if comparator_scope == "parent" or (uses_parent_flow and allow_parent_estimate):
            return "parent_comparator_only"
        if "ambiguous canonical matches" in mapping_note:
            return "ambiguous_canonical_mapping"
        if mapping_source in {"canonical_aggregated", "category_sector"}:
            return "aggregated_mapping"
        if "_x_" in str(row.get("ninth_fuel_code") or ""):
            return "aggregate_fuel_mapping"
        if fuel_label in {"others", "other sources"}:
            return "catch_all_fuel_bucket"
        return "direct_mapping_numeric_gap"

    def _agent_hint(row: pd.Series) -> str:
        cause = str(row.get("issue_cause") or "").strip()
        if cause == "parent_comparator_only":
            return "Check whether this child should compare only at the promoted parent sheet."
        if cause == "ambiguous_canonical_mapping":
            return "Review canonical pairs and explicit mappings; the same sector+fuel resolves to multiple ESTO targets."
        if cause == "aggregated_mapping":
            return "This row aggregates multiple targets; verify the aggregation is intended and not masking a missing child mapping."
        if cause == "aggregate_fuel_mapping":
            return "The 9th fuel is an aggregate bucket; compare against sibling fuels and the shared aggregate fuel audit."
        if cause == "catch_all_fuel_bucket":
            return "Catch-all fuel labels often hide reassignment problems; compare against specific fuels in the same sheet."
        return "Mapping looks direct; inspect source data values, signs, and scenario-specific series."

    for col in ["base_abs_gap", "base_gap_ratio", "projection_abs_gap", "projection_gap_ratio"]:
        summary[col] = pd.to_numeric(summary[col], errors="coerce")
    summary["worst_gap_ratio"] = summary[["base_gap_ratio", "projection_gap_ratio"]].max(axis=1, skipna=True)
    summary["worst_abs_gap"] = summary[["base_abs_gap", "projection_abs_gap"]].max(axis=1, skipna=True)
    if "ninth_fuel_code" not in summary.columns:
        summary["ninth_fuel_code"] = pd.NA
    summary["issue_cause"] = summary.apply(_classify_issue, axis=1)
    summary["agent_debug_hint"] = summary.apply(_agent_hint, axis=1)

    ordered = summary.sort_values(
        ["worst_gap_ratio", "worst_abs_gap", "sheet", "fuel_label", "scenario"],
        ascending=[False, False, True, True, True],
        na_position="last",
    ).reset_index(drop=True)

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out_path = diagnostics_dir / "comparison_issue_summary.csv"
    ordered.to_csv(out_path, index=False)

    preview = ordered.head(max(0, int(top_n)))
    if not preview.empty:
        print(f"[INFO] Top comparison issues (base year {base_year}, projection probe {probe_year})")
        display_cols = [
            "sheet", "fuel_label", "scenario", "worst_gap_ratio", "worst_abs_gap",
            "issue_cause", "mapping_source", "comparator_scope", "uses_parent_flow", "allow_parent_estimate",
        ]
        display_cols = [col for col in display_cols if col in preview.columns]
        print(preview[display_cols].to_string(index=False))

    cause_summary = (
        ordered.groupby("issue_cause", dropna=False)
        .agg(
            rows=("issue_cause", "size"),
            max_gap_ratio=("worst_gap_ratio", "max"),
            max_abs_gap=("worst_abs_gap", "max"),
        )
        .reset_index()
        .sort_values(["rows", "max_gap_ratio", "max_abs_gap"], ascending=[False, False, False], na_position="last")
    )
    if not cause_summary.empty:
        cause_path = diagnostics_dir / "comparison_issue_cause_summary.csv"
        cause_summary.to_csv(cause_path, index=False)
        print("[INFO] Issue causes by frequency")
        print(cause_summary.to_string(index=False))

    return str(out_path)


def write_diagnostics(
    *,
    comparison_long: pd.DataFrame,
    mapping_status: pd.DataFrame,
    out_dir: Path,
    base_year: int,
    diagnostic_probe_year: int,
    top_diagnostic_rows: int,
) -> dict[str, str | None]:
    artifacts: dict[str, str | None] = {
        "gap_diagnostics": None,
        "mapping_rundown_by_sheet": None,
        "mapping_rundown_details": None,
        "comparison_issue_summary": None,
        "comparison_issue_cause_summary": None,
    }
    layout = build_workflow_output_layout(out_dir)
    generated = _write_gap_and_mapping_diagnostics(
        comparison_long=comparison_long,
        mapping_status=mapping_status,
        diagnostics_dir=layout.diagnostics,
        mapping_dir=layout.mapping,
        base_year=base_year,
    )
    artifacts.update(generated)
    issue_path = _write_issue_summary(
        comparison_long=comparison_long,
        mapping_status=mapping_status,
        diagnostics_dir=layout.diagnostics,
        base_year=base_year,
        probe_year=diagnostic_probe_year,
        top_n=top_diagnostic_rows,
    )
    artifacts["comparison_issue_summary"] = issue_path
    cause_path = layout.diagnostics / "comparison_issue_cause_summary.csv"
    if cause_path.exists():
        artifacts["comparison_issue_cause_summary"] = str(cause_path)
    return artifacts


def run_basic_checks(
    sheet_map: pd.DataFrame,
    fuel_aliases: dict[str, dict[str, str]],
    comparison_long: pd.DataFrame,
    mapping_status: pd.DataFrame,
) -> dict[str, object]:
    return basic_checks(sheet_map, fuel_aliases, comparison_long, mapping_status)
