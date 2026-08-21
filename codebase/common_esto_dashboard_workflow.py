#%%
"""Notebook-safe production workflow for the Common ESTO dashboard."""

# Runtime toggles / environment variables (quick reference)
# ---------------------------------------------------------
# COMMON_ESTO_ECONOMIES
#   Optional comma-separated list of economy codes to render in one run
#   (e.g. "20_USA,02_BD"). You can also set ECONOMIES directly in this file
#   as either a string ("20_USA") or list (["20_USA", "02_BD"]).
# COMMON_ESTO_COMPARISON_SCOPE
#   Comparison scope filter (default: esto_leap_ninth).
# COMMON_ESTO_UPDATE_DATA
#   Boolean toggle for upstream data refresh before rendering.
#   When False, dashboard input files are reused as-is and are NOT refreshed.
#   Accepted true values: 1, true, yes, on.
# COMMON_ESTO_INPUT_DATA_PATH
#   Optional override for dashboard input CSV path.
# COMMON_ESTO_ROWS_PATH
#   Optional override for common rows CSV path.
# COMMON_ESTO_SOURCE_TO_COMMON_MAP_PATH / COMMON_ESTO_ESTO_TO_COMMON_MAP_PATH
#   Optional overrides for the published native-source provenance maps used by
#   guide page-content tables.
# LEAP_MAPPINGS_ROOT
#   Optional sibling-repository root. Defaults to ../leap_mappings.
# COMMON_ESTO_PUBLISH_TO_DOCS
#   Boolean toggle for copying serving assets into tracked docs/. Default False.
# COMMON_ESTO_CAPACITY_UNMET_CONVERGENCE_PATH
#   Optional path to a capacity-unmet convergence CSV.
# COMMON_ESTO_RAW_LEAP_RESULTS_PATH
#   Optional override for the upstream raw LEAP results extract used only by
#   the Energy balance overview's Unmet Requirements diagnostic.
# COMMON_ESTO_INCLUDE_NINTH_PRE_BASE_YEAR_DATA
#   Boolean toggle for retaining 9th-edition rows before the dashboard base
#   year. Default is False because ESTO is the preferred historical source.

#%%
import copy
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
MODULE_ROOT = CURRENT_FILE.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common_esto_dashboard_data import (  # noqa: E402
    apply_sign_semantics,
    apply_visible_series,
    build_sign_semantics_summary,
    enrich_with_component_metadata,
    filter_ninth_pre_base_year_data,
    filter_common_esto_data,
    filter_template_for_leap_demand_coverage,
    load_active_power_interim_branches,
    load_common_esto_data,
    load_leap_demand_representation_status,
    load_hydrogen_electricity_input_data,
    load_source_category_map,
    load_unmet_requirements_data,
)
from scripts.manage_dashboard_colors import synchronize_dashboard_colors  # noqa: E402
from common_esto_dashboard_emissions import set_leap_mappings_root  # noqa: E402
from common_esto_dashboard_renderer import load_json, render_dashboard  # noqa: E402
from common_esto_dashboard_output_layout import build_output_layout, publish_to_docs  # noqa: E402
from common_esto_dashboard_convergence import write_capacity_unmet_convergence_page  # noqa: E402
from common_esto_dashboard_mapping_diagnostics import (  # noqa: E402
    load_esto_exact_values_for_economy,
    prefer_compressed_csv_path,
    write_mapping_diagnostics_page,
)
from mapping_pipeline_provenance import selected_run_metadata  # noqa: E402


#%%
def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable with a safe default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_economies(economies: str | list[str]) -> list[str]:
    """Normalize ECONOMIES into a clean, non-empty list of economy codes."""
    if isinstance(economies, str):
        values = [part.strip() for part in economies.split(",") if part.strip()]
    else:
        values = [str(item).strip() for item in economies if str(item).strip()]
    return values


#%%
# ---------------------------------------------------------------------------
# Output logging
# ---------------------------------------------------------------------------
_WORKFLOW_LOG_PATH = REPO_ROOT / "outputs" / "logs" / "common_esto_dashboard_workflow.log"


