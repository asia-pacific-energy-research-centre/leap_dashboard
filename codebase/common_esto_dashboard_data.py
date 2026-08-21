#%%
"""Load and prepare common ESTO comparison data for dashboard rendering."""

#%%
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


#%%
DEFAULT_COMPARISON_SCOPE = "esto_leap_ninth"

# The wide common-ESTO file may stack multiple source comparison scopes in its
# ``comparison_scope`` column (e.g. "esto_leap_ninth" for the 3-way
# LEAP/ESTO/NINTH comparison and "esto_leap" for the 2-way LEAP/ESTO
# comparison). Shared scenarios such as "ESTO historical" and "LEAP Target" are
# byte-identical across scopes, so loading more than one scope double-counts
# those series. The loader selects exactly one file scope; callers may choose a
# different one in future (e.g. "esto_leap").
DEFAULT_WIDE_FILE_SCOPE = "esto_leap_ninth"

# Sentinel for ``filter_common_esto_data``: keep every comparison scope instead
# of selecting one. Only the alternate-scope diagnostic pages need this, since
# they compare scopes against each other. It must never reach a chart that sums
# values: scenarios shared between scopes are byte-identical, so an unfiltered
# frame double-counts them (see DEFAULT_WIDE_FILE_SCOPE above).
ALL_SCOPES = "__all_scopes__"
ID_COLUMNS_WIDE = ["economy", "scenario", "product", "flow"]
OUTPUT_CONTRACT_VERSION = "common_esto_output_contract_v1"

# Every row loaded through this module today is an energy series, so these are
# the defaults every existing input resolves to. A non-energy measure (e.g.
# emissions) is not registered anywhere in this pipeline yet — see
# leap_mappings' dataset_registry.csv "native_unit == 'PJ'" convention, which
# this module reads rather than assumes (load_dataset_registry_native_units).
DEFAULT_MEASURE = "energy"
DEFAULT_UNIT = "PJ"

# The 9th Outlook uses a 2021 base year for Russia only. Other sources in the
# Russia dashboard retain their own normal boundaries.
NINTH_BASE_YEAR_BY_ECONOMY = {"16RUS": 2021}


def ninth_base_year_for_economy(economy: object, default_base_year: int) -> int:
    """Return the 9th Outlook base year for one dashboard economy."""
    economy_key = str(economy or "").replace("_", "").strip().upper()
    return NINTH_BASE_YEAR_BY_ECONOMY.get(economy_key, int(default_base_year))


def ninth_base_year_for_rows(df: pd.DataFrame, default_base_year: int) -> int:
    """Resolve the 9th base year when rows belong to one known economy."""
    if df.empty or "economy" not in df.columns:
        return int(default_base_year)
    economy_keys = {
        str(value).replace("_", "").strip().upper()
        for value in df["economy"].dropna().unique()
        if str(value).strip()
    }
    if len(economy_keys) != 1:
        return int(default_base_year)
    return ninth_base_year_for_economy(next(iter(economy_keys)), default_base_year)

LEGACY_TEXT_COLUMNS = {
    "comparison_scope",
    "source_system",
    "economy",
    "scenario",
    "product",
    "flow",
    "component_esto_flow",
    "component_esto_product",
    "common_row_basis",
    "rollup_mode",
    "aggregate_group_source",
    "aggregation_reason",
    "notes",
}

CONTRACT_FACT_COLUMNS = [
    "comparison_scope",
    "source_system",
    "economy",
    "scenario",
    "year",
    "common_row_id",
    "value",
]
CONTRACT_FACT_KEY_COLUMNS = CONTRACT_FACT_COLUMNS[:6]

CONTRACT_METADATA_COLUMNS = [
    "comparison_scope",
    "common_row_id",
    "common_flow_code",
    "common_flow_name",
    "common_flow_label",
    "common_product_code",
    "common_product_name",
    "common_product_label",
    "common_row_basis",
    "is_exact_row",
    "requires_rollup",
    "is_non_expanding_rollup",
    "non_expanding_rollup_id",
    "rollup_mode",
    "source_aggregate_labels",
    "source_aggregate_group_ids",
]
CONTRACT_METADATA_KEY_COLUMNS = CONTRACT_METADATA_COLUMNS[:2]

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

CONTRACT_JOINED_COLUMNS = [
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
    "common_row_id",
    "common_row_basis",
    "is_exact_row",
    "requires_rollup",
    "is_non_expanding_rollup",
    "non_expanding_rollup_id",
    "rollup_mode",
    "source_aggregate_labels",
    "source_aggregate_group_ids",
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
    "non_expanding_rollup_id",
    "non_expanding_contributor_inputs",
]

SOURCE_CATEGORY_MAP_COLUMNS = [
    "comparison_scope",
    "source_system",
    "source_flow",
    "source_product",
    "common_flow_label",
    "common_product_label",
    "common_row_id",
]

