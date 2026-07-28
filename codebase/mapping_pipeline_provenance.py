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
import os
import subprocess

import pandas as pd


MAPPINGS_ROOT_ENV_VAR = "LEAP_MAPPINGS_ROOT"
USE_OUTPUT_CONTRACT_ENV_VAR = "COMMON_ESTO_USE_OUTPUT_CONTRACT"
OUTPUT_CONTRACT_PATH_ENV_VAR = "COMMON_ESTO_OUTPUT_CONTRACT_PATH"
OUTPUT_CONTRACT_VERSION = "common_esto_output_contract_v1"


def resolve_mappings_root(default: Path) -> Path:
    """Return the mapping repository to read, honouring ``LEAP_MAPPINGS_ROOT``.

    The pipeline can be run from a git worktree so the main checkout stays free
    for other work. A worktree writes its own ``results/``, so the dashboard
    needs to be pointed at it explicitly; otherwise it silently reports the main
    checkout's artifacts while appearing to describe the worktree run.
    """
    override = os.environ.get(MAPPINGS_ROOT_ENV_VAR, "").strip()
    if not override:
        return default
    root = Path(override).expanduser()
    if not (root / "results").is_dir():
        raise ValueError(
            f"{MAPPINGS_ROOT_ENV_VAR}={override!r} has no results/ directory. "
            "Point it at a mapping repository root or unset it."
        )
    return root


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


def output_contract_is_selected() -> bool:
    """Return whether dashboard inputs explicitly select the v1 output contract."""
    return os.environ.get(USE_OUTPUT_CONTRACT_ENV_VAR, "0").strip().casefold() in {
        "1",
        "true",
        "yes",
        "y",
    }