class _TeeWriter:
    def __init__(self, file_obj, stream):
        self._file = file_obj
        self._stream = stream

    def write(self, data):
        self._file.write(data)
        self._stream.write(data)
        return len(data)

    def flush(self):
        self._file.flush()
        self._stream.flush()

    def isatty(self):
        return False


@contextmanager
def _log_to_file(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    original = sys.stdout
    with open(log_path, "w", encoding="utf-8") as f:
        sys.stdout = _TeeWriter(f, original)
        try:
            yield log_path
        finally:
            sys.stdout = original


#%%
# Stable paths.
_DEFAULT_LEAP_MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
_LEAP_MAPPINGS_REPO = _resolve(
    os.getenv(
        "COMMON_ESTO_MAPPINGS_ROOT",
        os.getenv("LEAP_MAPPINGS_ROOT", str(_DEFAULT_LEAP_MAPPINGS_ROOT)),
    )
)
_LEAP_MAPPINGS_CODEBASE = _LEAP_MAPPINGS_REPO / "codebase"
_LEAP_MAPPINGS_RESULTS = _LEAP_MAPPINGS_REPO / "results" / "common_esto"
LEAP_DEMAND_REPRESENTATION_STATUS_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_LEAP_DEMAND_REPRESENTATION_STATUS_PATH",
        str(_LEAP_MAPPINGS_RESULTS / "leap_demand_representation_status.csv"),
    )
)
ESTO_EXACT_ROWS_PATH = prefer_compressed_csv_path(
    _LEAP_MAPPINGS_REPO / "results" / "mapping_relationships" / "esto_results_exact_rows.csv.gz"
)
# The long-form file only contains rows a source system actually reported, so
# years a source has no data for are simply absent instead of zero-filled
# (unlike the wide CSV, which pads every year column with 0).
DEFAULT_INPUT_PATH = _LEAP_MAPPINGS_RESULTS / "common_esto_comparison_data.parquet"
INPUT_DATA_PATH = _resolve(os.getenv("COMMON_ESTO_INPUT_DATA_PATH", str(DEFAULT_INPUT_PATH)))
DEFAULT_OUTPUT_CONTRACT_PATH = _LEAP_MAPPINGS_RESULTS / "common_esto_output_contract.json"
OUTPUT_CONTRACT_PATH = _resolve(
    os.getenv("COMMON_ESTO_OUTPUT_CONTRACT_PATH", str(DEFAULT_OUTPUT_CONTRACT_PATH))
)
COMMON_ROWS_PATH = _resolve(os.getenv("COMMON_ESTO_ROWS_PATH", str(_LEAP_MAPPINGS_RESULTS / "common_esto_rows.csv")))
SOURCE_TO_COMMON_MAP_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_SOURCE_TO_COMMON_MAP_PATH",
        str(_LEAP_MAPPINGS_RESULTS / "source_to_common_esto_map.csv"),
    )
)
RAW_LEAP_RESULTS_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_RAW_LEAP_RESULTS_PATH",
        str(_LEAP_MAPPINGS_REPO / "results" / "mapping_relationships" / "raw_leap_results.csv"),
    )
)
POWER_INTERIM_AUDIT_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_POWER_INTERIM_AUDIT_PATH",
        str(
            _LEAP_MAPPINGS_REPO
            / "results"
            / "mapping_relationships"
            / "leap_source_branch_fallback_audit.csv"
        ),
    )
)
ESTO_TO_COMMON_MAP_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_ESTO_TO_COMMON_MAP_PATH",
        str(_LEAP_MAPPINGS_RESULTS / "esto_to_common_esto_map.csv"),
    )
)
DATASET_REGISTRY_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_DATASET_REGISTRY_PATH",
        str(_LEAP_MAPPINGS_REPO / "config" / "datasets" / "dataset_registry.csv"),
    )
)
TEMPLATE_PATH = _resolve("config/common_esto_dashboard/common_esto_dashboard_template.json")
SERIES_CONFIG_PATH = _resolve("config/common_esto_dashboard/series_config.json")
OUTPUT_ROOT = _resolve(
    os.getenv("COMMON_ESTO_DASHBOARD_OUTPUT_ROOT", "outputs/common_esto_dashboard")
)
# The emissions page reads its 9th-fuel -> ESTO mapping contract and the
# generated ESTO -> common axis map from the same sibling repository.
set_leap_mappings_root(_LEAP_MAPPINGS_REPO)


