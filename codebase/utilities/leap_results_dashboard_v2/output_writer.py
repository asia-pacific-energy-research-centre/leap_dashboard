from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.comments import Comment


_HEADER_NOTES = {
    "mapping_source": {
        "canonical": "Matched directly from config/ninth_pairs_to_esto_pairs.xlsx (main sheet).",
        "codebook_fallback": "Matched from config/sector_fuel_codes_to_names.xlsx using the ESTO_LEAP_names or code_to_name sheet.",
        "explicit": "Matched from config/leap_results_explicit_mappings.csv using an exact sheet/fuel(/sector) override.",
        "override": "Matched from config/backup_leap_mappings.xlsx (manual override).",
    },
    "flow_source": {
        "canonical": "ESTO flow came from config/ninth_pairs_to_esto_pairs.xlsx (main sheet).",
        "explicit": "ESTO flow came from config/leap_results_explicit_mappings.csv using an exact override.",
        "sector_fallback": "ESTO flow came from config/sector_fuel_codes_to_names.xlsx, sheet code_to_name.",
        "sheet_override": "ESTO flow came from config/leap_results_sheet_map.csv, column esto_flow_override.",
        "override": "ESTO flow came from config/backup_leap_mappings.xlsx (manual override).",
    },
    "fuel_source": {
        "canonical": "9th fuel code came from config/ninth_pairs_to_esto_pairs.xlsx (main sheet).",
        "explicit": "9th fuel code came from config/leap_results_explicit_mappings.csv using an exact override.",
        "inferred": "9th fuel code was inferred by the workflow from the ESTO flow and product after the initial lookup.",
        "override": "9th fuel code came from config/backup_leap_mappings.xlsx (manual override).",
    },
    "mapped": {
        "true": "Row is complete for both ESTO base-year and 9th projection comparisons: esto_flow, esto_product, and ninth_fuel_code are all present.",
        "false": "Row is incomplete for at least one comparison requirement; see the completeness flags.",
    },
    "has_any_mapping": {
        "true": "At least one of ninth_fuel_code, esto_flow, or esto_product was filled.",
        "false": "All of ninth_fuel_code, esto_flow, and esto_product are blank.",
    },
    "base_mapping_complete": {
        "true": "Both esto_flow and esto_product are present, so ESTO base-year comparison is well-specified.",
        "false": "At least one of esto_flow or esto_product is missing, so ESTO base-year comparison is incomplete.",
    },
    "projection_mapping_complete": {
        "true": "ninth_fuel_code is present, so the workflow can pull a fuel-specific 9th projection series.",
        "false": "ninth_fuel_code is missing, so projection comparison is incomplete.",
    },
    "partially_mapped": {
        "true": "Some mapping fields are present, but the row is not complete for both ESTO base-year and 9th projection comparisons.",
        "false": "Either the row is fully mapped or nothing was mapped.",
    },
    "missing_ninth_fuel": {
        "true": "ninth_fuel_code is blank.",
        "false": "ninth_fuel_code is present.",
    },
    "missing_esto_flow": {
        "true": "esto_flow is blank.",
        "false": "esto_flow is present.",
    },
    "missing_esto_product": {
        "true": "esto_product is blank.",
        "false": "esto_product is present.",
    },
    "has_mapping_note": {
        "true": "mapping_note contains an extra note for this row.",
        "false": "mapping_note is blank.",
    },
}


def _build_header_note(df: pd.DataFrame, column_name: str) -> str:
    value_notes = _HEADER_NOTES.get(column_name)
    if not value_notes or column_name not in df.columns:
        return ""
    values = (
        df[column_name]
        .dropna()
        .astype(str)
        .str.strip()
        .str.lower()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    if not values:
        return ""
    lines = [f"{column_name} values in this file:"]
    for value in sorted(values):
        lines.append(f"{value}: {value_notes.get(value, 'Used by the workflow; see mapping logic for details.')}")
    return "\n".join(lines)


def _write_workbook_with_header_comments(df: pd.DataFrame, path: Path, *, sheet_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.book[sheet_name]
        for col_idx, column_name in enumerate(df.columns, start=1):
            note = _build_header_note(df, column_name)
            if note:
                worksheet.cell(row=1, column=col_idx).comment = Comment(note, "Codex")


def write_core_outputs(
    *,
    out_dir: Path,
    comparison_long: pd.DataFrame,
    comparison_wide: pd.DataFrame,
    mapping_status: pd.DataFrame,
    leap_long: pd.DataFrame,
    supporting_dir: Path | None = None,
    atomic_comparison_long: pd.DataFrame | None = None,
    atomic_comparison_wide: pd.DataFrame | None = None,
    atomic_mapping_edges: pd.DataFrame | None = None,
    atomic_validation_report: pd.DataFrame | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    comparison_long_path = out_dir / "comparison_long.csv"
    comparison_wide_path = out_dir / "comparison_wide.csv"
    mapping_status_path = out_dir / "mapping_status.xlsx"
    leap_long_path = out_dir / "leap_long.csv"

    comparison_long.to_csv(comparison_long_path, index=False)
    comparison_wide.to_csv(comparison_wide_path, index=False)
    _write_workbook_with_header_comments(mapping_status, mapping_status_path, sheet_name="mapping_status")
    leap_long.to_csv(leap_long_path, index=False)

    atomic_dir = (supporting_dir / "atomic") if supporting_dir is not None else out_dir
    if atomic_dir is not None:
        atomic_dir.mkdir(parents=True, exist_ok=True)

    out = {
        "comparison_long": str(comparison_long_path),
        "comparison_wide": str(comparison_wide_path),
        "mapping_status": str(mapping_status_path),
        "leap_long": str(leap_long_path),
    }
    if atomic_comparison_long is not None:
        p = atomic_dir / "atomic_comparison_long.csv"
        atomic_comparison_long.to_csv(p, index=False)
        out["atomic_comparison_long"] = str(p)
    if atomic_comparison_wide is not None:
        p = atomic_dir / "atomic_comparison_wide.csv"
        atomic_comparison_wide.to_csv(p, index=False)
        out["atomic_comparison_wide"] = str(p)
    if atomic_mapping_edges is not None:
        p = atomic_dir / "atomic_mapping_edges.csv"
        atomic_mapping_edges.to_csv(p, index=False)
        out["atomic_mapping_edges"] = str(p)
    if atomic_validation_report is not None:
        p = atomic_dir / "atomic_validation_report.csv"
        atomic_validation_report.to_csv(p, index=False)
        out["atomic_validation_report"] = str(p)
    return out
