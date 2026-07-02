#%%
"""Load and prepare common ESTO comparison data for dashboard rendering."""

#%%
import re
from pathlib import Path

import numpy as np
import pandas as pd


#%%
DEFAULT_COMPARISON_SCOPE = "leap_vs_esto_vs_ninth"
ID_COLUMNS_WIDE = ["economy", "scenario", "product", "flow"]

REQUIRED_COLUMNS = [
    "comparison_scope",
    "source_system",
    "economy",
    "scenario",
    "year",
    "common_flow_code",
    "common_flow_name",
    "common_flow_label",
    "common_product_code",
    "common_product_name",
    "common_product_label",
    "value",
]

COMPONENT_METADATA_COLUMNS = [
    "common_row_basis",
    "is_exact_row",
    "requires_rollup",
    "source_aggregate_labels",
    "source_aggregate_group_ids",
    "component_esto_flow",
    "component_esto_product",
    "component_flow_code",
    "component_flow_name",
    "component_product_code",
    "component_product_name",
    "common_row_basis",
    "aggregate_group_source",
    "aggregate_group_source_id",
    "aggregation_reason",
]


#%%
def get_year_columns(df: pd.DataFrame) -> list[str]:
    """Return columns whose names are plain year values."""
    return [column for column in df.columns if re.fullmatch(r"\d{4}", str(column))]


def split_code_name(label: object) -> tuple[str, str, str]:
    """Split a common ESTO label into code, name, and original label."""
    text = str(label or "").strip()
    if not text:
        return "", "", ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], "", text
    code, name = parts[0], parts[1]
    return code, name, text


def parse_combined_scenario(value: object) -> tuple[str, str]:
    """Split wide-file scenario strings into source system and scenario."""
    text = str(value or "").strip()
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    source_system = parts[0].upper()
    scenario = parts[1] if len(parts) > 1 else ""
    if source_system == "9TH":
        source_system = "NINTH"
    return source_system, scenario


def apply_sign_semantics(df: pd.DataFrame, sign_rules: list[dict]) -> pd.DataFrame:
    """Attach sign-convention metadata based on common ESTO flow/sector."""
    if not sign_rules:
        raise ValueError("Template is missing required 'sign_semantics' rules.")
    out = df.copy()

    codes = out["common_flow_code"].astype(str).str.strip()
    labels = out["common_flow_label"].astype(str)

    rule_masks: list[np.ndarray] = []
    for rule in sign_rules:
        mask = pd.Series(False, index=out.index)
        for prefix in rule.get("flow_code_prefixes", []):
            p = str(prefix).strip()
            mask = mask | (codes == p) | codes.str.startswith(p + ".")
        for keyword in rule.get("flow_keywords", []):
            mask = mask | labels.str.contains(re.escape(str(keyword)), case=False, na=False, regex=True)
        rule_masks.append(mask.values)

    def assign_field(field: str, default_val: str) -> pd.Series:
        choices = [str(rule.get(field, default_val)) for rule in sign_rules]
        return pd.Series(np.select(rule_masks, choices, default=default_val), index=out.index)

    out["sign_rule_id"] = assign_field("rule_id", "unclassified")
    out["sign_convention"] = assign_field("sign_convention", "unclassified")
    out["expected_sign"] = assign_field("expected_sign", "both")
    out["positive_value_meaning"] = assign_field("positive_value_meaning", "positive value; no sector sign rule matched")
    out["negative_value_meaning"] = assign_field("negative_value_meaning", "negative value; no sector sign rule matched")
    out["zero_value_meaning"] = assign_field("zero_value_meaning", "zero value; no sector sign rule matched")

    values = out["value"].astype(float)
    expected = out["expected_sign"]
    out["sign_status"] = np.select(
        [
            values == 0,
            (expected == "positive") & (values > 0),
            (expected == "positive") & (values < 0),
            (expected == "negative") & (values < 0),
            (expected == "negative") & (values > 0),
            values > 0,
        ],
        ["zero", "expected_positive", "unexpected_negative", "expected_negative", "unexpected_positive", "valid_positive"],
        default="valid_negative",
    )

    pos_interp = assign_field("positive_value_meaning", "positive value; no sector sign rule matched")
    neg_interp = assign_field("negative_value_meaning", "negative value; no sector sign rule matched")
    zero_interp = assign_field("zero_value_meaning", "zero value; no sector sign rule matched")
    out["sign_interpretation"] = np.where(values == 0, zero_interp, np.where(values > 0, pos_interp, neg_interp))

    out["plot_value"] = out["value"]
    return out