#%%
# User-tuned constants.
COMPARISON_SCOPE = os.getenv("COMMON_ESTO_COMPARISON_SCOPE", "esto_extended_leap_ninth")
RENDER_COMPARISON_SCOPE_VARIANTS = _env_bool(
    "COMMON_ESTO_RENDER_COMPARISON_SCOPE_VARIANTS", default=True
)
# Which source scope to read from the wide comparison file (see
# ``common_esto_dashboard_data.DEFAULT_WIDE_FILE_SCOPE``). Use "esto_leap" to
# read the 2-way LEAP/ESTO comparison instead.
WIDE_FILE_SCOPE = os.getenv("COMMON_ESTO_WIDE_FILE_SCOPE", "esto_extended_leap_ninth")
USE_OUTPUT_CONTRACT = _env_bool("COMMON_ESTO_USE_OUTPUT_CONTRACT", default=True)
ECONOMIES: str | list[str] = os.getenv("COMMON_ESTO_ECONOMIES", ["20_USA", "02_BD"])
MIN_YEAR = 2010
MAX_YEAR = 2060

# Env var override so importers (e.g. the batch render script) can load this
# module's functions without triggering the full workflow run at import time.
RUN_DASHBOARD_WORKFLOW = _env_bool("COMMON_ESTO_RUN_DASHBOARD_WORKFLOW", default=True)
CLEAR_EXISTING_OUTPUTS = True
PUBLISH_TO_DOCS = _env_bool("COMMON_ESTO_PUBLISH_TO_DOCS", default=False)
# Explicit notebook/script toggle: refresh upstream Common ESTO comparison inputs
# before rendering dashboard pages.
#
# What this does when True:
# - recomputes fast-path Common ESTO outputs in leap_mappings/results/common_esto
#   from latest mapping relationship files (Stage 3 fast-path equivalent);
# - updates dashboard inputs such as common_esto_comparison_data.parquet used below.
#
# Data refresh is opt-in so ordinary renders cannot mutate the sibling repo.
UPDATE_DATA = False

# Env var override for automation.
# Example: COMMON_ESTO_UPDATE_DATA=0 to skip refresh and render from existing files.
UPDATE_DATA = _env_bool(
    "COMMON_ESTO_UPDATE_DATA",
    default=UPDATE_DATA,
)
# By default, use ESTO for pre-base-year values. Set this to True when a
# diagnostic render needs the 9th-edition values retained as well.
INCLUDE_NINTH_PRE_BASE_YEAR_DATA = _env_bool(
    "COMMON_ESTO_INCLUDE_NINTH_PRE_BASE_YEAR_DATA",
    default=False,
)
INCLUDE_CAPACITY_UNMET_CONVERGENCE = _env_bool(
    "COMMON_ESTO_INCLUDE_CAPACITY_UNMET_CONVERGENCE",
    default=False,
)
PREFER_EXTENDED_ESTO = _env_bool(
    "COMMON_ESTO_PREFER_EXTENDED_ESTO",
    default=False,
)
_DEFAULT_CAPACITY_UNMET_CONVERGENCE_PATH = (
    REPO_ROOT.parent
    / "leap_initialisation"
    / "outputs"
    / "leap_exports"
    / "supply_reconciliation"
    / "results_update"
    / "supporting_files"
    / "runtime"
    / "capacity_unmet_convergence.csv"
)
CAPACITY_UNMET_CONVERGENCE_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_CAPACITY_UNMET_CONVERGENCE_PATH",
        str(_DEFAULT_CAPACITY_UNMET_CONVERGENCE_PATH),
    )
)


