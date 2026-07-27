#%%
"""Render the 20_USA mapping diagnostics prototype with an Extended-data toggle."""

from pathlib import Path
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.mapping_pipeline_provenance import resolve_mappings_root  # noqa: E402

MAPPINGS_ROOT = resolve_mappings_root(REPO_ROOT.parent / "leap_mappings")
COMPARISON_DATA_PATH = MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_comparison_data.csv"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "prototypes" / "transformation_rollup_diagnostics"
ECONOMY = "20_USA"
COMPARISON_SCOPE = "esto_leap_ninth"
ESTO_EXTENDED_COMPARISON_SCOPE = "esto_extended_leap_ninth"
INCLUDE_ESTO_EXTENDED_DATA = True
CHUNK_SIZE = 250_000

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.common_esto_dashboard_mapping_diagnostics import (
    load_esto_exact_values_for_economy,
    write_mapping_diagnostics_page,
)
from codebase.dashboard_page_fragment import provenance_banner_html, write_body_fragment
from codebase.mapping_pipeline_provenance import provenance_message


def _provenance_banner() -> str:
    """State which pipeline run this snapshot came from, and whether it is current."""
    message, tone = provenance_message(MAPPINGS_ROOT, page_label="This prototype")
    return provenance_banner_html(message, tone=tone)


#%%
def _read_prototype_values() -> pd.DataFrame:
    """Load diagnostic values, with Extended data available to the page toggle."""
    required_columns = [
        "economy",
        "comparison_scope",
        "source_system",
        "scenario",
        "year",
        "common_flow_label",
        "value",
    ]
    selected_chunks: list[pd.DataFrame] = []
    allowed_scopes = {COMPARISON_SCOPE}
    if INCLUDE_ESTO_EXTENDED_DATA:
        allowed_scopes.add(ESTO_EXTENDED_COMPARISON_SCOPE)
    for chunk in pd.read_csv(COMPARISON_DATA_PATH, usecols=required_columns, chunksize=CHUNK_SIZE):
        selected = chunk[
            chunk["economy"].astype(str).isin({ECONOMY, ECONOMY.replace("_", "")})
            & chunk["comparison_scope"].astype(str).isin(allowed_scopes)
        ]
        if not selected.empty:
            selected_chunks.append(selected)
    if not selected_chunks:
        return pd.DataFrame(columns=required_columns)
    return pd.concat(selected_chunks, ignore_index=True)


def render_prototype() -> dict[str, str]:
    """Write a compact, current prototype at the path open in the dashboard."""
    comparison_data = _read_prototype_values()
    esto_exact_values = load_esto_exact_values_for_economy(
        MAPPINGS_ROOT / "results" / "mapping_relationships" / "esto_results_exact_rows.csv",
        ECONOMY,
    )
    esto_extended_exact_values = load_esto_exact_values_for_economy(
        MAPPINGS_ROOT / "results" / "mapping_relationships" / "esto_extended_results_exact_rows.csv",
        ECONOMY,
        source_system="ESTO_EXTENDED_RAW",
    ) if INCLUDE_ESTO_EXTENDED_DATA else pd.DataFrame()
    layout = {
        "dashboards": OUTPUT_ROOT / "dashboards",
        "supporting": OUTPUT_ROOT / "supporting",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    result = write_mapping_diagnostics_page(
        layout,
        MAPPINGS_ROOT,
        dashboard_updated_label="20_USA prototype — ESTO Extended available from the diagnostics control",
        economy=ECONOMY,
        comparison_data=comparison_data,
        esto_exact_values=pd.concat([esto_exact_values, esto_extended_exact_values], ignore_index=True),
    )
    fragment_path = write_body_fragment(
        result["page"],
        title=f"Mapping diagnostics ({ECONOMY} prototype)",
        banner_html=_provenance_banner(),
    )
    result["body"] = str(fragment_path)
    print(f"Rows supplied to diagnostics: {len(comparison_data):,}")
    print(result["page"])
    print(fragment_path)
    return result


#%%
if __name__ == "__main__":
    render_prototype()

#%%