def build_sign_semantics_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise sign conventions and potential sign issues by flow/product/series."""
    required = {"sign_rule_id", "sign_convention", "expected_sign", "sign_status"}
    if df.empty or not required.issubset(set(df.columns)):
        return pd.DataFrame()

    grouped = (
        df.groupby(
            [
                "comparison_scope",
                "source_system",
                "scenario",
                "common_flow_label",
                "common_product_label",
                "sign_rule_id",
                "sign_convention",
                "expected_sign",
                "positive_value_meaning",
                "negative_value_meaning",
            ],
            as_index=False,
        )
        .agg(
            row_count=("value", "size"),
            nonzero_count=("value", lambda values: int((values != 0).sum())),
            positive_count=("value", lambda values: int((values > 0).sum())),
            negative_count=("value", lambda values: int((values < 0).sum())),
            min_value=("value", "min"),
            max_value=("value", "max"),
            sign_statuses=("sign_status", lambda values: "; ".join(sorted(set(map(str, values))))),
        )
        .sort_values(["source_system", "scenario", "common_flow_label", "common_product_label"])
    )
    grouped["has_unexpected_sign"] = grouped["sign_statuses"].str.contains("unexpected", case=False, na=False)
    return grouped


def load_wide_common_esto_data(path: Path) -> pd.DataFrame:
    """Load a wide common ESTO comparison file and convert it to long form."""
    wide_df = pd.read_csv(path, low_memory=False).fillna(0)
    missing_columns = [column for column in ID_COLUMNS_WIDE if column not in wide_df.columns]
    if missing_columns:
        raise ValueError(f"Wide common ESTO file is missing columns: {missing_columns}")
    year_columns = get_year_columns(wide_df)
    if not year_columns:
        raise ValueError("Wide common ESTO file does not contain year columns.")

    long_df = wide_df.melt(
        id_vars=ID_COLUMNS_WIDE,
        value_vars=year_columns,
        var_name="year",
        value_name="value",
    )
    scenario_parts = long_df["scenario"].apply(parse_combined_scenario)
    long_df["source_system"] = scenario_parts.apply(lambda item: item[0])
    long_df["scenario"] = scenario_parts.apply(lambda item: item[1])
    flow_parts = long_df["flow"].apply(split_code_name)
    product_parts = long_df["product"].apply(split_code_name)
    long_df["common_flow_code"] = flow_parts.apply(lambda item: item[0])
    long_df["common_flow_name"] = flow_parts.apply(lambda item: item[1])
    long_df["common_flow_label"] = flow_parts.apply(lambda item: item[2])
    long_df["common_product_code"] = product_parts.apply(lambda item: item[0])
    long_df["common_product_name"] = product_parts.apply(lambda item: item[1])
    long_df["common_product_label"] = product_parts.apply(lambda item: item[2])
    long_df["comparison_scope"] = DEFAULT_COMPARISON_SCOPE
    long_df = long_df[REQUIRED_COLUMNS].copy()
    long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce").fillna(0)
    return long_df


def load_long_common_esto_data(path: Path) -> pd.DataFrame:
    """Load already-long common ESTO comparison data."""
    df = pd.read_csv(path, low_memory=False).fillna("")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Common ESTO data is missing required columns: {missing_columns}")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
    return df


def load_common_esto_data(path: Path) -> pd.DataFrame:
    """Load either long or wide common ESTO comparison data."""
    sample_df = pd.read_csv(path, nrows=5, low_memory=False)
    if all(column in sample_df.columns for column in REQUIRED_COLUMNS):
        return load_long_common_esto_data(path)
    if all(column in sample_df.columns for column in ID_COLUMNS_WIDE) and get_year_columns(sample_df):
        return load_wide_common_esto_data(path)
    raise ValueError(
        "Input file is neither long common ESTO data nor recognised wide data. "
        f"Columns found: {list(sample_df.columns)}"
    )


def join_unique_text(values: pd.Series) -> str:
    """Join unique non-empty values in stable display order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return "; ".join(out)


