#%%
"""Render Common ESTO dashboards for all available economies and write a summary."""

#%%
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd


#%%
# Stable paths.
REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPO_ROOT / "codebase"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_data import (  # noqa: E402
    ALL_SCOPES,
    apply_sign_semantics,
    apply_visible_series,
    build_sign_semantics_summary,
    enrich_with_component_metadata,
    filter_common_esto_data,
    filter_template_for_leap_demand_coverage,
    load_common_esto_data,
)
from common_esto_dashboard_renderer import load_json, render_dashboard  # noqa: E402
from common_esto_dashboard_output_layout import build_output_layout  # noqa: E402

# The workflow module runs its full render (plus upstream data refresh and docs
# publish) at import time unless this env override is set first.
os.environ.setdefault("COMMON_ESTO_RUN_DASHBOARD_WORKFLOW", "0")
from common_esto_dashboard_workflow import _missing_leap_demand_branches  # noqa: E402


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


#%%
# User-tuned constants.
LEAP_MAPPINGS_ROOT = _resolve(
    os.getenv("LEAP_MAPPINGS_ROOT", REPO_ROOT.parent / "leap_mappings")
)
INPUT_DATA_PATH = _resolve(LEAP_MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_comparison_data.csv")
OUTPUT_CONTRACT_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_OUTPUT_CONTRACT_PATH",
        LEAP_MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_output_contract.json",
    )
)
COMMON_ROWS_PATH = _resolve(LEAP_MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_rows.csv")
TEMPLATE_PATH = _resolve("config/common_esto_dashboard/common_esto_dashboard_template.json")
SERIES_CONFIG_PATH = _resolve("config/common_esto_dashboard/series_config.json")
OUTPUT_ROOT = _resolve("outputs/common_esto_dashboard")
SUMMARY_PATH = OUTPUT_ROOT / "render_summary.csv"

COMPARISON_SCOPE = os.getenv("COMMON_ESTO_COMPARISON_SCOPE", "esto_leap_ninth")
WIDE_FILE_SCOPE = os.getenv("COMMON_ESTO_WIDE_FILE_SCOPE", "esto_leap_ninth")
USE_OUTPUT_CONTRACT = os.getenv("COMMON_ESTO_USE_OUTPUT_CONTRACT", "0") != "0"
MIN_YEAR = 2010
MAX_YEAR = 2060
ECONOMIES_TO_RENDER: list[str] = [
    item.strip()
    for item in os.getenv("COMMON_ESTO_ECONOMIES", "").split(",")
    if item.strip()
]  # Empty means all economies found in the input.
CLEAR_EXISTING_OUTPUTS = os.getenv("COMMON_ESTO_CLEAR_EXISTING_OUTPUTS", "1") != "0"
RENDER_DASHBOARDS = os.getenv("COMMON_ESTO_RENDER_DASHBOARDS", "1") != "0"
RUN_BATCH_RENDER = os.getenv("COMMON_ESTO_RUN_BATCH_RENDER", "1") != "0"


#%%
def _dashboard_economy(value: object) -> str:
    """Return the compact dashboard economy key used in output folders."""
    return str(value or "").replace("_", "").strip()


def _normalise_economy_column(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize compact and underscore economy spellings into one dashboard key."""
    out = df.copy()
    out["economy"] = out["economy"].apply(_dashboard_economy)
    return out


def _available_economies(df: pd.DataFrame) -> list[str]:
    """Return economy keys sorted in APEC code order."""
    return sorted(e for e in df["economy"].dropna().astype(str).unique() if e)


def _existing_dashboard_economies() -> list[str]:
    """Return economy keys that already have rendered dashboard folders."""
    if not OUTPUT_ROOT.exists():
        return []
    economies = []
    for path in OUTPUT_ROOT.iterdir():
        if path.is_dir() and (path / "dashboards" / "index.html").exists():
            economies.append(path.name)
    return sorted(economies)


def _dashboard_updated_label() -> str:
    """Return the human-facing timestamp shown in rendered dashboard headers."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _metadata_path(economy: str) -> Path:
    return OUTPUT_ROOT / economy / "supporting_files" / "dashboard_metadata.json"


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


def _read_dashboard_updated_label(economy: str) -> str:
    """Return the saved dashboard timestamp for an existing output, if available."""
    path = _metadata_path(economy)
    if not path.exists():
        return ""
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        return str(metadata.get("dashboard_updated_label") or "")
    except Exception:
        return ""


def _render_one_economy(
    raw_df: pd.DataFrame,
    template: dict,
    series_config: dict,
    economy: str,
) -> dict[str, object]:
    """Render one economy dashboard and return a summary row."""
    result: dict[str, object] = {
        "economy": economy,
        "status": "error",
        "input_rows": int((raw_df["economy"].astype(str) == economy).sum()),
        "filtered_rows": 0,
        "visible_rows": 0,
        "chart_count": 0,
        "dashboard_path": "",
        "dashboard_updated": "",
        "error": "",
    }
    try:
        missing_leap_branches = _missing_leap_demand_branches(economy)
        template = filter_template_for_leap_demand_coverage(template, missing_leap_branches)
        filtered_df = filter_common_esto_data(
            raw_df,
            comparison_scope=COMPARISON_SCOPE,
            economy=economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
        visible_df = apply_visible_series(filtered_df, series_config.get("visible_series", []))
        visible_df = apply_sign_semantics(visible_df, template.get("sign_semantics"))
        scope_filtered_df = filter_common_esto_data(
            raw_df,
            comparison_scope=ALL_SCOPES,
            economy=economy,
            min_year=MIN_YEAR,
            max_year=MAX_YEAR,
        )
        scope_visible_df = apply_visible_series(scope_filtered_df, series_config.get("visible_series", []))
        scope_visible_df = apply_sign_semantics(scope_visible_df, template.get("sign_semantics"))
        layout = build_output_layout(OUTPUT_ROOT, economy, clear_existing=CLEAR_EXISTING_OUTPUTS)
        dashboard_updated_label = _dashboard_updated_label()
        sign_summary_df = build_sign_semantics_summary(visible_df)
        sign_summary_df.to_csv(layout["supporting"] / "sign_semantics_summary.csv", index=False)
        manifest_df = render_dashboard(
            visible_df,
            template,
            series_config,
            layout,
            scope_df=scope_visible_df,
            dashboard_updated_label=dashboard_updated_label,
        )
        _write_dashboard_metadata(layout, dashboard_updated_label)

        result.update({
            "status": "ok",
            "filtered_rows": len(filtered_df),
            "visible_rows": len(visible_df),
            "chart_count": len(manifest_df),
            "dashboard_path": str(layout["dashboards"] / "index.html"),
            "dashboard_updated": dashboard_updated_label,
        })
    except Exception as exc:
        result["error"] = f"{exc}\n{traceback.format_exc(limit=5)}"
    return result


def _summarise_existing_economy(raw_df: pd.DataFrame, economy: str) -> dict[str, object]:
    """Return a summary row for an already-rendered dashboard."""
    dashboard_root = OUTPUT_ROOT / economy
    manifest_path = dashboard_root / "supporting_files" / "chart_manifest.csv"
    result: dict[str, object] = {
        "economy": economy,
        "status": "error",
        "input_rows": int((raw_df["economy"].astype(str) == economy).sum()),
        "filtered_rows": "",
        "visible_rows": "",
        "chart_count": 0,
        "dashboard_path": str(dashboard_root / "dashboards" / "index.html"),
        "dashboard_updated": _read_dashboard_updated_label(economy),
        "error": "",
    }
    if not manifest_path.exists():
        result["error"] = f"Missing chart manifest: {manifest_path}"
        return result
    try:
        manifest_df = pd.read_csv(manifest_path)
    except pd.errors.EmptyDataError:
        result["error"] = f"Empty chart manifest: {manifest_path}"
        return result
    result["status"] = "ok"
    result["chart_count"] = len(manifest_df)
    return result


def _write_summary(summary_rows: list[dict[str, object]]) -> pd.DataFrame:
    """Write the current render summary and return it as a DataFrame."""
    summary_df = pd.DataFrame(summary_rows)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_PATH, index=False)
    return summary_df


def render_all_economies() -> pd.DataFrame:
    """Load data once, render selected economies, and write render_summary.csv."""
    template = load_json(TEMPLATE_PATH)
    series_config = json.loads(SERIES_CONFIG_PATH.read_text(encoding="utf-8"))
    raw_df = load_common_esto_data(
        INPUT_DATA_PATH,
        wide_file_scope=WIDE_FILE_SCOPE,
        output_contract_path=OUTPUT_CONTRACT_PATH if USE_OUTPUT_CONTRACT else None,
    )
    raw_df = _normalise_economy_column(raw_df)
    raw_df = enrich_with_component_metadata(raw_df, COMMON_ROWS_PATH)

    requested_economies = [_dashboard_economy(e) for e in ECONOMIES_TO_RENDER]
    economies = requested_economies or _available_economies(raw_df)
    summary_rows: list[dict[str, object]] = []
    for economy in economies:
        if RENDER_DASHBOARDS:
            print(f"Rendering {economy}...")
            row = _render_one_economy(raw_df, template, series_config, economy)
        else:
            print(f"Summarising existing output for {economy}...")
            row = _summarise_existing_economy(raw_df, economy)
        summary_rows.append(row)
        _write_summary(summary_rows)
        print(f"  {row['status']}: {row['chart_count']} charts, {row['visible_rows']} visible rows")
        if row["error"]:
            print(f"  error: {row['error']}")

    if requested_economies:
        rendered = set(economies)
        for economy in _existing_dashboard_economies():
            if economy in rendered:
                continue
            print(f"Keeping existing output for {economy} in summary.")
            summary_rows.append(_summarise_existing_economy(raw_df, economy))

    summary_df = _write_summary(summary_rows)
    print(f"Summary written: {SUMMARY_PATH}")
    return summary_df


#%%
try:
    if RUN_BATCH_RENDER:
        BATCH_RENDER_SUMMARY = render_all_economies()
        if not BATCH_RENDER_SUMMARY.empty and (BATCH_RENDER_SUMMARY["status"] != "ok").any():
            raise RuntimeError("One or more Common ESTO dashboard renders failed.")
    else:
        print("Set RUN_BATCH_RENDER = True to render all economies.")
except Exception as exc:
    print("Common ESTO batch render failed.")
    print(f"Error: {exc}")
    raise

#%%
