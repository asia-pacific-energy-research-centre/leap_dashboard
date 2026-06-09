#%%
"""
Load LEAP balance exports into dataframes for ESTO-axis balance comparisons.

This workflow extracts REF/TGT LEAP balance workbooks into long-form mapped
rows, then compares them against ESTO and 9th reference data using ESTO balance
rows as the chart axis. It writes the comparison tables, mapping diagnostics,
ledgers, and rendered dashboard outputs under the configured output directory.

Why ESTO axis:
- ESTO flow/product rows are a practical middle ground for balance-table
  comparison. They are usually less granular than the full 9th sector/fuel
  hierarchy, but more structured and comparable than raw LEAP balance labels.
- The workflow maps LEAP balance cells to ESTO flow/product pairs and maps 9th
  sector/fuel projections back to those same ESTO pairs, so LEAP, ESTO, and 9th
  can be compared on one common axis.
- Mapping lineage is the primary source of truth for charted 9th rows. The
  workflow should first use mappings carried through the LEAP mapping lineage
  audit path. Template-level use_esto_to_ninth_mapping is a fallback for
  ESTO-axis rows where no LEAP-derived mapping lineage can be created; it
  reaches directly into the ESTO-to-9th canonical mapping and should not replace
  valid LEAP-derived lineage.
- The dashboard target universe is built from the active
  ESTO -> LEAP -> 9th crosswalk in config/leap_mappings.xlsx:
  leap_combined_esto is joined to leap_combined_ninth on the LEAP sector/fuel
  path before chart rows are generated. This means mapped 9th rows can still be
  shown when the corresponding LEAP export row is zero or absent, as long as the
  9th pair is nonzero in the requested projection slice.
- LEAP-backed rows get priority when many ESTO products share the same 9th
  sector/fuel pair. Workbook-only template rows fill gaps, but should not steal
  shared 9th values from rows that have direct LEAP balance evidence.
- Transformation and transfer charts split signed balance rows at render time:
  negative values are inputs and displayed as positive magnitudes; positive
  values are outputs.
- Simple audit outputs are written for the key ESTO-axis inputs:
  LEAP-to-ESTO rows, 9th-to-ESTO rows, and the combined comparison table.
- See docs/esto_axis_balance_dashboard_system.md for the full system guide,
  including mapping expansion, subtotal rules, many-to-many behavior, and
  debugging steps.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.utilities.leap_results_dashboard_balance import (  # noqa: E402
    attach_chart_groups_to_dashboard_exposure,
    attach_chart_groups_to_mapping_lineage_audit,
    build_mapped_ninth_to_esto_balance_rows,
    build_mapping_lineage_audit_table,
    build_merged_esto_axis_balance_table,
    build_simple_balance_duplicate_diagnostics,
    build_simple_ninth_balance_table,
    build_balance_comparison_esto_axis,
    build_esto_axis_structure_from_dashboard_template,
    convert_leap_balances_to_esto_long_table,
    render_balance_dashboards,
    simplify_chart_line_mapping_ledger_output,
    simplify_chart_total_component_ledger_output,
    simplify_mapping_lineage_audit_output,
    write_balance_missing_mapping_candidates,
    write_dashboard_comparator_pair_coverage,
    write_ninth_mapping_data_coverage,
    write_runtime_missing_pair_summary,
)
from codebase.utilities.leap_results_dashboard_utils import _prepare_render_long  # noqa: E402
from codebase.utilities.leap_results_dashboard_v2.comparison_engine import (  # noqa: E402
    build_chart_line_mapping_ledger,
    build_total_component_ledger,
)
from codebase.utilities.leap_results_dashboard_v2.diagnostics import write_diagnostics  # noqa: E402
from codebase.utilities.leap_results_dashboard_v2.output_writer import write_core_outputs  # noqa: E402
from codebase.utilities.leap_balance_export_resolver import resolve_balance_export_workbook  # noqa: E402
from codebase.utilities.workflow_common import (  # noqa: E402
    WorkflowTimer,
    archive_config_dir_once_per_day,
)
from codebase.utilities.workflow_outputs import build_workflow_output_layout, write_output_manifest  # noqa: E402
from codebase.utilities.output_paths import BALANCE_TABLES_ROOT  # noqa: E402
from codebase.utilities.workflow_transforms import (  # noqa: E402
    normalize_base_scenario as _normalize_base_scenario,
    filter_visible_comparison_series as _filter_visible_comparison_series,
    apply_bunker_abs_values as _apply_bunker_abs_values,
    comparison_wide_from_long as _comparison_wide_from_long,
    split_directional_balance_rows_for_charts as _split_directional_balance_rows_for_charts,
)
from codebase.utilities.workflow_io import (  # noqa: E402
    load_json as _load_json,
    load_cached_ingestion as _load_cached_ingestion,
    load_cached_comparison as _load_cached_comparison,
    filter_ignored_unmapped_issues as _filter_ignored_unmapped_issues,
    raise_if_unmapped_balance_rows as _raise_if_unmapped_balance_rows,
    write_dashboard_about_supplements as _write_dashboard_about_supplements,
    write_chart_series_snapshot_and_maybe_delta as _write_chart_series_snapshot_and_maybe_delta,
    write_shared_balance_to_esto_outputs as _write_shared_balance_to_esto_outputs,
)


#%%
def _resolve(path: Path | str) -> Path:
    raw = str(path).replace("\\", "/")
    drive_match = re.match(r"^([a-zA-Z]):/(.*)$", raw)
    if drive_match:
        drive = drive_match.group(1).lower()
        rest = drive_match.group(2)
        if os.name == "nt":
            return Path(f"{drive.upper()}:/{rest}")
        return Path(f"/mnt/{drive}/{rest}")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate)


def _shared_repo_root() -> Path:
    """Return the sibling leap_utilities repo used for shared inputs."""
    return _resolve(os.environ.get("LEAP_UTILITIES_ROOT", "../leap_utilities"))


def _require_shared_file(path: Path, *, description: str) -> Path:
    if path.exists():
        return path
    raise FileNotFoundError(
        f"Missing shared {description}: {path}\n"
        "Install or clone the leap_utilities repo next to leap_dashboard, or set "
        "LEAP_UTILITIES_ROOT to its location. Expected layout example: "
        "C:/Users/Work/github/leap_utilities."
    )


def _mapping_workbook(mapping_ref: tuple[Path, str]) -> Path:
    return mapping_ref[0]


def _economy_token(economy_code: str) -> str:
    """Derive a short token from a LEAP economy code, e.g. '12_NZ' -> 'NZ'."""
    return re.sub(r"^\d+_?", "", economy_code.strip())


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


#%%
# ---------------------------------------------------------------------------
# Configuration — the only section most users need to edit.
# ---------------------------------------------------------------------------

# Economy codes to process. Each run writes both dashboard site files and
# supporting analytical outputs under outputs/{token}/.
# Examples: "12_NZ", "20_USA""12_NZ",
ECONOMIES: list[str] = [ "20_USA"]

# Optional per-run date overrides for locating workbook files (None = auto-detect latest).
REF_BALANCE_EXPORT_DATE_ID: str | None = None
TGT_BALANCE_EXPORT_DATE_ID: str | None = None

KNOWN_ISSUES_CONFIG_PATH = _resolve("config/leap_results_balance_known_issues.json")
# Optional override to switch dashboard templates without code edits.
# Useful when maintaining both high-detail and low-detail template variants.
# Example:
#   LEAP_DASHBOARD_TEMPLATE_PATH=config/leap_comparison_dashboard_template_v3.json
CHART_NAVIGATION_GUIDE_PATH = _resolve(
    os.getenv("LEAP_DASHBOARD_TEMPLATE_PATH", "config/leap_comparison_dashboard_template_v3.json")
)
LEAP_ROWS_TO_REMOVE_AND_ADD_SHEET = "leap_rows_to_remove_and_add"
LEAP_UTILITIES_ROOT = _shared_repo_root()
SHARED_CONFIG_DIR = LEAP_UTILITIES_ROOT / "config"
SHARED_DATA_DIR = LEAP_UTILITIES_ROOT / "data"
SHARED_LEAP_MAPPINGS_PATH = _require_shared_file(
    SHARED_CONFIG_DIR / "leap_mappings.xlsx",
    description="LEAP mapping workbook",
)
SHARED_MASTER_CONFIG_PATH = _require_shared_file(
    SHARED_CONFIG_DIR / "master_config.xlsx",
    description="master config workbook",
)
SHARED_BASE_TABLE_PATH = _require_shared_file(
    SHARED_DATA_DIR / "00APEC_2025_low_with_subtotals.csv",
    description="ESTO base table",
)
SHARED_PROJECTION_TABLE_PATH = _require_shared_file(
    SHARED_DATA_DIR / "merged_file_energy_ALL_20251106.csv",
    description="9th projection table",
)

LEAP_MAPPING_WORKBOOK_OVERRIDE = os.getenv("LEAP_MAPPING_WORKBOOK_PATH", "").strip()
ACTIVE_LEAP_MAPPINGS_PATH = (
    _resolve(LEAP_MAPPING_WORKBOOK_OVERRIDE)
    if LEAP_MAPPING_WORKBOOK_OVERRIDE
    else SHARED_LEAP_MAPPINGS_PATH
)

LEAP_TO_ESTO_MAPPING = (ACTIVE_LEAP_MAPPINGS_PATH, "leap_combined_esto")
NINTH_TO_ESTO_MAPPING = (SHARED_MASTER_CONFIG_PATH, "ninth_pairs_to_esto_pairs")
CODEBOOK_PATH = SHARED_MASTER_CONFIG_PATH
SHEET_MAP_PATH = _resolve("config/leap_results_sheet_map.csv")
BACKUP_MAPPINGS_PATH = _resolve("config/backup_leap_mappings.xlsx")
EXPLICIT_MAPPINGS_PATH = _resolve("config/leap_results_explicit_mappings.csv")
EXPLICIT_REASSIGNMENTS_PATH = _resolve("config/leap_results_explicit_reassignments.csv")
SYNTHETIC_REFERENCE_ROWS_PATH = _resolve("config/synthetic_reference_rows.csv")

BASE_TABLE_PATH = SHARED_BASE_TABLE_PATH
PROJECTION_TABLE_PATH = SHARED_PROJECTION_TABLE_PATH

# Mapping behavior for LEAP balance extraction. Keep these explicit because
# low-detail LEAP exports can otherwise let parent rows inherit many child
# mappings and create overly broad dashboard lineage groups.
EXPLICIT_PAIR_MAPPINGS_ONLY = True
ALLOW_DESCENDANT_MAPPING_EXPANSION = False

BASE_YEAR = 2022
MAX_OUTPUT_YEAR = 2060
PROJECTION_YEARS: Sequence[int] = tuple(range(BASE_YEAR + 1, MAX_OUTPUT_YEAR + 1))
SCENARIO_MAP = {"Reference": "reference", "Target": "target"}

CHART_BACKEND = "plotly"
CHART_OUTPUT_MODE = "page_bundles"
HIDE_LEAP_ONLY_CHARTS = False
# When True, charts with no non-zero LEAP series are omitted from the dashboard.
# Helpful for reduced-detail exports to avoid placeholder pages/charts driven only
# by ESTO/9th values when LEAP has no data for that line.
HIDE_CHARTS_WITHOUT_LEAP_DATA = _env_flag("HIDE_CHARTS_WITHOUT_LEAP_DATA", default=False)
APPLY_EXPLICIT_REFERENCE_REASSIGNMENTS = False
ENABLE_WORKFLOW_TIMING = True
WRITE_WORKFLOW_TIMING_CSV = True
WORKFLOW_TIMING_FILENAME = "workflow_stage_timings.csv"

# Stage control — set False to skip a stage and reload cached outputs instead.
# Run the full workflow at least once before skipping any stage.
#   STAGE_EXTRACT           reads LEAP Excel workbooks (typically the slowest step)
#   STAGE_COMPARE           builds the ESTO-axis comparison (reads large projection CSVs)
#   STAGE_WRITE_OUTPUTS     writes comparison tables, simple balance tables, diagnostics
#   STAGE_RENDER_DASHBOARDS renders HTML dashboards (slow for large chart sets)
#   STAGE_WRITE_COVERAGE    writes coverage, runtime issues, and mapping checks
# Common skip patterns:
#   Re-render only:   STAGE_EXTRACT=False, STAGE_COMPARE=False, STAGE_WRITE_OUTPUTS=False, STAGE_WRITE_COVERAGE=False
#   Skip Excel read:  STAGE_EXTRACT=False
STAGE_EXTRACT: bool = True
STAGE_COMPARE: bool = True
STAGE_WRITE_OUTPUTS: bool = True
STAGE_RENDER_DASHBOARDS: bool = True
STAGE_WRITE_COVERAGE: bool = True

# Controls which source/scenario series are written and rendered.
# Source labels: "base" = ESTO base-year data, "projection" = 9th projection, "leap" = LEAP balance export.
VISIBLE_COMPARISON_SERIES: set[tuple[str, str]] = {
    ("base", "ESTO"),
    # ("projection", "Reference"),
    ("projection", "Target"),
    ("leap", "Target"),
}
BUNKER_SHEET_KEYS = {
    "esto__04__International_marine_bunkers",
    "esto__05__International_aviation_bunkers",
}
FAIL_ON_UNMAPPED_BALANCE_ROWS = os.getenv("FAIL_ON_UNMAPPED_BALANCE_ROWS", "1").strip().lower() in {
    "1", "true", "yes", "y",
}


#%%
# ---------------------------------------------------------------------------
# Stage functions — each function contains the data operations for one phase.
# This is where the workflow logic lives; run_workflow() is just the orchestrator.
# ---------------------------------------------------------------------------

def _stage_extract(
    *,
    run: bool,
    ref_workbook_path,
    tgt_workbook_path,
    structure_config: dict,
    known_issues: dict,
    projection_economy: str,
    max_output_year: int,
    codebook_path: Path,
    mapping_workbook_path: Path,
    balance_to_esto_long_output_dir: Path,
    timer,
) -> tuple[dict, dict, dict]:
    """Read LEAP Excel workbooks and map balance rows to ESTO flow/product pairs.

    Returns (conversion, ingestion, resolved_structure).
    """
    if run:
        conversion = convert_leap_balances_to_esto_long_table(
            ref_workbook_path=ref_workbook_path,
            tgt_workbook_path=tgt_workbook_path,
            template_sheet="EBal|2060",
            mapping_pairs_path=mapping_workbook_path,
            codebook_path=codebook_path,
            structure_config=structure_config,
            known_issues=known_issues,
            projection_economy=projection_economy,
            max_output_year=max_output_year,
            explicit_pair_mappings_only=EXPLICIT_PAIR_MAPPINGS_ONLY,
            allow_descendant_mapping_expansion=ALLOW_DESCENDANT_MAPPING_EXPANSION,
        )
        ingestion = conversion["ingestion"]
        resolved_structure = ingestion.get("resolved_structure", structure_config)
    else:
        print("[SKIP] Stage: extract and map LEAP balance workbooks - loading cached outputs")
        conversion, ingestion, resolved_structure = _load_cached_ingestion(
            structure_config=structure_config,
            balance_to_esto_long_output_dir=balance_to_esto_long_output_dir,
        )
    timer.lap("extract and map LEAP balance workbooks")
    return conversion, ingestion, resolved_structure


def _raise_if_visible_leap_scenarios_use_mixed_detail(
    ingestion: dict,
    visible_comparison_series: set[tuple[str, str]],
) -> None:
    visible_leap_scenarios = {
        str(scenario).strip().lower()
        for source, scenario in visible_comparison_series
        if str(source).strip().lower() == "leap"
    }
    if not {"reference", "target"}.issubset(visible_leap_scenarios):
        return

    extraction_summary = ingestion.get("extraction_summary", {})
    ref_detail_mode = str(extraction_summary.get("ref", {}).get("detail_mode", "")).strip()
    tgt_detail_mode = str(extraction_summary.get("tgt", {}).get("detail_mode", "")).strip()
    if not ref_detail_mode or not tgt_detail_mode or ref_detail_mode == tgt_detail_mode:
        return

    raise RuntimeError(
        "REF and TGT LEAP balance workbooks use different detected detail modes "
        "while both LEAP Reference and LEAP Target are configured as visible series. "
        f"REF detail_mode={ref_detail_mode!r}; TGT detail_mode={tgt_detail_mode!r}. "
        "Export both scenarios at the same LEAP detail level, or hide one LEAP scenario "
        "from VISIBLE_COMPARISON_SERIES."
    )


def _raise_if_visible_leap_scenarios_are_not_detailed(
    ingestion: dict,
    visible_comparison_series: set[tuple[str, str]],
) -> None:
    visible_leap_scenarios = {
        str(scenario).strip().lower()
        for source, scenario in visible_comparison_series
        if str(source).strip().lower() == "leap"
    }
    if not visible_leap_scenarios:
        return

    scenario_to_summary_key = {
        "reference": "ref",
        "target": "tgt",
    }
    extraction_summary = ingestion.get("extraction_summary", {})
    low_detail: list[str] = []
    for scenario in sorted(visible_leap_scenarios):
        summary_key = scenario_to_summary_key.get(scenario)
        if not summary_key:
            continue
        scenario_summary = extraction_summary.get(summary_key, {})
        detail_mode = str(scenario_summary.get("detail_mode", "")).strip()
        if detail_mode != "detailed":
            selected_sheet_count = scenario_summary.get("selected_sheet_count", "")
            detail_path_row_ratio = scenario_summary.get("detail_path_row_ratio", "")
            low_detail.append(
                f"{scenario.title()} detail_mode={detail_mode!r}, "
                f"selected_sheet_count={selected_sheet_count}, "
                f"detail_path_row_ratio={detail_path_row_ratio}"
            )

    if not low_detail:
        return

    details = "; ".join(low_detail)
    raise RuntimeError(
        "LEAP balance dashboard requires level-4/high-detail LEAP balance exports "
        "for all visible LEAP scenarios. Reduced-detail exports do not contain the "
        "sector paths expected by leap_mappings.xlsx and can produce misleading "
        f"parent/child mappings. Offending scenario(s): {details}. Re-export the "
        "LEAP balance workbook at level 4, or remove the affected LEAP scenario "
        "from VISIBLE_COMPARISON_SERIES."
    )


def _stage_compare(
    *,
    run: bool,
    ingestion: dict,
    base_year: int,
    projection_years,
    base_economy: str,
    projection_economy: str,
    scenario_map: dict,
    sheet_map_path: Path,
    backup_mappings_path: Path,
    codebook_path: Path,
    ninth_to_esto_mapping,
    explicit_mappings_path: Path,
    explicit_reassignments_path: Path,
    apply_reference_reassignments: bool,
    synthetic_reference_rows_path: Path,
    base_table_path: Path,
    projection_table_path: Path,
    chart_navigation_guide_path: Path,
    mapping_workbook_path: Path,
    known_issues: dict,
    max_output_year: int,
    visible_comparison_series: set,
    bunker_sheet_keys: set,
    layout,
    timer,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Build the ESTO-axis comparison table from LEAP, ESTO base, and 9th projection data.

    Returns (comparison_long, comparison_wide, leap_long, mapping_status, comparison).
    """
    if run:
        comparison = build_balance_comparison_esto_axis(
            leap_long=ingestion["leap_long"],
            mapping_status=ingestion["mapping_status"],
            base_year=base_year,
            projection_years=tuple(projection_years),
            base_economy=base_economy,
            projection_economy=projection_economy,
            scenario_map=scenario_map,
            sheet_map_path=sheet_map_path,
            backup_mappings_path=backup_mappings_path,
            codebook_path=codebook_path,
            canonical_pairs_path=ninth_to_esto_mapping,
            explicit_mappings_path=explicit_mappings_path,
            explicit_reassignments_path=explicit_reassignments_path,
            apply_reference_reassignments=apply_reference_reassignments,
            synthetic_reference_rows_path=synthetic_reference_rows_path,
            esto_table_path=base_table_path,
            projection_table_path=projection_table_path,
            chart_navigation_guide_path=chart_navigation_guide_path,
            balance_mapping_workbook_path=mapping_workbook_path,
            known_issues=known_issues,
        )
        comparison_long = comparison["comparison_long"].copy()
        mapping_status = comparison["mapping_status"].copy()
        leap_long = ingestion["leap_long"].copy()
        comparison_long = comparison_long[pd.to_numeric(comparison_long["year"], errors="coerce").le(max_output_year)].copy()
        comparison_long = _normalize_base_scenario(comparison_long)
        comparison_long = _apply_bunker_abs_values(comparison_long, bunker_sheet_keys)
        comparison_long = _filter_visible_comparison_series(comparison_long, visible_comparison_series)
        leap_long = leap_long[pd.to_numeric(leap_long["year"], errors="coerce").le(max_output_year)].copy()
    else:
        print("[SKIP] Stage: build ESTO-axis comparison - loading cached outputs")
        comparison_long, mapping_status, leap_long, comparison = _load_cached_comparison(layout)
    comparison_wide = _comparison_wide_from_long(comparison_long)
    timer.lap("build ESTO-axis comparison")
    return comparison_long, comparison_wide, leap_long, mapping_status, comparison


