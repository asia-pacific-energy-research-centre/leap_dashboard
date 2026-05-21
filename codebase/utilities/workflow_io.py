"""File I/O and filtering helpers for the LEAP balance dashboard workflow."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from codebase.utilities.leap_results_dashboard_balance import build_ninth_balance_esto_long_table
from codebase.utilities.workflow_transforms import chart_series_snapshot

_LEAP_ROWS_TO_REMOVE_AND_ADD_SHEET = "leap_rows_to_remove_and_add"


def _normalize_key(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _mapping_file_hash(mapping_path: Path) -> str:
    h = hashlib.sha256()
    with open(mapping_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON config file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_ignored_unmapped_issue_keys(mapping_workbook_path: Path) -> set[tuple[str, str]]:
    if not mapping_workbook_path.exists():
        return set()
    try:
        sheet = pd.read_excel(
            mapping_workbook_path,
            sheet_name=_LEAP_ROWS_TO_REMOVE_AND_ADD_SHEET,
            dtype=str,
        ).fillna("")
    except Exception:
        return set()
    for col in ["leap_sector_name_full_path", "raw_leap_fuel_name"]:
        if col not in sheet.columns:
            sheet[col] = ""
    keys = set()
    for _, row in sheet.iterrows():
        sector = _normalize_key(row.get("leap_sector_name_full_path", ""))
        fuel = _normalize_key(row.get("raw_leap_fuel_name", ""))
        if sector and fuel:
            keys.add((sector, fuel))
    return keys


def issue_source_key(row: pd.Series) -> tuple[str, str]:
    sector = _normalize_key(row.get("mapping_key_sector", "") or row.get("leap_sector_name_full_path", ""))
    fuel = _normalize_key(row.get("mapping_key_fuel", "") or row.get("leap_product_name", "") or row.get("leap_product", ""))
    return sector, fuel


def filter_ignored_unmapped_issues(
    runtime_issues: pd.DataFrame,
    *,
    mapping_workbook_path: Path,
) -> pd.DataFrame:
    if runtime_issues.empty:
        return runtime_issues.copy()
    ignored_keys = load_ignored_unmapped_issue_keys(mapping_workbook_path)
    if not ignored_keys:
        return runtime_issues.copy()
    work = runtime_issues.copy()
    reason = (
        work["reason"].fillna("").astype(str).str.strip().str.lower()
        if "reason" in work.columns
        else pd.Series("", index=work.index)
    )
    unmapped_mask = reason.eq("missing_esto_pair")
    if not unmapped_mask.any():
        return work
    source_keys = work.loc[unmapped_mask].apply(issue_source_key, axis=1)
    suppress_mask = pd.Series(False, index=work.index)
    suppress_mask.loc[unmapped_mask] = source_keys.map(lambda key: key in ignored_keys).to_numpy()
    return work.loc[~suppress_mask].copy()


def raise_if_unmapped_balance_rows(
    runtime_issues: pd.DataFrame,
    runtime_issues_path: Path,
    *,
    fail_on_unmapped: bool,
) -> None:
    if runtime_issues.empty or not fail_on_unmapped:
        return
    reason_counts = (
        runtime_issues.groupby("reason", dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["row_count", "reason"], ascending=[False, True])
    )
    counts_text = ", ".join(
        f"{row.reason}: {int(row.row_count)}" for row in reason_counts.itertuples(index=False)
    )
    raise RuntimeError(
        "Unmapped LEAP balance rows remain after writing dashboard outputs. "
        f"See {runtime_issues_path}. Counts: {counts_text}"
    )


def load_cached_ingestion(
    structure_config: dict,
    balance_to_esto_long_output_dir: Path,
) -> tuple[dict, dict, dict]:
    """Load ingestion sub-tables written by a previous extraction run.

    Returns (conversion, ingestion, resolved_structure) matching the shapes
    produced by convert_leap_balances_to_esto_long_table(). Fields not written
    to the shared cache (e.g. matching_diagnostics) are returned as empty DataFrames.
    """
    shared_dir = Path(balance_to_esto_long_output_dir)
    support_dir = shared_dir / "supporting_files"

    def _rcsv(path: Path) -> pd.DataFrame:
        return pd.read_csv(path, dtype=str, low_memory=False).fillna("") if path.exists() else pd.DataFrame()

    def _rjson(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    ingestion: dict = {
        "leap_long": _rcsv(support_dir / "leap_balance_mapped_detail_long.csv"),
        "mapping_status": _rcsv(support_dir / "leap_balance_mapping_status.csv"),
        "issues": _rcsv(support_dir / "leap_balance_runtime_issues.csv"),
        "override_report": _rcsv(support_dir / "leap_balance_override_application_report.csv"),
        "auto_sheet_rows": _rcsv(support_dir / "auto_sheet_rows.csv"),
        "coverage": _rcsv(support_dir / "leap_balance_coverage.csv"),
        "unit_diagnostics": _rcsv(support_dir / "leap_balance_unit_diagnostics.csv"),
        "matching_diagnostics": pd.DataFrame(),
        "extraction_summary": _rjson(support_dir / "leap_balance_extraction_summary.json"),
        "resolved_structure": _rjson(support_dir / "resolved_structure_config.json"),
    }
    resolved_structure = ingestion["resolved_structure"] or structure_config
    conversion: dict = {
        "esto_long": _rcsv(shared_dir / "leap_balance_esto_long.csv"),
        "ingestion": ingestion,
        "pre_group_leap_mapped": pd.DataFrame(),
        "pre_group_incomplete_rows": pd.DataFrame(),
        "issues": ingestion["issues"],
        "override_report": ingestion["override_report"],
        "auto_sheet_rows": ingestion["auto_sheet_rows"],
        "coverage": ingestion["coverage"],
        "unit_diagnostics": ingestion["unit_diagnostics"],
        "extraction_summary": ingestion["extraction_summary"],
        "resolved_structure": resolved_structure,
    }
    return conversion, ingestion, resolved_structure


def load_cached_comparison(layout) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Load comparison_long, mapping_status, and leap_long from a previous run.

    Returns (comparison_long, mapping_status, leap_long, comparison_stub).
    The stub contains empty DataFrames for fields not cached separately.
    """
    comparison_long_path = layout.root / "comparison_long.csv"
    mapping_status_path = layout.root / "mapping_status.xlsx"
    leap_long_path = layout.root / "leap_long.csv"

    comparison_long = (
        pd.read_csv(comparison_long_path, dtype=str, low_memory=False).fillna("")
        if comparison_long_path.exists()
        else pd.DataFrame()
    )
    mapping_status = (
        pd.read_excel(mapping_status_path, dtype=str, sheet_name="mapping_status").fillna("")
        if mapping_status_path.exists()
        else pd.DataFrame()
    )
    leap_long = (
        pd.read_csv(leap_long_path, dtype=str, low_memory=False).fillna("")
        if leap_long_path.exists()
        else pd.DataFrame()
    )
    comparison_stub: dict = {"base_df": pd.DataFrame(), "ninth_df": pd.DataFrame(), "mapping_inputs": {}}
    return comparison_long, mapping_status, leap_long, comparison_stub


