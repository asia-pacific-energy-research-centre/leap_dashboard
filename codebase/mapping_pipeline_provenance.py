#%%
"""Answer one question about the mapping artifacts: were they built by current code?

A rendered dashboard page is only as trustworthy as the ``leap_mappings``
artifacts behind it, and an artifact carries no record of the code version that
produced it. Comparing artifact write times against ``leap_mappings``
``codebase/`` commit dates is the cheapest available proxy, and it is what caught
the 2026-07-27 ESTO rollup source-identity doubling: the Stage 3 run finished 35
minutes before the commit that fixed it, so every published rollup value for 15
flows was doubled.

Both the diagnostics prototype and the pipeline health report use this module, so
they cannot disagree about whether a run is current.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pandas as pd


def stage3_manifest(mappings_root: Path) -> dict:
    """Read the Stage 3 run manifest, or return an explicit failure marker."""
    manifest_path = mappings_root / "results" / "common_esto" / "stage3_run_manifest.json"
    if not manifest_path.exists():
        return {"_missing": True, "_path": str(manifest_path)}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - report, never fail a render
        return {"_missing": True, "_path": str(manifest_path),
                "_error": f"{type(error).__name__}: {error}"}


def pipeline_commits_since(
    mappings_root: Path, cutoff: pd.Timestamp | None
) -> tuple[list[dict[str, str]], str]:
    """List ``leap_mappings`` pipeline-code commits made after ``cutoff``.

    ``cutoff`` must be local time, so it compares correctly with local git commit
    dates. Returns ``(commits, error)``; a non-empty error means the question
    could not be answered, which is not the same as "no newer commits".
    """
    if cutoff is None:
        return [], "No artifact timestamp to compare against."
    try:
        completed = subprocess.run(
            ["git", "log", "--since", cutoff.strftime("%Y-%m-%d %H:%M:%S"),
             "--format=%h%x1f%ad%x1f%s", "--date=iso", "--", "codebase/"],
            cwd=mappings_root, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return [], f"Could not read mapping-pipeline history: {type(error).__name__}: {error}"
    if completed.returncode != 0:
        return [], f"git log failed: {completed.stderr.strip()[:200]}"
    commits: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        fields = line.split("\x1f")
        if len(fields) == 3:
            commits.append({"commit": fields[0], "committed": fields[1], "subject": fields[2]})
    return commits, ""


def artifact_mtime(path: Path) -> pd.Timestamp | None:
    """Local-time write timestamp, comparable with local git commit dates."""
    return pd.Timestamp.fromtimestamp(path.stat().st_mtime) if path.exists() else None


def provenance_message(mappings_root: Path, *, page_label: str = "This page") -> tuple[str, str]:
    """Describe where a rendered page's data came from, and whether it is current.

    Returns ``(message_html, tone)`` where tone is ``"warning"`` when the
    artifacts were produced by superseded code, and ``"info"`` otherwise.
    """
    manifest = stage3_manifest(mappings_root)
    comparison_path = mappings_root / "results" / "common_esto" / "common_esto_comparison_data.csv"
    written = artifact_mtime(comparison_path)
    written_label = written.strftime("%Y-%m-%d %H:%M") if written is not None else "an unknown time"
    if manifest.get("_missing"):
        return (
            f"<strong>Snapshot with unknown provenance.</strong> {page_label} was rendered from "
            f"artifacts written {written_label}, but no Stage 3 run manifest was found at "
            f"<code>{manifest.get('_path', '')}</code>, so the run that produced them cannot be "
            "identified.",
            "warning",
        )
    run_id = str(manifest.get("run_id", "unknown"))
    commits, error = pipeline_commits_since(mappings_root, written)
    if error:
        return (
            f"<strong>Snapshot.</strong> {page_label} was rendered {written_label} from Stage 3 run "
            f"<code>{run_id}</code>. Whether the mapping pipeline has changed since could not be "
            f"checked: {error}",
            "warning",
        )
    if not commits:
        return (
            f"<strong>Snapshot.</strong> {page_label} was rendered {written_label} from Stage 3 run "
            f"<code>{run_id}</code>, and no mapping-pipeline code commit is newer than those "
            "artifacts. Values reflect the pipeline as it currently stands.",
            "info",
        )
    subjects = "; ".join(f"<code>{commit['commit']}</code> {commit['subject']}" for commit in commits[:3])
    remainder = f" and {len(commits) - 3} more" if len(commits) > 3 else ""
    return (
        f"<strong>Snapshot, and the source artifacts were produced by superseded code.</strong> "
        f"{page_label} was rendered {written_label} from Stage 3 run <code>{run_id}</code>, which "
        f"predates {len(commits)} mapping-pipeline commit(s): {subjects}{remainder}. The page reports "
        "the artifact faithfully; the artifact needs a rebuild.",
        "warning",
    )


#%%
