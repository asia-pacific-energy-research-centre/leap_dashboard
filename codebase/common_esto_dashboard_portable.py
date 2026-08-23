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
diagnostics page from the complete ``leap_mappings`` results tree. The portable
release instead publishes a clearly labelled per-export Mapping diagnostics
page from its mapping-chain category-recognition QA; it does not substitute for
the APEC-wide hierarchy contract.

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
from html import escape
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
    "normalize_dashboard_economy_key",
    "render_common_esto_dashboard",
    "render_common_esto_dashboard_variants",
    "write_portable_mapping_diagnostics_page",
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
}


def normalize_dashboard_economy_key(economy: object) -> str:
    """Return the compact dashboard economy key used for output folders.

    Accepts either the underscore-normalized workflow form (``20_USA``) or the
    compact dashboard form (``20USA``) and always returns the compact form.
    """
    key = str(economy).replace("_", "").strip()
    if not key:
        raise ValueError("An economy code is required (for example '20_USA').")
    return key


def _portable_diagnostics_table(frame: pd.DataFrame, columns: list[str]) -> str:
    """Render a small escaped table for the portable mapping QA page."""
    available = [column for column in columns if column in frame.columns]
    if frame.empty:
        return '<p class="empty-state">No non-zero unmapped LEAP branches were recorded.</p>'
    if not available:
        # The fast mapping path emits source-row evidence with a different
        # schema from the maintainer QA workbook. Show that evidence rather
        # than rendering an empty diagnostics panel.
        available = [str(column) for column in frame.columns]
    header = "".join(f"<th>{escape(column)}</th>" for column in available)
    rows = []
    for _, row in frame.loc[:, available].iterrows():
        cells = "".join(
            f"<td>{escape('' if pd.isna(row[column]) else str(row[column]))}</td>"
            for column in available
        )
        rows.append(f"<tr>{cells}</tr>")
    return f'<div class="table-scroll"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def write_portable_mapping_diagnostics_page(
    *,
    output_root: Path | str,
    economy: str,
    unmapped_branches_path: Path | str | None,
    dashboard_updated_label: str = "",
) -> dict[str, str | int]:
    """Write the per-export category-recognition page used by review tools.

    This only presents the mapping-chain QA generated for the submitted export.
    It deliberately does not recreate the maintainer-only APEC hierarchy checks.
    """
    output_root = Path(output_root)
    economy_key = normalize_dashboard_economy_key(economy)
    qa_path = Path(unmapped_branches_path) if unmapped_branches_path else None
    if qa_path is not None and qa_path.is_file():
        unmapped = pd.read_csv(qa_path)
        qa_note = f"Category-recognition QA: {qa_path.name}"
    else:
        unmapped = pd.DataFrame()
        qa_note = "The mapping-chain category-recognition QA file was not available for this run."

    dashboard_dir = output_root / "diagnostics" / "dashboards"
    supporting_dir = output_root / "diagnostics" / "supporting_files"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    supporting_dir.mkdir(parents=True, exist_ok=True)
    page_path = dashboard_dir / "mapping_diagnostics.html"
    summary_path = supporting_dir / "mapping_diagnostics_summary.csv"
    pd.DataFrame([{
        "metric": "Non-zero unmapped LEAP branches",
        "rows": len(unmapped),
    }]).to_csv(summary_path, index=False)
    table_html = _portable_diagnostics_table(
        unmapped,
        ["leap_flow", "leap_product", "indirect_esto_flow", "indirect_esto_product", "qa_status"],
    )
    page_path.write_text(
        f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapping diagnostics | {escape(economy_key)}</title><style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f8;color:#172033}}.shell{{max-width:1200px;margin:auto;padding:20px}}header,.panel{{background:#fff;border:1px solid #d9e1ea;border-radius:10px;padding:16px;margin-bottom:16px}}h1,h2{{margin:0 0 10px}}.subtle,.empty-state{{color:#5f6b7a;line-height:1.5}}.warning{{background:#fff4e5;color:#8a4b08;border-radius:7px;padding:11px;line-height:1.5}}.count{{font-size:28px;font-weight:700;color:#9b1c1c}}.table-scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #d9e1ea;padding:7px 9px;text-align:left;vertical-align:top}}th{{background:#e8f0fa}}a{{color:#1b5e9a}}</style></head>
<body><main class="shell"><header><a href="../../{escape(economy_key)}/dashboards/index.html">← Back to economy dashboard</a><h1>Mapping diagnostics</h1><p class="subtle">Per-export review for {escape(economy_key)}. Updated: {escape(dashboard_updated_label)}</p></header>
<section class="panel"><h2>Imported LEAP category recognition</h2><p class="subtle">The import retains LEAP labels after known aliases are normalised. A category appears below only when a non-zero LEAP flow/product pair has no direct maintained LEAP-to-ESTO mapping. It is a mapping-review signal, not a claim that the source label is invalid.</p><p class="count">{len(unmapped):,}</p><p class="subtle">non-zero unmapped LEAP branch(es)</p></section>
<section class="panel"><p class="warning"><strong>ESTO Extended caution.</strong> Do not treat missing detailed LEAP branches as mapping failures until the detailed LEAP sectors are fully imported into the main LEAP areas.</p></section>
<section class="panel"><h2>Non-zero unmapped LEAP branches</h2>{table_html}</section><footer class="subtle">{escape(qa_note)}</footer></main></body></html>""",
        encoding="utf-8",
    )
    return {
        "page": str(page_path),
        "summary": str(summary_path),
        "unmapped_branch_count": len(unmapped),
    }


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
) -> dict[str, object]:
    """Render the Common ESTO dashboard for one economy from explicit inputs.

    ``representation_status_df`` is optional current-run upstream presentation
    metadata. It controls placeholder notices only; common facts still control
    category and page rendering.

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
    template["_power_interim_placeholder_branches"] = (
        load_active_power_interim_branches(
            Path(power_interim_audit_path),
            economy_key,
            min_year=min_year,
            max_year=max_year,
        )
        if power_interim_audit_path is not None
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
        if source_to_common_map_path is not None or esto_to_common_map_path is not None
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

    base_year = int(template.get("chart_generation", {}).get("base_year", 2022))
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
    )

    return {
        "economy": economy_key,
        "output_root": str(layout["root"]),
        "dashboard_index": str(layout["dashboards"] / "index.html"),
        "chart_manifest": str(layout["supporting"] / "chart_manifest.csv"),
        "sign_semantics_summary": str(layout["supporting"] / "sign_semantics_summary.csv"),
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


def render_common_esto_dashboard_variants(
    **kwargs: object,
) -> dict[str, object]:
    """Render every configured comparison basis and the per-export QA page."""
    template_path = Path(str(kwargs["template_path"]))
    output_root = Path(str(kwargs["output_root"]))
    economy_key = normalize_dashboard_economy_key(kwargs["economy"])
    diagnostics_result = write_portable_mapping_diagnostics_page(
        output_root=output_root,
        economy=economy_key,
        unmapped_branches_path=kwargs.get("mapping_diagnostics_unmapped_branches_path"),
        dashboard_updated_label=str(kwargs.get("dashboard_updated_label", "")),
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
        call_kwargs.pop("mapping_diagnostics_unmapped_branches_path", None)
        call_kwargs.update({
            "comparison_scope": str(definition["comparison_scope"]),
            "dashboard_key": f"{economy_key}{definition['output_suffix']}",
            "category_basis_options": options,
            "active_dataset_filter_options": list(definition["source_systems"]),
            "dashboard_key_suffix": str(definition["output_suffix"]),
            "additional_pages": [diagnostics_page],
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