def _stage_write_outputs(
    *,
    run: bool,
    conversion: dict,
    mapping_status: pd.DataFrame,
    comparison_long: pd.DataFrame,
    comparison_wide: pd.DataFrame,
    leap_long: pd.DataFrame,
    comparison: dict,
    layout,
    balance_to_esto_long_output_dir: Path,
    base_year: int,
    max_output_year: int,
    timer,
) -> tuple[dict, dict, dict]:
    """Write comparison tables, simple balance tables, and diagnostics.

    Returns (core_paths, shared_conversion_paths, diagnostics_paths).
    """
    if not run:
        print("[SKIP] Stage: write outputs")
        return {}, {}, {}

    core_paths = write_core_outputs(
        out_dir=layout.root,
        supporting_dir=layout.supporting,
        comparison_long=comparison_long,
        comparison_wide=comparison_wide,
        mapping_status=mapping_status,
        leap_long=leap_long,
    )
    simple_leap_balance = conversion["esto_long"].copy()
    simple_ninth_balance = build_simple_ninth_balance_table(
        comparison_long=comparison_long,
        mapping_status=mapping_status,
    )
    shared_conversion_paths = _write_shared_balance_to_esto_outputs(
        conversion=conversion,
        mapping_status=mapping_status,
        comparison_long=comparison_long,
        simple_ninth_balance=simple_ninth_balance,
        output_dir=balance_to_esto_long_output_dir,
    )
    mapped_ninth_to_esto = comparison.get("ninth_projection_components", pd.DataFrame())
    if mapped_ninth_to_esto.empty:
        mapped_ninth_to_esto = build_mapped_ninth_to_esto_balance_rows(
            comparison_long=comparison_long,
            mapping_status=mapping_status,
        )
    merged_esto_axis_balance = build_merged_esto_axis_balance_table(
        simple_leap_balance=simple_leap_balance,
        simple_ninth_balance=simple_ninth_balance,
        comparison_long=comparison_long,
        mapping_status=mapping_status,
    )
    duplicate_summary, duplicate_details = build_simple_balance_duplicate_diagnostics(
        simple_leap_balance=simple_leap_balance,
        simple_ninth_balance=simple_ninth_balance,
    )

    simple_leap_balance.to_csv(layout.root / "simple_leap_balance_mapped.csv", index=False)
    simple_ninth_balance.to_csv(layout.root / "simple_ninth_balance_mapped.csv", index=False)
    merged_esto_axis_balance.to_csv(layout.root / "merged_leap_ninth_esto_balance.csv", index=False)
    duplicate_summary.to_csv(layout.diagnostics / "simple_balance_duplicate_summary.csv", index=False)
    duplicate_details.to_csv(layout.diagnostics / "simple_balance_duplicate_details.csv", index=False)
    simple_leap_balance.to_csv(layout.mapping / "mapped_leap_to_esto_balance_rows.csv", index=False)
    mapped_ninth_to_esto.to_csv(layout.mapping / "mapped_ninth_to_esto_balance_rows.csv", index=False)
    comparison_long.to_csv(layout.root / "esto_axis_comparison_long.csv", index=False)
    timer.lap("write core and simple ESTO-axis outputs")

    diagnostics_paths = write_diagnostics(
        comparison_long=comparison_long,
        mapping_status=mapping_status,
        out_dir=layout.root,
        base_year=base_year,
        diagnostic_probe_year=min(2030, max_output_year),
        top_diagnostic_rows=40,
    )
    timer.lap("write diagnostics")
    return core_paths, shared_conversion_paths, diagnostics_paths