def write_dashboard_about_supplements(
    *,
    dashboards_dir: Path,
    template_json_path: Path,
) -> None:
    """Copy the dashboard JSON template into dashboards_dir, then patch about.html."""
    json_filename = "dashboard_template.json"
    if template_json_path.exists():
        shutil.copy2(template_json_path, dashboards_dir / json_filename)
    about_path = dashboards_dir / "about.html"
    if not about_path.exists():
        return
    html = about_path.read_text(encoding="utf-8")
    extra = (
        '<section class="about-section"><h2>Reference files</h2>'
        "<ul>"
        f'<li><a href="{json_filename}">dashboard_template.json</a>'
        " - the chart navigation template that defines the ESTO-axis structure and dashboard sections.</li>"
        "</ul>"
        "</section>"
        '<section class="about-section"><h2>Note on losses and own use</h2>'
        "<p>Losses and own use are still a work in progress in the LEAP model."
        " In the transformation sector, LEAP currently models only electricity transmission and distribution losses directly."
        " Other losses and own-use lines are handled in the demand sector under Other loss and own use.</p>"
        "<p>The demand-sector approach is iterative."
        " First-pass values are estimated from the 9th edition loss and own-use series."
        " After the relevant proxy sector has been projected, that projected activity is used as the activity proxy."
        " Loss and own-use intensities are then calculated from historical ESTO ratios and applied to the proxy activity."
        " These rows should therefore be read as proxy-based estimates rather than fully final transformation-sector results.</p>"
        "</section>"
    )
    if "</article>" in html:
        html = html.replace("</article>", extra + "</article>", 1)
        about_path.write_text(html, encoding="utf-8")


