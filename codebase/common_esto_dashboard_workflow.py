#%%
"""Notebook-safe production workflow for the Common ESTO dashboard."""

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

from common_esto_dashboard_data import (  # noqa: E402
    apply_sign_semantics,
    apply_visible_series,
    build_sign_semantics_summary,
    enrich_with_component_metadata,
    filter_common_esto_data,
    load_common_esto_data,
)
from common_esto_dashboard_renderer import load_json, render_dashboard  # noqa: E402
from common_esto_dashboard_output_layout import build_output_layout, publish_to_docs  # noqa: E402


#%%
def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


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
_LEAP_MAPPINGS_REPO = Path(r"C:\Users\Work\github\leap_mappings")
_LEAP_MAPPINGS_RESULTS = Path(r"C:\Users\Work\github\leap_mappings\results\common_esto")
DEFAULT_WIDE_INPUT_PATH = _LEAP_MAPPINGS_RESULTS / "common_esto_comparison_wide.csv"
INPUT_DATA_PATH = _resolve(os.getenv("COMMON_ESTO_INPUT_DATA_PATH", str(DEFAULT_WIDE_INPUT_PATH)))
COMMON_ROWS_PATH = _resolve(os.getenv("COMMON_ESTO_ROWS_PATH", str(_LEAP_MAPPINGS_RESULTS / "common_esto_rows.csv")))
TEMPLATE_PATH = _resolve("config/common_esto_dashboard/common_esto_dashboard_template.json")
SERIES_CONFIG_PATH = _resolve("config/common_esto_dashboard/series_config.json")
OUTPUT_ROOT = _resolve("outputs/common_esto_dashboard")


#%%
# User-tuned constants.
COMPARISON_SCOPE = os.getenv("COMMON_ESTO_COMPARISON_SCOPE", "leap_vs_esto_vs_ninth")
ECONOMY = os.getenv("COMMON_ESTO_ECONOMY", "20_USA")
MIN_YEAR = 1990
MAX_YEAR = 2060

RUN_DASHBOARD_WORKFLOW = True
CLEAR_EXISTING_OUTPUTS = True
PUBLISH_TO_DOCS = False  # Set True to copy dashboard files to docs/<economy>/ after each run.
REGEN_COMMON_ESTO_FAST_PATH = os.getenv("COMMON_ESTO_REGEN_FAST_PATH", "0").strip().lower() in {"1", "true", "yes"}


#%%
def maybe_regen_common_esto_fast_path() -> None:
    """Optionally refresh upstream Common ESTO outputs before dashboard rendering."""
    if not REGEN_COMMON_ESTO_FAST_PATH:
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


def run_dashboard_workflow() -> dict[str, object]:
    """Run the production Common ESTO dashboard."""
    maybe_regen_common_esto_fast_path()
    template = load_json(TEMPLATE_PATH)
    series_config = json.loads(SERIES_CONFIG_PATH.read_text(encoding="utf-8"))
    raw_df = load_common_esto_data(INPUT_DATA_PATH)
    raw_df = enrich_with_component_metadata(raw_df, COMMON_ROWS_PATH)
    filtered_df = filter_common_esto_data(
        raw_df,
        comparison_scope=COMPARISON_SCOPE,
        economy=ECONOMY,
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    visible_df = apply_visible_series(filtered_df, series_config.get("visible_series", []))
    visible_df = apply_sign_semantics(visible_df, template.get("sign_semantics"))
    scope_filtered_df = filter_common_esto_data(
        raw_df,
        comparison_scope="__all_scopes__",
        economy=ECONOMY,
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    scope_visible_df = apply_visible_series(scope_filtered_df, series_config.get("visible_series", []))
    scope_visible_df = apply_sign_semantics(scope_visible_df, template.get("sign_semantics"))
    layout = build_output_layout(OUTPUT_ROOT, ECONOMY.replace("_", ""), clear_existing=CLEAR_EXISTING_OUTPUTS)
    sign_summary_df = build_sign_semantics_summary(visible_df)
    sign_summary_df.to_csv(layout["supporting"] / "sign_semantics_summary.csv", index=False)
    manifest_df = render_dashboard(visible_df, template, series_config, layout, scope_df=scope_visible_df)
    print(f"Input rows read: {len(raw_df):,}")
    print(f"Rows after scope/economy/year filter: {len(filtered_df):,}")
    print(f"Rows after visible-series filter: {len(visible_df):,}")
    print(f"Charts written: {len(manifest_df):,}")
    print(f"Sign summary rows written: {len(sign_summary_df):,}")
    print(f"Dashboard index: {layout['dashboards'] / 'index.html'}")
    result: dict[str, object] = {
        "dashboard_index": str(layout["dashboards"] / "index.html"),
        "chart_manifest": str(layout["supporting"] / "chart_manifest.csv"),
        "sign_semantics_summary": str(layout["supporting"] / "sign_semantics_summary.csv"),
        "chart_count": len(manifest_df),
    }
    if PUBLISH_TO_DOCS:
        docs_root = REPO_ROOT / "docs"
        counts = publish_to_docs(layout, docs_root)
        print(f"Published to docs/: {counts}")
        result["docs_published"] = counts
    return result


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
