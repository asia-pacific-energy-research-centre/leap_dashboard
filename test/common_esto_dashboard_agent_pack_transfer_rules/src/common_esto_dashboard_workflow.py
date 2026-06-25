#%%
"""Notebook-safe entry workflow for the common ESTO dashboard prototype."""

#%%
import json
import os
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
PACK_ROOT = CURRENT_FILE.parents[1]
if str(PACK_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACK_ROOT / "src"))

from common_esto_dashboard_data import (  # noqa: E402
    apply_sign_semantics,
    apply_visible_series,
    build_sign_semantics_summary,
    enrich_with_component_metadata,
    filter_common_esto_data,
    load_common_esto_data,
)
from common_esto_dashboard_renderer import load_json, render_dashboard  # noqa: E402
from output_layout import build_output_layout, publish_to_docs  # noqa: E402


#%%
# Stable paths.
DEFAULT_WIDE_INPUT_PATH = PACK_ROOT / "inputs" / "common_esto_comparison_wide.csv"
DEFAULT_LONG_INPUT_PATH = PACK_ROOT / "inputs" / "common_esto_comparison_data_sample.csv"
INPUT_DATA_PATH = Path(os.getenv("COMMON_ESTO_INPUT_DATA_PATH", DEFAULT_WIDE_INPUT_PATH if DEFAULT_WIDE_INPUT_PATH.exists() else DEFAULT_LONG_INPUT_PATH))
COMMON_ROWS_PATH = Path(os.getenv("COMMON_ESTO_ROWS_PATH", PACK_ROOT / "inputs" / "common_esto_rows.csv"))
TEMPLATE_PATH = PACK_ROOT / "config" / "common_esto_dashboard_template.json"
SERIES_CONFIG_PATH = PACK_ROOT / "config" / "series_config.json"
OUTPUT_ROOT = PACK_ROOT / "outputs"


#%%
# User-tuned constants.
COMPARISON_SCOPE = os.getenv("COMMON_ESTO_COMPARISON_SCOPE", "leap_vs_esto_vs_ninth")
ECONOMY = os.getenv("COMMON_ESTO_ECONOMY", "20_USA")
MIN_YEAR = 1990
MAX_YEAR = 2060

RUN_DASHBOARD_WORKFLOW = True
CLEAR_EXISTING_OUTPUTS = True
PUBLISH_TO_DOCS = False  # Set True to copy dashboard files to docs/<economy>/ after each run.


#%%
def run_dashboard_workflow() -> dict[str, object]:
    """Run the common ESTO dashboard prototype."""
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
        docs_root = PACK_ROOT / "docs"
        counts = publish_to_docs(layout, docs_root)
        print(f"Published to docs/: {counts}")
        result["docs_published"] = counts
    return result


#%%
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