def _stage_render_dashboards(
    *,
    run: bool,
    comparison_long: pd.DataFrame,
    mapping_status: pd.DataFrame,
    resolved_structure: dict,
    conversion: dict,
    comparison: dict,
    publish_dir: Path,
    layout,
    chart_backend: str,
    chart_output_mode: str,
    hide_leap_only_charts: bool,
    hide_charts_without_leap_data: bool,
    chart_navigation_guide_path: Path,
    mapping_workbook_path: Path,
    base_year: int,
    max_output_year: int,
    timer,
) -> tuple[pd.DataFrame, pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    """Render HTML dashboards and write chart mapping ledgers.

    Returns (chart_line_mapping_ledger, chart_total_component_ledger, dashboard_paths,
             chart_group_exposure_df, all_chart_groups_df).
    """
    chart_line_mapping_path = layout.ledgers / "chart_line_mapping_ledger.csv"
    chart_total_component_path = layout.ledgers / "chart_total_component_ledger.csv"

    if not run:
        print("[SKIP] Stage: render dashboards")
        chart_line_mapping_ledger = (
            pd.read_csv(chart_line_mapping_path, dtype=str, low_memory=False).fillna("")
            if chart_line_mapping_path.exists() else pd.DataFrame()
        )
        chart_total_component_ledger = (
            pd.read_csv(chart_total_component_path, dtype=str, low_memory=False).fillna("")
            if chart_total_component_path.exists() else pd.DataFrame()
        )
        return chart_line_mapping_ledger, chart_total_component_ledger, {}, pd.DataFrame(), pd.DataFrame()

    split_comparison_long = _split_directional_balance_rows_for_charts(comparison_long, resolved_structure)
    chart_input = _prepare_render_long(split_comparison_long)
    chart_line_mapping_ledger = build_chart_line_mapping_ledger(chart_input, mapping_status)
    chart_total_component_ledger = build_total_component_ledger(chart_input, mapping_status)
    dashboard_paths = render_balance_dashboards(
        comparison_long=comparison_long,
        mapping_status=mapping_status,
        structure_config=resolved_structure,
        output_dir=publish_dir,
        support_output_dir=layout.charting,
        chart_backend=chart_backend,
        chart_output_mode=chart_output_mode,
        hide_leap_only_charts=hide_leap_only_charts,
        hide_charts_without_leap_data=hide_charts_without_leap_data,
        chart_navigation_guide_path=chart_navigation_guide_path,
    )
    _write_dashboard_about_supplements(
        dashboards_dir=Path(str(dashboard_paths["dashboards_dir"])),
        template_json_path=chart_navigation_guide_path,
    )
    timer.lap("render dashboards")

    chart_line_mapping_ledger = attach_chart_groups_to_dashboard_exposure(
        chart_line_mapping_ledger,
        dashboard_paths.get("chart_group_exposure"),
        dashboard_paths.get("all_chart_groups"),
    )
    chart_group_exposure_df = (
        pd.read_csv(dashboard_paths["chart_group_exposure"], dtype=str).fillna("")
        if dashboard_paths.get("chart_group_exposure") else pd.DataFrame()
    )
    all_chart_groups_df = (
        pd.read_csv(dashboard_paths["all_chart_groups"], dtype=str).fillna("")
        if dashboard_paths.get("all_chart_groups") else pd.DataFrame()
    )
    simplify_chart_line_mapping_ledger_output(chart_line_mapping_ledger).to_csv(chart_line_mapping_path, index=False)
    simplify_chart_total_component_ledger_output(chart_total_component_ledger).to_csv(chart_total_component_path, index=False)

    mapping_lineage_audit = build_mapping_lineage_audit_table(
        pre_group_leap_mapped=conversion.get("pre_group_leap_mapped", pd.DataFrame()),
        pre_group_incomplete_rows=conversion.get("pre_group_incomplete_rows", pd.DataFrame()),
        comparison_long_full=comparison_long,
        mapping_status=mapping_status,
        mapped_ninth_to_esto_balance_rows=comparison.get("ninth_projection_components", pd.DataFrame()),
        target_years=(base_year, base_year + 1, max_output_year),
    )
    mapping_lineage_audit = attach_chart_groups_to_mapping_lineage_audit(
        mapping_lineage_audit,
        dashboard_paths.get("chart_group_exposure"),
        dashboard_paths.get("all_chart_groups"),
    )
    simplify_mapping_lineage_audit_output(mapping_lineage_audit).to_csv(
        layout.mapping / "mapping_lineage_audit.csv", index=False,
    )

    delta_written = _write_chart_series_snapshot_and_maybe_delta(
        chart_line_ledger=chart_line_mapping_ledger,
        snapshot_path=layout.coverage / "chart_series_value_snapshot.csv",
        delta_path=layout.coverage / "chart_series_value_delta.csv",
        mapping_path=mapping_workbook_path,
        hash_path=layout.coverage / ".mapping_hash",
    )
    if delta_written:
        print(f"[INFO] leap_mappings.xlsx changed since the last run. Chart value delta written to: {layout.coverage / 'chart_series_value_delta.csv'}")
    timer.lap("write chart ledgers")
    return chart_line_mapping_ledger, chart_total_component_ledger, dashboard_paths, chart_group_exposure_df, all_chart_groups_df


def _stage_write_coverage(
    *,
    run: bool,
    ingestion: dict,
    resolved_structure: dict,
    mapping_status: pd.DataFrame,
    comparison: dict,
    chart_line_mapping_ledger: pd.DataFrame,
    chart_group_exposure_df: pd.DataFrame,
    all_chart_groups_df: pd.DataFrame,
    mapping_workbook_path: Path,
    mapping_sheet_name: str,
    layout,
    base_economy: str,
    projection_economy: str,
    base_year: int,
    projection_years,
    scenario_map: dict,
    chart_navigation_guide_path: Path,
    timer,
) -> tuple[pd.DataFrame, object, object, object]:
    """Write runtime issues, mapping candidates, and coverage checks.

    Returns (filtered_runtime_issues, comparator_pair_coverage_xlsx,
             missing_mapping_candidates_path, ninth_mapping_data_coverage_path).
    """
    filtered_runtime_issues = ingestion["issues"].copy()
    if not run:
        print("[SKIP] Stage: write coverage")
        return filtered_runtime_issues, None, None, None

    runtime_issues_path = layout.runtime / "balance_runtime_issues.csv"
    ingestion["issues"].to_csv(runtime_issues_path, index=False)
    filtered_runtime_issues = _filter_ignored_unmapped_issues(
        ingestion["issues"],
        mapping_workbook_path=mapping_workbook_path,
    )
    write_runtime_missing_pair_summary(
        runtime_issues=filtered_runtime_issues,
        output_path=layout.runtime / "balance_runtime_missing_pair_summary.xlsx",
    )
    comparator_pair_coverage_xlsx = write_dashboard_comparator_pair_coverage(
        mapping_status=mapping_status,
        dashboard_exposure=chart_line_mapping_ledger,
        chart_group_exposure=chart_group_exposure_df,
        all_chart_groups=all_chart_groups_df,
        base_df=comparison.get("base_df", pd.DataFrame()),
        ninth_df=comparison.get("ninth_df", pd.DataFrame()),
        output_path=layout.coverage / "dashboard_comparator_pair_coverage.xlsx",
        base_economy=base_economy,
        projection_economy=projection_economy,
        base_year=base_year,
        projection_years=tuple(projection_years),
        scenarios=tuple(scenario_map.values()),
        runtime_issues=filtered_runtime_issues,
        chart_navigation_guide_path=chart_navigation_guide_path,
        mapping_workbook_path=mapping_workbook_path,
        mapping_sheet_name=mapping_sheet_name,
    )
    missing_mapping_candidates_path = write_balance_missing_mapping_candidates(
        runtime_issues=filtered_runtime_issues,
        output_path=layout.mapping / "balance_missing_mapping_candidates.xlsx",
        mapping_workbook_path=mapping_workbook_path,
    )
    leap_combined_ninth_mapping = pd.read_excel(
        mapping_workbook_path, sheet_name="leap_combined_ninth", dtype=str,
    ).fillna("")
    ninth_mapping_data_coverage_path = write_ninth_mapping_data_coverage(
        ninth_df=comparison.get("ninth_df", pd.DataFrame()),
        ninth_mapping_pairs=leap_combined_ninth_mapping,
        output_path=layout.coverage / "ninth_mapping_data_coverage.xlsx",
        projection_economy=projection_economy,
        scenarios=tuple(scenario_map.values()),
        years=tuple(projection_years),
    )
    ingestion["override_report"].to_csv(layout.runtime / "balance_override_application_report.csv", index=False)
    ingestion.get("auto_sheet_rows", pd.DataFrame()).to_csv(layout.mapping / "auto_sheet_rows.csv", index=False)
    (layout.mapping / "resolved_structure_config.json").write_text(
        json.dumps(resolved_structure, ensure_ascii=True, indent=2), encoding="utf-8",
    )
    ingestion["coverage"].to_csv(layout.coverage / "balance_coverage.csv", index=False)
    ingestion["unit_diagnostics"].to_csv(layout.coverage / "balance_unit_diagnostics.csv", index=False)
    ingestion.get("matching_diagnostics", pd.DataFrame()).to_csv(layout.coverage / "balance_matching_diagnostics.csv", index=False)
    (layout.coverage / "balance_extraction_summary.json").write_text(
        json.dumps(ingestion["extraction_summary"], ensure_ascii=True, indent=2), encoding="utf-8",
    )
    timer.lap("write runtime, mapping, and coverage checks")
    return filtered_runtime_issues, comparator_pair_coverage_xlsx, missing_mapping_candidates_path, ninth_mapping_data_coverage_path


#%%
def run_workflow(economy_code: str) -> dict[str, object]:
    economy_token = _economy_token(economy_code)
    base_economy = economy_code.replace("_", "")
    projection_economy = economy_code
    output_dir = _resolve(f"outputs/{economy_token}")
    publish_dir = output_dir
    balance_to_esto_long_output_dir = BALANCE_TABLES_ROOT / "leap_balance_to_esto_long" / economy_token

    ref_workbook_override = os.getenv("LEAP_REF_WORKBOOK_PATH", "").strip()
    tgt_workbook_override = os.getenv("LEAP_TGT_WORKBOOK_PATH", "").strip()

    if ref_workbook_override:
        ref_workbook_path = _resolve(ref_workbook_override)
    else:
        try:
            ref_workbook_path = resolve_balance_export_workbook(
                economy=economy_code, scenario="REF", date_id=REF_BALANCE_EXPORT_DATE_ID,
            )
        except (FileNotFoundError, ValueError):
            ref_workbook_path = None
    if tgt_workbook_override:
        tgt_workbook_path = _resolve(tgt_workbook_override)
    else:
        try:
            tgt_workbook_path = resolve_balance_export_workbook(
                economy=economy_code, scenario="TGT", date_id=TGT_BALANCE_EXPORT_DATE_ID,
            )
        except (FileNotFoundError, ValueError):
            tgt_workbook_path = None

    timer = WorkflowTimer("leap_results_dashboard_balance_estoaxis", enabled=ENABLE_WORKFLOW_TIMING)
    archive_config_dir_once_per_day()
    layout = build_workflow_output_layout(output_dir)
    timing_path = layout.runtime / WORKFLOW_TIMING_FILENAME

    structure_config = build_esto_axis_structure_from_dashboard_template(CHART_NAVIGATION_GUIDE_PATH)
    known_issues = _load_json(KNOWN_ISSUES_CONFIG_PATH)
    timer.lap("setup")

    conversion, ingestion, resolved_structure = _stage_extract(
        run=STAGE_EXTRACT,
        ref_workbook_path=ref_workbook_path,
        tgt_workbook_path=tgt_workbook_path,
        structure_config=structure_config,
        known_issues=known_issues,
        projection_economy=projection_economy,
        max_output_year=MAX_OUTPUT_YEAR,
        codebook_path=CODEBOOK_PATH,
        mapping_workbook_path=_mapping_workbook(LEAP_TO_ESTO_MAPPING),
        balance_to_esto_long_output_dir=balance_to_esto_long_output_dir,
        timer=timer,
    )
    _raise_if_visible_leap_scenarios_use_mixed_detail(
        ingestion,
        VISIBLE_COMPARISON_SERIES,
    )
    _raise_if_visible_leap_scenarios_are_not_detailed(
        ingestion,
        VISIBLE_COMPARISON_SERIES,
    )

    comparison_long, comparison_wide, leap_long, mapping_status, comparison = _stage_compare(
        run=STAGE_COMPARE,
        ingestion=ingestion,
        base_year=BASE_YEAR,
        projection_years=PROJECTION_YEARS,
        base_economy=base_economy,
        projection_economy=projection_economy,
        scenario_map=SCENARIO_MAP,
        sheet_map_path=SHEET_MAP_PATH,
        backup_mappings_path=BACKUP_MAPPINGS_PATH,
        codebook_path=CODEBOOK_PATH,
        ninth_to_esto_mapping=NINTH_TO_ESTO_MAPPING,
        explicit_mappings_path=EXPLICIT_MAPPINGS_PATH,
        explicit_reassignments_path=EXPLICIT_REASSIGNMENTS_PATH,
        apply_reference_reassignments=APPLY_EXPLICIT_REFERENCE_REASSIGNMENTS,
        synthetic_reference_rows_path=SYNTHETIC_REFERENCE_ROWS_PATH,
        base_table_path=BASE_TABLE_PATH,
        projection_table_path=PROJECTION_TABLE_PATH,
        chart_navigation_guide_path=CHART_NAVIGATION_GUIDE_PATH,
        mapping_workbook_path=_mapping_workbook(LEAP_TO_ESTO_MAPPING),
        known_issues=known_issues,
        max_output_year=MAX_OUTPUT_YEAR,
        visible_comparison_series=VISIBLE_COMPARISON_SERIES,
        bunker_sheet_keys=BUNKER_SHEET_KEYS,
        layout=layout,
        timer=timer,
    )

    core_paths, shared_conversion_paths, diagnostics_paths = _stage_write_outputs(
        run=STAGE_WRITE_OUTPUTS,
        conversion=conversion,
        mapping_status=mapping_status,
        comparison_long=comparison_long,
        comparison_wide=comparison_wide,
        leap_long=leap_long,
        comparison=comparison,
        layout=layout,
        balance_to_esto_long_output_dir=balance_to_esto_long_output_dir,
        base_year=BASE_YEAR,
        max_output_year=MAX_OUTPUT_YEAR,
        timer=timer,
    )

    (
        chart_line_mapping_ledger,
        _,
        dashboard_paths,
        chart_group_exposure_df,
        all_chart_groups_df,
    ) = _stage_render_dashboards(
        run=STAGE_RENDER_DASHBOARDS,
        comparison_long=comparison_long,
        mapping_status=mapping_status,
        resolved_structure=resolved_structure,
        conversion=conversion,
        comparison=comparison,
        publish_dir=publish_dir,
        layout=layout,
        chart_backend=CHART_BACKEND,
        chart_output_mode=CHART_OUTPUT_MODE,
        hide_leap_only_charts=HIDE_LEAP_ONLY_CHARTS,
        hide_charts_without_leap_data=HIDE_CHARTS_WITHOUT_LEAP_DATA,
        chart_navigation_guide_path=CHART_NAVIGATION_GUIDE_PATH,
        mapping_workbook_path=_mapping_workbook(LEAP_TO_ESTO_MAPPING),
        base_year=BASE_YEAR,
        max_output_year=MAX_OUTPUT_YEAR,
        timer=timer,
    )

    filtered_runtime_issues, comparator_pair_coverage_xlsx, missing_mapping_candidates_path, ninth_mapping_data_coverage_path = _stage_write_coverage(
        run=STAGE_WRITE_COVERAGE,
        ingestion=ingestion,
        resolved_structure=resolved_structure,
        mapping_status=mapping_status,
        comparison=comparison,
        chart_line_mapping_ledger=chart_line_mapping_ledger,
        chart_group_exposure_df=chart_group_exposure_df,
        all_chart_groups_df=all_chart_groups_df,
        mapping_workbook_path=_mapping_workbook(LEAP_TO_ESTO_MAPPING),
        mapping_sheet_name=LEAP_TO_ESTO_MAPPING[1],
        layout=layout,
        base_economy=base_economy,
        projection_economy=projection_economy,
        base_year=BASE_YEAR,
        projection_years=PROJECTION_YEARS,
        scenario_map=SCENARIO_MAP,
        chart_navigation_guide_path=CHART_NAVIGATION_GUIDE_PATH,
        timer=timer,
    )

    manifest = write_output_manifest(
        out_dir=layout.root,
        primary_outputs={
            "comparison_long": str(layout.root / "comparison_long.csv"),
            "comparison_wide": str(layout.root / "comparison_wide.csv"),
            "mapping_status": str(layout.root / "mapping_status.xlsx"),
            "leap_long": str(layout.root / "leap_long.csv"),
            "simple_leap_balance_mapped": str(layout.root / "simple_leap_balance_mapped.csv"),
            "simple_ninth_balance_mapped": str(layout.root / "simple_ninth_balance_mapped.csv"),
            "merged_leap_ninth_esto_balance": str(layout.root / "merged_leap_ninth_esto_balance.csv"),
            "dashboard_index": dashboard_paths.get("dashboard_index"),
            "charts_dir": str(publish_dir / "charts"),
            "chart_bundles_dir": dashboard_paths.get("chart_bundles_dir"),
            "dashboards_dir": str(publish_dir / "dashboards"),
        },
        supporting_outputs={
            "shared_leap_balance_esto_long": shared_conversion_paths.get("shared_leap_balance_esto_long"),
            "shared_ninth_balance_esto_long": shared_conversion_paths.get("shared_ninth_balance_esto_long"),
            "shared_supporting_files_dir": shared_conversion_paths.get("shared_supporting_files_dir"),
            "mapping_lineage_audit_csv": str(layout.mapping / "mapping_lineage_audit.csv"),
            "gap_diagnostics": diagnostics_paths.get("gap_diagnostics"),
            "mapping_rundown_by_sheet": diagnostics_paths.get("mapping_rundown_by_sheet"),
            "mapping_rundown_details": diagnostics_paths.get("mapping_rundown_details"),
            "comparison_issue_summary": diagnostics_paths.get("comparison_issue_summary"),
            "comparison_issue_cause_summary": diagnostics_paths.get("comparison_issue_cause_summary"),
            "chart_line_mapping_ledger": str(layout.ledgers / "chart_line_mapping_ledger.csv"),
            "chart_total_component_ledger": str(layout.ledgers / "chart_total_component_ledger.csv"),
            "runtime_issues_csv": str(layout.runtime / "balance_runtime_issues.csv"),
            "runtime_missing_pair_summary_xlsx": str(layout.runtime / "balance_runtime_missing_pair_summary.xlsx"),
            "dashboard_comparator_pair_coverage_xlsx": comparator_pair_coverage_xlsx,
            "missing_mapping_candidates_xlsx": missing_mapping_candidates_path,
            "ninth_mapping_data_coverage_xlsx": ninth_mapping_data_coverage_path,
            "override_report_csv": str(layout.runtime / "balance_override_application_report.csv"),
            "auto_sheet_rows_csv": str(layout.mapping / "auto_sheet_rows.csv"),
            "resolved_structure_json": str(layout.mapping / "resolved_structure_config.json"),
            "balance_coverage_csv": str(layout.coverage / "balance_coverage.csv"),
            "balance_unit_diagnostics_csv": str(layout.coverage / "balance_unit_diagnostics.csv"),
            "balance_matching_diagnostics_csv": str(layout.coverage / "balance_matching_diagnostics.csv"),
            "balance_extraction_summary_json": str(layout.coverage / "balance_extraction_summary.json"),
            "workflow_stage_timings_csv": str(timing_path),
        },
        primary_output_descriptions={
            "comparison_long": "Main ESTO-axis comparison table across LEAP, ESTO, and 9th sources.",
            "comparison_wide": "Wide ESTO-axis comparison table with one column per source.",
            "mapping_status": "Mapping workbook for ESTO-axis comparison rows.",
            "leap_long": "Normalized LEAP balance rows before ESTO-axis aggregation.",
            "simple_leap_balance_mapped": "Compact LEAP balance table on the ESTO-axis structure.",
            "simple_ninth_balance_mapped": "Compact 9th balance table on the ESTO-axis structure.",
            "merged_leap_ninth_esto_balance": "Merged LEAP and 9th compact balance table on the ESTO axis.",
            "dashboard_index": "Main HTML entrypoint for the rendered ESTO-axis dashboard.",
            "charts_dir": "Legacy per-chart HTML/PNG output directory, used when CHART_OUTPUT_MODE is not page_bundles.",
            "chart_bundles_dir": "Page-level Plotly JSON bundles used by the ESTO-axis dashboards.",
            "dashboards_dir": "Rendered ESTO-axis dashboard HTML pages.",
        },
        supporting_output_descriptions={
            "shared_leap_balance_esto_long": "Reusable LEAP balance long table mapped to ESTO rows.",
            "shared_ninth_balance_esto_long": "Reusable 9th balance long table mapped to ESTO rows.",
            "shared_supporting_files_dir": "Shared supporting folder for the reusable ESTO-long conversion outputs.",
            "gap_diagnostics": "Largest gaps between LEAP and ESTO-axis comparator sources.",
            "mapping_lineage_audit_csv": "Row-level mapping lineage for LEAP/9th/ESTO at audit years (see dataset column).",
            "mapping_rundown_by_sheet": "Sheet-level summary of ESTO-axis mapping completeness.",
            "mapping_rundown_details": "Detailed mapping audit workbook for ESTO-axis rows.",
            "comparison_issue_summary": "Prioritized ESTO-axis comparison issues with gap metrics and hints.",
            "comparison_issue_cause_summary": "Frequency summary of ESTO-axis issue categories.",
            "chart_line_mapping_ledger": "Per-chart-line ledger linking visible chart rows to mapping decisions.",
            "chart_total_component_ledger": "Ledger showing how visible total lines were constructed.",
            "runtime_issues_csv": "Runtime balance rows that could not be mapped cleanly.",
            "runtime_missing_pair_summary_xlsx": "Grouped summary of missing ESTO-axis mapping pairs.",
            "dashboard_comparator_pair_coverage_xlsx": "Coverage audit for comparator pairs actually exposed in ESTO-axis dashboards.",
            "missing_mapping_candidates_xlsx": "Workbook of candidate mapping additions based on runtime misses.",
            "ninth_mapping_data_coverage_xlsx": "Coverage check for mapped 9th pairs against available 9th data.",
            "override_report_csv": "Report of which manual overrides were applied.",
            "auto_sheet_rows_csv": "Rows automatically assigned to dashboard sheets during preparation.",
            "resolved_structure_json": "Resolved dashboard structure config used for rendering.",
            "balance_coverage_csv": "Coverage summary from LEAP balance extraction.",
            "balance_unit_diagnostics_csv": "Unit normalization checks from LEAP balance extraction.",
            "balance_matching_diagnostics_csv": "Row-level detail-mode and allocation diagnostics from LEAP balance extraction.",
            "balance_extraction_summary_json": "Summary metadata from the balance extraction stage.",
            "workflow_stage_timings_csv": "Runtime duration by broad workflow stage.",
        },
        notes=[
            "Public dashboard HTML, JS, and JSON assets are written under outputs/<economy>/.",
            "CSV, XLSX, and audit outputs are written under outputs/<economy>/.",
            "Supporting diagnostics and mapping evidence are grouped under outputs/<economy>/supporting_files/.",
        ],
    )
    timer.lap("write manifest")

    result = {
        **core_paths,
        **shared_conversion_paths,
        "gap_diagnostics": diagnostics_paths.get("gap_diagnostics"),
        "mapping_rundown_by_sheet": diagnostics_paths.get("mapping_rundown_by_sheet"),
        "mapping_rundown_details": diagnostics_paths.get("mapping_rundown_details"),
        "comparison_issue_summary": diagnostics_paths.get("comparison_issue_summary"),
        "comparison_issue_cause_summary": diagnostics_paths.get("comparison_issue_cause_summary"),
        "simple_leap_balance_mapped": str(layout.root / "simple_leap_balance_mapped.csv"),
        "simple_ninth_balance_mapped": str(layout.root / "simple_ninth_balance_mapped.csv"),
        "merged_leap_ninth_esto_balance": str(layout.root / "merged_leap_ninth_esto_balance.csv"),
        "simple_balance_duplicate_summary": str(layout.diagnostics / "simple_balance_duplicate_summary.csv"),
        "simple_balance_duplicate_details": str(layout.diagnostics / "simple_balance_duplicate_details.csv"),
        "mapped_leap_to_esto_balance_rows": str(layout.mapping / "mapped_leap_to_esto_balance_rows.csv"),
        "mapped_ninth_to_esto_balance_rows": str(layout.mapping / "mapped_ninth_to_esto_balance_rows.csv"),
        "esto_axis_comparison_long": str(layout.root / "esto_axis_comparison_long.csv"),
        "mapping_lineage_audit_csv": str(layout.mapping / "mapping_lineage_audit.csv"),
        "chart_line_mapping_ledger": str(layout.ledgers / "chart_line_mapping_ledger.csv"),
        "chart_total_component_ledger": str(layout.ledgers / "chart_total_component_ledger.csv"),
        "dashboard_index": dashboard_paths.get("dashboard_index"),
        "charts_written": dashboard_paths.get("charts_written"),
        "chart_output_mode": CHART_OUTPUT_MODE,
        "chart_bundles_dir": dashboard_paths.get("chart_bundles_dir"),
        "empty_pages_csv": dashboard_paths.get("empty_pages_csv"),
        "chart_navigation_hierarchy": dashboard_paths.get("chart_navigation_hierarchy"),
        "chart_navigation_hierarchy_flat": dashboard_paths.get("chart_navigation_hierarchy_flat"),
        "chart_navigation_guide": str(CHART_NAVIGATION_GUIDE_PATH),
        "chart_navigation_rendered_template": dashboard_paths.get("chart_navigation_rendered_template"),
        "runtime_issues_csv": str(layout.runtime / "balance_runtime_issues.csv"),
        "runtime_missing_pair_summary_xlsx": str(layout.runtime / "balance_runtime_missing_pair_summary.xlsx"),
        "dashboard_comparator_pair_coverage_xlsx": comparator_pair_coverage_xlsx,
        "missing_mapping_candidates_xlsx": missing_mapping_candidates_path,
        "ninth_mapping_data_coverage_xlsx": ninth_mapping_data_coverage_path,
        "override_report_csv": str(layout.runtime / "balance_override_application_report.csv"),
        "auto_sheet_rows_csv": str(layout.mapping / "auto_sheet_rows.csv"),
        "resolved_structure_json": str(layout.mapping / "resolved_structure_config.json"),
        "balance_coverage_csv": str(layout.coverage / "balance_coverage.csv"),
        "balance_unit_diagnostics_csv": str(layout.coverage / "balance_unit_diagnostics.csv"),
        "balance_matching_diagnostics_csv": str(layout.coverage / "balance_matching_diagnostics.csv"),
        "balance_extraction_summary_json": str(layout.coverage / "balance_extraction_summary.json"),
        "output_manifest": str(manifest),
        "workflow_stage_timings_csv": str(timing_path),
    }
    try:
        _raise_if_unmapped_balance_rows(
            filtered_runtime_issues,
            layout.runtime / "balance_runtime_issues.csv",
            fail_on_unmapped=FAIL_ON_UNMAPPED_BALANCE_ROWS,
        )
    except RuntimeError as exc:
        result["runtime_error"] = str(exc)
        result["completed_with_unmapped_rows"] = True
    timer.finish()
    if WRITE_WORKFLOW_TIMING_CSV:
        timer.write_csv(timing_path)
    return result


#%%
RUN_WORKFLOW = True
WORKFLOW_RESULTS: dict[str, dict[str, object]] = {}
if RUN_WORKFLOW:
    for _economy in ECONOMIES:
        print(f"\n[RUN] Economy: {_economy}")
        WORKFLOW_RESULTS[_economy] = run_workflow(_economy)
        print(f"[OK] {_economy}: Balance dashboard ESTO-axis workflow complete.")
        for key, value in WORKFLOW_RESULTS[_economy].items():
            print(f"- {key}: {value}")
#%%
