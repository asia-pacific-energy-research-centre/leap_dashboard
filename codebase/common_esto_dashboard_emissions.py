#%%
"""Emissions factors and the dashboard Emissions page.

Two responsibilities, kept apart on purpose:

1. ``build_factor_table`` turns a configured *factor set* into a factor per
   dashboard axis value (``common_product_label``, optionally paired with
   ``common_flow_label``). Factor sets declare the axis their factors are
   keyed on, so a future set keyed on ESTO products - or on ESTO
   product/flow combinations - drops in as config rather than code.
2. ``build_emissions_page`` renders the page, mirroring
   ``build_total_demand_page`` in the renderer: a bespoke, config-driven page
   that aggregates across sector pages instead of operating on one page's rows.

Mapping logic itself stays in ``leap_mappings``. This module only reads the
mapping contract it publishes (9th fuel -> ESTO product) and the generated
ESTO -> common axis map, then joins factors along that chain.
"""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]

# Axis kinds a factor set may be keyed on. Each maps to a resolver below.
NINTH_FUEL_AXIS = "ninth_fuel"
ESTO_PRODUCT_AXIS = "esto_product"
ESTO_PRODUCT_FLOW_AXIS = "esto_product_flow"
SUPPORTED_MAPPING_AXES = (NINTH_FUEL_AXIS, ESTO_PRODUCT_AXIS, ESTO_PRODUCT_FLOW_AXIS)

DEFAULT_EMISSIONS_UNIT = "Mt CO2e"
EMISSIONS_COLUMN = "emissions_value"

_LEAP_MAPPINGS_ROOT: Path | None = None


def _renderer():
    """Import the renderer lazily, so the two modules can reference each other.

    Both spellings are supported because the workflow puts ``codebase/`` on
    ``sys.path`` while tests import ``codebase`` as a package.
    """
    try:
        import common_esto_dashboard_renderer as renderer
    except ModuleNotFoundError:
        from codebase import common_esto_dashboard_renderer as renderer
    return renderer


#%%
# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def set_leap_mappings_root(path: str | Path | None) -> Path:
    """Point the loader at a specific ``leap_mappings`` checkout.

    The workflow resolves that repository once and calls this so the renderer
    does not have to thread the path through every page builder. Called with
    ``None`` it restores the default lookup.
    """
    global _LEAP_MAPPINGS_ROOT
    _LEAP_MAPPINGS_ROOT = Path(path).resolve() if path else None
    return leap_mappings_root()


def leap_mappings_root() -> Path:
    """Return the ``leap_mappings`` repository root used for mapping inputs."""
    if _LEAP_MAPPINGS_ROOT is not None:
        return _LEAP_MAPPINGS_ROOT
    default_root = REPO_ROOT.parent / "leap_mappings"
    return Path(os.getenv("LEAP_MAPPINGS_ROOT", str(default_root)))


def _resolve_repo_path(path: str | Path) -> Path:
    """Resolve a dashboard-repo-relative path, notebook-safe."""
    path_obj = Path(str(path).replace("\\", "/"))
    return path_obj if path_obj.is_absolute() else REPO_ROOT / path_obj


def _resolve_mappings_path(path: str | Path) -> Path:
    """Resolve a leap_mappings-relative path."""
    path_obj = Path(str(path).replace("\\", "/"))
    return path_obj if path_obj.is_absolute() else leap_mappings_root() / path_obj


#%%
# ---------------------------------------------------------------------------
# Factor set configuration
# ---------------------------------------------------------------------------
def load_factor_set_config(config_path: str | Path) -> dict:
    """Load the emissions factor-set config file."""
    return json.loads(_resolve_repo_path(config_path).read_text(encoding="utf-8"))


def select_factor_set(config: dict, factor_set_key: str | None = None) -> dict:
    """Return the requested factor set, defaulting to ``active_factor_set``."""
    factor_sets = config.get("factor_sets", [])
    if not factor_sets:
        raise ValueError("Emissions factor config declares no factor_sets.")
    wanted = str(factor_set_key or config.get("active_factor_set", "")).strip()
    if not wanted:
        return factor_sets[0]
    for factor_set in factor_sets:
        if str(factor_set.get("key", "")) == wanted:
            return factor_set
    available = ", ".join(str(item.get("key", "")) for item in factor_sets)
    raise ValueError(f"Unknown emissions factor set '{wanted}'. Available: {available}")


