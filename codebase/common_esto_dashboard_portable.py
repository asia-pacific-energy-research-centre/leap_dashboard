#%%
"""Minimal, dependency-light entry point for rendering one Common ESTO dashboard.

``common_esto_dashboard_workflow.py`` is the maintainer-facing notebook workflow:
it resolves sibling-repository paths, refreshes upstream data, renders the shared
mapping-diagnostics page and the full mapping tree explorer, and executes its own
run block at import time. That makes it unsuitable for reuse as a library and
impossible to package for a machine that has no ``leap_mappings`` checkout.

This module is the narrow, importable core of the same render: every input is an
explicit argument, nothing is read from the current working directory, nothing is
executed at import, and the only in-repo dependencies are the three production
dashboard modules. It is what the developer launcher and the portable release
both call, so both run identical rendering code.

Deliberately **not** included here (they need ``leap_mappings`` artifacts that a
portable package does not carry):

- the shared mapping-diagnostics page (``common_esto_dashboard_mapping_diagnostics``);
- the full mapping tree explorer (``scripts/render_full_mapping_tree_explorer``);
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
    load_common_esto_data,
)
from common_esto_dashboard_output_layout import build_output_layout  # noqa: E402
from common_esto_dashboard_renderer import render_dashboard, set_code_colors_path  # noqa: E402


__all__ = [
    "OPTIONAL_DASHBOARD_INPUTS",
    "REQUIRED_DASHBOARD_INPUTS",
    "normalize_dashboard_economy_key",
    "render_common_esto_dashboard",
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


def render_common_esto_dashboard(
    *,
    economy: str,
    comparison_data_path: Path | str,
    common_rows_path: Path | str,
    template_path: Path | str,
    series_config_path: Path | str,
    output_root: Path | str,
    code_colors_path: Path | str | None = None,
    comparison_scope: str = "esto_leap_ninth",
    wide_file_scope: str = "esto_leap_ninth",
    min_year: int | None = 2010,
    max_year: int | None = 2060,
    include_ninth_pre_base_year_data: bool = False,
    missing_leap_demand_branches: Sequence[str] = (),
    dashboard_updated_label: str = "",
    clear_existing: bool = True,
) -> dict[str, object]:
    """Render the Common ESTO dashboard for one economy from explicit inputs.

    ``missing_leap_demand_branches`` lists LEAP demand branches that have no
    separately modelled detail for this economy. It is a caller argument rather
    than a lookup because the record that answers it is owned by ``leap_mappings``
    (``config/all_demand_aggregated_components.json``); passing an empty sequence
    renders every sector page.
    """
    economy_key = normalize_dashboard_economy_key(economy)
    if code_colors_path is not None:
        set_code_colors_path(code_colors_path)
    template = json.loads(Path(template_path).read_text(encoding="utf-8"))
    template = filter_template_for_leap_demand_coverage(
        template,
        list(missing_leap_demand_branches),
    )
    series_config = json.loads(Path(series_config_path).read_text(encoding="utf-8"))

    raw_df = load_common_esto_data(
        Path(comparison_data_path),
        wide_file_scope=wide_file_scope,
    )
    raw_df["economy"] = (
        raw_df["economy"].astype(str).str.replace("_", "", regex=False).str.strip()
    )
    raw_df = enrich_with_component_metadata(raw_df, Path(common_rows_path))

    base_year = int(template.get("chart_generation", {}).get("base_year", 2022))
    input_row_count = len(raw_df)
    raw_df = filter_ninth_pre_base_year_data(
        raw_df,
        base_year=base_year,
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
        economy_key,
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
        "missing_leap_demand_branches": list(missing_leap_demand_branches),
        "code_colors_path": str(code_colors_path) if code_colors_path else "",
    }


#%%