def load_common_esto_component_metadata(common_rows_path: Path) -> pd.DataFrame:
    """Load common-row component membership as one metadata row per common row."""
    common_rows = pd.read_csv(common_rows_path, low_memory=False).fillna("")
    if "common_row_id" in common_rows.columns:
        key_columns = ["comparison_scope", "common_row_id"]
    else:
        key_columns = [
            "comparison_scope",
            "common_flow_label",
            "common_product_label",
        ]
    missing_keys = [column for column in key_columns if column not in common_rows.columns]
    if missing_keys:
        raise ValueError(f"Common ESTO rows file is missing columns: {missing_keys}")

    # Always include label columns so callers can fall back to label-based merging
    # even when common_row_id is the primary key.
    extra_key_columns = [
        col for col in ["common_flow_label", "common_product_label"]
        if col not in key_columns and col in common_rows.columns
    ]
    all_key_columns = key_columns + extra_key_columns

    metadata_columns = [column for column in COMPONENT_METADATA_COLUMNS if column in common_rows.columns]
    if not metadata_columns:
        return common_rows[all_key_columns].drop_duplicates().copy()

    return (
        common_rows.groupby(all_key_columns, as_index=False)[metadata_columns]
        .agg(join_unique_text)
        .reset_index(drop=True)
    )


def enrich_with_component_metadata(df: pd.DataFrame, common_rows_path: Path | None) -> pd.DataFrame:
    """Attach component membership metadata without duplicating chart values."""
    if common_rows_path is None or not common_rows_path.exists() or df.empty:
        return df.copy()
    metadata = load_common_esto_component_metadata(common_rows_path)
    if "common_row_id" in df.columns and "common_row_id" in metadata.columns:
        merge_keys = ["comparison_scope", "common_row_id"]
    else:
        merge_keys = [
            "comparison_scope",
            "common_flow_label",
            "common_product_label",
        ]
    attach_columns = [
        column for column in metadata.columns
        if column in merge_keys or column not in df.columns
    ]
    out = df.merge(metadata[attach_columns], on=merge_keys, how="left")
    for column in COMPONENT_METADATA_COLUMNS:
        if column in out.columns:
            out[column] = out[column].fillna("").astype(str)
    return out


def filter_common_esto_data(
    df: pd.DataFrame,
    comparison_scope: str,
    economy: str,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    """Filter common ESTO data to the dashboard scope."""
    out = df[(df["economy"].astype(str) == str(economy))].copy()
    if "comparison_scope" in out.columns and comparison_scope in set(out["comparison_scope"].astype(str)):
        out = out[out["comparison_scope"].astype(str) == str(comparison_scope)].copy()
    if min_year is not None:
        out = out[out["year"] >= min_year].copy()
    if max_year is not None:
        out = out[out["year"] <= max_year].copy()
    return out.reset_index(drop=True)


def apply_visible_series(df: pd.DataFrame, visible_series: list[dict[str, str]]) -> pd.DataFrame:
    """Keep only configured source/scenario series, matching case-insensitively."""
    if df.empty:
        return df.copy()
    if not visible_series:
        return df.copy()
    keys = {
        (str(item.get("source_system", "")).casefold(), str(item.get("scenario", "")).casefold())
        for item in visible_series
    }
    row_keys = list(zip(df["source_system"].astype(str).str.casefold(), df["scenario"].astype(str).str.casefold()))
    mask = pd.Series([key in keys for key in row_keys], index=df.index)
    return df[mask].copy()

#%%
