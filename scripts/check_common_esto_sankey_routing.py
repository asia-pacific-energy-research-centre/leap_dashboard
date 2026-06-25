#%%
"""Validate draft Sankey routing rules against Common ESTO comparison rows."""

#%%
import sys
from pathlib import Path

import pandas as pd


#%%
# Stable paths.
REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPO_ROOT / "codebase" / "common_esto_dashboard"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_data import filter_common_esto_data, load_common_esto_data  # noqa: E402


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


#%%
# User-tuned constants.
INPUT_DATA_PATH = _resolve("tests/fixtures/common_esto_dashboard/common_esto_comparison_data_sample.csv")
ROUTING_TABLE_PATH = _resolve("config/common_esto_dashboard/sankey_routing_table_draft.csv")
OUTPUT_DIR = _resolve("outputs/common_esto_dashboard/sankey_routing_qa")

ECONOMY = "20_USA"
COMPARISON_SCOPE = "leap_vs_esto_vs_ninth"
MIN_YEAR = 1990
MAX_YEAR = 2060
RUN_SANKEY_ROUTING_QA = True

REQUIRED_ROUTING_COLUMNS = [
    "route_id",
    "enabled",
    "diagram_key",
    "comparison_scope",
    "source_node",
    "target_node",
    "flow_code_prefixes",
    "product_code_prefixes",
    "value_sign",
    "include_in_total",
    "priority",
]


