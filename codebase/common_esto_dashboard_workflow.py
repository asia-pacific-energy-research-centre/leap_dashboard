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
# LEAP_MAPPINGS_ROOT
#   Optional sibling-repository root. Defaults to ../leap_mappings.
# COMMON_ESTO_PUBLISH_TO_DOCS
#   Boolean toggle for copying serving assets into tracked docs/. Default False.
# COMMON_ESTO_CAPACITY_UNMET_CONVERGENCE_PATH
#   Optional path to a capacity-unmet convergence CSV.
# COMMON_ESTO_INCLUDE_NINTH_PRE_BASE_YEAR_DATA
#   Boolean toggle for retaining 9th-edition rows before the dashboard base
#   year. Default is False because ESTO is the preferred historical source.

#%%
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

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
    load_common_esto_data,
)
from common_esto_dashboard_renderer import load_json, render_dashboard  # noqa: E402
from common_esto_dashboard_output_layout import build_output_layout, publish_to_docs  # noqa: E402
from common_esto_dashboard_convergence import write_capacity_unmet_convergence_page  # noqa: E402
from common_esto_dashboard_mapping_diagnostics import write_mapping_diagnostics_page  # noqa: E402
from scripts.render_full_mapping_tree_explorer import render_full_tree_explorer  # noqa: E402


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
_LEAP_MAPPINGS_REPO = _resolve(os.getenv("LEAP_MAPPINGS_ROOT", str(_DEFAULT_LEAP_MAPPINGS_ROOT)))
_LEAP_MAPPINGS_RESULTS = _LEAP_MAPPINGS_REPO / "results" / "common_esto"
# The long-form file only contains rows a source system actually reported, so
# years a source has no data for are simply absent instead of zero-filled
# (unlike the wide CSV, which pads every year column with 0).
DEFAULT_INPUT_PATH = _LEAP_MAPPINGS_RESULTS / "common_esto_comparison_data.csv"
INPUT_DATA_PATH = _resolve(os.getenv("COMMON_ESTO_INPUT_DATA_PATH", str(DEFAULT_INPUT_PATH)))
COMMON_ROWS_PATH = _resolve(os.getenv("COMMON_ESTO_ROWS_PATH", str(_LEAP_MAPPINGS_RESULTS / "common_esto_rows.csv")))
TEMPLATE_PATH = _resolve("config/common_esto_dashboard/common_esto_dashboard_template.json")
SERIES_CONFIG_PATH = _resolve("config/common_esto_dashboard/series_config.json")
OUTPUT_ROOT = _resolve("outputs/common_esto_dashboard")