#%%
# ---------------------------------------------------------------------------
# Shared collapse helper
# ---------------------------------------------------------------------------
def _collapse_factors(
    df: pd.DataFrame,
    key_columns: list[str],
    strategy: str,
    stage: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse many factor rows onto one factor per key.

    Returns ``(collapsed, conflicts)``. A conflict is any key whose incoming
    rows disagree on the factor value; it is resolved by *strategy* and
    reported rather than silently averaged away.
    """
    working = df.copy()
    working["emissions_factor"] = pd.to_numeric(working["emissions_factor"], errors="coerce")
    configured_strategy = strategy

    distinct = (
        working.dropna(subset=["emissions_factor"])
        .groupby(key_columns)["emissions_factor"]
        .nunique()
    )
    conflict_keys = distinct[distinct > 1].index

    if strategy == "prefer_specific_then_mean" and "factor_is_residual" in working.columns:
        # Drop residual/unallocated contributors for keys that also have a
        # specific contributor, then fall through to the mean of what is left.
        has_specific = (
            working.assign(_specific=~working["factor_is_residual"].fillna(False))
            .groupby(key_columns)["_specific"]
            .transform("max")
        )
        working = working[~(working["factor_is_residual"].fillna(False) & has_specific)]
        strategy = "mean"

    aggregator = {"mean": "mean", "max": "max", "min": "min"}.get(strategy, "mean")
    collapsed = (
        working.groupby(key_columns, as_index=False)
        .agg(emissions_factor=("emissions_factor", aggregator))
    )

    if len(conflict_keys) == 0:
        conflicts = pd.DataFrame(columns=[*key_columns, "stage", "resolution", "contributors"])
    else:
        conflict_rows = df.set_index(key_columns).loc[conflict_keys].reset_index()
        source_column = next(
            (col for col in ("ninth_fuel", "esto_product", "component_esto_product") if col in conflict_rows.columns),
            key_columns[0],
        )
        conflicts = (
            conflict_rows.assign(
                contributor=conflict_rows[source_column].astype(str)
                + " = "
                + conflict_rows["emissions_factor"].astype(str)
            )
            .groupby(key_columns, as_index=False)
            .agg(contributors=("contributor", lambda values: "; ".join(sorted(set(values)))))
        )
        conflicts["stage"] = stage
        conflicts["resolution"] = configured_strategy
    return collapsed, conflicts


#%%
# ---------------------------------------------------------------------------
# Axis resolvers: factor file -> ESTO product (and optionally ESTO flow)
# ---------------------------------------------------------------------------
def collapse_ninth_fuel_rows(
    factor_df: pd.DataFrame,
    factor_set: dict,
    ninth_fuel_registry: list[str] | set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse a fuels/subfuels factor file onto 9th-edition fuel codes.

    Any subfuel other than the placeholder replaces its parent fuel. A parent
    row carrying the placeholder stands in for that fuel's ``_unallocated``
    code only when no explicit unallocated subfuel row already supplies it;
    otherwise it is a fuel-level aggregate over rows already present and is
    dropped so its members are not counted twice.

    *ninth_fuel_registry* is the set of 9th fuel codes the leap_mappings
    contract knows about; anything outside it is not a mappable fuel.

    Returns ``(resolved, dropped)``.
    """
    axis = factor_set.get("ninth_fuel_axis", {})
    fuel_col = str(axis.get("fuel_column", "fuels"))
    subfuel_col = str(axis.get("subfuel_column", "subfuels"))
    placeholder = str(axis.get("subfuel_placeholder", "x")).strip().casefold()
    suffix = str(axis.get("unallocated_suffix", "_unallocated"))

    working = factor_df.copy()
    subfuel = working[subfuel_col].astype(str).str.strip()
    is_placeholder = subfuel.str.casefold() == placeholder
    working["ninth_fuel_key"] = working[fuel_col].astype(str).str.strip().where(
        is_placeholder, subfuel
    )
    working["is_fuel_level_row"] = is_placeholder

    registry = {str(code).strip() for code in ninth_fuel_registry}
    direct_keys = set(working.loc[~working["is_fuel_level_row"], "ninth_fuel_key"]) & registry

    def resolve(row: pd.Series) -> str | None:
        key = str(row["ninth_fuel_key"])
        if key in registry:
            return key
        alias = f"{key}{suffix}"
        if row["is_fuel_level_row"] and alias in registry and alias not in direct_keys:
            return alias
        return None

    working["ninth_fuel"] = working.apply(resolve, axis=1)
    working["factor_is_residual"] = working["ninth_fuel"].astype(str).str.endswith(suffix)

    dropped = working[working["ninth_fuel"].isna()].copy()
    dropped["drop_reason"] = (
        "No 9th fuel in the leap_mappings ninth_fuel_to_esto contract; treated as "
        "a fuel-level aggregate or total whose members are already listed."
    )
    resolved = working[working["ninth_fuel"].notna()].copy()

    duplicated = resolved["ninth_fuel"].duplicated(keep=False)
    if duplicated.any():
        clashing = sorted(set(resolved.loc[duplicated, "ninth_fuel"]))
        raise ValueError(
            "Emissions factor file collapses to duplicate 9th fuel codes: " + ", ".join(clashing)
        )
    return resolved, dropped


_NINTH_FUEL_TO_ESTO_CACHE: dict[str, pd.DataFrame] = {}


def load_ninth_fuel_to_esto(
    workbook_path: str | Path | None = None,
    sheet_name: str = "ninth_fuel_to_esto",
) -> pd.DataFrame:
    """Read the leap_mappings 9th-fuel -> ESTO-product mapping contract."""
    path = _resolve_mappings_path(
        workbook_path or "config/outlook_mappings_single_axis.xlsx"
    )
    cache_key = f"{path}::{sheet_name}"
    cached = _NINTH_FUEL_TO_ESTO_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()
    frame = pd.read_excel(path, sheet_name=sheet_name)
    missing = {"ninth_fuel", "esto_product"} - set(frame.columns)
    if missing:
        raise ValueError(
            f"{path} sheet '{sheet_name}' is missing required columns: {sorted(missing)}"
        )
    frame = frame[["ninth_fuel", "esto_product"]].dropna().drop_duplicates()
    frame["ninth_fuel"] = frame["ninth_fuel"].astype(str).str.strip()
    frame["esto_product"] = frame["esto_product"].astype(str).str.strip()
    _NINTH_FUEL_TO_ESTO_CACHE[cache_key] = frame
    return frame.copy()


def load_esto_to_common_map(
    map_path: str | Path | None = None,
    comparison_scope: str = "esto_leap_ninth",
) -> pd.DataFrame:
    """Read the generated ESTO component -> common dashboard axis map.

    Reads ``common_esto_rows.csv`` rather than ``esto_to_common_esto_map.csv``:
    the two give set-identical component-ESTO -> common product/flow pairs
    (verified 2026-08-06), and ``common_esto_rows.csv`` is already a declared
    runtime asset (``mapping_chain_common_esto_rows``), so this removes one
    manifest entry the Emissions page would otherwise need added.
    """
    path = _resolve_mappings_path(map_path or "results/common_esto/common_esto_rows.csv")
    frame = pd.read_csv(
        path,
        usecols=[
            "comparison_scope",
            "component_esto_flow",
            "component_esto_product",
            "common_flow_label",
            "common_product_label",
        ],
    )
    scoped = frame[frame["comparison_scope"].astype(str) == str(comparison_scope)]
    if scoped.empty:
        scoped = frame
    return scoped.drop_duplicates().reset_index(drop=True)


#%%
# ---------------------------------------------------------------------------
# Factor table
# ---------------------------------------------------------------------------
def build_factor_table(
    factor_set: dict,
    mapping_sources: dict | None = None,
    comparison_scope: str = "esto_leap_ninth",
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Resolve a factor set onto the dashboard's common axes.

    Returns ``(factors, diagnostics)`` where ``factors`` has one row per
    ``common_product_label`` (plus ``common_flow_label`` when the factor set is
    keyed on ESTO product/flow combinations) and ``diagnostics`` holds the
    dropped-row, conflict, and resolution tables written beside the page.
    """
    mapping_sources = mapping_sources or {}
    axis = str(factor_set.get("mapping_axis", NINTH_FUEL_AXIS))
    if axis not in SUPPORTED_MAPPING_AXES:
        raise ValueError(
            f"Unsupported emissions mapping_axis '{axis}'. Supported: {', '.join(SUPPORTED_MAPPING_AXES)}"
        )

    raw = pd.read_csv(_resolve_repo_path(factor_set["path"]))
    factor_column = str(factor_set.get("factor_column", "CO2e emissions factor"))
    raw = raw.rename(columns={factor_column: "emissions_factor"})

    gas_column = str(factor_set.get("gas_column", "")).strip()
    gases = [str(gas).strip().casefold() for gas in factor_set.get("gases", []) if str(gas).strip()]
    if gas_column and gas_column in raw.columns:
        present = sorted(set(raw[gas_column].astype(str).str.strip()))
        if gases:
            raw = raw[raw[gas_column].astype(str).str.strip().str.casefold().isin(gases)]
        if raw.empty:
            raise ValueError(
                f"Emissions factor set '{factor_set.get('key')}' has no rows for the configured "
                f"gases {factor_set.get('gases')}; file contains: {present}."
            )
        # One factor column carries one gas. Multiple retained gases would need
        # per-gas factor columns before they could be summed, so refuse rather
        # than silently mixing them into a single factor.
        retained = sorted(set(raw[gas_column].astype(str).str.strip()))
        if len(retained) > 1:
            raise ValueError(
                f"Emissions factor set '{factor_set.get('key')}' retains multiple gases {retained} "
                "in a single factor column. Restrict 'gases' to one, or add a per-gas factor set."
            )

    # A blank factor is 'no emissions associated with this fuel', not missing data.
    if str(factor_set.get("blank_factor_means", "zero")).casefold() == "zero":
        raw["emissions_factor"] = pd.to_numeric(raw["emissions_factor"], errors="coerce").fillna(0.0)
    else:
        raw["emissions_factor"] = pd.to_numeric(raw["emissions_factor"], errors="coerce")

    diagnostics: dict[str, pd.DataFrame] = {}
    conflict_frames: list[pd.DataFrame] = []

    if axis == NINTH_FUEL_AXIS:
        crosswalk = load_ninth_fuel_to_esto(
            mapping_sources.get("ninth_fuel_to_esto_workbook"),
            str(mapping_sources.get("ninth_fuel_to_esto_sheet", "ninth_fuel_to_esto")),
        )
        resolved, dropped = collapse_ninth_fuel_rows(
            raw, factor_set, crosswalk["ninth_fuel"].tolist()
        )
        diagnostics["dropped_factor_rows"] = dropped[
            ["ninth_fuel_key", "emissions_factor", "drop_reason"]
        ].rename(columns={"ninth_fuel_key": "factor_key"})
        product_level = crosswalk.merge(
            resolved[["ninth_fuel", "emissions_factor", "factor_is_residual"]],
            on="ninth_fuel",
            how="left",
        )
        product_level, ninth_conflicts = _collapse_factors(
            product_level,
            ["esto_product"],
            str(factor_set.get("ninth_conflict_resolution", "prefer_specific_then_mean")),
            stage="ninth_fuel_to_esto_product",
        )
        conflict_frames.append(ninth_conflicts)
        contributors = (
            crosswalk.groupby("esto_product")["ninth_fuel"]
            .apply(lambda values: "; ".join(sorted(set(values))))
            .rename("factor_source_keys")
        )
        product_level = product_level.merge(contributors, on="esto_product", how="left")
    else:
        product_column = str(factor_set.get("esto_product_column", "esto_product"))
        renames = {product_column: "esto_product"}
        if axis == ESTO_PRODUCT_FLOW_AXIS:
            renames[str(factor_set.get("esto_flow_column", "esto_flow"))] = "esto_flow"
        product_level = raw.rename(columns=renames)
        keep = ["esto_product", "emissions_factor"] + (
            ["esto_flow"] if axis == ESTO_PRODUCT_FLOW_AXIS else []
        )
        missing = [column for column in keep if column not in product_level.columns]
        if missing:
            raise ValueError(
                f"Emissions factor set '{factor_set.get('key')}' is missing columns {missing} "
                f"required by mapping_axis '{axis}'."
            )
        product_level = product_level[keep].copy()
        product_level["factor_source_keys"] = product_level["esto_product"].astype(str)
        diagnostics["dropped_factor_rows"] = pd.DataFrame(
            columns=["factor_key", "emissions_factor", "drop_reason"]
        )

    overrides = {
        str(key): float(value)
        for key, value in (factor_set.get("esto_product_factor_overrides") or {}).items()
        if not str(key).startswith("_")
    }
    if overrides:
        override_mask = product_level["esto_product"].astype(str).isin(overrides)
        product_level.loc[override_mask, "emissions_factor"] = (
            product_level.loc[override_mask, "esto_product"].astype(str).map(overrides)
        )

    common_map = load_esto_to_common_map(
        mapping_sources.get("esto_to_common_map"), comparison_scope
    )
    join_keys = ["component_esto_product"]
    axis_keys = ["common_product_label"]
    left_keys = ["esto_product"]
    if axis == ESTO_PRODUCT_FLOW_AXIS:
        join_keys.append("component_esto_flow")
        left_keys.append("esto_flow")
        axis_keys.insert(0, "common_flow_label")

    joined = common_map.merge(
        product_level, left_on=join_keys, right_on=left_keys, how="left"
    )
    unmapped = joined[joined["emissions_factor"].isna()][
        ["component_esto_flow", "component_esto_product", *axis_keys]
    ].drop_duplicates()
    diagnostics["axis_values_without_factor"] = unmapped

    factors, component_conflicts = _collapse_factors(
        joined.dropna(subset=["emissions_factor"]),
        axis_keys,
        str(factor_set.get("component_conflict_resolution", "mean")),
        stage="esto_component_to_common_axis",
    )
    conflict_frames.append(component_conflicts)

    provenance = (
        joined.dropna(subset=["emissions_factor"])
        .groupby(axis_keys, as_index=False)
        .agg(
            esto_components=("component_esto_product", lambda values: "; ".join(sorted(set(values)))),
            factor_source_keys=(
                "factor_source_keys",
                lambda values: "; ".join(
                    sorted({part.strip() for value in values for part in str(value).split(";") if part.strip()})
                ),
            ),
        )
    )
    factors = factors.merge(provenance, on=axis_keys, how="left")
    factors["factor_set_key"] = str(factor_set.get("key", ""))
    factors["emissions_unit"] = str(factor_set.get("emissions_unit", DEFAULT_EMISSIONS_UNIT))
    factors["mapping_axis"] = axis

    diagnostics["factor_conflicts"] = (
        pd.concat([frame for frame in conflict_frames if not frame.empty], ignore_index=True)
        if any(not frame.empty for frame in conflict_frames)
        else pd.DataFrame(columns=["stage", "resolution", "contributors"])
    )
    diagnostics["factor_resolution"] = factors.copy()
    return factors, diagnostics


#%%
# ---------------------------------------------------------------------------
# Applying factors to dashboard rows
# ---------------------------------------------------------------------------
def attach_emissions(
    df: pd.DataFrame,
    factors: pd.DataFrame,
    value_column: str = "value",
    output_column: str = EMISSIONS_COLUMN,
) -> pd.DataFrame:
    """Return *df* with an emissions column derived from *factors*.

    Rows whose axis value has no factor keep ``NaN`` so they can be reported
    instead of quietly contributing zero to a total.
    """
    axis_keys = [
        key for key in ("common_flow_label", "common_product_label") if key in factors.columns
    ]
    merged = df.merge(
        factors[[*axis_keys, "emissions_factor", "emissions_unit"]], on=axis_keys, how="left"
    )
    merged[output_column] = (
        pd.to_numeric(merged[value_column], errors="coerce") * merged["emissions_factor"]
    )
    return merged


#%%
# ---------------------------------------------------------------------------
# Non-overlapping demand frontier
# ---------------------------------------------------------------------------
def _containment_map(labels: list[str]) -> dict[str, list[str]]:
    """Map each axis label to the labels that strictly contain it.

    Containment is decided on the code expression embedded in the label, so
    ``16.03-16.05,17 Other sector including non-energy`` contains both
    ``16.05 Non-specified others`` and ``17 Non-energy use``. Two labels with
    equal coverage but different text (an exact row and its boundary-adjusted
    twin) would otherwise contain each other; sort order breaks the tie so one
    of the pair survives.
    """
    _code_expression_contains_expression = _renderer()._code_expression_contains_expression

    covers: dict[str, list[str]] = {label: [] for label in labels}
    for inner in labels:
        for outer in labels:
            if inner == outer or not _code_expression_contains_expression(outer, inner):
                continue
            if _code_expression_contains_expression(inner, outer) and inner < outer:
                continue
            covers[inner].append(outer)
    return covers


def select_non_overlapping_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the most detailed non-overlapping frontier per source/scenario.

    Sector pages carry a whole flow hierarchy at once - ``14 Industry sector``
    sits beside ``14.03 Manufacturing`` and ``14.03.01 Iron and steel`` - plus
    generated rollups whose codes span several branches
    (``16.03-16.05,17 Other sector including non-energy``). Charting those
    individually is fine, but summing them into one emissions total counts the
    same fuel several times.

    A row is dropped when it covers another row of the same source system and
    scenario on both axes, which keeps the detail rather than the aggregate.
    Detail is preferred over aggregate because the aggregates overlap each
    other - ``16 Other sector`` and ``16.03-16.05,17`` share ``16.03-16.05`` -
    so no set of aggregates is guaranteed to partition demand, whereas the
    frontier below them does. ``frontier_coverage_check`` verifies that each
    dropped aggregate still equals the detail retained inside it.
    """
    if df.empty:
        return df

    flow_covers = _containment_map(sorted(set(df["common_flow_label"].astype(str))))
    product_covers = _containment_map(sorted(set(df["common_product_label"].astype(str))))

    keep = pd.Series(True, index=df.index)
    for _, group in df.groupby(["source_system", "scenario"], sort=False):
        present = set(zip(group["common_flow_label"].astype(str), group["common_product_label"].astype(str)))
        aggregates = {
            outer
            for inner in present
            for outer in _covering_pairs(inner, present, flow_covers, product_covers)
        }
        if not aggregates:
            continue
        group_pairs = zip(group["common_flow_label"].astype(str), group["common_product_label"].astype(str))
        keep.loc[group.index] = [pair not in aggregates for pair in group_pairs]
    return df[keep]


def _covering_pairs(
    pair: tuple[str, str],
    present: set[tuple[str, str]],
    flow_covers: dict[str, list[str]],
    product_covers: dict[str, list[str]],
) -> set[tuple[str, str]]:
    """Return the present pairs that strictly contain *pair* on both axes."""
    flow, product = pair
    return {
        (outer_flow, outer_product)
        for outer_flow in [flow, *flow_covers.get(flow, [])]
        for outer_product in [product, *product_covers.get(product, [])]
        if (outer_flow, outer_product) != pair and (outer_flow, outer_product) in present
    }


def frontier_coverage_check(
    all_rows: pd.DataFrame,
    frontier_rows: pd.DataFrame,
    value_column: str = "value",
) -> pd.DataFrame:
    """Compare each dropped aggregate against the detail retained inside it.

    A non-zero difference means the retained frontier does not add back up to
    the aggregate the source also reported - the detail is incomplete, and the
    emissions total for that source is understated by that amount.
    """
    if all_rows.empty:
        return pd.DataFrame(
            columns=["source_system", "scenario", "year", "common_flow_label",
                     "common_product_label", "aggregate_value", "frontier_value", "difference"]
        )
    dropped = all_rows.loc[all_rows.index.difference(frontier_rows.index)]
    if dropped.empty:
        return pd.DataFrame(
            columns=["source_system", "scenario", "year", "common_flow_label",
                     "common_product_label", "aggregate_value", "frontier_value", "difference"]
        )

    flow_covers = _containment_map(sorted(set(all_rows["common_flow_label"].astype(str))))
    product_covers = _containment_map(sorted(set(all_rows["common_product_label"].astype(str))))
    group_keys = ["source_system", "scenario", "year", "common_flow_label", "common_product_label"]
    dropped_totals = dropped.groupby(group_keys, as_index=False)[value_column].sum()
    frontier_totals = frontier_rows.groupby(group_keys, as_index=False)[value_column].sum()

    records: list[dict[str, object]] = []
    for (source_system, scenario), scope in frontier_totals.groupby(["source_system", "scenario"]):
        present = set(zip(scope["common_flow_label"].astype(str), scope["common_product_label"].astype(str)))
        matching_dropped = dropped_totals[
            (dropped_totals["source_system"] == source_system)
            & (dropped_totals["scenario"] == scenario)
        ]
        for aggregate_pair in set(
            zip(matching_dropped["common_flow_label"].astype(str),
                matching_dropped["common_product_label"].astype(str))
        ):
            inner = [
                pair for pair in present
                if aggregate_pair in _covering_pairs(pair, present | {aggregate_pair}, flow_covers, product_covers)
            ]
            inner_rows = scope[
                scope[["common_flow_label", "common_product_label"]]
                .apply(tuple, axis=1)
                .isin(inner)
            ]
            aggregate_rows = matching_dropped[
                (matching_dropped["common_flow_label"] == aggregate_pair[0])
                & (matching_dropped["common_product_label"] == aggregate_pair[1])
            ]
            for _, aggregate_row in aggregate_rows.iterrows():
                frontier_value = float(
                    inner_rows.loc[inner_rows["year"] == aggregate_row["year"], value_column].sum()
                )
                records.append({
                    "source_system": source_system,
                    "scenario": scenario,
                    "year": int(aggregate_row["year"]),
                    "common_flow_label": aggregate_pair[0],
                    "common_product_label": aggregate_pair[1],
                    "aggregate_value": float(aggregate_row[value_column]),
                    "frontier_value": frontier_value,
                    "difference": float(aggregate_row[value_column]) - frontier_value,
                })
    return pd.DataFrame(records)


#%%
# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _stacked_emissions_chart(
    emissions_df: pd.DataFrame,
    group_column: str,
    title: str,
    unit: str,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    base_year: int | None,
    code_axis: str | None = None,
    group_colors: dict[str, str] | None = None,
) -> go.Figure:
    """Stack emissions by *group_column* for one source, over comparison totals."""
    renderer = _renderer()
    apply_chart_chrome = renderer.apply_chart_chrome
    scenario_toggle_tag = renderer.scenario_toggle_tag
    series_label_from_values = renderer.series_label_from_values
    stacked_area_dataset_note = renderer.stacked_area_dataset_note
    trace_meta_entry = renderer.trace_meta_entry
    comparison_projection_rows = renderer._comparison_projection_area_rows
    has_nonzero_values = renderer._has_nonzero_values

    fig = go.Figure()
    trace_meta: list[dict] = []
    stacked_sources: set[str] = set()

    def stack_rows(scenario_name: str) -> pd.DataFrame:
        """Return ESTO historical plus the most detailed projected source."""
        if base_year is None:
            return emissions_df.iloc[0:0]
        rows, _ = comparison_projection_rows(
            emissions_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=int(base_year),
            group_col=group_column,
            detail_col=group_column,
            detail_minimum=1,
            value_col=EMISSIONS_COLUMN,
        )
        return rows

    # Stacking order comes from the default scenario and is reused for both, so
    # switching REF/TGT does not reshuffle the layers.
    order = (
        stack_rows(primary_scenario)
        .groupby(group_column)[EMISSIONS_COLUMN]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .index.tolist()
    )
    for scenario_name in ("Reference", "Target"):
        scenario_df = stack_rows(scenario_name)
        if scenario_df.empty or not order:
            continue
        is_default = scenario_name.casefold() == primary_scenario.casefold()
        projected_source = scenario_df[
            scenario_df["source_system"].astype(str).str.casefold().ne("esto")
        ]
        if projected_source.empty:
            continue
        stack_source_name = str(projected_source["source_system"].iloc[0])
        by_year = scenario_df.groupby([group_column, "year"], as_index=False)[EMISSIONS_COLUMN].sum()
        for group_value in order:
            group_rows = by_year[by_year[group_column] == group_value].sort_values("year")
            if group_rows.empty:
                continue
            if not has_nonzero_values(group_rows[EMISSIONS_COLUMN]):
                continue
            label = str(group_value)
            sign = "neg" if group_rows[EMISSIONS_COLUMN].sum() < 0 else "pos"
            trace_kwargs: dict[str, object] = {}
            if group_colors and label in group_colors:
                trace_kwargs["line"] = {"color": group_colors[label]}
                trace_kwargs["fillcolor"] = group_colors[label]
            fig.add_trace(go.Scatter(
                x=group_rows["year"],
                y=group_rows[EMISSIONS_COLUMN],
                mode="lines",
                stackgroup=f"emissions_{scenario_toggle_tag(stack_source_name, scenario_name)}_{sign}",
                name=label,
                visible=True if is_default else False,
                hovertemplate="%{x}<br>%{y:,.2f} " + escape(unit) + "<extra>" + escape(label) + "</extra>",
                **trace_kwargs,
            ))
            if (scenario_df["source_system"].astype(str).str.casefold() == "esto").any():
                stacked_sources.add("ESTO")
            stacked_sources.add(stack_source_name)
            trace_meta.append(trace_meta_entry(stack_source_name, scenario_name, True))

    totals = emissions_df.groupby(["source_system", "scenario", "year"], as_index=False)[EMISSIONS_COLUMN].sum()
    for (source_system, scenario), group in totals.groupby(["source_system", "scenario"]):
        if not has_nonzero_values(group[EMISSIONS_COLUMN]):
            continue
        label = series_label_from_values(source_system, scenario, series_labels) + " total"
        ordered = group.sort_values("year")
        fig.add_trace(go.Scatter(
            x=ordered["year"],
            y=ordered[EMISSIONS_COLUMN],
            mode="lines+markers",
            name=label,
            line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f} " + escape(unit) + "<extra>" + escape(label) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(source_system, scenario, True))

    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title=f"Emissions ({unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": stacked_area_dataset_note(
                stacked_sources, "fuel" if group_column == "common_product_label" else "sector"
            ),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis=code_axis)
    return fig


def _emissions_comparison_chart(
    emissions_df: pd.DataFrame,
    title: str,
    unit: str,
    series_labels: dict[str, str],
    base_year: int | None,
) -> go.Figure:
    """Compare one emissions total across LEAP, ESTO, and 9th edition."""
    renderer = _renderer()
    apply_chart_chrome = renderer.apply_chart_chrome
    series_label_from_values = renderer.series_label_from_values
    trace_meta_entry = renderer.trace_meta_entry

    fig = go.Figure()
    trace_meta: list[dict] = []
    totals = emissions_df.groupby(["source_system", "scenario", "year"], as_index=False)[EMISSIONS_COLUMN].sum()
    for (source_system, scenario), group in totals.groupby(["source_system", "scenario"]):
        label = series_label_from_values(source_system, scenario, series_labels)
        ordered = group.sort_values("year")
        fig.add_trace(go.Scatter(
            x=ordered["year"],
            y=ordered[EMISSIONS_COLUMN],
            mode="lines+markers",
            name=label,
            hovertemplate="%{x}<br>%{y:,.2f} " + escape(unit) + "<extra>" + escape(label) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title=f"Emissions ({unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={"trace_meta": trace_meta},
    )
    apply_chart_chrome(fig, base_year)
    return fig


#%%
# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def emissions_page_config(template: dict) -> dict:
    """Return the template's ``emissions_page`` block."""
    return template.get("emissions_page", {}) or {}


def _demand_rows(assigned_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Return the assigned rows the Emissions page derives from."""
    demand_page_keys = [str(key) for key in config.get("demand_page_keys", [])]
    if "_page_key" not in assigned_df.columns:
        return assigned_df.iloc[0:0]
    return assigned_df[assigned_df["_page_key"].isin(demand_page_keys)]


def select_emissions_demand_rows(
    detail_frontier: pd.DataFrame,
    overview_flow_rows: pd.DataFrame,
    aggregate_flow_code: str = "12",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select one emissions level per source/scenario without allocating totals.

    Sources with sector detail use their non-overlapping detail frontier. A
    source with no sector detail falls back to its declared top-level TFC row,
    preserving the aggregate as one series rather than inventing a sector split.
    The second return value records which level was selected.
    """
    detail = detail_frontier.copy()
    if not detail.empty:
        detail["emissions_level"] = "detail"
    overview = overview_flow_rows.copy()
    if not overview.empty:
        overview = overview[
            overview["common_flow_code"].astype(str).eq(str(aggregate_flow_code))
        ].copy()
        overview["emissions_level"] = "aggregate"

    source_keys = set()
    for frame in (detail, overview):
        if not frame.empty:
            source_keys.update(
                zip(frame["source_system"].astype(str), frame["scenario"].astype(str))
            )

    selected: list[pd.DataFrame] = []
    records: list[dict[str, object]] = []
    for source, scenario in sorted(source_keys):
        detail_rows = detail[
            detail["source_system"].astype(str).eq(source)
            & detail["scenario"].astype(str).eq(scenario)
        ]
        aggregate_rows = overview[
            overview["source_system"].astype(str).eq(source)
            & overview["scenario"].astype(str).eq(scenario)
        ]
        chosen = detail_rows if not detail_rows.empty else aggregate_rows
        if chosen.empty:
            continue
        selected.append(chosen)
        records.append({
            "source_system": source,
            "scenario": scenario,
            "emissions_level": str(chosen["emissions_level"].iloc[0]),
            "row_count": int(len(chosen)),
        })

    columns = ["source_system", "scenario", "emissions_level", "row_count"]
    if not selected:
        return detail.iloc[0:0].copy(), pd.DataFrame(columns=columns)
    return pd.concat(selected, ignore_index=True), pd.DataFrame(records, columns=columns)


def emissions_page_enabled(
    template: dict,
    assigned_df: pd.DataFrame | None = None,
    factor_config_path: str | Path | None = None,
) -> bool:
    """Whether the Emissions page should appear in navigation and be rendered.

    Requires the config switch, the inputs the page derives from (its factor
    file, the leap_mappings 9th-fuel contract, and the generated ESTO -> common
    axis map), and - when *assigned_df* is supplied - demand rows to derive
    emissions from. A checkout without the sibling repository simply has no
    Emissions page rather than a navigation chip pointing at nothing.

    ``render_dashboard`` decides the navigation inventory before any page is
    written, so this is the single condition both that gate and
    ``build_emissions_page`` consult. They must not be able to disagree: a chip
    without a page is a broken link on every other page of the dashboard.

    ``factor_config_path``, when given, is used in place of the template's
    ``factor_sets_config_path`` and, being resolved as-is when absolute,
    bypasses ``REPO_ROOT = __file__.parents[1]`` entirely. That default only
    matches the Gradio runtime layout (``runtime/leap_dashboard/{codebase,config}/``);
    a caller in a different layout (e.g. the portable staging, which flattens
    with ``strip_prefix = "codebase"``) should pass its own resolved path
    instead of relying on it.
    """
    config = emissions_page_config(template)
    if not config.get("enabled", False):
        return False
    if assigned_df is not None and not _demand_rows(assigned_df, config).shape[0]:
        return False
    try:
        factor_config = load_factor_set_config(
            factor_config_path
            or config.get(
                "factor_sets_config_path",
                "config/common_esto_dashboard/emissions_factor_sets.json",
            )
        )
        factor_set = select_factor_set(factor_config, config.get("factor_set_key"))
    except (FileNotFoundError, ValueError):
        return False
    mapping_sources = factor_config.get("mapping_sources", {})
    required = [_resolve_repo_path(factor_set["path"])]
    if str(factor_set.get("mapping_axis", NINTH_FUEL_AXIS)) == NINTH_FUEL_AXIS:
        required.append(
            _resolve_mappings_path(
                mapping_sources.get(
                    "ninth_fuel_to_esto_workbook", "config/outlook_mappings_single_axis.xlsx"
                )
            )
        )
    required.append(
        _resolve_mappings_path(
            mapping_sources.get(
                "esto_to_common_map", "results/common_esto/common_esto_rows.csv"
            )
        )
    )
    return all(path.exists() for path in required)


def build_emissions_page(
    assigned_df: pd.DataFrame,
    template: dict,
    series_labels: dict[str, str],
    layout: dict[str, Path],
    all_pages: list[dict],
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    economy_label: str = "",
    dashboard_switcher: list[dict[str, str]] | None = None,
    current_dashboard: str = "",
    dashboard_updated_label: str = "",
    factor_config_path: str | Path | None = None,
) -> tuple[list[dict], dict | None]:
    """Build the Emissions page (config-driven bespoke page).

    Applies the active emissions factor set to the same final-energy demand
    rows the sector pages plot, then compares the resulting emissions across
    LEAP, ESTO, and the 9th edition:

    - stacked emissions by fuel and by sector, with comparison total lines;
    - a total-emissions comparison line;
    - one comparison line chart per sector and per fuel.

    Scope, factor set, sector membership, and suppression are config-driven via
    the ``emissions_page`` template key and
    ``config/common_esto_dashboard/emissions_factor_sets.json``.

    ``factor_config_path``, when given, overrides that default location and is
    passed straight through to ``emissions_page_enabled`` and
    ``load_factor_set_config`` — see ``emissions_page_enabled`` for why a
    caller outside the Gradio runtime layout needs this.

    Returns ``(manifest_rows, page_row_dict)``, or ``([], None)`` when disabled
    or when no demand rows carry a factor.
    """
    renderer = _renderer()
    chart_dataset_tokens = renderer.chart_dataset_tokens
    safe_slug = renderer.safe_slug
    stacked_area_note_from_figure = renderer.stacked_area_note_from_figure
    write_chart_bundle = renderer.write_chart_bundle
    write_dashboard_page = renderer.write_dashboard_page

    config = emissions_page_config(template)
    if not emissions_page_enabled(template, assigned_df, factor_config_path):
        return [], None

    page_key = str(config.get("page_key", "emissions"))
    page_label = str(config.get("page_label", "Emissions"))
    base_year = int(template.get("chart_generation", {}).get("base_year", 2023))
    demand_page_keys = [str(key) for key in config.get("demand_page_keys", [])]
    suppression_threshold = float(config.get("suppression_threshold", 0.1))

    demand_detail_df = _demand_rows(assigned_df, config).copy()
    # Sector pages plot every level of the flow hierarchy; an emissions total
    # may only add up one non-overlapping frontier of it. Applied across all
    # demand pages at once because generated rollups such as
    # "16.03-16.05,17 Other sector including non-energy" span several pages.
    all_demand_df = demand_detail_df
    detail_frontier = select_non_overlapping_rows(all_demand_df)
    coverage_check = frontier_coverage_check(all_demand_df, detail_frontier)
    aggregate_flow_code = str(config.get("aggregate_flow_code", "12"))
    overview_flow_rows = assigned_df[
        assigned_df["_page_key"].eq("total_demand")
        & assigned_df["common_flow_code"].astype(str).eq(aggregate_flow_code)
    ].copy()
    demand_df, source_selection = select_emissions_demand_rows(
        detail_frontier, overview_flow_rows, aggregate_flow_code
    )

    comparison_scope = str(
        demand_df["comparison_scope"].astype(str).mode().iloc[0]
        if "comparison_scope" in demand_df.columns and not demand_df.empty
        else "esto_leap_ninth"
    )
    factor_config = load_factor_set_config(
        factor_config_path
        or config.get(
            "factor_sets_config_path",
            "config/common_esto_dashboard/emissions_factor_sets.json",
        )
    )
    factor_set = select_factor_set(factor_config, config.get("factor_set_key"))
    try:
        factors, diagnostics = build_factor_table(
            factor_set,
            factor_config.get("mapping_sources", {}),
            comparison_scope=comparison_scope,
        )
    except FileNotFoundError as error:
        # emissions_page_enabled already checked these paths, so this is a race
        # rather than an ordinary absence. The navigation chip is written by
        # then, so explain it on the page instead of leaving a broken link.
        return _write_explained_empty_page(
            page_key, page_label, layout, all_pages, economy_label, dashboard_switcher,
            current_dashboard, dashboard_updated_label,
            f"No emissions charts: an emissions factor input could not be read ({error}).",
        )
    unit = str(factor_set.get("emissions_unit", DEFAULT_EMISSIONS_UNIT))

    emissions_df = attach_emissions(demand_df, factors)
    missing = emissions_df[emissions_df[EMISSIONS_COLUMN].isna()]
    missing_labels = sorted(set(missing["common_product_label"].astype(str)))
    emissions_df = emissions_df[emissions_df[EMISSIONS_COLUMN].notna()].copy()
    if emissions_df.empty:
        return _write_explained_empty_page(
            page_key, page_label, layout, all_pages, economy_label, dashboard_switcher,
            current_dashboard, dashboard_updated_label,
            "No emissions charts: none of the demand fuels for this economy carry an "
            f"emissions factor. Unmatched fuels: {', '.join(missing_labels) or 'none'}.",
        )
    emissions_df["_sector_label"] = emissions_df["_page_label"].astype(str)
    aggregate_mask = emissions_df["emissions_level"].eq("aggregate")
    emissions_df.loc[aggregate_mask, "_sector_label"] = "LEAP aggregate demand"

    diagnostics["frontier_coverage_check"] = coverage_check
    diagnostics["source_selection"] = source_selection
    for name, frame in diagnostics.items():
        frame.to_csv(layout["supporting"] / f"emissions_{name}.csv", index=False)
    emissions_df.groupby(
        ["source_system", "scenario", "year", "_sector_label", "common_product_label"], as_index=False
    )[EMISSIONS_COLUMN].sum().to_csv(
        layout["supporting"] / "emissions_by_sector_and_fuel.csv", index=False
    )

    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    def record(
        chart_key: str,
        figure: go.Figure,
        chart_type: str,
        title: str,
        section_label: str,
        rows: pd.DataFrame,
        flow_group_label: str | None = None,
    ) -> None:
        chart_total_abs = float(rows[EMISSIONS_COLUMN].abs().sum())
        charts[chart_key] = figure
        row: dict[str, object] = {
            "chart_key": chart_key,
            "chart_type": chart_type,
            "title": title,
            "product_label": title,
            "section_label": section_label,
            "total_abs_value": chart_total_abs,
            "abs_diff": 0.0,
            "pct_diff": 0.0,
            # chart_dataset_tokens reads a "value" column; feed it emissions so
            # a fuel that carries energy but no factor is not offered as a filter.
            "datasets": chart_dataset_tokens(
                rows[["source_system", EMISSIONS_COLUMN]].rename(columns={EMISSIONS_COLUMN: "value"})
            ),
        }
        if chart_type == "stacked_area":
            row["stacked_area_note"] = stacked_area_note_from_figure(figure)
        if flow_group_label:
            row["flow_group_label"] = flow_group_label
        chart_rows.append(row)
        manifest_rows.append({
            "page_key": page_key,
            "page_label": page_label,
            "section_label": section_label,
            "chart_type": chart_type,
            "chart_key": chart_key,
            "common_flow_label": title,
            "common_product_label": "All products",
            "row_count": int(len(rows)),
            "source_flow_labels": "; ".join(demand_page_keys),
            "sign_note": f"Emissions in {unit}, derived from final energy demand and the "
                         f"{factor_set.get('label', factor_set.get('key', ''))} factor set.",
            "suppressed": False,
            "total_abs_value": chart_total_abs,
            "abs_diff": 0.0,
            "pct_diff": 0.0,
            "diff_hist_json": "",
            "diff_proj_json": "",
        })

    record(
        f"chart__area__{page_key}__fuel",
        _stacked_emissions_chart(
            emissions_df, "common_product_label", f"Emissions by fuel ({unit})", unit,
            series_labels, primary_source, primary_scenario, base_year, code_axis="product",
        ),
        "stacked_area",
        f"Emissions by fuel ({unit})",
        "Overview",
        emissions_df,
    )
    record(
        f"chart__area__{page_key}__sector",
        _stacked_emissions_chart(
            emissions_df, "_sector_label", f"Emissions by sector ({unit})", unit,
            series_labels, primary_source, primary_scenario, base_year,
            group_colors=_sector_color_map(template, assigned_df),
        ),
        "stacked_area",
        f"Emissions by sector ({unit})",
        "Overview",
        emissions_df,
    )
    record(
        f"chart__line__{page_key}__total",
        _emissions_comparison_chart(
            emissions_df, f"Total emissions from final energy demand ({unit})", unit,
            series_labels, base_year,
        ),
        "line",
        f"Total emissions from final energy demand ({unit})",
        "Total emissions",
        emissions_df,
    )

    for sector_label, sector_rows in emissions_df.groupby("_sector_label"):
        if float(sector_rows[EMISSIONS_COLUMN].abs().sum()) < suppression_threshold:
            continue
        record(
            f"chart__line__{page_key}__sector__{safe_slug(sector_label)}",
            _emissions_comparison_chart(
                sector_rows, f"{sector_label} emissions", unit, series_labels, base_year
            ),
            "line",
            str(sector_label),
            "By sector",
            sector_rows,
        )

    fuel_order = (
        emissions_df.groupby("common_product_label")[EMISSIONS_COLUMN]
        .apply(lambda values: values.abs().sum())
        .sort_values(ascending=False)
    )
    for fuel_label, fuel_total in fuel_order.items():
        if float(fuel_total) < suppression_threshold:
            continue
        fuel_rows = emissions_df[emissions_df["common_product_label"] == fuel_label]
        record(
            f"chart__line__{page_key}__fuel__{safe_slug(fuel_label)}",
            _emissions_comparison_chart(
                fuel_rows, f"{fuel_label} emissions", unit, series_labels, base_year
            ),
            "line",
            str(fuel_label),
            "By fuel",
            fuel_rows,
        )

    bundle_name = f"{page_key}__charts.json"
    write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
    write_dashboard_page(
        {"page_key": page_key, "page_label": page_label},
        chart_rows=chart_rows,
        bundle_js_name=bundle_name.replace(".json", ".js"),
        output_path=layout["dashboards"] / f"{page_key}.html",
        all_pages=all_pages,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        page_note=_page_note(
            factor_set,
            unit,
            sorted(emissions_df.loc[aggregate_mask, "source_system"].astype(str).unique()),
        ),
        dashboard_updated_label=dashboard_updated_label,
    )
    page_row = {
        "file": f"{page_key}.html",
        "label": page_label,
        "area_chart_count": sum(row["chart_type"] == "stacked_area" for row in chart_rows),
        "summary_chart_count": 0,
        "line_chart_count": sum(row["chart_type"] == "line" for row in chart_rows),
    }
    return manifest_rows, page_row


def _write_explained_empty_page(
    page_key: str,
    page_label: str,
    layout: dict[str, Path],
    all_pages: list[dict],
    economy_label: str,
    dashboard_switcher: list[dict[str, str]] | None,
    current_dashboard: str,
    dashboard_updated_label: str,
    reason: str,
) -> tuple[list[dict], dict]:
    """Write a chartless Emissions page that explains why it has no charts.

    Navigation chips for this page are already baked into every other page by
    the time chart building can fail, so the page has to exist. An empty page
    carrying the reason beats a 404 on every page of the dashboard.
    """
    renderer = _renderer()
    print(f"Emissions page rendered without charts: {reason}")
    bundle_name = f"{page_key}__charts.json"
    renderer.write_chart_bundle({}, layout["chart_bundles"] / bundle_name)
    renderer.write_dashboard_page(
        {"page_key": page_key, "page_label": page_label},
        chart_rows=[],
        bundle_js_name=bundle_name.replace(".json", ".js"),
        output_path=layout["dashboards"] / f"{page_key}.html",
        all_pages=all_pages,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        page_note=reason,
        dashboard_updated_label=dashboard_updated_label,
    )
    return [], {
        "file": f"{page_key}.html",
        "label": page_label,
        "area_chart_count": 0,
        "summary_chart_count": 0,
        "line_chart_count": 0,
    }


def _sector_color_map(template: dict, assigned_df: pd.DataFrame) -> dict[str, str]:
    """Map sector page labels to the colours the overview page already uses."""
    colors_by_key = {
        **(template.get("total_demand_page", {}).get("sector_colors", {})),
        **(emissions_page_config(template).get("sector_colors", {})),
    }
    label_by_key = (
        assigned_df[["_page_key", "_page_label"]]
        .drop_duplicates()
        .set_index("_page_key")["_page_label"]
        .astype(str)
        .to_dict()
    )
    return {
        label_by_key[key]: color
        for key, color in colors_by_key.items()
        if key in label_by_key
    }


def _page_note(
    factor_set: dict,
    unit: str,
    aggregate_sources: list[str],
) -> str:
    """Give the page a short explanation of what its emissions represent."""
    note = (
        f"Emissions ({unit}) are estimated from final energy demand using "
        f"{factor_set.get('label', factor_set.get('key', 'CO2e emissions factors'))}. "
        "The same demand categories used elsewhere in the dashboard are used here. "
        "Factors are mapped onto the common ESTO fuel categories, so this page shows "
        "combustion emissions from final demand; transformation and power-sector fuel use are excluded."
    )
    if aggregate_sources:
        note += (
            " Where LEAP detail is unavailable, aggregate demand is shown as one series for "
            + ", ".join(aggregate_sources)
            + "."
        )
    return note

#%%