#%%
def _bool_text(value: object) -> bool:
    """Parse a text boolean field."""
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _split_prefixes(value: object) -> list[str]:
    """Split semicolon/comma-delimited prefix cells into a clean list."""
    text = str(value or "").strip()
    if not text:
        return []
    text = text.replace(",", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def _code_matches_prefixes(code: object, prefixes: list[str]) -> bool:
    """Return whether a code matches any exact or dotted-prefix rule."""
    if not prefixes:
        return True
    code_text = str(code or "").strip()
    for prefix in prefixes:
        if code_text == prefix or code_text.startswith(prefix + "."):
            return True
    return False


def _value_matches_sign(value: float, value_sign: object) -> bool:
    """Return whether a row value matches the routing sign rule."""
    sign = str(value_sign or "both").strip().casefold()
    if sign == "positive":
        return value > 0
    if sign == "negative":
        return value < 0
    if sign in {"both", "any", ""}:
        return value != 0
    return False


def load_routing_table(path: Path) -> pd.DataFrame:
    """Load and validate the Sankey routing table draft."""
    if not path.exists():
        raise FileNotFoundError(f"Missing Sankey routing table: {path}")
    routes = pd.read_csv(path).fillna("")
    missing = [column for column in REQUIRED_ROUTING_COLUMNS if column not in routes.columns]
    if missing:
        raise ValueError(f"Sankey routing table is missing columns: {missing}")
    routes["enabled_bool"] = routes["enabled"].apply(_bool_text)
    routes["include_in_total_bool"] = routes["include_in_total"].apply(_bool_text)
    routes["priority"] = pd.to_numeric(routes["priority"], errors="coerce").fillna(0).astype(int)
    return routes


def load_candidate_rows(path: Path, economy: str, comparison_scope: str) -> pd.DataFrame:
    """Load candidate row totals to validate against routing rules."""
    raw_df = load_common_esto_data(path)
    filtered = filter_common_esto_data(
        raw_df,
        comparison_scope=comparison_scope,
        economy=economy,
        min_year=MIN_YEAR,
        max_year=MAX_YEAR,
    )
    if filtered.empty:
        return filtered
    grouped = (
        filtered.groupby(
            [
                "comparison_scope",
                "economy",
                "common_flow_code",
                "common_flow_label",
                "common_product_code",
                "common_product_label",
            ],
            as_index=False,
        )
        .agg(
            row_count=("value", "size"),
            min_value=("value", "min"),
            max_value=("value", "max"),
            total_abs_value=("value", lambda values: float(values.abs().sum())),
        )
    )
    return grouped[grouped["total_abs_value"] > 0].copy()


def matching_route_ids(candidate_row: pd.Series, active_routes: pd.DataFrame) -> list[str]:
    """Return active route IDs that match one candidate flow/product row."""
    matches: list[str] = []
    for _, route in active_routes.sort_values(["priority", "route_id"]).iterrows():
        if str(route["comparison_scope"]).strip() != str(candidate_row["comparison_scope"]).strip():
            continue
        flow_prefixes = _split_prefixes(route["flow_code_prefixes"])
        product_prefixes = _split_prefixes(route["product_code_prefixes"])
        if not _code_matches_prefixes(candidate_row["common_flow_code"], flow_prefixes):
            continue
        if not _code_matches_prefixes(candidate_row["common_product_code"], product_prefixes):
            continue
        if _value_matches_sign(float(candidate_row["max_value"]), route["value_sign"]) or _value_matches_sign(float(candidate_row["min_value"]), route["value_sign"]):
            matches.append(str(route["route_id"]))
    return matches


def build_sankey_routing_qa(candidate_rows: pd.DataFrame, routes: pd.DataFrame) -> pd.DataFrame:
    """Return row-level route coverage QA for the draft Sankey routes."""
    active_routes = routes[routes["enabled_bool"]].copy()
    qa_rows: list[dict[str, object]] = []
    for _, row in candidate_rows.iterrows():
        route_ids = matching_route_ids(row, active_routes)
        if len(route_ids) == 0:
            status = "no_route"
        elif len(route_ids) == 1:
            status = "one_route"
        else:
            status = "multiple_routes"
        qa_rows.append({
            "comparison_scope": row["comparison_scope"],
            "economy": row["economy"],
            "common_flow_code": row["common_flow_code"],
            "common_flow_label": row["common_flow_label"],
            "common_product_code": row["common_product_code"],
            "common_product_label": row["common_product_label"],
            "row_count": row["row_count"],
            "total_abs_value": row["total_abs_value"],
            "route_status": status,
            "route_ids": "; ".join(route_ids),
        })
    return pd.DataFrame(qa_rows)


def write_sankey_routing_qa() -> dict[str, object]:
    """Run draft Sankey routing QA and write route coverage outputs."""
    routes = load_routing_table(ROUTING_TABLE_PATH)
    candidates = load_candidate_rows(INPUT_DATA_PATH, ECONOMY, COMPARISON_SCOPE)
    qa_df = build_sankey_routing_qa(candidates, routes)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    route_summary = (
        qa_df.groupby("route_status", as_index=False)
        .agg(row_count=("route_status", "size"), total_abs_value=("total_abs_value", "sum"))
        .sort_values("route_status")
    )
    qa_path = OUTPUT_DIR / "sankey_routing_row_qa.csv"
    summary_path = OUTPUT_DIR / "sankey_routing_summary.csv"
    qa_df.to_csv(qa_path, index=False)
    route_summary.to_csv(summary_path, index=False)

    print(f"Routes read: {len(routes):,}")
    print(f"Active routes: {int(routes['enabled_bool'].sum()):,}")
    print(f"Candidate rows checked: {len(candidates):,}")
    print(f"Route QA written: {qa_path}")
    print(f"Route summary written: {summary_path}")
    if not route_summary.empty:
        print(route_summary.to_string(index=False))
    return {
        "routes_read": len(routes),
        "active_routes": int(routes["enabled_bool"].sum()),
        "candidate_rows": len(candidates),
        "qa_path": str(qa_path),
        "summary_path": str(summary_path),
    }


#%%
try:
    if RUN_SANKEY_ROUTING_QA:
        SANKEY_ROUTING_QA_RESULT = write_sankey_routing_qa()
    else:
        print("Set RUN_SANKEY_ROUTING_QA = True to check draft Sankey routing.")
except Exception as exc:
    print("Common ESTO Sankey routing QA failed.")
    print(f"Error: {exc}")
    raise

#%%
