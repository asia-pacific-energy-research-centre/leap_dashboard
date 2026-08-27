#%%
"""Output-layout helpers for the production Common ESTO dashboard."""

#%%
from pathlib import Path
import shutil


#%%
def clear_generated_output_folders(layout: dict[str, Path]) -> None:
    """Remove generated dashboard files from this pack's output folders."""
    for key in ["dashboards", "chart_bundles", "supporting"]:
        path = layout[key]
        if path.exists():
            shutil.rmtree(path)


def build_output_layout(output_root: Path, economy: str, *, clear_existing: bool = False) -> dict[str, Path]:
    """Create and return the standard dashboard output folders."""
    root = output_root / economy
    layout = {
        "root": root,
        "dashboards": root / "dashboards",
        "chart_bundles": root / "chart_bundles",
        "supporting": root / "supporting_files",
    }
    if clear_existing:
        clear_generated_output_folders(layout)
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def publish_to_docs(layout: dict[str, Path], docs_root: Path) -> dict[str, int]:
    """Copy dashboard-serving files from outputs/<economy>/ to docs/<economy>/.

    Copies only:
        dashboards/*.html      -> docs/<economy>/dashboards/
        chart_bundles/*.js     -> docs/<economy>/chart_bundles/

    Supporting files (CSV, XLSX, page-assignment summaries, sign summaries,
    chart manifests) are never copied — they stay in outputs/ only.

    Destination files matching the copied patterns that are no longer present
    in the source (e.g. a demand-sector page dropped by the LEAP-coverage
    filter) are removed, so stale pages don't linger in docs/.

    Returns {subfolder_name: file_count} for reporting.
    """
    economy = layout["root"].name
    copy_specs = [
        (layout["dashboards"],    docs_root / economy / "dashboards",    ["*.html"], ["*.html"]),
        (layout["chart_bundles"], docs_root / economy / "chart_bundles", ["*.js"], ["*.js", "*.json"]),
    ]
    if economy == "diagnostics":
        copy_specs.append(
            (
                layout["supporting"],
                docs_root / economy / "supporting_files",
                ["source_to_common_esto_map.csv"],
                ["source_to_common_esto_map.csv"],
            )
        )
    counts: dict[str, int] = {}
    for src_dir, dst_dir, copy_patterns, cleanup_patterns in copy_specs:
        dst_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        keep_names: set[str] = set()
        for pattern in copy_patterns:
            for src_file in src_dir.glob(pattern):
                shutil.copy2(src_file, dst_dir / src_file.name)
                keep_names.add(src_file.name)
                n += 1
        for pattern in cleanup_patterns:
            for dst_file in dst_dir.glob(pattern):
                if dst_file.name not in keep_names:
                    dst_file.unlink()
        counts[dst_dir.name] = n
    return counts

#%%