#%%
# Dashboards are read by the APERC team in Tokyo, and a hosted render would
# otherwise be stamped with whatever timezone the server happens to sit in.
DASHBOARD_TIMEZONE = os.environ.get("COMMON_ESTO_DASHBOARD_TIMEZONE", "Asia/Tokyo")


def _dashboard_timezone() -> timezone | ZoneInfo:
    """Return the timezone dashboard timestamps are shown in.

    Falls back to the machine's own zone if the tz database is unavailable,
    which is better than failing a completed render over a label.
    """
    try:
        return ZoneInfo(DASHBOARD_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo or timezone.utc


def _dashboard_updated_label() -> str:
    """Return the human-facing timestamp shown in rendered dashboard headers."""
    return datetime.now(_dashboard_timezone()).strftime("%Y-%m-%d %H:%M %Z")


def _write_dashboard_metadata(
    layout: dict[str, Path],
    updated_label: str,
) -> None:
    """Write lightweight render metadata for summary scripts and manual inspection."""
    metadata = {
        "economy": layout["root"].name,
        "dashboard_updated_label": updated_label,
        "rendered_at_local": datetime.now(_dashboard_timezone()).isoformat(
            timespec="seconds"
        ),
        **selected_run_metadata(_LEAP_MAPPINGS_REPO),
    }
    (layout["supporting"] / "dashboard_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


#%%
def maybe_regen_common_esto_fast_path() -> None:
    """Refresh upstream Common ESTO outputs before dashboard rendering when enabled.

    This updates the fast-path input data under leap_mappings/results/common_esto
    that the dashboard reads from (notably common_esto_comparison_data.parquet).
    """
    if not UPDATE_DATA:
        print(
            "Skipping Common ESTO fast-path refresh "
            "(COMMON_ESTO_UPDATE_DATA disabled; input data unchanged)."
        )
        return
    if str(_LEAP_MAPPINGS_CODEBASE) not in sys.path:
        sys.path.insert(0, str(_LEAP_MAPPINGS_CODEBASE))
    from mapping_tools.apply_common_esto_structure import (  # noqa: E402
        NINTH_PROJECTION_START_YEAR,
        run_common_esto_comparison_fast_path,
    )
    from mapping_tools.value_adapter_registry import (  # noqa: E402
        get_component_relevance_reference_paths,
    )

    relationship_dir = _LEAP_MAPPINGS_REPO / "results" / "mapping_relationships"
    run_timestamp = datetime.now(timezone.utc)
    print("Refreshing Common ESTO comparison outputs via leap_mappings fast path.")
    run_common_esto_comparison_fast_path(
        source_paths={
            "LEAP": relationship_dir / "leap_results_converted_to_esto.csv",
            "NINTH": prefer_compressed_csv_path(
                relationship_dir / "ninth_results_converted_to_esto.csv.gz"
            ),
            "ESTO": prefer_compressed_csv_path(
                relationship_dir / "esto_results_exact_rows.csv.gz"
            ),
            "ESTO_EXTENDED": prefer_compressed_csv_path(
                relationship_dir / "esto_results_exact_rows.csv.gz"
            ),
        },
        common_rows_path=_LEAP_MAPPINGS_RESULTS / "common_esto_rows.csv",
        output_dir=_LEAP_MAPPINGS_RESULTS,
        default_economy="20_USA",
        active_component_abs_tolerance=0.0,
        ninth_projection_start_year=NINTH_PROJECTION_START_YEAR,
        run_id=run_timestamp.strftime("common_esto_fast_path_%Y%m%dT%H%M%S%fZ"),
        run_timestamp_utc=run_timestamp.isoformat(),
        relevance_reference_paths=get_component_relevance_reference_paths(
            _LEAP_MAPPINGS_REPO
        ),
        source_system_overrides={"ESTO_EXTENDED": "ESTO_EXTENDED"},
    )


def configured_comparison_scopes(template: dict) -> list[dict[str, object]]:
    """Return validated, configuration-driven category-basis definitions."""
    selector = template.get("comparison_scope_selector", {}) or {}
    configured = selector.get("scopes", []) if selector.get("enabled", False) else []
    if not RENDER_COMPARISON_SCOPE_VARIANTS:
        configured = [
            {**item, "output_suffix": ""} for item in configured
            if str(item.get("comparison_scope", "")) == COMPARISON_SCOPE
        ]
    if not configured:
        configured = [{
            "comparison_scope": COMPARISON_SCOPE,
            "label": COMPARISON_SCOPE,
            "source_systems": [],
            "output_suffix": "",
        }]

    definitions: list[dict[str, object]] = []
    seen_scopes: set[str] = set()
    seen_suffixes: set[str] = set()
    for position, raw in enumerate(configured):
        scope = str(raw.get("comparison_scope", "")).strip()
        if not scope or scope in seen_scopes:
            raise ValueError(f"Comparison-scope selector contains a missing or duplicate scope: {scope!r}")
        suffix = str(raw.get("output_suffix", "")).strip()
        if suffix in seen_suffixes or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in suffix):
            raise ValueError(f"Comparison-scope selector contains an invalid or duplicate output suffix: {suffix!r}")
        sources = [
            str(source).strip().upper()
            for source in raw.get("source_systems", [])
            if str(source).strip()
        ]
        definitions.append({
            "comparison_scope": scope,
            "label": str(raw.get("label", scope)).strip() or scope,
            "source_systems": sources,
            "output_suffix": suffix,
            "is_default": position == 0,
        })
        seen_scopes.add(scope)
        seen_suffixes.add(suffix)

    requested_default = str(selector.get("default_scope", template.get("default_comparison_scope", ""))).strip()
    if RENDER_COMPARISON_SCOPE_VARIANTS and requested_default:
        if requested_default not in seen_scopes:
            raise ValueError(f"Configured default comparison scope is not selectable: {requested_default!r}")
        for definition in definitions:
            definition["is_default"] = definition["comparison_scope"] == requested_default
    default_definitions = [item for item in definitions if item["is_default"]]
    if len(default_definitions) != 1:
        raise ValueError("Comparison-scope selector must define exactly one default scope.")
    if str(default_definitions[0]["output_suffix"]):
        raise ValueError("The default comparison scope must use an empty output_suffix to preserve existing URLs.")
    return definitions


def category_basis_options(economy: str, definitions: list[dict[str, object]]) -> list[dict[str, str]]:
    """Return selector options with concrete static dashboard destinations."""
    return [
        {
            "comparison_scope": str(item["comparison_scope"]),
            "label": str(item["label"]),
            "dashboard_key": f"{economy}{item['output_suffix']}",
        }
        for item in definitions
    ]


def run_dashboard_for_economy(
    economy: str,
    source_category_map: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Render every configured Common-category basis for one economy."""
    economy = str(economy).replace("_", "").strip()
    base_template = load_json(TEMPLATE_PATH)
    representation_status_df = load_leap_demand_representation_status(
        LEAP_DEMAND_REPRESENTATION_STATUS_PATH,
        economy,
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    base_template = filter_template_for_leap_demand_coverage(
        base_template, representation_status_df
    )
    base_template["_power_interim_placeholder_branches"] = (
        load_active_power_interim_branches(
            POWER_INTERIM_AUDIT_PATH,
            economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
    )
    definitions = configured_comparison_scopes(base_template)
    selector_options = category_basis_options(economy, definitions)
    series_config = json.loads(SERIES_CONFIG_PATH.read_text(encoding="utf-8"))
    if source_category_map is None:
        source_category_map = load_source_category_map(
            SOURCE_TO_COMMON_MAP_PATH,
            ESTO_TO_COMMON_MAP_PATH,
        )
    raw_df = load_common_esto_data(
        INPUT_DATA_PATH,
        wide_file_scope=WIDE_FILE_SCOPE,
        output_contract_path=OUTPUT_CONTRACT_PATH if USE_OUTPUT_CONTRACT else None,
        dataset_registry_path=DATASET_REGISTRY_PATH,
    )
    raw_df["economy"] = raw_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    raw_df = enrich_with_component_metadata(raw_df, COMMON_ROWS_PATH)
    base_year = int(base_template.get("chart_generation", {}).get("base_year", 2022))
    input_row_count = len(raw_df)
    raw_df = filter_ninth_pre_base_year_data(
        raw_df,
        base_year=base_year,
        include_pre_base_year_data=INCLUDE_NINTH_PRE_BASE_YEAR_DATA,
    )
    if len(raw_df) != input_row_count:
        print(
            f"Excluded {input_row_count - len(raw_df):,} NINTH rows before base year "
            f"{base_year} (ESTO retained for pre-base-year data)."
        )

    scope_filtered_df = raw_df[raw_df["economy"].astype(str) == economy].copy()
    if MIN_YEAR is not None:
        scope_filtered_df = scope_filtered_df[scope_filtered_df["year"] >= MIN_YEAR]
    if MAX_YEAR is not None:
        scope_filtered_df = scope_filtered_df[scope_filtered_df["year"] <= MAX_YEAR]
    scope_filtered_df = scope_filtered_df.reset_index(drop=True)
    scope_visible_df = apply_visible_series(
        scope_filtered_df, series_config.get("visible_series", [])
    )
    scope_visible_df = apply_sign_semantics(
        scope_visible_df, base_template.get("sign_semantics")
    )
    dashboard_updated_label = _dashboard_updated_label()

    scope_results: dict[str, dict[str, object]] = {}
    default_layout: dict[str, Path] | None = None
    default_result: dict[str, object] | None = None
    for definition in definitions:
        comparison_scope = str(definition["comparison_scope"])
        output_suffix = str(definition["output_suffix"])
        dashboard_key = f"{economy}{output_suffix}"
        print(f"Rendering Common categories: {definition['label']} ({comparison_scope})")
        filtered_df = filter_common_esto_data(
            raw_df,
            comparison_scope=comparison_scope,
            economy=economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
        visible_df = apply_visible_series(
            filtered_df, series_config.get("visible_series", [])
        )
        scope_template = copy.deepcopy(base_template)
        scope_template["_current_dashboard_key"] = economy
        scope_template["_active_comparison_scope"] = comparison_scope
        scope_template["_active_dataset_filter_options"] = list(definition["source_systems"])
        if "ESTO_EXTENDED" in definition["source_systems"]:
            scope_template["chart_generation"]["comparison_source_system"] = "ESTO_EXTENDED"
        scope_template["_dashboard_key_suffix"] = output_suffix
        scope_template["_category_basis_options"] = selector_options
        visible_df = apply_sign_semantics(
            visible_df, scope_template.get("sign_semantics")
        )
        unmet_requirements_df = load_unmet_requirements_data(
            RAW_LEAP_RESULTS_PATH,
            SOURCE_TO_COMMON_MAP_PATH,
            comparison_scope=comparison_scope,
            economy=economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
        hydrogen_electricity_input_df = load_hydrogen_electricity_input_data(
            RAW_LEAP_RESULTS_PATH,
            economy=economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
        layout = build_output_layout(
            OUTPUT_ROOT, dashboard_key, clear_existing=CLEAR_EXISTING_OUTPUTS
        )
        _write_dashboard_metadata(layout, dashboard_updated_label)
        (layout["supporting"] / "comparison_scope_selection.json").write_text(
            json.dumps(
                {
                    "active_comparison_scope": comparison_scope,
                    "label": definition["label"],
                    "source_systems": definition["source_systems"],
                    "dashboard_key": dashboard_key,
                    "selectable_scopes": selector_options,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sign_summary_df = build_sign_semantics_summary(visible_df)
        sign_summary_df.to_csv(
            layout["supporting"] / "sign_semantics_summary.csv", index=False
        )
        unmet_requirements_df.to_csv(
            layout["supporting"] / "unmet_requirements_fuel_mapping.csv", index=False
        )
        hydrogen_electricity_input_df.to_csv(
            layout["supporting"] / "hydrogen_electrolysers_electricity_input.csv",
            index=False,
        )
        manifest_df = render_dashboard(
            visible_df,
            scope_template,
            series_config,
            layout,
            scope_df=scope_visible_df,
            dashboard_updated_label=dashboard_updated_label,
            additional_pages=[
                {
                    "page_key": "mapping_diagnostics",
                    "page_label": "Mapping diagnostics",
                    "file": "../../diagnostics/dashboards/mapping_diagnostics.html",
                },
            ],
            source_category_map=source_category_map,
            unmet_requirements_df=unmet_requirements_df,
            hydrogen_electricity_input_df=hydrogen_electricity_input_df,
        )
        scope_result: dict[str, object] = {
            "comparison_scope": comparison_scope,
            "dashboard_key": dashboard_key,
            "dashboard_index": str(layout["dashboards"] / "index.html"),
            "chart_manifest": str(layout["supporting"] / "chart_manifest.csv"),
            "sign_semantics_summary": str(layout["supporting"] / "sign_semantics_summary.csv"),
            "chart_count": len(manifest_df),
            "input_rows": len(filtered_df),
            "visible_rows": len(visible_df),
        }
        if PUBLISH_TO_DOCS:
            counts = publish_to_docs(layout, REPO_ROOT / "docs")
            scope_result["docs_published"] = counts
            print(f"Published {comparison_scope} to docs/: {counts}")
        scope_results[comparison_scope] = scope_result
        if definition["is_default"]:
            default_layout = layout
            default_result = scope_result
        print(f"Rows after scope/economy/year filter: {len(filtered_df):,}")
        print(f"Rows after visible-series filter: {len(visible_df):,}")
        print(f"Charts written: {len(manifest_df):,}")
        print(f"Dashboard index: {layout['dashboards'] / 'index.html'}")

    if default_layout is None or default_result is None:
        raise RuntimeError("No default comparison-scope dashboard was rendered.")
    convergence_result = write_capacity_unmet_convergence_page(
        CAPACITY_UNMET_CONVERGENCE_PATH,
        default_layout,
        enabled=INCLUDE_CAPACITY_UNMET_CONVERGENCE,
    )
    coverage_config = base_template.get("leap_demand_sector_coverage", {})
    hidden_page_keys = set(coverage_config.get("_hidden_page_keys", []))
    aggregate_only_skipped = sorted(
        set(coverage_config.get("page_leap_branches", {})) & hidden_page_keys
    )
    always_skipped = sorted(
        set(coverage_config.get("always_skip_page_keys", [])) & hidden_page_keys
    )
    if aggregate_only_skipped:
        print(
            f"Demand-sector standalone pages hidden (no LEAP detail for {economy}, only 'All "
            f"demand aggregated'; still included in total_demand): {', '.join(aggregate_only_skipped)}"
        )
    if always_skipped:
        print(
            f"Sector pages hidden (no LEAP-to-ESTO mapping at all for {economy}): "
            f"{', '.join(always_skipped)}"
        )
    placeholder_components = sorted(
        {
            str(value)
            for branches in coverage_config.get("_aggregate_only_page_branches", {}).values()
            for value in branches
        }
    )
    print(
        f"LEAP placeholder components active in the selected run for {economy}: "
        f"{', '.join(placeholder_components) or 'none'}"
    )
    print(f"Input rows read: {len(raw_df):,}")
    print(f"Total charts across category bases: {sum(int(item['chart_count']) for item in scope_results.values()):,}")

    mapping_diagnostics = {
        "page": str(OUTPUT_ROOT / "diagnostics" / "dashboards" / "mapping_diagnostics.html"),
        "summary": str(OUTPUT_ROOT / "diagnostics" / "supporting_files" / "mapping_diagnostics_summary.csv"),
    }
    result: dict[str, object] = {
        "economy": economy,
        "dashboard_index": default_result["dashboard_index"],
        "chart_manifest": default_result["chart_manifest"],
        "sign_semantics_summary": default_result["sign_semantics_summary"],
        "chart_count": sum(int(item["chart_count"]) for item in scope_results.values()),
        "default_chart_count": default_result["chart_count"],
        "scope_results": scope_results,
        "leap_demand_representation_status_rows": len(representation_status_df),
        "mapping_diagnostics": mapping_diagnostics,
    }
    if convergence_result:
        result["capacity_unmet_convergence"] = convergence_result
    return result


def run_shared_mapping_diagnostics() -> dict[str, str]:
    """Render the one APEC-first diagnostics page linked by every economy."""
    raw_df = load_common_esto_data(
        INPUT_DATA_PATH,
        wide_file_scope=WIDE_FILE_SCOPE,
        output_contract_path=OUTPUT_CONTRACT_PATH if USE_OUTPUT_CONTRACT else None,
        dataset_registry_path=DATASET_REGISTRY_PATH,
    )
    raw_df["economy"] = raw_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    raw_df = enrich_with_component_metadata(raw_df, COMMON_ROWS_PATH)
    if MIN_YEAR is not None:
        raw_df = raw_df[raw_df["year"] >= MIN_YEAR]
    if MAX_YEAR is not None:
        raw_df = raw_df[raw_df["year"] <= MAX_YEAR]
    layout = build_output_layout(
        OUTPUT_ROOT,
        "diagnostics",
        clear_existing=CLEAR_EXISTING_OUTPUTS,
    )
    updated_label = _dashboard_updated_label()
    esto_exact_values = load_esto_exact_values_for_economy(
        ESTO_EXACT_ROWS_PATH,
        "",
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    esto_extended_exact_values = load_esto_exact_values_for_economy(
        ESTO_EXACT_ROWS_PATH,
        "",
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
        source_system="ESTO_EXTENDED_RAW",
    )
    result = write_mapping_diagnostics_page(
        layout,
        _LEAP_MAPPINGS_REPO,
        dashboard_updated_label=updated_label,
        economy="00APEC",
        comparison_data=raw_df,
        esto_exact_values=pd.concat(
            [esto_exact_values, esto_extended_exact_values], ignore_index=True
        ),
    )
    if PUBLISH_TO_DOCS:
        publish_to_docs(layout, REPO_ROOT / "docs")
    return result


def run_dashboard_workflow() -> dict[str, object]:
    """Run dashboard render once for all configured economies."""
    synchronize_dashboard_colors()
    maybe_regen_common_esto_fast_path()

    configured_economies = _normalize_economies(ECONOMIES)
    if not configured_economies:
        raise ValueError("ECONOMIES is empty. Provide a string or list with at least one economy code.")

    print(f"Configured economies: {', '.join(configured_economies)}")
    shared_mapping_diagnostics = run_shared_mapping_diagnostics()
    source_category_map = load_source_category_map(
        SOURCE_TO_COMMON_MAP_PATH,
        ESTO_TO_COMMON_MAP_PATH,
    )
    economy_results: dict[str, dict[str, object]] = {}
    for idx, economy in enumerate(configured_economies, start=1):
        print("-" * 72)
        print(f"[{idx}/{len(configured_economies)}] Rendering economy: {economy}")
        economy_results[economy] = run_dashboard_for_economy(
            economy,
            source_category_map,
        )

    total_charts = sum(int(result.get("chart_count", 0)) for result in economy_results.values())
    print("-" * 72)
    print(f"Completed dashboard run for {len(economy_results)} economies.")
    print(f"Total charts written across all economies: {total_charts:,}")
    return {
        "economies": configured_economies,
        "economy_results": economy_results,
        "total_chart_count": total_charts,
        "mapping_diagnostics": shared_mapping_diagnostics,
    }


#%%
with _log_to_file(_WORKFLOW_LOG_PATH) as _log_path:
    print(f"[LOG] Writing output to: {_log_path}")
    try:
        if RUN_DASHBOARD_WORKFLOW:
            WORKFLOW_RESULT = run_dashboard_workflow()
        else:
            print("Set RUN_DASHBOARD_WORKFLOW = True to render the dashboard.")
    except Exception as exc:
        print("Common ESTO dashboard workflow failed.")
        print(f"Error: {exc}")
        raise

#%%
