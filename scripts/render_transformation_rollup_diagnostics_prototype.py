#%%
"""Render the 20_USA mapping diagnostics prototype without ESTO Extended."""

from pathlib import Path
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
COMPARISON_DATA_PATH = MAPPINGS_ROOT / "results" / "common_esto" / "common_esto_comparison_data.csv"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "prototypes" / "transformation_rollup_diagnostics"
ECONOMY = "20_USA"
COMPARISON_SCOPE = "esto_leap_ninth"
CHUNK_SIZE = 250_000

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.common_esto_dashboard_mapping_diagnostics import write_mapping_diagnostics_page


#%%
def _read_prototype_values() -> pd.DataFrame:
    """Load only the diagnostics columns and exclude the memory-heavy Extended axis."""
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
    for chunk in pd.read_csv(COMPARISON_DATA_PATH, usecols=required_columns, chunksize=CHUNK_SIZE):
        selected = chunk[
            chunk["economy"].astype(str).isin({ECONOMY, ECONOMY.replace("_", "")})
            & chunk["comparison_scope"].astype(str).eq(COMPARISON_SCOPE)
            & ~chunk["source_system"].astype(str).eq("ESTO_EXTENDED")
        ]
        if not selected.empty:
            selected_chunks.append(selected)
    if not selected_chunks:
        return pd.DataFrame(columns=required_columns)
    return pd.concat(selected_chunks, ignore_index=True)


def render_prototype() -> dict[str, str]:
    """Write a compact, current prototype at the path open in the dashboard."""
    comparison_data = _read_prototype_values()
    layout = {
        "dashboards": OUTPUT_ROOT / "dashboards",
        "supporting": OUTPUT_ROOT / "supporting",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    result = write_mapping_diagnostics_page(
        layout,
        MAPPINGS_ROOT,
        dashboard_updated_label="20_USA prototype — ESTO Extended excluded",
        economy=ECONOMY,
        comparison_data=comparison_data,
    )
    print(f"Rows supplied to diagnostics: {len(comparison_data):,}")
    print(result["page"])
    return result


#%%
if __name__ == "__main__":
    render_prototype()

#%%