#%%
# User-tuned constants.
COMPARISON_SCOPE = os.getenv("COMMON_ESTO_COMPARISON_SCOPE", "esto_leap_ninth")
# Which source scope to read from the wide comparison file (see
# ``common_esto_dashboard_data.DEFAULT_WIDE_FILE_SCOPE``). Use "esto_leap" to
# read the 2-way LEAP/ESTO comparison instead.
WIDE_FILE_SCOPE = os.getenv("COMMON_ESTO_WIDE_FILE_SCOPE", "esto_leap_ninth")
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
# - updates dashboard inputs such as common_esto_comparison_data.csv used below.
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
def _dashboard_updated_label() -> str:
    """Return the human-facing timestamp shown in rendered dashboard headers."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _write_dashboard_metadata(layout: dict[str, Path], updated_label: str) -> None:
    """Write lightweight render metadata for summary scripts and manual inspection."""
    metadata = {
        "economy": layout["root"].name,
        "dashboard_updated_label": updated_label,
        "rendered_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (layout["supporting"] / "dashboard_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


#%%
def maybe_regen_common_esto_fast_path() -> None:
    """Refresh upstream Common ESTO outputs before dashboard rendering when enabled.

    This updates the fast-path input data under leap_mappings/results/common_esto
    that the dashboard reads from (notably common_esto_comparison_data.csv).
    """
    if not UPDATE_DATA:
        print(
            "Skipping Common ESTO fast-path refresh "
            "(COMMON_ESTO_UPDATE_DATA disabled; input data unchanged)."
        )
        return
    if str(_LEAP_MAPPINGS_REPO) not in sys.path:
        sys.path.insert(0, str(_LEAP_MAPPINGS_REPO))
    from codebase.mapping_tools.apply_common_esto_structure import (  # noqa: E402
        NINTH_PROJECTION_START_YEAR,
        run_common_esto_comparison_fast_path,
    )

    relationship_dir = _LEAP_MAPPINGS_REPO / "results" / "mapping_relationships"
    run_timestamp = datetime.now(timezone.utc)
    print("Refreshing Common ESTO comparison outputs via leap_mappings fast path.")
    run_common_esto_comparison_fast_path(
        source_paths={
            "LEAP": relationship_dir / "leap_results_converted_to_esto.csv",
            "NINTH": relationship_dir / "ninth_results_converted_to_esto.csv",
            "ESTO": relationship_dir / "esto_results_exact_rows.csv",
        },
        common_rows_path=_LEAP_MAPPINGS_RESULTS / "common_esto_rows.csv",
        output_dir=_LEAP_MAPPINGS_RESULTS,
        default_economy="20_USA",
        active_component_abs_tolerance=0.0,
        ninth_projection_start_year=NINTH_PROJECTION_START_YEAR,
        run_id=run_timestamp.strftime("common_esto_fast_path_%Y%m%dT%H%M%S%fZ"),
        run_timestamp_utc=run_timestamp.isoformat(),
    )


def _missing_leap_demand_branches(economy: str) -> list[str]:
    """Return LEAP demand branches with no separately modelled detail for *economy*.

    Delegates to leap_mappings' own config-owned record of which sectors are
    still only available via 'All demand aggregated'
    (config/all_demand_aggregated_components.json), resolved per economy.
    """
    if str(_LEAP_MAPPINGS_REPO) not in sys.path:
        sys.path.insert(0, str(_LEAP_MAPPINGS_REPO))
    from codebase.mapping_tools.source_branch_preflight import (  # noqa: E402
        get_demand_sectors_without_detail,
        load_all_demand_aggregated_components,
    )

    components_path = _LEAP_MAPPINGS_REPO / "config" / "all_demand_aggregated_components.json"
    components_df = load_all_demand_aggregated_components(components_path)
    return get_demand_sectors_without_detail(components_df, economy)


def run_dashboard_for_economy(economy: str) -> dict[str, object]:
    """Render the production Common ESTO dashboard for one economy."""
    # Accept both underscore ("20_USA") and compact ("20USA") economy keys by
    # normalizing the key and the data's economy column to the compact form
    # used for output folders (matches the batch render script).
    economy = str(economy).replace("_", "").strip()
    template = load_json(TEMPLATE_PATH)
    missing_leap_branches = _missing_leap_demand_branches(economy)
    template = filter_template_for_leap_demand_coverage(template, missing_leap_branches)
    series_config = json.loads(SERIES_CONFIG_PATH.read_text(encoding="utf-8"))
    raw_df = load_common_esto_data(INPUT_DATA_PATH, wide_file_scope=WIDE_FILE_SCOPE)
    raw_df["economy"] = raw_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    raw_df = enrich_with_component_metadata(raw_df, COMMON_ROWS_PATH)
    base_year = int(template.get("chart_generation", {}).get("base_year", 2022))
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
    filtered_df = filter_common_esto_data(
        raw_df,
        comparison_scope=COMPARISON_SCOPE,
        economy=economy,
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    visible_df = apply_visible_series(filtered_df, series_config.get("visible_series", []))
    visible_df = apply_sign_semantics(visible_df, template.get("sign_semantics"))
    # Keep all scopes only for scope-specific diagnostic pages. The main
    # dashboard dataframe above is always restricted to one required scope.
    scope_filtered_df = raw_df[raw_df["economy"].astype(str) == str(economy)].copy()
    if MIN_YEAR is not None:
        scope_filtered_df = scope_filtered_df[scope_filtered_df["year"] >= MIN_YEAR]
    if MAX_YEAR is not None:
        scope_filtered_df = scope_filtered_df[scope_filtered_df["year"] <= MAX_YEAR]
    scope_filtered_df = scope_filtered_df.reset_index(drop=True)
    scope_visible_df = apply_visible_series(scope_filtered_df, series_config.get("visible_series", []))
    scope_visible_df = apply_sign_semantics(scope_visible_df, template.get("sign_semantics"))
    layout = build_output_layout(OUTPUT_ROOT, economy, clear_existing=CLEAR_EXISTING_OUTPUTS)
    dashboard_updated_label = _dashboard_updated_label()
    _write_dashboard_metadata(layout, dashboard_updated_label)
    sign_summary_df = build_sign_semantics_summary(visible_df)
    sign_summary_df.to_csv(layout["supporting"] / "sign_semantics_summary.csv", index=False)
    manifest_df = render_dashboard(
        visible_df,
        template,
        series_config,
        layout,
        scope_df=scope_visible_df,
        dashboard_updated_label=dashboard_updated_label,
        additional_pages=[
            {
                "page_key": "mapping_diagnostics",
                "page_label": "Mapping diagnostics",
                "file": "mapping_diagnostics.html",
            },
            {
                "page_key": "mapping_tree_explorer",
                "page_label": "Full mapping tree explorer",
                "file": "mapping_tree_explorer.html",
            },
        ],
    )
    mapping_diagnostics = write_mapping_diagnostics_page(
        layout,
        _LEAP_MAPPINGS_REPO,
        dashboard_updated_label=dashboard_updated_label,
        economy=economy,
        comparison_data=scope_filtered_df,
    )
    mapping_tree_explorer = render_full_tree_explorer(
        output_path=layout["dashboards"] / "mapping_tree_explorer.html",
        comparison_data=raw_df,
        prefer_extended_esto=PREFER_EXTENDED_ESTO,
    )
    convergence_result = write_capacity_unmet_convergence_page(
        CAPACITY_UNMET_CONVERGENCE_PATH,
        layout,
        enabled=INCLUDE_CAPACITY_UNMET_CONVERGENCE,
    )
    coverage_config = template.get("leap_demand_sector_coverage", {})
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
    print(f"LEAP demand branches without detail for {economy}: {', '.join(missing_leap_branches) or 'none'}")
    print(f"Input rows read: {len(raw_df):,}")
    print(f"Rows after scope/economy/year filter: {len(filtered_df):,}")
    print(f"Rows after visible-series filter: {len(visible_df):,}")
    print(f"Charts written: {len(manifest_df):,}")
    print(f"Sign summary rows written: {len(sign_summary_df):,}")
    print(f"Dashboard index: {layout['dashboards'] / 'index.html'}")
    result: dict[str, object] = {
        "economy": economy,
        "dashboard_index": str(layout["dashboards"] / "index.html"),
        "chart_manifest": str(layout["supporting"] / "chart_manifest.csv"),
        "sign_semantics_summary": str(layout["supporting"] / "sign_semantics_summary.csv"),
        "chart_count": len(manifest_df),
        "mapping_diagnostics": mapping_diagnostics,
        "mapping_tree_explorer": str(mapping_tree_explorer),
    }
    if convergence_result:
        result["capacity_unmet_convergence"] = convergence_result
    if PUBLISH_TO_DOCS:
        docs_root = REPO_ROOT / "docs"
        counts = publish_to_docs(layout, docs_root)
        print(f"Published to docs/: {counts}")
        result["docs_published"] = counts
    return result


def run_dashboard_workflow() -> dict[str, object]:
    """Run dashboard render once for all configured economies."""
    maybe_regen_common_esto_fast_path()

    configured_economies = _normalize_economies(ECONOMIES)
    if not configured_economies:
        raise ValueError("ECONOMIES is empty. Provide a string or list with at least one economy code.")

    print(f"Configured economies: {', '.join(configured_economies)}")
    economy_results: dict[str, dict[str, object]] = {}
    for idx, economy in enumerate(configured_economies, start=1):
        print("-" * 72)
        print(f"[{idx}/{len(configured_economies)}] Rendering economy: {economy}")
        economy_results[economy] = run_dashboard_for_economy(economy)

    total_charts = sum(int(result.get("chart_count", 0)) for result in economy_results.values())
    print("-" * 72)
    print(f"Completed dashboard run for {len(economy_results)} economies.")
    print(f"Total charts written across all economies: {total_charts:,}")
    return {
        "economies": configured_economies,
        "economy_results": economy_results,
        "total_chart_count": total_charts,
    }


def _chime() -> None:
    try:
        import time
        import winsound  # type: ignore
        for freq, dur in [(659, 90), (784, 90), (988, 140)]:
            winsound.Beep(freq, dur)
            time.sleep(0.04)
    except Exception:
        pass


#%%
with _log_to_file(_WORKFLOW_LOG_PATH) as _log_path:
    print(f"[LOG] Writing output to: {_log_path}")
    try:
        if RUN_DASHBOARD_WORKFLOW:
            WORKFLOW_RESULT = run_dashboard_workflow()
            _chime()
        else:
            print("Set RUN_DASHBOARD_WORKFLOW = True to render the dashboard.")
    except Exception as exc:
        print("Common ESTO dashboard workflow failed.")
        print(f"Error: {exc}")
        raise

#%%