def write_chart_series_snapshot_and_maybe_delta(
    chart_line_ledger: pd.DataFrame,
    snapshot_path: Path,
    delta_path: Path,
    mapping_path: Path,
    hash_path: Path,
) -> bool:
    """Write a chart-series snapshot and a delta CSV when the mapping workbook changed."""
    current_snapshot = chart_series_snapshot(chart_line_ledger)
    if "year" in current_snapshot.columns:
        current_snapshot["year"] = current_snapshot["year"].astype(str)
    current_hash = _mapping_file_hash(mapping_path) if mapping_path.exists() else ""
    stored_hash = hash_path.read_text(encoding="utf-8").strip() if hash_path.exists() else ""
    mapping_changed = current_hash != stored_hash

    delta_written = False
    if mapping_changed and snapshot_path.exists():
        previous_snapshot = pd.read_csv(snapshot_path, dtype={"year": str})
        previous_snapshot["value"] = pd.to_numeric(previous_snapshot["value"], errors="coerce")
        merge_cols = ["dashboard_section_label", "esto_flow_group_label", "fuel_label", "source", "year"]
        merged = current_snapshot.merge(previous_snapshot, on=merge_cols, how="outer", suffixes=("_after", "_before"))
        merged["value_after"] = merged["value_after"].fillna(0.0)
        merged["value_before"] = merged["value_before"].fillna(0.0)
        merged["delta"] = merged["value_after"] - merged["value_before"]
        delta = merged[merged["delta"].abs() > 1e-9].copy()
        if not delta.empty:
            delta[merge_cols + ["value_before", "value_after", "delta"]].to_csv(delta_path, index=False)
            delta_written = True

    current_snapshot.to_csv(snapshot_path, index=False)
    if current_hash:
        hash_path.write_text(current_hash, encoding="utf-8")
    return delta_written


def write_shared_balance_to_esto_outputs(
    *,
    conversion: dict[str, object],
    mapping_status: pd.DataFrame,
    comparison_long: pd.DataFrame,
    simple_ninth_balance: pd.DataFrame,
    output_dir: Path,
) -> dict[str, str]:
    out_dir = Path(output_dir)
    support_dir = out_dir / "supporting_files"
    out_dir.mkdir(parents=True, exist_ok=True)
    support_dir.mkdir(parents=True, exist_ok=True)

    leap_path = out_dir / "leap_balance_esto_long.csv"
    ninth_path = out_dir / "ninth_balance_esto_long.csv"
    detail_path = support_dir / "leap_balance_mapped_detail_long.csv"
    mapping_status_path = support_dir / "leap_balance_mapping_status.csv"
    comparison_long_path = support_dir / "esto_axis_comparison_long.csv"
    ninth_semantic_path = support_dir / "ninth_balance_esto_long_semantic_columns.csv"
    runtime_issues_path = support_dir / "leap_balance_runtime_issues.csv"
    override_report_path = support_dir / "leap_balance_override_application_report.csv"
    auto_sheet_path = support_dir / "auto_sheet_rows.csv"
    coverage_path = support_dir / "leap_balance_coverage.csv"
    unit_diag_path = support_dir / "leap_balance_unit_diagnostics.csv"
    extraction_summary_path = support_dir / "leap_balance_extraction_summary.json"
    resolved_structure_path = support_dir / "resolved_structure_config.json"

    conversion["esto_long"].to_csv(leap_path, index=False)
    build_ninth_balance_esto_long_table(simple_ninth_balance).to_csv(ninth_path, index=False)
    conversion["leap_long"].to_csv(detail_path, index=False)
    mapping_status.to_csv(mapping_status_path, index=False)
    comparison_long.to_csv(comparison_long_path, index=False)
    simple_ninth_balance.to_csv(ninth_semantic_path, index=False)
    conversion["issues"].to_csv(runtime_issues_path, index=False)
    conversion["override_report"].to_csv(override_report_path, index=False)
    conversion["auto_sheet_rows"].to_csv(auto_sheet_path, index=False)
    conversion["coverage"].to_csv(coverage_path, index=False)
    conversion["unit_diagnostics"].to_csv(unit_diag_path, index=False)
    extraction_summary_path.write_text(
        json.dumps(conversion["extraction_summary"], ensure_ascii=True, indent=2), encoding="utf-8",
    )
    resolved_structure_path.write_text(
        json.dumps(conversion["resolved_structure"], ensure_ascii=True, indent=2), encoding="utf-8",
    )
    return {
        "shared_leap_balance_esto_long": str(leap_path),
        "shared_ninth_balance_esto_long": str(ninth_path),
        "shared_supporting_files_dir": str(support_dir),
    }
