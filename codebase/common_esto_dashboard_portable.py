#%%
"""Dependency-light entry points for rendering portable Common ESTO dashboards.

``common_esto_dashboard_workflow.py`` is the maintainer-facing notebook workflow:
it resolves sibling-repository paths, refreshes upstream data, renders the shared
mapping-diagnostics page, and executes its own
run block at import time. That makes it unsuitable for reuse as a library and
impossible to package for a machine that has no ``leap_mappings`` checkout.

This module is the narrow, importable core of the same render: every input is an
explicit argument, nothing is read from the current working directory, nothing is
executed at import, and the only in-repo dependencies are the three production
dashboard modules. It is what the developer launcher and the portable release
both call, so both run identical rendering code.

The maintainer workflow separately renders the full APEC-wide hierarchy/rollup
diagnostics page from the complete ``leap_mappings`` results tree. When that
rendered page is supplied, this module copies it into an export dashboard so
reviewers see the same diagnostic, rather than a reduced substitute.

Deliberately **not** included here:

- the capacity-unmet convergence page (needs a ``leap_initialisation`` run CSV);
- the upstream Common ESTO fast-path data refresh;
- the Emissions page. ``render_dashboard`` still offers it, but its factor
  mapping needs the ``leap_mappings`` 9th-fuel contract and generated
  ESTO -> common axis map, so a portable package without that checkout renders
  neither the page nor its navigation chip. See
  ``common_esto_dashboard_emissions.emissions_page_enabled``.

Use ``common_esto_dashboard_workflow.py`` when those pages are wanted.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

# Match the workflow's convention so this module imports identically whether the
# repository root is on sys.path (``codebase.common_esto_dashboard_portable``) or
# only this directory is (``common_esto_dashboard_portable``, the packaged form).
_MODULE_ROOT = Path(__file__).resolve().parent
if str(_MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODULE_ROOT))

from common_esto_dashboard_data import (  # noqa: E402
    apply_sign_semantics,
    apply_visible_series,
    build_sign_semantics_summary,
    enrich_with_component_metadata,
    filter_common_esto_data,
    filter_ninth_pre_base_year_data,
    filter_template_for_leap_demand_coverage,
    load_active_power_interim_branches,
    load_common_esto_data,
    load_source_category_map,
    ninth_base_year_for_economy,
)
from common_esto_dashboard_output_layout import build_output_layout  # noqa: E402
from common_esto_dashboard_renderer import render_dashboard, set_code_colors_path  # noqa: E402


__all__ = [
    "OPTIONAL_DASHBOARD_INPUTS",
    "REQUIRED_DASHBOARD_INPUTS",
    "dashboard_base_year_from_leap_data",
    "normalize_dashboard_economy_key",
    "render_common_esto_dashboard",
    "render_common_esto_comparison_traces",
    "render_common_esto_dashboard_variants",
    "copy_mapping_diagnostics_page",
]


#: Input files a caller must supply, keyed by the argument that carries them.
#: Used by callers to explain a missing input before any work starts.
REQUIRED_DASHBOARD_INPUTS = {
    "comparison_data_path": "Common ESTO comparison data (common_esto_comparison_data.csv)",
    "common_rows_path": "Common ESTO row metadata (common_esto_rows.csv)",
    "template_path": "Dashboard template JSON (common_esto_dashboard_template.json)",
    "series_config_path": "Dashboard series configuration JSON (series_config.json)",
}

#: Optional inputs. Absent ones fall back to a documented default.
OPTIONAL_DASHBOARD_INPUTS = {
    "code_colors_path": "Per-axis ESTO code colour map (code_colors.json)",
    "power_interim_audit_path": "Mapping-chain interim power fallback audit",
    "source_to_common_map_path": "LEAP/9th native-source to Common ESTO map",
    "esto_to_common_map_path": "ESTO component to Common ESTO map",
    "missing_branch_exceptions_path": "Known missing LEAP branch exception ledger",
    "relationships_path": "LEAP-to-Common ESTO mapping relationships",
    "esto_vintage_issue": "Selected ESTO release issue (for example 2026)",
}


def _normalise_coverage_key(value: object) -> str:
    """Compare mapping labels without depending on slash or case conventions."""
    return " ".join(
        str(value or "").replace("\\", "/").replace("_", " ").split()
    ).casefold()


def _enabled(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "t", "yes", "y", "on"}


def _nonzero(value: object) -> bool:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return bool(pd.notna(numeric) and float(numeric) != 0.0)


def load_known_missing_branch_notes(
    *,
    exception_path: Path | str | None,
    relationships_path: Path | str | None,
    economy: object,
    esto_vintage_issue: object = "",
) -> dict[tuple[str, str], list[str]]:
    """Map eligible per-economy missing LEAP branches to Common ESTO chart keys."""
    workbook = Path(exception_path) if exception_path else None
    relationships_file = Path(relationships_path) if relationships_path else None
    if not workbook or not workbook.is_file() or not relationships_file or not relationships_file.is_file():
        return {}
    rows = pd.read_excel(workbook, sheet_name="branch_exceptions", dtype=object).fillna("")
    relationships = pd.read_csv(relationships_file, low_memory=False).fillna("")
    required = {"enabled", "branch_path", "economies_that_need_it"}
    relationship_columns = {"source_system", "source_sector_path", "source_fuel", "target_flow", "target_product"}
    if not required.issubset(rows.columns) or not relationship_columns.issubset(relationships.columns):
        return {}
    issue = str(esto_vintage_issue or "").strip()
    esto_column = f"esto_{issue}_last_year_signed_pj_all_economies"
    economy_key = str(economy or "").replace("_", "").strip().upper()
    notes: dict[tuple[str, str], list[str]] = {}
    leap_relationships = relationships[relationships["source_system"].astype(str).str.upper().eq("LEAP")]
    for row in rows.itertuples(index=False):
        item = row._asdict()
        if not _enabled(item.get("enabled")):
            continue
        economies = {
            value.strip().replace("_", "").upper()
            for value in str(item.get("economies_that_need_it", "")).split("|")
            if value.strip()
        }
        if economy_key not in economies:
            continue
        ninth_nonzero = _nonzero(item.get("ninth_reference_average_pj_per_year_all_economies"))
        esto_nonzero = esto_column in rows.columns and _nonzero(item.get(esto_column))
        if not (ninth_nonzero or esto_nonzero):
            continue
        branch_path = str(item.get("branch_path", "")).strip()
        parts = [part.strip() for part in branch_path.replace("/", "\\").split("\\") if part.strip()]
        if len(parts) < 2:
            continue
        if parts[0].casefold() == "demand":
            parts = parts[1:]
        source_sector, source_fuel = "/".join(parts[:-1]), parts[-1]
        matched = leap_relationships[
            leap_relationships["source_sector_path"].map(_normalise_coverage_key).eq(_normalise_coverage_key(source_sector))
            & leap_relationships["source_fuel"].map(_normalise_coverage_key).eq(_normalise_coverage_key(source_fuel))
        ]
        sources = []
        if esto_nonzero:
            sources.append(f"ESTO {issue}")
        if ninth_nonzero:
            sources.append("Ninth Reference")
        note = (
            f"Known coverage gap: LEAP has no '{' > '.join(parts)}' branch for this economy; "
            f"{' and '.join(sources)} is non-zero."
        )
        for match in matched[["target_flow", "target_product"]].drop_duplicates().itertuples(index=False):
            key = (_normalise_coverage_key(match.target_flow), _normalise_coverage_key(match.target_product))
            notes.setdefault(key, []).append(note)
    return {key: list(dict.fromkeys(values)) for key, values in notes.items()}


def normalize_dashboard_economy_key(economy: object) -> str:
    """Return the compact dashboard economy key used for output folders.

    Accepts either the underscore-normalized workflow form (``20_USA``) or the
    compact dashboard form (``20USA``) and always returns the compact form.
    """
    key = str(economy).replace("_", "").strip()
    if not key:
        raise ValueError("An economy code is required (for example '20_USA').")
    return key


def dashboard_base_year_from_leap_data(
    comparison_df: pd.DataFrame,
    configured_base_year: int,
) -> int:
    """Return the first available LEAP year, or the configured fallback.

    The base year marks the handover between historical ESTO and the LEAP
    scenario in the dashboard. It must therefore follow the supplied LEAP
    export rather than an assumption embedded in the shared template.
    """
    if comparison_df.empty or not {"source_system", "year"}.issubset(comparison_df.columns):
        return int(configured_base_year)
    leap_rows = comparison_df["source_system"].astype(str).str.upper().eq("LEAP")
    leap_years = pd.to_numeric(comparison_df.loc[leap_rows, "year"], errors="coerce")
    leap_years = leap_years.dropna()
    if leap_years.empty:
        return int(configured_base_year)
    return int(leap_years.min())


def copy_mapping_diagnostics_page(
    *,
    output_root: Path | str,
    economy: str,
    source_page_path: Path | str | None,
) -> dict[str, str] | None:
    """Copy the shared page and give it a durable link back to one dashboard."""
    source_page = Path(source_page_path) if source_page_path else None
    if source_page is None or not source_page.is_file():
        return None
    page_path = Path(output_root) / "diagnostics" / "dashboards" / "mapping_diagnostics.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_href = (
        f"../../{normalize_dashboard_economy_key(economy)}"
        "/dashboards/energy_balance_overview.html"
    )
    page_html = source_page.read_text(encoding="utf-8")
    page_html = page_html.replace(
        '<a href="#" onclick="history.back();return false;">← Back to economy dashboard</a>',
        f'<a href="{dashboard_href}">← Back to economy dashboard</a>',
        1,
    )
    page_path.write_text(page_html, encoding="utf-8")
    return {"page": str(page_path), "source_page": str(source_page)}


def configured_comparison_scopes(template: dict) -> list[dict[str, object]]:
    """Return validated category-basis definitions from maintained config."""
    selector = template.get("comparison_scope_selector", {}) or {}
    configured = selector.get("scopes", []) if selector.get("enabled", False) else []
    if not configured:
        scope = str(template.get("default_comparison_scope", "esto_leap_ninth"))
        configured = [{
            "comparison_scope": scope,
            "label": scope,
            "source_systems": [],
            "output_suffix": "",
        }]
    definitions: list[dict[str, object]] = []
    seen_scopes: set[str] = set()
    seen_suffixes: set[str] = set()
    requested_default = str(
        selector.get("default_scope", template.get("default_comparison_scope", ""))
    ).strip()
    for position, raw in enumerate(configured):
        scope = str(raw.get("comparison_scope", "")).strip()
        suffix = str(raw.get("output_suffix", "")).strip()
        if not scope or scope in seen_scopes:
            raise ValueError(
                f"Comparison-scope selector contains a missing or duplicate scope: {scope!r}"
            )
        if suffix in seen_suffixes or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for char in suffix
        ):
            raise ValueError(
                f"Comparison-scope selector contains an invalid or duplicate output suffix: {suffix!r}"
            )
        definitions.append({
            "comparison_scope": scope,
            "label": str(raw.get("label", scope)).strip() or scope,
            "source_systems": [
                str(source).strip().upper()
                for source in raw.get("source_systems", [])
                if str(source).strip()
            ],
            "output_suffix": suffix,
            "is_default": scope == requested_default if requested_default else position == 0,
        })
        seen_scopes.add(scope)
        seen_suffixes.add(suffix)
    defaults = [item for item in definitions if item["is_default"]]
    if len(defaults) != 1:
        raise ValueError("Comparison-scope selector must define exactly one default scope.")
    if str(defaults[0]["output_suffix"]):
        raise ValueError(
            "The default comparison scope must use an empty output_suffix to preserve existing URLs."
        )
    return definitions


def render_common_esto_dashboard(
    *,
    economy: str,
    comparison_data_path: Path | str,
    common_rows_path: Path | str,
    template_path: Path | str,
    series_config_path: Path | str,
    output_root: Path | str,
    code_colors_path: Path | str | None = None,
    power_interim_audit_path: Path | str | None = None,
    source_to_common_map_path: Path | str | None = None,
    esto_to_common_map_path: Path | str | None = None,
    missing_branch_exceptions_path: Path | str | None = None,
    relationships_path: Path | str | None = None,
    esto_vintage_issue: str = "",
    comparison_scope: str = "esto_leap_ninth",
    wide_file_scope: str = "esto_leap_ninth",
    min_year: int | None = 2010,
    max_year: int | None = 2060,
    include_ninth_pre_base_year_data: bool = False,
    representation_status_df: pd.DataFrame | None = None,
    dashboard_updated_label: str = "",
    clear_existing: bool = True,
    dashboard_key: str | None = None,
    category_basis_options: Sequence[dict[str, str]] = (),
    active_dataset_filter_options: Sequence[str] = (),
    dashboard_key_suffix: str = "",
    additional_pages: Sequence[dict[str, str]] = (),
    trace_only: bool = False,
) -> dict[str, object]:
    """Render the Common ESTO dashboard for one economy from explicit inputs.

    ``representation_status_df`` is optional current-run upstream presentation
    metadata. It controls placeholder notices and suppresses false detail cards
    for placeholder-only component prefixes after routing; Common ESTO facts
    still control page-level aggregate and category rendering. Partial detail
    remains visible with a warning.

    ``source_to_common_map_path`` and ``esto_to_common_map_path`` are optional
    provenance inputs for the guide's native-category table. When omitted, the
    dashboard still renders and the table retains the Common categories with
    unavailable source cells.
    """
    economy_key = normalize_dashboard_economy_key(economy)
    if code_colors_path is not None:
        set_code_colors_path(code_colors_path)
    template = json.loads(Path(template_path).read_text(encoding="utf-8"))
    template = filter_template_for_leap_demand_coverage(
        template,
        representation_status_df,
    )
    resolved_power_interim_audit_path = (
        Path(power_interim_audit_path)
        if power_interim_audit_path is not None
        else Path(comparison_data_path).resolve().parent
        / "leap_source_branch_fallback_audit.csv"
    )
    template["_power_interim_placeholder_branches"] = (
        load_active_power_interim_branches(
            resolved_power_interim_audit_path,
            economy_key,
            min_year=min_year,
            max_year=max_year,
        )
        if resolved_power_interim_audit_path.exists()
        else []
    )
    template["_active_comparison_scope"] = comparison_scope
    template["_current_dashboard_key"] = economy_key
    template["_category_basis_options"] = list(category_basis_options)
    template["_active_dataset_filter_options"] = list(active_dataset_filter_options)
    if "ESTO_EXTENDED" in {
        str(source).upper() for source in active_dataset_filter_options
    }:
        template["chart_generation"]["comparison_source_system"] = "ESTO_EXTENDED"
    template["_dashboard_key_suffix"] = dashboard_key_suffix
    series_config = json.loads(Path(series_config_path).read_text(encoding="utf-8"))
    source_category_map = (
        load_source_category_map(
            Path(source_to_common_map_path) if source_to_common_map_path is not None else None,
            Path(esto_to_common_map_path) if esto_to_common_map_path is not None else None,
        )
        if not trace_only and (
            source_to_common_map_path is not None or esto_to_common_map_path is not None
        )
        else None
    )

    raw_df = load_common_esto_data(
        Path(comparison_data_path),
        wide_file_scope=wide_file_scope,
    )
    raw_df["economy"] = (
        raw_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    )
    raw_df = enrich_with_component_metadata(raw_df, Path(common_rows_path))
    coverage_notes = load_known_missing_branch_notes(
        exception_path=missing_branch_exceptions_path,
        relationships_path=relationships_path,
        economy=economy,
        esto_vintage_issue=esto_vintage_issue,
    )
    raw_df["known_missing_branch_notes"] = [
        "\n".join(coverage_notes.get((_normalise_coverage_key(flow), _normalise_coverage_key(product)), []))
        for flow, product in zip(raw_df["common_flow_label"], raw_df["common_product_label"])
    ]

    configured_base_year = int(template.get("chart_generation", {}).get("base_year", 2022))
    economy_raw_df = raw_df[raw_df["economy"].astype(str).eq(economy_key)]
    base_year = dashboard_base_year_from_leap_data(economy_raw_df, configured_base_year)
    template.setdefault("chart_generation", {})["base_year"] = base_year
    ninth_base_year = ninth_base_year_for_economy(economy_key, base_year)
    input_row_count = len(raw_df)
    raw_df = filter_ninth_pre_base_year_data(
        raw_df,
        base_year=ninth_base_year,
        include_pre_base_year_data=include_ninth_pre_base_year_data,
    )
    excluded_pre_base_year_rows = input_row_count - len(raw_df)

    filtered_df = filter_common_esto_data(
        raw_df,
        comparison_scope=comparison_scope,
        economy=economy_key,
        min_year=min_year,
        max_year=max_year,
    )
    visible_df = apply_visible_series(filtered_df, series_config.get("visible_series", []))
    visible_df = apply_sign_semantics(visible_df, template.get("sign_semantics"))

    # Scope-specific diagnostic pages need every comparison scope, so they read a
    # separate frame that is filtered by economy and year only.
    scope_df = raw_df[raw_df["economy"].astype(str) == economy_key].copy()
    if min_year is not None:
        scope_df = scope_df[scope_df["year"] >= min_year]
    if max_year is not None:
        scope_df = scope_df[scope_df["year"] <= max_year]
    scope_df = scope_df.reset_index(drop=True)
    scope_visible_df = apply_visible_series(scope_df, series_config.get("visible_series", []))
    scope_visible_df = apply_sign_semantics(scope_visible_df, template.get("sign_semantics"))

    if visible_df.empty:
        raise ValueError(
            f"No dashboard rows survived filtering for economy {economy_key!r} "
            f"(comparison scope {comparison_scope!r}, years {min_year}-{max_year}). "
            "Check that the comparison data covers this economy and scope."
        )

    layout = build_output_layout(
        Path(output_root),
        dashboard_key or economy_key,
        clear_existing=clear_existing,
    )
    if not trace_only:
        sign_summary_df = build_sign_semantics_summary(visible_df)
        sign_summary_df.to_csv(layout["supporting"] / "sign_semantics_summary.csv", index=False)
    manifest_df: pd.DataFrame = render_dashboard(
        visible_df,
        template,
        series_config,
        layout,
        scope_df=scope_visible_df,
        dashboard_updated_label=dashboard_updated_label,
        source_category_map=source_category_map,
        additional_pages=list(additional_pages),
        trace_only=trace_only,
    )

    return {
        "economy": economy_key,
        "output_root": str(layout["root"]),
        "dashboard_index": str(layout["dashboards"] / "index.html") if not trace_only else "",
        "chart_manifest": str(layout["supporting"] / "chart_manifest.csv") if not trace_only else "",
        "sign_semantics_summary": str(layout["supporting"] / "sign_semantics_summary.csv") if not trace_only else "",
        "comparison_trace_root": str(layout["root"]) if trace_only else "",
        "chart_bundle_directory": str(layout["chart_bundles"]),
        "chart_count": int(len(manifest_df)),
        "input_row_count": int(input_row_count),
        "excluded_pre_base_year_rows": int(excluded_pre_base_year_rows),
        "filtered_row_count": int(len(filtered_df)),
        "visible_row_count": int(len(visible_df)),
        "base_year": base_year,
        "ninth_base_year": ninth_base_year,
        "leap_demand_representation_status_rows": (
            0 if representation_status_df is None else len(representation_status_df)
        ),
        "power_interim_placeholder_branches": list(
            template["_power_interim_placeholder_branches"]
        ),
        "code_colors_path": str(code_colors_path) if code_colors_path else "",
    }


def render_common_esto_comparison_traces(**kwargs: object) -> dict[str, object]:
    """Render the normal dashboard chart bundles without presentation outputs.

    This is intentionally a thin call-through to :func:`render_common_esto_dashboard`.
    Version comparison therefore shares every reviewed input, mapping-derived
    row, source/scenario decision, routing rule, and hierarchy frontier with
    the full renderer instead of maintaining a second comparison mapping path.
    """
    call_kwargs = dict(kwargs)
    template_path = Path(str(call_kwargs["template_path"]))
    economy_key = normalize_dashboard_economy_key(call_kwargs["economy"])
    definitions = configured_comparison_scopes(
        json.loads(template_path.read_text(encoding="utf-8"))
    )
    default = next(item for item in definitions if item["is_default"])
    options = [
        {
            "comparison_scope": str(item["comparison_scope"]),
            "label": str(item["label"]),
            "dashboard_key": f"{economy_key}{item['output_suffix']}",
        }
        for item in definitions
    ]
    call_kwargs.update(
        {
            "comparison_scope": str(default["comparison_scope"]),
            "dashboard_key": f"{economy_key}{default['output_suffix']}",
            "category_basis_options": options,
            "active_dataset_filter_options": list(default["source_systems"]),
            "dashboard_key_suffix": str(default["output_suffix"]),
            "clear_existing": True,
            "trace_only": True,
        }
    )
    return render_common_esto_dashboard(**call_kwargs)


def render_common_esto_dashboard_variants(
    **kwargs: object,
) -> dict[str, object]:
    """Render every configured comparison basis and the shared diagnostics page."""
    template_path = Path(str(kwargs["template_path"]))
    output_root = Path(str(kwargs["output_root"]))
    economy_key = normalize_dashboard_economy_key(kwargs["economy"])
    diagnostics_result = copy_mapping_diagnostics_page(
        output_root=output_root,
        economy=economy_key,
        source_page_path=kwargs.get("mapping_diagnostics_source_page_path"),
    )
    diagnostics_page = {
        "page_key": "mapping_diagnostics",
        "page_label": "Mapping diagnostics",
        "file": "../../diagnostics/dashboards/mapping_diagnostics.html",
    }
    definitions = configured_comparison_scopes(
        json.loads(template_path.read_text(encoding="utf-8"))
    )
    options = [
        {
            "comparison_scope": str(item["comparison_scope"]),
            "label": str(item["label"]),
            "dashboard_key": f"{economy_key}{item['output_suffix']}",
        }
        for item in definitions
    ]
    scope_results: dict[str, dict[str, object]] = {}
    default_result: dict[str, object] | None = None
    for definition in definitions:
        call_kwargs = deepcopy(kwargs)
        call_kwargs.pop("mapping_diagnostics_source_page_path", None)
        call_kwargs.update({
            "comparison_scope": str(definition["comparison_scope"]),
            "dashboard_key": f"{economy_key}{definition['output_suffix']}",
            "category_basis_options": options,
            "active_dataset_filter_options": list(definition["source_systems"]),
            "dashboard_key_suffix": str(definition["output_suffix"]),
            "additional_pages": [diagnostics_page] if diagnostics_result else [],
            "clear_existing": True,
        })
        result = render_common_esto_dashboard(**call_kwargs)
        scope_results[str(definition["comparison_scope"])] = result
        if definition["is_default"]:
            default_result = result
    if default_result is None:
        raise RuntimeError("No default comparison-scope dashboard was rendered.")
    combined = dict(default_result)
    combined["output_root"] = str(output_root)
    combined["scope_results"] = scope_results
    combined["mapping_diagnostics"] = diagnostics_result
    combined["chart_count"] = sum(
        int(result.get("chart_count", 0)) for result in scope_results.values()
    )
    return combined


#%%