UNMET_REQUIREMENTS_COLUMNS = [
    "comparison_scope",
    "source_system",
    "economy",
    "scenario",
    "year",
    "leap_product",
    "common_product_label",
    "fuel_mapping_status",
    "value",
]

HYDROGEN_ELECTRICITY_INPUT_COLUMNS = [
    "source_system",
    "scenario",
    "year",
    "value",
]


def load_hydrogen_electricity_input_data(
    raw_leap_results_path: Path,
    *,
    economy: str,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    """Load the LEAP-only electrolyser electricity input diagnostic.

    ``Electricity for hydrogen`` has no reviewed Common ESTO product mapping,
    so it must not be merged into normal comparison charts.  Select the exact
    Electrolysers branch only; this deliberately excludes Resources/Imports
    rows carrying the same LEAP product.
    """
    empty = pd.DataFrame(columns=HYDROGEN_ELECTRICITY_INPUT_COLUMNS)
    raw_path = Path(raw_leap_results_path)
    if not raw_path.exists():
        return empty

    raw = pd.read_csv(
        raw_path,
        usecols=["economy", "scenario", "year", "leap_flow", "leap_product", "value"],
        low_memory=False,
    )
    raw["economy"] = raw["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    selected = raw[
        raw["economy"].eq(str(economy).replace("_", "").strip())
        & raw["leap_flow"].astype(str).str.strip().str.casefold().eq(
            "hydrogen transformation/electrolysers"
        )
        & raw["leap_product"].astype(str).str.strip().str.casefold().eq(
            "electricity for hydrogen"
        )
    ].copy()
    if selected.empty:
        return empty
    selected["year"] = pd.to_numeric(selected["year"], errors="coerce")
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce").fillna(0.0)
    if min_year is not None:
        selected = selected[selected["year"] >= min_year]
    if max_year is not None:
        selected = selected[selected["year"] <= max_year]
    selected = selected[selected["value"].abs() > 1e-12]
    if selected.empty:
        return empty
    selected["source_system"] = "LEAP"
    return selected[HYDROGEN_ELECTRICITY_INPUT_COLUMNS].sort_values(
        ["scenario", "year"], ignore_index=True
    )


def load_unmet_requirements_data(
    raw_leap_results_path: Path,
    source_to_common_map_path: Path,
    *,
    comparison_scope: str,
    economy: str,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    """Load unmapped LEAP Unmet Requirements and resolve only their fuel axis.

    Unmet Requirements is intentionally not a Common ESTO balance flow. Its
    LEAP fuels are resolved through the published, scope-specific source map so
    the diagnostic chart uses the same product categories as the dashboard
    without reproducing mapping logic or allocating source aggregates.
    """
    empty = pd.DataFrame(columns=UNMET_REQUIREMENTS_COLUMNS)
    raw_path = Path(raw_leap_results_path)
    map_path = Path(source_to_common_map_path)
    if not raw_path.exists() or not map_path.exists():
        return empty

    required_raw = ["economy", "scenario", "year", "leap_flow", "leap_product", "value"]
    raw = pd.read_csv(raw_path, usecols=required_raw, low_memory=False)
    raw["economy"] = (
        raw["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    )
    selected = raw[
        raw["economy"].eq(str(economy).replace("_", "").strip())
        & raw["leap_flow"].astype(str).str.strip().str.casefold().eq("unmet requirements")
        & ~raw["leap_product"].astype(str).str.strip().str.casefold().eq("total")
    ].copy()
    selected["year"] = pd.to_numeric(selected["year"], errors="coerce")
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce").fillna(0.0)
    if min_year is not None:
        selected = selected[selected["year"] >= min_year]
    if max_year is not None:
        selected = selected[selected["year"] <= max_year]
    selected = selected[selected["value"].abs() > 1e-12]
    if selected.empty:
        return empty

    source_map = pd.read_csv(
        map_path,
        usecols=["scope", "system", "source_product", "common_product_label"],
        low_memory=False,
    )
    fuel_map = source_map[
        source_map["scope"].astype(str).eq(str(comparison_scope))
        & source_map["system"].astype(str).str.strip().str.casefold().eq("leap")
    ][["source_product", "common_product_label"]].drop_duplicates()
    ambiguous = fuel_map.groupby("source_product")["common_product_label"].nunique()
    ambiguous = ambiguous[ambiguous > 1]
    if not ambiguous.empty:
        raise ValueError(
            "Published LEAP fuel map is ambiguous for Unmet Requirements: "
            + ", ".join(map(str, ambiguous.index.tolist()))
        )

    selected = selected.merge(
        fuel_map,
        how="left",
        left_on="leap_product",
        right_on="source_product",
        validate="many_to_one",
    )
    mapped = selected["common_product_label"].notna()
    selected["fuel_mapping_status"] = np.where(mapped, "mapped", "unmapped")
    selected.loc[~mapped, "common_product_label"] = (
        "Unmapped LEAP fuel: " + selected.loc[~mapped, "leap_product"].astype(str)
    )
    selected["comparison_scope"] = str(comparison_scope)
    selected["source_system"] = "LEAP"
    selected = selected[UNMET_REQUIREMENTS_COLUMNS]
    return selected.sort_values(
        ["scenario", "common_product_label", "year"], ignore_index=True
    )


def load_active_power_interim_branches(
    audit_path: Path,
    economy: str,
    *,
    min_year: int | None = None,
    max_year: int | None = None,
) -> list[str]:
    """Return interim LEAP power branches retained in the rendered period."""
    path = Path(audit_path)
    if not path.exists():
        return []
    required = ["economy", "year", "status", "interim_branch"]
    audit = pd.read_csv(path, usecols=required, dtype=str).fillna("")
    audit["economy"] = (
        audit["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    )
    audit["year"] = pd.to_numeric(audit["year"], errors="coerce")
    active = audit[
        audit["economy"].eq(str(economy).replace("_", "").strip())
        & audit["status"].astype(str).str.casefold().eq("interim_only_retained")
    ].copy()
    if min_year is not None:
        active = active[active["year"] >= min_year]
    if max_year is not None:
        active = active[active["year"] <= max_year]
    return [
        str(value)
        for value in active["interim_branch"].drop_duplicates()
        if str(value).strip()
    ]


def load_source_category_map(
    source_to_common_map_path: Path | None = None,
    esto_to_common_map_path: Path | None = None,
) -> pd.DataFrame:
    """Load published native-source provenance for Common ESTO rows."""
    frames: list[pd.DataFrame] = []
    if source_to_common_map_path is not None:
        source_map = pd.read_csv(Path(source_to_common_map_path), dtype=str).fillna("")
        source_map = source_map.rename(
            columns={"scope": "comparison_scope", "system": "source_system"}
        )
        missing = [
            column for column in SOURCE_CATEGORY_MAP_COLUMNS
            if column not in source_map.columns
        ]
        if missing:
            raise ValueError(
                f"Source-to-Common map is missing columns: {missing}"
            )
        frames.append(source_map[SOURCE_CATEGORY_MAP_COLUMNS].copy())

    if esto_to_common_map_path is not None:
        esto_map = pd.read_csv(Path(esto_to_common_map_path), dtype=str).fillna("")
        required = [
            "comparison_scope",
            "component_esto_flow",
            "component_esto_product",
            "common_flow_label",
            "common_product_label",
            "common_row_id",
        ]
        missing = [column for column in required if column not in esto_map.columns]
        if missing:
            raise ValueError(f"ESTO-to-Common map is missing columns: {missing}")
        esto_map = esto_map.rename(
            columns={
                "component_esto_flow": "source_flow",
                "component_esto_product": "source_product",
            }
        )
        esto_map["source_system"] = "ESTO"
        frames.append(esto_map[SOURCE_CATEGORY_MAP_COLUMNS].copy())

    if not frames:
        return pd.DataFrame(columns=SOURCE_CATEGORY_MAP_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    combined["source_system"] = combined["source_system"].astype(str).str.upper()
    return combined.drop_duplicates(SOURCE_CATEGORY_MAP_COLUMNS).reset_index(drop=True)


def filter_ninth_pre_base_year_data(
    df: pd.DataFrame,
    *,
    base_year: int,
    include_pre_base_year_data: bool,
) -> pd.DataFrame:
    """Optionally remove 9th-edition rows before the dashboard base year."""
    if include_pre_base_year_data or df.empty:
        return df.copy()

    source_is_ninth = df["source_system"].astype(str).str.casefold().eq("ninth")
    is_pre_base_year = pd.to_numeric(df["year"], errors="coerce") < int(base_year)
    return df.loc[~(source_is_ninth & is_pre_base_year)].copy()


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


def _legacy_csv_text_dtypes(path: Path) -> dict[str, type[str]]:
    """Preserve identifier and display columns while leaving facts numeric."""
    columns = pd.read_csv(path, nrows=0).columns
    text_suffixes = ("_code", "_name", "_label", "_labels", "_id", "_ids")
    return {
        column: str
        for column in columns
        if column in LEGACY_TEXT_COLUMNS or column.endswith(text_suffixes)
    }


def apply_sign_semantics(df: pd.DataFrame, sign_rules: list[dict]) -> pd.DataFrame:
    """Attach sign-convention metadata based on common ESTO flow/sector.

    Sign rules are keyed on ``common_flow_code``/``common_flow_label``, which
    only means what the energy-balance identities (supply/TFC/TFEC) say it
    means for ``measure == "energy"`` rows. Any other measure gets a
    "not_applicable" placeholder instead of a sign classification derived
    from rules that were never written with it in mind (see the bottom of
    this function). A frame without a ``measure`` column is treated as
    all-energy, matching behaviour before that column existed.
    """
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

    if "measure" in out.columns:
        is_energy = out["measure"].astype(str).eq(DEFAULT_MEASURE)
        if (~is_energy).any():
            not_applicable_text = "not applicable; sign semantics apply only to measure == energy"
            not_applicable_columns = {
                "sign_rule_id": "not_applicable",
                "sign_convention": "not_applicable",
                "expected_sign": "not_applicable",
                "positive_value_meaning": not_applicable_text,
                "negative_value_meaning": not_applicable_text,
                "zero_value_meaning": not_applicable_text,
                "sign_status": "not_applicable",
                "sign_interpretation": not_applicable_text,
            }
            for column, placeholder in not_applicable_columns.items():
                out.loc[~is_energy, column] = placeholder
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


def load_wide_common_esto_data(
    path: Path,
    wide_file_scope: str = DEFAULT_WIDE_FILE_SCOPE,
) -> pd.DataFrame:
    """Load a wide common ESTO comparison file and convert it to long form.

    ``wide_file_scope`` selects a single value from the file's own
    ``comparison_scope`` column (see ``DEFAULT_WIDE_FILE_SCOPE``). This prevents
    double-counting scenarios that appear identically under more than one scope.
    """
    wide_df = pd.read_csv(
        path,
        dtype=_legacy_csv_text_dtypes(path),
        low_memory=False,
    ).fillna(0)
    missing_columns = [column for column in ID_COLUMNS_WIDE if column not in wide_df.columns]
    if missing_columns:
        raise ValueError(f"Wide common ESTO file is missing columns: {missing_columns}")
    if "comparison_scope" in wide_df.columns:
        wide_df["comparison_scope"] = wide_df["comparison_scope"].astype(str)
        available_scopes = sorted(set(wide_df["comparison_scope"]))
        if wide_file_scope not in available_scopes:
            raise ValueError(
                f"Wide common ESTO file does not contain scope {wide_file_scope!r}. "
                f"Available scopes: {available_scopes}"
            )
        wide_df = wide_df[wide_df["comparison_scope"] == wide_file_scope].copy()
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
    path = Path(path)
    if path.suffix.casefold() == ".parquet":
        df = pd.read_parquet(path)
        # Arrow dictionary columns become pandas Categoricals. Filling them
        # with an empty string fails unless that value is first added as a
        # category, so normalize text-like columns to ordinary objects before
        # applying the legacy empty-text convention.
        categorical_columns = list(df.select_dtypes(include=["category"]).columns)
        if categorical_columns:
            df[categorical_columns] = df[categorical_columns].astype(object)
        text_columns = sorted(
            set(df.select_dtypes(include=["object", "string"]).columns)
            | {
                column
                for column in REQUIRED_COLUMNS
                if column in df.columns and column not in {"year", "value"}
            }
        )
        if text_columns:
            df[text_columns] = df[text_columns].astype(object).fillna("")
    else:
        df = pd.read_csv(
            path,
            dtype=_legacy_csv_text_dtypes(path),
            low_memory=False,
        ).fillna("")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Common ESTO data is missing required columns: {missing_columns}")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
    return df


def _contract_member_path(manifest_path: Path, declared_path: object, member_name: str) -> Path:
    """Resolve one manifest member without permitting absolute or escaping paths."""
    path_text = str(declared_path or "").strip()
    if not path_text:
        raise ValueError(f"Output contract {member_name} is missing a declared path.")
    relative_path = Path(path_text.replace("\\", "/"))
    if relative_path.is_absolute():
        raise ValueError(
            f"Output contract {member_name} path must be relative to the manifest: {path_text!r}"
        )
    manifest_root = manifest_path.resolve().parent
    member_path = (manifest_root / relative_path).resolve()
    try:
        member_path.relative_to(manifest_root)
    except ValueError as error:
        raise ValueError(
            f"Output contract {member_name} path escapes the manifest directory: {path_text!r}"
        ) from error
    return member_path


def _sha256(path: Path) -> str:
    """Return a lowercase SHA-256 digest without loading a whole member into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_contract_member_declaration(
    declaration: object,
    *,
    member_name: str,
    expected_columns: list[str],
    expected_key_columns: list[str],
) -> dict:
    """Validate the strict v1 declaration for one tabular contract member."""
    if not isinstance(declaration, dict):
        raise ValueError(f"Output contract {member_name} declaration must be an object.")
    required_fields = {
        "path",
        "format",
        "columns",
        "key_columns",
        "row_count",
        "size_bytes",
        "sha256",
    }
    missing_fields = sorted(required_fields - set(declaration))
    if missing_fields:
        raise ValueError(
            f"Output contract {member_name} declaration is missing fields: {missing_fields}"
        )
    if declaration["format"] not in {"csv", "csv.gz"}:
        raise ValueError(
            f"Output contract {member_name} has unsupported format "
            f"{declaration['format']!r}; expected 'csv' or 'csv.gz'."
        )
    declared_name = str(declaration["path"]).strip().lower()
    suffix_matches = (
        declaration["format"] == "csv"
        and declared_name.endswith(".csv")
        and not declared_name.endswith(".csv.gz")
    ) or (
        declaration["format"] == "csv.gz"
        and declared_name.endswith(".csv.gz")
    )
    if not suffix_matches:
        raise ValueError(
            f"Output contract {member_name} format {declaration['format']!r} "
            f"does not match path {declaration['path']!r}."
        )
    if declaration["columns"] != expected_columns:
        raise ValueError(
            f"Output contract {member_name} columns must exactly equal {expected_columns}; "
            f"found {declaration['columns']!r}."
        )
    if declaration["key_columns"] != expected_key_columns:
        raise ValueError(
            f"Output contract {member_name} key_columns must exactly equal "
            f"{expected_key_columns}; found {declaration['key_columns']!r}."
        )
    for field in ["row_count", "size_bytes"]:
        value = declaration[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"Output contract {member_name} {field} must be a non-negative integer."
            )
    checksum = str(declaration["sha256"] or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError(
            f"Output contract {member_name} sha256 must be a 64-character hex digest."
        )
    return declaration


def _read_contract_member(
    manifest_path: Path,
    declaration: dict,
    *,
    member_name: str,
    expected_columns: list[str],
) -> pd.DataFrame:
    """Validate file identity and read one exactly declared contract member."""
    member_path = _contract_member_path(manifest_path, declaration["path"], member_name)
    if not member_path.is_file():
        raise FileNotFoundError(
            f"Output contract {member_name} member does not exist: {member_path}"
        )
    actual_size = member_path.stat().st_size
    if actual_size != declaration["size_bytes"]:
        raise ValueError(
            f"Output contract {member_name} size mismatch for {member_path}: "
            f"declared {declaration['size_bytes']}, found {actual_size}."
        )
    actual_checksum = _sha256(member_path)
    if actual_checksum != str(declaration["sha256"]).lower():
        raise ValueError(
            f"Output contract {member_name} SHA-256 mismatch for {member_path}."
        )
    frame = pd.read_csv(member_path, dtype=str, keep_default_na=False, low_memory=False)
    if list(frame.columns) != expected_columns:
        raise ValueError(
            f"Output contract {member_name} file columns must exactly equal "
            f"{expected_columns}; found {list(frame.columns)}."
        )
    if len(frame) != declaration["row_count"]:
        raise ValueError(
            f"Output contract {member_name} row count mismatch for {member_path}: "
            f"declared {declaration['row_count']}, found {len(frame)}."
        )
    return frame


def _duplicate_metadata_error(metadata: pd.DataFrame) -> ValueError:
    """Describe whether repeated metadata keys are identical or contradictory."""
    duplicate_rows = metadata[
        metadata.duplicated(CONTRACT_METADATA_KEY_COLUMNS, keep=False)
    ]
    conflicting_keys = 0
    for _, group in duplicate_rows.groupby(CONTRACT_METADATA_KEY_COLUMNS, dropna=False):
        if len(group.drop_duplicates()) > 1:
            conflicting_keys += 1
    if conflicting_keys:
        return ValueError(
            "Output contract metadata has conflicting rows for "
            f"{conflicting_keys} compound key(s) {CONTRACT_METADATA_KEY_COLUMNS}."
        )
    return ValueError(
        "Output contract metadata compound key is not unique: "
        f"{CONTRACT_METADATA_KEY_COLUMNS}."
    )


def load_common_esto_output_contract(manifest_path: Path) -> pd.DataFrame:
    """Load and strictly validate the opt-in Common ESTO v1 output contract."""
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Common ESTO output contract not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Could not read Common ESTO output contract {manifest_path}: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise ValueError("Common ESTO output contract must contain a JSON object.")
    if manifest.get("contract_version") != OUTPUT_CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported Common ESTO output contract version "
            f"{manifest.get('contract_version')!r}; expected {OUTPUT_CONTRACT_VERSION!r}."
        )
    if not str(manifest.get("run_id", "")).strip():
        raise ValueError("Common ESTO output contract is missing a non-empty run_id.")
    run_timestamp = str(manifest.get("run_timestamp_utc", "")).strip()
    try:
        parsed_timestamp = pd.Timestamp(run_timestamp)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Common ESTO output contract run_timestamp_utc is not a valid timestamp."
        ) from error
    if parsed_timestamp.tzinfo is None:
        raise ValueError("Common ESTO output contract run_timestamp_utc must include a timezone.")
    if manifest.get("observed_rows_only") is not True:
        raise ValueError(
            "Common ESTO output contract observed_rows_only must be exactly true."
        )

    fact_declaration = _validate_contract_member_declaration(
        manifest.get("fact"),
        member_name="fact",
        expected_columns=CONTRACT_FACT_COLUMNS,
        expected_key_columns=CONTRACT_FACT_KEY_COLUMNS,
    )
    metadata_declaration = _validate_contract_member_declaration(
        manifest.get("metadata"),
        member_name="metadata",
        expected_columns=CONTRACT_METADATA_COLUMNS,
        expected_key_columns=CONTRACT_METADATA_KEY_COLUMNS,
    )
    fact = _read_contract_member(
        manifest_path,
        fact_declaration,
        member_name="fact",
        expected_columns=CONTRACT_FACT_COLUMNS,
    )
    metadata = _read_contract_member(
        manifest_path,
        metadata_declaration,
        member_name="metadata",
        expected_columns=CONTRACT_METADATA_COLUMNS,
    )

    if fact[CONTRACT_FACT_KEY_COLUMNS].eq("").any(axis=None):
        raise ValueError("Output contract fact key columns must not contain empty values.")
    if metadata[CONTRACT_METADATA_KEY_COLUMNS].eq("").any(axis=None):
        raise ValueError("Output contract metadata key columns must not contain empty values.")
    if fact.duplicated(CONTRACT_FACT_KEY_COLUMNS).any():
        raise ValueError(
            f"Output contract fact key is not unique: {CONTRACT_FACT_KEY_COLUMNS}."
        )
    if metadata.duplicated(CONTRACT_METADATA_KEY_COLUMNS).any():
        raise _duplicate_metadata_error(metadata)

    numeric_years = pd.to_numeric(fact["year"], errors="coerce")
    valid_years = (
        numeric_years.notna()
        & np.isfinite(numeric_years)
        & numeric_years.eq(numeric_years.round())
        & numeric_years.between(1000, 9999)
    )
    if not valid_years.all():
        invalid_years = sorted(set(fact.loc[~valid_years, "year"].astype(str)))
        raise ValueError(f"Output contract fact contains invalid years: {invalid_years[:10]}")
    numeric_values = pd.to_numeric(fact["value"], errors="coerce")
    valid_values = numeric_values.notna() & numeric_values.map(math.isfinite)
    if not valid_values.all():
        invalid_values = sorted(set(fact.loc[~valid_values, "value"].astype(str)))
        raise ValueError(
            f"Output contract fact contains invalid numeric values: {invalid_values[:10]}"
        )

    fact_keys = fact[CONTRACT_METADATA_KEY_COLUMNS].drop_duplicates()
    metadata_keys = metadata[CONTRACT_METADATA_KEY_COLUMNS].drop_duplicates()
    missing_metadata = fact_keys.merge(
        metadata_keys,
        on=CONTRACT_METADATA_KEY_COLUMNS,
        how="left",
        indicator=True,
    )
    missing_metadata = missing_metadata[missing_metadata["_merge"] == "left_only"]
    if not missing_metadata.empty:
        raise ValueError(
            "Output contract fact contains compound keys with no metadata row: "
            f"{missing_metadata[CONTRACT_METADATA_KEY_COLUMNS].head(10).to_dict('records')}"
        )
    orphan_metadata = metadata_keys.merge(
        fact_keys,
        on=CONTRACT_METADATA_KEY_COLUMNS,
        how="left",
        indicator=True,
    )
    orphan_metadata = orphan_metadata[orphan_metadata["_merge"] == "left_only"]
    if not orphan_metadata.empty:
        raise ValueError(
            "Output contract metadata contains orphan compound keys with no fact row: "
            f"{orphan_metadata[CONTRACT_METADATA_KEY_COLUMNS].head(10).to_dict('records')}"
        )

    for column in ["is_exact_row", "requires_rollup", "is_non_expanding_rollup"]:
        normalized = metadata[column].str.strip().str.casefold()
        if not normalized.isin({"true", "false"}).all():
            invalid = sorted(set(metadata.loc[~normalized.isin({"true", "false"}), column]))
            raise ValueError(
                f"Output contract metadata column {column!r} contains invalid booleans: "
                f"{invalid[:10]}"
            )
        metadata[column] = normalized.eq("true")

    fact["year"] = numeric_years.astype(int)
    fact["value"] = numeric_values.astype(float)
    joined = fact.merge(
        metadata,
        on=CONTRACT_METADATA_KEY_COLUMNS,
        how="left",
        validate="many_to_one",
    )
    return joined[CONTRACT_JOINED_COLUMNS].copy()


def load_dataset_registry_native_units(registry_path: Path | str | None) -> dict[str, str]:
    """Read ``{dataset_id: native_unit}`` from leap_mappings' dataset registry.

    Returns an empty dict when no path is given or the file is absent, so a
    caller without a leap_mappings checkout (the portable module, tests) gets
    the documented ``DEFAULT_UNIT`` fallback for every row rather than an
    error. This is the single reason a "measure" dimension does not need its
    own registry: the dashboard is not the owner of what unit a dataset
    reports in, so it reads that fact rather than repeating it.
    """
    if not registry_path:
        return {}
    path = Path(registry_path)
    if not path.exists():
        return {}
    registry = pd.read_csv(path, usecols=["dataset_id", "native_unit"])
    return dict(zip(registry["dataset_id"].astype(str), registry["native_unit"].astype(str)))


def add_measure_and_unit_columns(
    df: pd.DataFrame,
    native_units: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Add ``measure`` and ``unit`` columns, defaulting to energy/PJ.

    ``measure`` is constant today: nothing in this pipeline registers a
    non-energy series yet (see the overnight work program's Deferred list —
    "registering emissions datasets" is explicitly out of scope). ``unit`` is
    looked up per ``source_system`` from ``native_units`` (the dataset
    registry's ``native_unit``, keyed by ``dataset_id`` — the same values as
    this frame's ``source_system``); a source system absent from the registry,
    or no registry at all, keeps ``DEFAULT_UNIT`` so every existing input
    renders exactly as before.
    """
    df = df.copy()
    native_units = native_units or {}
    df["measure"] = DEFAULT_MEASURE
    if "source_system" in df.columns:
        df["unit"] = (
            df["source_system"].astype(str).map(native_units).fillna(DEFAULT_UNIT)
        )
    else:
        df["unit"] = DEFAULT_UNIT
    return df


def load_common_esto_data(
    path: Path,
    wide_file_scope: str = DEFAULT_WIDE_FILE_SCOPE,
    output_contract_path: Path | None = None,
    dataset_registry_path: Path | str | None = None,
) -> pd.DataFrame:
    """Load an explicit output contract, or retain the legacy long/wide adapters.

    ``wide_file_scope`` is only consulted for wide-format inputs; long-format
    files already carry a resolved ``comparison_scope`` column. Supplying
    ``output_contract_path`` is an explicit opt-in and never falls back to
    ``path`` when the selected contract is invalid.

    Every path adds ``measure`` and ``unit`` columns (see
    ``add_measure_and_unit_columns``) before returning, so callers downstream
    of this loader never need to branch on which adapter ran.
    ``dataset_registry_path``, when given, sources ``unit`` from
    leap_mappings' dataset registry rather than the ``DEFAULT_UNIT`` fallback.
    """
    if output_contract_path is not None:
        loaded = load_common_esto_output_contract(output_contract_path)
    elif Path(path).suffix.casefold() == ".parquet":
        loaded = load_long_common_esto_data(path)
    else:
        sample_df = pd.read_csv(path, nrows=0, low_memory=False)
        if all(column in sample_df.columns for column in REQUIRED_COLUMNS):
            loaded = load_long_common_esto_data(path)
        elif all(column in sample_df.columns for column in ID_COLUMNS_WIDE) and get_year_columns(sample_df):
            loaded = load_wide_common_esto_data(path, wide_file_scope=wide_file_scope)
        else:
            raise ValueError(
                "Input file is neither long common ESTO data nor recognised wide data. "
                f"Columns found: {list(sample_df.columns)}"
            )
    native_units = load_dataset_registry_native_units(dataset_registry_path)
    return add_measure_and_unit_columns(loaded, native_units)


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


def _attach_non_expanding_contributor_metadata(
    metadata: pd.DataFrame,
    common_rows_path: Path,
) -> pd.DataFrame:
    """Attach contributor labels from the upstream non-expanding-rollup QA."""
    qa_path = common_rows_path.parent / "qa_common_esto_non_expanding_rollups.csv"
    required_columns = [
        "comparison_scope",
        "non_expanding_rollup_id",
        "contributor_inputs",
    ]
    if not qa_path.exists() or "non_expanding_rollup_id" not in metadata.columns:
        return metadata

    rollups = pd.read_csv(qa_path, low_memory=False).fillna("")
    if not set(required_columns).issubset(rollups.columns):
        return metadata
    rollups = (
        rollups[required_columns]
        .rename(columns={"contributor_inputs": "non_expanding_contributor_inputs"})
        .drop_duplicates(["comparison_scope", "non_expanding_rollup_id"])
    )
    return metadata.merge(
        rollups,
        on=["comparison_scope", "non_expanding_rollup_id"],
        how="left",
    )


def enrich_with_component_metadata(df: pd.DataFrame, common_rows_path: Path | None) -> pd.DataFrame:
    """Attach component membership metadata without duplicating chart values."""
    if common_rows_path is None or not common_rows_path.exists() or df.empty:
        return df.copy()
    metadata = load_common_esto_component_metadata(common_rows_path)
    metadata = _attach_non_expanding_contributor_metadata(metadata, common_rows_path)
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
    """Filter common ESTO data to the dashboard scope.

    Pass ``ALL_SCOPES`` to keep every scope; see the sentinel's note on why that
    frame must not be charted directly.
    """
    economy_key = str(economy).replace("_", "").strip()
    economy_values = df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    out = df[economy_values.eq(economy_key)].copy()
    if "comparison_scope" not in out.columns:
        raise ValueError(
            "Common ESTO data is missing the required 'comparison_scope' column."
        )
    available_scopes = sorted(set(out["comparison_scope"].astype(str)))
    if comparison_scope != ALL_SCOPES:
        if comparison_scope not in available_scopes:
            raise ValueError(
                f"Common ESTO data does not contain requested comparison scope "
                f"{comparison_scope!r} for economy {economy!r}. "
                f"Available scopes: {available_scopes}"
            )
        out = out[out["comparison_scope"].astype(str) == str(comparison_scope)].copy()
    if min_year is not None:
        out = out[out["year"] >= min_year].copy()
    if max_year is not None:
        out = out[out["year"] <= max_year].copy()
    return out.reset_index(drop=True)


def filter_template_for_leap_demand_coverage(
    template: dict,
    representation_status_df: pd.DataFrame | None = None,
) -> dict:
    """Attach current-run placeholder metadata without hiding ordinary pages.

    The upstream representation-status artifact records what the current LEAP
    export supplied.  It controls notices only: available Common ESTO facts
    still determine which chart categories render.  ``always_skip_page_keys``
    remains the sole explicit structural page suppression mechanism.
    """
    coverage_config = template.get("leap_demand_sector_coverage", {})
    if not coverage_config.get("enabled", False):
        return template
    page_branches = coverage_config.get("page_leap_branches", {})
    always_skip = {str(key) for key in coverage_config.get("always_skip_page_keys", [])}
    if not page_branches and not always_skip:
        return template
    out = dict(template)
    coverage_config = dict(coverage_config)
    placeholder_statuses = {
        "placeholder_only_retained",
        "partial_detail_placeholder_retained",
    }
    active_components: list[dict[str, object]] = []
    if representation_status_df is not None and not representation_status_df.empty:
        active_components = representation_status_df.loc[
            representation_status_df["representation_status"].astype(str).isin(placeholder_statuses),
            ["component_branch", "detailed_branches", "representation_status"],
        ].drop_duplicates().to_dict("records")
    aggregate_only_page_branches: dict[str, list[str]] = {}
    for page_key, branches in page_branches.items():
        page_branches_casefold = {str(branch).casefold() for branch in branches}
        components = []
        for component in active_components:
            detailed = {
                value.strip().casefold()
                for value in str(component["detailed_branches"]).split(";")
                if value.strip()
            }
            component_branch = str(component["component_branch"]).strip()
            if (
                component_branch.casefold() in page_branches_casefold
                or detailed.intersection(page_branches_casefold)
            ):
                components.append(component_branch)
        if components:
            aggregate_only_page_branches[str(page_key)] = sorted(set(components))
    coverage_config["_aggregate_only_page_branches"] = aggregate_only_page_branches
    if always_skip:
        coverage_config["_hidden_page_keys"] = sorted(always_skip)
    out["leap_demand_sector_coverage"] = coverage_config
    return out


def load_leap_demand_representation_status(
    path: str | Path,
    economy: str,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    """Load one economy's current-run LEAP placeholder/detail evidence."""
    status_path = Path(path)
    required = {
        "economy", "scenario", "year", "component_branch", "detailed_branches",
        "representation_status",
    }
    if not status_path.exists():
        return pd.DataFrame(columns=sorted(required))
    status_df = pd.read_csv(status_path)
    missing = required.difference(status_df.columns)
    if missing:
        raise ValueError(f"LEAP demand representation status is missing columns: {sorted(missing)}")
    economy_key = str(economy).replace("_", "").strip()
    status_df["economy"] = status_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    status_df = status_df[status_df["economy"].eq(economy_key)].copy()
    status_df["year"] = pd.to_numeric(status_df["year"], errors="raise").astype(int)
    if min_year is not None:
        status_df = status_df[status_df["year"] >= int(min_year)]
    if max_year is not None:
        status_df = status_df[status_df["year"] <= int(max_year)]
    return status_df.reset_index(drop=True)


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