def output_contract_path(mappings_root: Path) -> Path:
    """Return the explicit or canonical selected output-contract manifest path."""
    override = os.environ.get(OUTPUT_CONTRACT_PATH_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return mappings_root / "results" / "common_esto" / "common_esto_output_contract.json"


def _declared_contract_member_path(
    manifest_path: Path,
    declaration: object,
    member_name: str,
) -> Path:
    """Resolve a declared member path without allowing absolute or escaping paths."""
    if not isinstance(declaration, dict):
        raise ValueError(f"Output contract {member_name} declaration must be an object.")
    path_text = str(declaration.get("path", "")).strip()
    if not path_text:
        raise ValueError(f"Output contract {member_name} is missing its declared path.")
    relative_path = Path(path_text.replace("\\", "/"))
    if relative_path.is_absolute():
        raise ValueError(f"Output contract {member_name} path must be relative.")
    manifest_root = manifest_path.resolve().parent
    member_path = (manifest_root / relative_path).resolve()
    try:
        member_path.relative_to(manifest_root)
    except ValueError as error:
        raise ValueError(f"Output contract {member_name} path escapes the manifest directory.") from error
    return member_path


def output_contract_manifest(mappings_root: Path) -> dict:
    """Read the selected v1 contract identity without loading its tabular members."""
    manifest_path = output_contract_path(mappings_root)
    if not manifest_path.is_file():
        return {
            "_missing": True,
            "_manifest_kind": "output_contract",
            "_path": str(manifest_path),
            "_error": "Selected Common ESTO output contract was not found.",
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must contain a JSON object.")
        if manifest.get("contract_version") != OUTPUT_CONTRACT_VERSION:
            raise ValueError(
                f"Unsupported contract version {manifest.get('contract_version')!r}; "
                f"expected {OUTPUT_CONTRACT_VERSION!r}."
            )
        if not str(manifest.get("run_id", "")).strip():
            raise ValueError("Manifest is missing a non-empty run_id.")
        run_timestamp = pd.Timestamp(str(manifest.get("run_timestamp_utc", "")).strip())
        if run_timestamp.tzinfo is None:
            raise ValueError("run_timestamp_utc must include a timezone.")
        if manifest.get("observed_rows_only") is not True:
            raise ValueError("observed_rows_only must be exactly true.")
        member_paths = [
            _declared_contract_member_path(manifest_path, manifest.get(name), name)
            for name in ["fact", "metadata"]
        ]
    except Exception as error:  # noqa: BLE001 - provenance must report, not crash
        return {
            "_missing": True,
            "_manifest_kind": "output_contract",
            "_path": str(manifest_path),
            "_error": f"{type(error).__name__}: {error}",
        }
    manifest["_manifest_kind"] = "output_contract"
    manifest["_path"] = str(manifest_path)
    manifest["_artifact_paths"] = [str(path) for path in member_paths]
    return manifest


def selected_run_manifest(mappings_root: Path) -> dict:
    """Return the selected contract identity, or the legacy Stage 3 manifest."""
    if output_contract_is_selected():
        contract = output_contract_manifest(mappings_root)
        latest_stage3 = stage3_manifest(mappings_root)
        if not latest_stage3.get("_missing"):
            contract["_latest_stage3_manifest"] = latest_stage3
        return contract
    manifest = stage3_manifest(mappings_root)
    manifest["_manifest_kind"] = "stage3"
    return manifest


def manifest_artifact_paths(manifest: dict, mappings_root: Path) -> list[Path]:
    """Return data members whose mtimes represent the selected run snapshot."""
    if manifest.get("_manifest_kind") == "output_contract":
        return [Path(value) for value in manifest.get("_artifact_paths", [])]
    return [
        mappings_root / "results" / "common_esto" / "common_esto_comparison_data.csv"
    ]


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
    manifest = selected_run_manifest(mappings_root)
    artifact_paths = manifest_artifact_paths(manifest, mappings_root)
    written_values = [
        written
        for written in (artifact_mtime(path) for path in artifact_paths)
        if written is not None
    ]
    written = max(written_values) if written_values else None
    written_label = written.strftime("%Y-%m-%d %H:%M") if written is not None else "an unknown time"
    is_contract = manifest.get("_manifest_kind") == "output_contract"
    run_label = "Common ESTO output contract" if is_contract else "Stage 3 run"
    if manifest.get("_missing"):
        missing_label = (
            "the selected Common ESTO output contract"
            if is_contract
            else "a Stage 3 run manifest"
        )
        error_detail = (
            f" Details: {manifest.get('_error')}"
            if manifest.get("_error")
            else ""
        )
        return (
            f"<strong>Snapshot with unknown provenance.</strong> {page_label} was rendered from "
            f"artifacts written {written_label}, but {missing_label} could not be read at "
            f"<code>{manifest.get('_path', '')}</code>, so the run that produced them cannot be "
            f"identified.{error_detail}",
            "warning",
        )
    run_id = str(manifest.get("run_id", "unknown"))
    latest_stage3 = manifest.get("_latest_stage3_manifest", {})
    latest_run_id = str(latest_stage3.get("run_id", "")).strip()
    latest_status = str(latest_stage3.get("status", "unknown")).strip()
    latest_status_key = latest_status.casefold()
    failed_latest_attempt = any(
        marker in latest_status_key
        for marker in ["fail", "error", "incomplete", "review", "not_published"]
    )
    if is_contract and latest_run_id and (
        latest_run_id != run_id or failed_latest_attempt
    ):
        if failed_latest_attempt:
            explanation = (
                f"the latest Stage 3 attempt <code>{latest_run_id}</code> has status "
                f"<strong>{latest_status}</strong>. The pipeline preserved output contract "
                f"<code>{run_id}</code> as the last successful snapshot"
            )
        else:
            explanation = (
                f"the latest Stage 3 run is <code>{latest_run_id}</code> with status "
                f"<strong>{latest_status}</strong>, while the selected output contract is "
                f"<code>{run_id}</code>"
            )
        return (
            f"<strong>Preserved snapshot, not the latest pipeline attempt.</strong> "
            f"{page_label} was rendered {written_label} from Common ESTO output contract "
            f"<code>{run_id}</code>, but {explanation}. Values identify the selected contract "
            "faithfully; investigate the newer Stage 3 attempt before calling them current.",
            "warning",
        )
    commits, error = pipeline_commits_since(mappings_root, written)
    if error:
        return (
            f"<strong>Snapshot.</strong> {page_label} was rendered {written_label} from {run_label} "
            f"<code>{run_id}</code>. Whether the mapping pipeline has changed since could not be "
            f"checked: {error}",
            "warning",
        )
    if not commits:
        return (
            f"<strong>Snapshot.</strong> {page_label} was rendered {written_label} from {run_label} "
            f"<code>{run_id}</code>, and no mapping-pipeline code commit is newer than those "
            "artifacts. Values reflect the pipeline as it currently stands.",
            "info",
        )
    subjects = "; ".join(f"<code>{commit['commit']}</code> {commit['subject']}" for commit in commits[:3])
    remainder = f" and {len(commits) - 3} more" if len(commits) > 3 else ""
    return (
        f"<strong>Snapshot, and the source artifacts were produced by superseded code.</strong> "
        f"{page_label} was rendered {written_label} from {run_label} <code>{run_id}</code>, which "
        f"predates {len(commits)} mapping-pipeline commit(s): {subjects}{remainder}. The page reports "
        "the artifact faithfully; the artifact needs a rebuild.",
        "warning",
    )


#%%
