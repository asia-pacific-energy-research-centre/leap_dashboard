#%%
"""Summarise Common ESTO dashboard page density and noisy chart patterns."""

#%%
import csv
import os
from pathlib import Path

import pandas as pd


#%%
# Stable paths.
REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


#%%
# User-tuned constants.
DASHBOARD_OUTPUT_ROOT = _resolve(
    os.getenv("COMMON_ESTO_DASHBOARD_OUTPUT_ROOT", "outputs/common_esto_dashboard")
)
PAGE_NOISE_SUMMARY_PATH = DASHBOARD_OUTPUT_ROOT / "page_noise_summary.csv"
PAGE_NOISE_FLAGS_PATH = DASHBOARD_OUTPUT_ROOT / "page_noise_flags.csv"

HIGH_CHART_COUNT_THRESHOLD = 150
HIGH_SUPPRESSED_SHARE_THRESHOLD = 0.25
SPARSE_ONE_ROW_CHART_THRESHOLD = 10
# Large chart trees, suppressed candidates, and sparse one-row charts are valid
# dashboard outcomes. Keep their counts in the summary for inspection, but do
# not turn them into page-noise warnings.
ENABLE_HIGH_CHART_COUNT_DIAGNOSTIC = False
ENABLE_HIGH_SUPPRESSED_SHARE_DIAGNOSTIC = False
ENABLE_SPARSE_ONE_ROW_CHART_DIAGNOSTIC = False
RUN_PAGE_NOISE_ANALYSIS = True


#%%
def _bool_text(value: object) -> bool:
    """Parse manifest boolean text conservatively."""
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _read_manifest(path: Path) -> pd.DataFrame:
    """Read one chart manifest with safe numeric columns."""
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["row_count"] = pd.to_numeric(df.get("row_count", 0), errors="coerce").fillna(0)
    df["suppressed_bool"] = df.get("suppressed", False).apply(_bool_text)
    return df


def find_manifest_paths(output_root: Path) -> list[Path]:
    """Return chart manifests for rendered economy dashboards."""
    if not output_root.exists():
        return []
    paths = []
    for economy_dir in output_root.iterdir():
        manifest_path = economy_dir / "supporting_files" / "chart_manifest.csv"
        if economy_dir.is_dir() and manifest_path.exists():
            paths.append(manifest_path)
    return sorted(paths, key=lambda path: path.parts[-3])


def build_page_noise_summary(output_root: Path) -> pd.DataFrame:
    """Build one page-level density/noise summary row per economy and page."""
    rows: list[dict[str, object]] = []
    for manifest_path in find_manifest_paths(output_root):
        economy = manifest_path.parts[-3]
        manifest_df = _read_manifest(manifest_path)
        if manifest_df.empty:
            rows.append({
                "economy": economy,
                "page_key": "",
                "page_label": "",
                "chart_count": 0,
                "suppressed_count": 0,
                "suppressed_share": 0.0,
                "sparse_one_row_chart_count": 0,
                "flag_reasons": "empty_manifest",
            })
            continue
        grouped = manifest_df.groupby(["page_key", "page_label"], dropna=False)
        for (page_key, page_label), page_df in grouped:
            chart_count = len(page_df)
            suppressed_count = int(page_df["suppressed_bool"].sum())
            sparse_count = int((page_df["row_count"] <= 1).sum())
            suppressed_share = suppressed_count / chart_count if chart_count else 0.0
            flag_reasons: list[str] = []
            if (
                ENABLE_HIGH_CHART_COUNT_DIAGNOSTIC
                and chart_count > HIGH_CHART_COUNT_THRESHOLD
            ):
                flag_reasons.append("high_chart_count")
            if (
                ENABLE_HIGH_SUPPRESSED_SHARE_DIAGNOSTIC
                and suppressed_share > HIGH_SUPPRESSED_SHARE_THRESHOLD
            ):
                flag_reasons.append("high_suppressed_share")
            if (
                ENABLE_SPARSE_ONE_ROW_CHART_DIAGNOSTIC
                and sparse_count > SPARSE_ONE_ROW_CHART_THRESHOLD
            ):
                flag_reasons.append("many_sparse_one_row_charts")
            rows.append({
                "economy": economy,
                "page_key": page_key,
                "page_label": page_label,
                "chart_count": chart_count,
                "suppressed_count": suppressed_count,
                "suppressed_share": round(suppressed_share, 4),
                "sparse_one_row_chart_count": sparse_count,
                "flag_reasons": "; ".join(flag_reasons),
            })
    return pd.DataFrame(rows)


def write_page_noise_outputs(output_root: Path) -> dict[str, object]:
    """Write page noise summary and filtered flags CSVs."""
    summary_df = build_page_noise_summary(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(PAGE_NOISE_SUMMARY_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    flags_df = summary_df[summary_df["flag_reasons"].astype(str).str.strip() != ""].copy()
    flags_df.to_csv(PAGE_NOISE_FLAGS_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Page noise summary written: {PAGE_NOISE_SUMMARY_PATH}")
    print(f"Page noise flags written: {PAGE_NOISE_FLAGS_PATH}")
    print(f"Summary rows: {len(summary_df):,}")
    print(f"Flagged rows: {len(flags_df):,}")
    if not flags_df.empty:
        print("Flagged pages:")
        for _, row in flags_df.sort_values(["economy", "page_key"]).iterrows():
            print(
                f"- {row['economy']} {row['page_key']}: "
                f"{row['chart_count']} charts, "
                f"{row['suppressed_share']:.0%} suppressed, "
                f"{row['sparse_one_row_chart_count']} sparse; "
                f"{row['flag_reasons']}"
            )
    return {
        "summary_path": str(PAGE_NOISE_SUMMARY_PATH),
        "flags_path": str(PAGE_NOISE_FLAGS_PATH),
        "summary_rows": len(summary_df),
        "flagged_rows": len(flags_df),
    }


#%%
try:
    if RUN_PAGE_NOISE_ANALYSIS:
        PAGE_NOISE_RESULT = write_page_noise_outputs(DASHBOARD_OUTPUT_ROOT)
    else:
        print("Set RUN_PAGE_NOISE_ANALYSIS = True to analyze page density/noise.")
except Exception as exc:
    print("Common ESTO page noise analysis failed.")
    print(f"Error: {exc}")
    raise

#%%
