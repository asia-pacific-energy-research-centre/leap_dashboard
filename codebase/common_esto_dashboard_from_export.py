#%%
"""Render a Common ESTO dashboard directly from a LEAP export directory.

This dashboard entry point delegates parsing and mapping to the supported
developer launcher owned by ``leap_initialisation`` and ``leap_mappings``.
"""

#%%
from __future__ import annotations

import shutil
import sys
import os
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "common_esto_dashboard"
# Worktrees live below ``leap_dashboard/.claude/worktrees/<name>``; the
# initialisation repository is a sibling of ``leap_dashboard`` under github.
DEFAULT_LEAP_INITIALISATION_ROOT = REPO_ROOT.parents[3] / "leap_initialisation"


#%%
def render_dashboard_from_leap_export(
    *,
    economy: str,
    export_dir: str | Path,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    leap_initialisation_root: str | Path = DEFAULT_LEAP_INITIALISATION_ROOT,
    min_year: int = 2010,
    max_year: int = 2060,
    comparison_scope: str = "esto_leap_ninth",
    run_label: str | None = "dashboard-from-export",
):
    """Parse, map, and render one economy from its LEAP export directory.

    The delegated mapping chain reads the LEAP export, converts it into the
    ESTO-shaped component space, applies the Common ESTO mappings, and renders
    the dashboard. No cached LEAP values are substituted.
    """
    init_root = Path(leap_initialisation_root).resolve()
    export_path = Path(export_dir).resolve()
    if not export_path.is_dir():
        raise FileNotFoundError(f"LEAP export directory does not exist: {export_path}")

    # Always place the sibling repository first.  It may already be present
    # later in sys.path through the web-app launcher, in which case merely
    # checking membership leaves this worktree's ``codebase`` package ahead
    # of the package that owns ``portable_release``.
    init_root_text = str(init_root)
    sys.path[:] = [entry for entry in sys.path if entry != init_root_text]
    sys.path.insert(0, init_root_text)
    # The dashboard worktree may already have its own ``codebase`` package on
    # sys.modules. Remove that package before importing the sibling launcher,
    # whose package contains ``portable_release``.
    for module_name in list(sys.modules):
        if module_name == "codebase" or module_name.startswith("codebase."):
            del sys.modules[module_name]
    from codebase.portable_release import developer_launcher
    from codebase.portable_release.settings import DeveloperSettings

    mappings_root = Path(
        os.environ.get("LEAP_MAPPINGS_ROOT", str(init_root.parent / "leap_mappings"))
    ).resolve()
    destination_root = Path(output_root).resolve()
    run_root = destination_root / "_export_runs"
    settings = DeveloperSettings(
        source_path=init_root / "config" / "portable_release_manifest.toml",
        repositories={
            "leap_initialisation": init_root,
            "leap_mappings": mappings_root,
            "leap_dashboard": REPO_ROOT,
        },
        output_root=run_root / "output",
        input_root=run_root / "input",
        log_root=run_root / "logs",
    )
    context = developer_launcher.build_context(settings=settings)
    context.require_ready()
    context.activate_sys_path()

    result = developer_launcher.run_dashboard_from_export(
        economy=economy,
        export_dir=export_path,
        comparison_scope=comparison_scope,
        min_year=min_year,
        max_year=max_year,
        run_label=run_label,
        context=context,
    )
    if not result.ok:
        return result

    source_index = Path(result.outputs["dashboard_index"])
    source_dashboard = source_index.parent.parent
    economy_key = str(economy).replace("_", "").strip()
    destination = destination_root / economy_key
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dashboard, destination, dirs_exist_ok=True)

    result.outputs["copied_dashboard"] = destination
    result.outputs["copied_dashboard_index"] = destination / "dashboards" / "index.html"
    result.outputs["copied_emissions_page"] = destination / "dashboards" / "emissions.html"
    return result


#%%
# Notebook controls: set RUN_RENDER_FROM_EXPORT = True when intentionally running.
RUN_RENDER_FROM_EXPORT = False
ECONOMY = "20_USA"
EXPORT_DIR = REPO_ROOT.parent / "leap_initialisation" / "data" / "leap balances exports" / ECONOMY

if RUN_RENDER_FROM_EXPORT:
    RENDER_RESULT = render_dashboard_from_leap_export(
        economy=ECONOMY,
        export_dir=EXPORT_DIR,
    )
    print("\n".join(RENDER_RESULT.summary_lines()))

#%%
