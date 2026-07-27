#%%
"""Render a standalone mapping-pipeline health report from canonical artifacts.

This is a fast investigation tool. It reads only the small summary and QA
artifacts written by the ``leap_mappings`` Stage 3 run, so it never loads the
multi-hundred-megabyte comparison data. It is deliberately separate from
``common_esto_dashboard_mapping_diagnostics.py``: that page explains one
economy's rollup arithmetic, this report answers "what does the latest
mapping-pipeline run actually say about itself?".

Statuses are reported honestly:

* ``skipped`` is rendered as "not validated", never as a pass.
* A QA file is only reported clean when the file exists and is empty.
* A missing artifact is reported as missing, not as zero findings.

Outputs
-------
outputs/prototypes/mapping_pipeline_health/mapping_pipeline_health.html
    Standalone document for local viewing.
outputs/prototypes/mapping_pipeline_health/mapping_pipeline_health_body.html
    Same content as a body fragment, for publishing as an artifact page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import json
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.mapping_pipeline_provenance import (  # noqa: E402 - needs sys.path above
    artifact_mtime as _artifact_mtime,
    pipeline_commits_since as _pipeline_commits_since,
)

MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
RESULTS_ROOT = MAPPINGS_ROOT / "results"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "prototypes" / "mapping_pipeline_health"
MANIFEST_PATH = RESULTS_ROOT / "common_esto" / "stage3_run_manifest.json"
TOP_GAP_ROWS = 60


#%%
@dataclass
class Artifact:
    """One canonical pipeline artifact used by this report."""

    key: str
    path: Path
    label: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    exists: bool = False
    mtime: pd.Timestamp | None = None
    error: str = ""

    @property
    def rows(self) -> int:
        return 0 if self.frame is None else len(self.frame)


def _read_artifact(key: str, relative: str, label: str) -> Artifact:
    """Read one small CSV artifact without raising on missing or bad files."""
    path = RESULTS_ROOT / relative
    artifact = Artifact(key=key, path=path, label=label)
    if not path.exists():
        return artifact
    artifact.exists = True
    # Local time, so artifact timestamps compare correctly with local git commit dates.
    artifact.mtime = _artifact_mtime(path)
    try:
        artifact.frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as error:  # noqa: BLE001 - report, never fail the page
        artifact.error = f"{type(error).__name__}: {error}"
    return artifact


ARTIFACT_SPECS: list[tuple[str, str, str]] = [
    ("common_esto_validation", "tree_structure/common_esto_validation_summary.csv",
     "Common ESTO hierarchy validation summary"),
    ("anchor_validation", "tree_structure/source_parent_anchor_validation_summary.csv",
     "Source-parent anchor validation summary"),
    ("rollup_validation", "tree_structure/common_esto_rollup_validation_summary.csv",
     "Rollup boundary reconciliation summary"),
    ("output_status", "common_esto/common_esto_output_status.csv",
     "Stage 3 output status"),
    ("frontier_check", "common_esto/qa_common_esto_non_expanding_frontier_check.csv",
     "Non-expanding rollup frontier check"),
    ("structural_summary", "common_esto/structural_artifacts/structural_compilation_summary.csv",
     "Structural compilation summary"),
    ("structural_ambiguous", "common_esto/structural_artifacts/qa_ambiguous_structural.csv",
     "Ambiguous structural assignments"),
    ("structural_unresolved", "common_esto/structural_artifacts/qa_unresolved_structural.csv",
     "Unresolved structural relationships"),
    ("structural_conflicting", "common_esto/structural_artifacts/qa_conflicting_structural.csv",
     "Conflicting structural assignments"),
    ("structural_cyclic", "common_esto/structural_artifacts/qa_cyclic_structural.csv",
     "Cyclic structural assignments"),
    ("structural_duplicate", "common_esto/structural_artifacts/qa_duplicate_structural.csv",
     "Duplicate structural assignments"),
    ("maintenance_summary", "maintenance/maintenance_summary.csv",
     "Mapping maintenance summary"),
    ("many_to_many", "maintenance/many_to_many_conflicts.csv",
     "Active many-to-many mapping conflicts"),
    ("crosswalk_conflicts", "maintenance/crosswalk_target_conflicts.csv",
     "Crosswalk target conflicts"),
    ("duplicate_mappings", "maintenance/duplicate_mappings.csv",
     "Duplicate workbook mappings"),
    ("actionable_gaps", "mapping_relationships/leap_missing_esto_absent_nonzero_pairs_actionable.csv",
     "Material non-zero mapping gaps"),
]


def load_artifacts() -> dict[str, Artifact]:
    """Load every artifact this report reads."""
    return {key: _read_artifact(key, relative, label) for key, relative, label in ARTIFACT_SPECS}


def load_manifest() -> dict:
    """Read the Stage 3 run manifest, or return an explicit failure marker."""
    if not MANIFEST_PATH.exists():
        return {"_missing": True}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        return {"_missing": True, "_error": f"{type(error).__name__}: {error}"}


#%%
def _number(value: object, decimals: int = 0) -> str:
    """Format a value as a grouped number, or pass text through unchanged."""
    try:
        numeric = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return escape(str(value))
    if pd.isna(numeric):
        return "—"
    return f"{numeric:,.{decimals}f}"


def _to_float(value: object) -> float:
    try:
        numeric = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if pd.isna(numeric) else numeric


def _timestamp(value: pd.Timestamp | None) -> str:
    return "—" if value is None else value.strftime("%Y-%m-%d %H:%M")


def _status_tone(status: str) -> str:
    """Map a pipeline status string to a severity tone."""
    text = str(status).strip().lower()
    if text in {"failed", "fail", "error", "violation", "review"}:
        return "critical"
    if text in {"skipped", "skip", "unknown", "empty", "missing", "incomplete"}:
        return "unknown"
    if text in {"passed", "pass", "ok", "completed"}:
        return "good"
    return "info"


def _chip(text: str, tone: str = "") -> str:
    tone = tone or _status_tone(text)
    return f'<span class="chip chip--{tone}">{escape(str(text))}</span>'


def _table(frame: pd.DataFrame, columns: list[str] | None = None,
           renderers: dict[str, callable] | None = None,
           empty_message: str = "No rows.") -> str:
    """Render a data frame as a scrollable, filterable table."""
    if frame is None or frame.empty:
        return f'<p class="empty">{escape(empty_message)}</p>'
    columns = [column for column in (columns or list(frame.columns)) if column in frame.columns]
    renderers = renderers or {}
    head = "".join(f"<th>{escape(column.replace('_', ' '))}</th>" for column in columns)
    body_rows: list[str] = []
    for _, row in frame.iterrows():
        cells: list[str] = []
        for column in columns:
            render = renderers.get(column)
            cells.append(f"<td>{render(row[column]) if render else escape(str(row[column]))}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table><thead><tr>'
        f"{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"
    )


def _section(title: str, tone: str, headline: str, body: str, *, open_by_default: bool = False,
             source_note: str = "") -> str:
    """Render one collapsible report section with a severity headline."""
    note = f'<p class="source">Source: {escape(source_note)}</p>' if source_note else ""
    return (
        f'<section class="panel panel--{tone}">'
        f'<details{" open" if open_by_default else ""}>'
        f"<summary><span class=\"panel__title\">{escape(title)}</span>"
        f'<span class="panel__headline">{headline}</span></summary>'
        f'<div class="panel__body">{note}{body}</div>'
        "</details></section>"
    )


def _missing_note(artifact: Artifact) -> str:
    if not artifact.exists:
        return (
            f'<p class="empty empty--warn">Artifact not found: '
            f"<code>{escape(str(artifact.path))}</code>. This is unknown, not clean.</p>"
        )
    if artifact.error:
        return f'<p class="empty empty--warn">Could not read artifact: {escape(artifact.error)}</p>'
    return ""


#%%
def _run_header(manifest: dict, artifacts: dict[str, Artifact]) -> tuple[str, str]:
    """Build the run identity block and the freshness table."""
    if manifest.get("_missing"):
        header = (
            '<p class="empty empty--warn">Stage 3 run manifest not found at '
            f"<code>{escape(str(MANIFEST_PATH))}</code>.</p>"
        )
        return header, ""
    run_id = str(manifest.get("run_id", "unknown"))
    run_time = str(manifest.get("run_timestamp_utc", "unknown"))
    status = str(manifest.get("status", "unknown"))
    timings = manifest.get("timings_seconds", {})
    scopes = manifest.get("comparison_scopes", [])
    datasets = manifest.get("datasets", {})
    dataset_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{_chip('present' if info.get('exists') else 'missing')}</td>"
        f"<td class=\"num\">{_number(info.get('size_bytes', 0) / 1_000_000, 1)} MB</td></tr>"
        for name, info in datasets.items()
    )
    timing_rows = "".join(
        f"<tr><td>{escape(name.replace('_', ' '))}</td>"
        f"<td class=\"num\">{_number(seconds / 60, 1)} min</td></tr>"
        for name, seconds in timings.items()
    )
    header = (
        '<div class="run-grid">'
        f'<div class="run-cell"><span class="run-label">Run</span>'
        f'<span class="run-value mono">{escape(run_id)}</span></div>'
        f'<div class="run-cell"><span class="run-label">Stage 3 finished</span>'
        f'<span class="run-value">{escape(run_time)}</span></div>'
        f'<div class="run-cell"><span class="run-label">Stage 3 status</span>'
        f'<span class="run-value">{_chip(status)}</span></div>'
        f'<div class="run-cell"><span class="run-label">Comparison scopes</span>'
        f'<span class="run-value mono">{escape(", ".join(scopes)) or "—"}</span></div>'
        "</div>"
        '<div class="split">'
        f'<div><h3>Source datasets</h3><div class="table-wrap"><table><thead><tr>'
        f"<th>Dataset</th><th>State</th><th>Size</th></tr></thead><tbody>{dataset_rows}"
        "</tbody></table></div></div>"
        f'<div><h3>Stage timings</h3><div class="table-wrap"><table><thead><tr>'
        f"<th>Step</th><th>Duration</th></tr></thead><tbody>{timing_rows}"
        "</tbody></table></div></div>"
        "</div>"
    )

    comparison_path = Path(
        str(manifest.get("validation", {}).get("common_esto_status", [{}])[0]
            .get("input_path", RESULTS_ROOT / "common_esto" / "common_esto_comparison_data.csv"))
    )
    comparison_mtime = _artifact_mtime(comparison_path)
    freshness_rows: list[str] = []
    for artifact in artifacts.values():
        if not artifact.exists:
            state = _chip("missing")
        elif comparison_mtime is not None and artifact.mtime is not None and artifact.mtime < comparison_mtime:
            state = _chip("older than input", "unknown")
        else:
            state = _chip("current", "good")
        freshness_rows.append(
            f"<tr><td>{escape(artifact.label)}</td>"
            f"<td class=\"mono\">{escape(artifact.path.name)}</td>"
            f"<td>{escape(_timestamp(artifact.mtime))}</td>"
            f"<td class=\"num\">{_number(artifact.rows)}</td><td>{state}</td></tr>"
        )
    freshness = (
        f'<p class="source">Compared against the Stage 3 comparison input '
        f"<code>{escape(comparison_path.name)}</code> "
        f"(written {escape(_timestamp(comparison_mtime))}).</p>"
        '<div class="table-wrap"><table><thead><tr><th>Artifact</th><th>File</th>'
        "<th>Written</th><th>Rows</th><th>State</th></tr></thead><tbody>"
        f"{''.join(freshness_rows)}</tbody></table></div>"
    )
    return header, freshness


def _hierarchy_validation_section(artifact: Artifact) -> str:
    """Common ESTO parent/child hierarchy validation, with skipped shown honestly."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body or frame.empty:
        return _section("Common ESTO hierarchy validation", "unknown",
                        _chip("no summary available", "unknown"),
                        body or '<p class="empty empty--warn">Summary file is empty.</p>',
                        open_by_default=True, source_note=artifact.path.name)
    failed = int((frame["status"].str.lower() == "failed").sum())
    skipped = int((frame["status"].str.lower() == "skipped").sum())
    passed = int((frame["status"].str.lower() == "passed").sum())
    tone = "critical" if failed else ("unknown" if skipped else "good")
    headline = " ".join(filter(None, [
        _chip(f"{failed} failed", "critical") if failed else "",
        _chip(f"{skipped} not validated", "unknown") if skipped else "",
        _chip(f"{passed} passed", "good") if passed else "",
    ]))
    caution = ""
    if skipped:
        caution = (
            '<p class="callout">A skipped check produced no evidence. It is not a pass: the '
            "product-axis hierarchy has not been validated in this run.</p>"
        )
    display = frame.copy()
    display["status"] = display["status"].map(lambda value: _chip(value))
    table = _table(
        display,
        ["validation_name", "validation_axis", "source_system", "status", "checks_performed",
         "eligible_parent_count", "mismatch_count", "raw_mismatch_row_count", "reason"],
        renderers={
            "status": lambda value: str(value),
            "checks_performed": _number,
            "eligible_parent_count": _number,
            "mismatch_count": _number,
            "raw_mismatch_row_count": _number,
        },
    )
    return _section("Common ESTO hierarchy validation", tone, headline, caution + table,
                    open_by_default=True, source_note=artifact.path.name)


def _anchor_section(artifact: Artifact) -> str:
    """Source-parent anchor validation, expressed as failure rate over eligible checks."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body or frame.empty:
        return _section("Source-parent anchor validation", "unknown",
                        _chip("no summary available", "unknown"),
                        body or '<p class="empty empty--warn">Summary file is empty.</p>',
                        open_by_default=True, source_note=artifact.path.name)
    display = frame.copy()
    for column in ["eligible", "passed", "failed", "skipped"]:
        display[column] = display[column].map(_to_float)
    display["failure_rate"] = [
        (failed / eligible) if eligible else float("nan")
        for failed, eligible in zip(display["failed"], display["eligible"])
    ]
    failing_rows = int((display["status"].str.lower() == "failed").sum())
    worst_rate = display["failure_rate"].max()
    worst_row = display.loc[display["failure_rate"].idxmax()] if failing_rows else None
    tone = "critical" if failing_rows else "good"
    headline = " ".join(filter(None, [
        _chip(f"{failing_rows} of {len(display)} scope checks failing",
              "critical" if failing_rows else "good"),
        _chip(f"worst {worst_rate * 100:.1f}% — {worst_row['comparison_scope']} "
              f"{worst_row['source_system']}", "critical") if worst_row is not None else "",
    ]))
    note = (
        '<p class="callout">Each row is one comparison scope and source system, and the scopes '
        "overlap: <code>esto_leap</code> and <code>esto_leap_ninth</code> re-check the same source "
        "data under different scope definitions, and <code>esto_extended_*</code> is a separate "
        "basis entirely. These rows are deliberately not summed into one headline figure. A skipped "
        "check is an ineligible parent boundary, not a silent pass.</p>"
    )
    basis = display.copy()
    basis["basis"] = [
        "ESTO Extended basis" if str(scope).startswith("esto_extended") else "Ordinary ESTO basis"
        for scope in basis["comparison_scope"]
    ]
    per_scope = (
        basis.groupby(["basis", "comparison_scope"], dropna=False)[["eligible", "passed", "failed", "skipped"]]
        .sum().reset_index().sort_values(["basis", "comparison_scope"], kind="mergesort")
    )
    per_scope["failure_rate"] = [
        f"{(failed / eligible * 100):.1f}%" if eligible else "—"
        for failed, eligible in zip(per_scope["failed"], per_scope["eligible"])
    ]
    display["failure_rate"] = [
        f"{rate * 100:.1f}%" if rate == rate else "—" for rate in display["failure_rate"]
    ]
    display["status"] = display["status"].map(lambda value: _chip(value))
    table = (
        "<h3>Totals within one comparison scope</h3>"
        + _table(per_scope, ["basis", "comparison_scope", "eligible", "passed", "failed",
                             "failure_rate", "skipped"],
                 renderers={"eligible": _number, "passed": _number, "failed": _number,
                            "skipped": _number})
        + "<h3>Every scope, system, and validation axis</h3>"
        + _table(
            display,
            ["validation_axis", "comparison_scope", "source_system", "status", "eligible", "passed",
             "failed", "failure_rate", "skipped"],
            renderers={
                "status": lambda value: str(value),
                "eligible": _number, "passed": _number, "failed": _number, "skipped": _number,
            },
        )
    )
    return _section("Source-parent anchor validation", tone, headline, note + table,
                    open_by_default=True, source_note=artifact.path.name)


def _rollup_section(artifact: Artifact) -> str:
    """Rollup boundary reconciliation, separating true failures from missing contributors."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body or frame.empty:
        return _section("Rollup boundary reconciliation", "unknown",
                        _chip("no summary available", "unknown"),
                        body or '<p class="empty empty--warn">Summary file is empty.</p>',
                        source_note=artifact.path.name)
    display = frame.copy()
    for column in ["checks", "passed", "failed", "incomplete_contributors",
                   "no_contributors_available", "total_abs_error", "max_abs_error"]:
        if column in display.columns:
            display[column] = display[column].map(_to_float)
    total_failed = int(display["failed"].sum())
    total_incomplete = int(display["incomplete_contributors"].sum())
    total_absent = int(display["no_contributors_available"].sum())
    display = display.sort_values(["failed", "max_abs_error"], ascending=False, kind="mergesort")
    tone = "critical" if total_failed else ("unknown" if total_incomplete or total_absent else "good")
    headline = " ".join([
        _chip(f"{total_failed:,} failed", "critical" if total_failed else "good"),
        _chip(f"{total_incomplete:,} incomplete contributors", "unknown"),
        _chip(f"{total_absent:,} no contributors", "unknown"),
    ])
    note = (
        '<p class="callout">"Incomplete contributors" and "no contributors available" mean the check '
        "could not be evaluated. They are not reconciliation failures, and they are not passes either.</p>"
    )
    table = _table(
        display,
        ["rollup_label", "rollup_mode", "source_system", "checks", "passed", "failed",
         "incomplete_contributors", "no_contributors_available", "max_abs_error"],
        renderers={
            "checks": _number, "passed": _number, "failed": _number,
            "incomplete_contributors": _number, "no_contributors_available": _number,
            "max_abs_error": lambda value: _number(value, 2),
        },
    )
    return _section("Rollup boundary reconciliation", tone, headline, note + table,
                    source_note=artifact.path.name)


def _frontier_section(artifact: Artifact) -> str:
    """Only the non-expanding frontier violations, not every successful check."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body:
        return _section("Non-expanding rollup frontier", "unknown",
                        _chip("artifact missing", "unknown"), body,
                        source_note=artifact.path.name)
    violations = frame[frame["check_status"].str.lower() != "ok"] if "check_status" in frame else frame
    checked = len(frame)
    tone = "critical" if len(violations) else "good"
    headline = " ".join([
        _chip(f"{len(violations):,} violations", "critical" if len(violations) else "good"),
        _chip(f"{checked:,} boundaries checked", "info"),
    ])
    table = _table(
        violations,
        ["comparison_scope", "rolled_flow_label", "declared_child_flow_labels", "check_status",
         "violation_reason", "violating_common_row_ids"],
        empty_message=f"All {checked:,} declared non-expanding frontiers passed in this run.",
    )
    return _section("Non-expanding rollup frontier", tone, headline, table,
                    source_note=artifact.path.name)


def _structural_section(artifacts: dict[str, Artifact]) -> str:
    """Structural compilation health, clean only where a file proves it."""
    checks = [
        ("structural_ambiguous", "Ambiguous assignments",
         "One source pair could resolve to more than one Common ESTO row."),
        ("structural_unresolved", "Unresolved relationships",
         "A relationship reached no Common ESTO row."),
        ("structural_conflicting", "Conflicting assignments", "Contradictory structural claims."),
        ("structural_cyclic", "Cyclic assignments", "A structural cycle was detected."),
        ("structural_duplicate", "Duplicate assignments", "The same assignment was compiled twice."),
    ]
    cards: list[str] = []
    worst = "good"
    for key, title, description in checks:
        artifact = artifacts[key]
        if not artifact.exists or artifact.error:
            state, tone = "unknown", "unknown"
        elif artifact.rows:
            state, tone = f"{artifact.rows:,} rows", "critical"
        else:
            state, tone = "clean", "good"
        if tone == "critical":
            worst = "critical"
        elif tone == "unknown" and worst != "critical":
            worst = "unknown"
        cards.append(
            f'<div class="card card--{tone}"><span class="card__value">{escape(state)}</span>'
            f'<span class="card__title">{escape(title)}</span>'
            f'<span class="card__note">{escape(description)}</span>'
            f'<span class="card__file mono">{escape(artifact.path.name)}</span></div>'
        )
    version_note = ""
    summary = artifacts["structural_summary"]
    if summary.exists and not summary.frame.empty and "structural_mapping_version" in summary.frame:
        version = str(summary.frame["structural_mapping_version"].iloc[0])
        version_note = (
            f'<p class="source">Structural mapping version <code>{escape(version)}</code>: '
            + ", ".join(
                f"{escape(str(row['artifact']))} {_number(row['row_count'])}"
                for _, row in summary.frame.iterrows()
            )
            + ".</p>"
        )
    headline = _chip(
        {"critical": "issues present", "unknown": "state unknown", "good": "clean"}[worst], worst
    )
    detail = ""
    ambiguous = artifacts["structural_ambiguous"]
    if ambiguous.rows:
        detail += "<h3>Ambiguous assignments</h3>" + _table(
            ambiguous.frame, ["source_system", "issue_type", "input_pair", "related_pairs",
                              "rollup_context", "comparison_scope"],
        )
    unresolved = artifacts["structural_unresolved"]
    if unresolved.rows:
        detail += "<h3>Unresolved relationships</h3>" + _table(
            unresolved.frame, ["source_system", "issue_type", "evidence_type", "effective_source_flow",
                               "effective_source_product", "component_esto_flow", "component_esto_product"],
        )
    return _section("Structural compilation health", worst, headline,
                    version_note + f'<div class="cards">{"".join(cards)}</div>' + detail,
                    open_by_default=True,
                    source_note="results/common_esto/structural_artifacts/")


def _workbook_section(artifacts: dict[str, Artifact]) -> str:
    """Mapping-workbook integrity. Global, and independent of the comparison basis."""
    maintenance = artifacts["maintenance_summary"]
    review_table = ""
    review_rows = 0
    if maintenance.exists and not maintenance.frame.empty and "status" in maintenance.frame:
        review = maintenance.frame[maintenance.frame["status"].str.lower() == "review"].copy()
        review["row_count"] = review["row_count"].map(_to_float)
        review = review.sort_values("row_count", ascending=False, kind="mergesort")
        review_rows = len(review)
        review_table = "<h3>Maintenance outputs awaiting review</h3>" + _table(
            review, ["file_name", "output_area", "row_count"], renderers={"row_count": _number},
        )
    many_to_many = artifacts["many_to_many"]
    conflict_table = "<h3>Active many-to-many mapping conflicts</h3>" + (
        _missing_note(many_to_many) or _table(
            many_to_many.frame,
            ["sheet", "leap_sector_name_full_path", "raw_leap_fuel_name", "ninth_sector", "ninth_fuel",
             "n_targets_for_source", "n_sources_for_target", "cardinality"],
            empty_message="No active many-to-many conflicts in this workbook.",
        )
    )
    crosswalk = artifacts["crosswalk_conflicts"]
    crosswalk_block = "<h3>Crosswalk target conflicts</h3>"
    if crosswalk.exists and crosswalk.rows and "conflict_classification" in crosswalk.frame:
        classes = (
            crosswalk.frame.groupby("conflict_classification").size()
            .reset_index(name="rows").sort_values("rows", ascending=False, kind="mergesort")
        )
        crosswalk_block += (
            '<p class="callout">Classified first, not presented as raw errors. Review the '
            "classification before treating any row as a defect.</p>"
            + _table(classes, ["conflict_classification", "rows"], renderers={"rows": _number})
            + _table(crosswalk.frame, ["leap_sector_name_full_path", "raw_leap_fuel_name",
                                       "ninth_sector", "ninth_fuel", "active_esto_targets",
                                       "conflict_reason", "conflict_classification"])
        )
    else:
        crosswalk_block += _missing_note(crosswalk) or '<p class="empty">No crosswalk target conflicts.</p>'
    duplicates = artifacts["duplicate_mappings"]
    duplicate_block = "<h3>Duplicate workbook mappings</h3>"
    if duplicates.exists and duplicates.rows:
        grouped = (
            duplicates.frame.groupby("sheet_name").size()
            .reset_index(name="duplicate_rows").sort_values("duplicate_rows", ascending=False,
                                                            kind="mergesort")
        )
        duplicate_block += (
            '<p class="callout">Duplicate rows are not automatically defects: an intentional '
            "repeated route and an accidental copy look the same here. Classify before acting.</p>"
            + _table(grouped, ["sheet_name", "duplicate_rows"], renderers={"duplicate_rows": _number})
        )
    else:
        duplicate_block += _missing_note(duplicates) or '<p class="empty">No duplicate mappings.</p>'
    total_flagged = many_to_many.rows + crosswalk.rows + duplicates.rows
    tone = "critical" if total_flagged else "good"
    headline = " ".join([
        _chip(f"{many_to_many.rows} many-to-many", "critical" if many_to_many.rows else "good"),
        _chip(f"{crosswalk.rows} crosswalk conflicts", "critical" if crosswalk.rows else "good"),
        _chip(f"{duplicates.rows} duplicate rows", "unknown" if duplicates.rows else "good"),
        _chip(f"{review_rows} review outputs", "info"),
    ])
    note = (
        '<p class="callout">These are mapping-workbook integrity checks. They are global: they do not '
        "change when an ESTO Extended comparison basis is selected.</p>"
    )
    return _section("Mapping workbook integrity", tone, headline,
                    note + conflict_table + crosswalk_block + duplicate_block + review_table,
                    source_note="results/maintenance/")


def _gap_section(artifact: Artifact) -> str:
    """Material non-zero mapping gaps, ranked by absolute value rather than listed flat."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body or frame.empty:
        return _section("Material non-zero mapping gaps", "unknown",
                        _chip("artifact missing", "unknown"),
                        body or '<p class="empty">No actionable gaps recorded.</p>',
                        source_note=artifact.path.name)
    display = frame.copy()
    display["value_sum"] = display["value_sum"].map(_to_float)
    display["rows"] = display["rows"].map(_to_float)
    display["abs_value"] = display["value_sum"].abs()
    total_abs = display["abs_value"].sum()
    display = display.sort_values("abs_value", ascending=False, kind="mergesort")
    display["share"] = [
        f"{(value / total_abs * 100):.1f}%" if total_abs else "—" for value in display["abs_value"]
    ]
    shown = display.head(TOP_GAP_ROWS)
    headline = " ".join([
        _chip(f"{len(display):,} LEAP pairs", "critical"),
        _chip(f"{_number(total_abs)} absolute total", "info"),
    ])
    note = (
        '<p class="callout">Ranked by absolute magnitude, not listed alphabetically: the top rows are '
        f"where an unmapped LEAP pair moves the most energy. Showing the largest {TOP_GAP_ROWS} of "
        f"{len(display):,}. Rank alone does not make a row a defect &mdash; LEAP aggregate branches "
        "such as <code>Total Transformation</code> and <code>Total Final Energy Demand</code> are "
        "expected to have no direct ESTO pair, and mapping them would double-count their children. "
        "Read this list as a materiality queue to triage, not a list of missing maps.</p>"
    )
    table = _table(
        shown, ["leap_flow", "leap_product", "rows", "value_sum", "share"],
        renderers={"rows": _number, "value_sum": lambda value: _number(value, 1)},
    )
    return _section("Material non-zero mapping gaps", "critical", headline, note + table,
                    source_note=artifact.path.name)


def pipeline_commits_since(cutoff: pd.Timestamp | None) -> tuple[list[dict[str, str]], str]:
    """List ``leap_mappings`` pipeline-code commits made after the artifacts were written.

    An artifact written before a pipeline-code commit was produced by superseded
    code. That is the single cheapest way to catch a stale rebuild, and it is
    what a value-level check cannot tell you on its own.
    """
    return _pipeline_commits_since(MAPPINGS_ROOT, cutoff)


def _code_freshness_section(artifacts: dict[str, Artifact]) -> str:
    """Warn when pipeline code changed after the artifacts on disk were written."""
    written = [artifact.mtime for artifact in artifacts.values() if artifact.mtime is not None]
    newest = max(written) if written else None
    commits, error = pipeline_commits_since(newest)
    if error:
        return _section("Pipeline code versus artifacts", "unknown", _chip("unknown", "unknown"),
                        f'<p class="empty empty--warn">{escape(error)}</p>',
                        source_note=str(MAPPINGS_ROOT / "codebase"))
    if not commits:
        return _section(
            "Pipeline code versus artifacts", "good", _chip("artifacts match current code", "good"),
            f'<p class="empty">No <code>codebase/</code> commit in <code>leap_mappings</code> is newer '
            f"than the newest artifact ({escape(_timestamp(newest))}).</p>",
            source_note=str(MAPPINGS_ROOT / "codebase"),
        )
    rows = "".join(
        f"<tr><td class=\"mono\">{escape(commit['commit'])}</td>"
        f"<td>{escape(commit['committed'])}</td><td>{escape(commit['subject'])}</td></tr>"
        for commit in commits
    )
    body = (
        f'<p class="callout"><strong>These artifacts were produced by superseded code.</strong> '
        f"The newest artifact was written {escape(_timestamp(newest))}, but "
        f"{len(commits)} pipeline-code commit(s) landed after that. Every number in this report, and "
        "in the dashboard pages built from these files, reflects the older code. Re-run the mapping "
        "pipeline before treating any value here as current.</p>"
        '<div class="table-wrap"><table><thead><tr><th>Commit</th><th>Committed</th>'
        f"<th>Subject</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )
    return _section("Pipeline code versus artifacts", "critical",
                    _chip(f"{len(commits)} commit(s) newer than the artifacts", "critical"),
                    body, open_by_default=True, source_note=str(MAPPINGS_ROOT / "codebase"))


def _output_status_section(artifact: Artifact) -> str:
    """Stage 3 artifact write status."""
    body = _missing_note(artifact)
    frame = artifact.frame
    if body or frame.empty:
        return _section("Stage 3 output status", "unknown", _chip("unknown", "unknown"),
                        body or '<p class="empty">No output status rows.</p>',
                        source_note=artifact.path.name)
    display = frame.copy()
    failed = int((display["status"].str.lower().isin({"failed", "error"})).sum())
    skipped = int((display["status"].str.lower() == "skipped").sum())
    display["status"] = display["status"].map(lambda value: _chip(value))
    tone = "critical" if failed else ("unknown" if skipped else "good")
    headline = " ".join(filter(None, [
        _chip(f"{failed} failed", "critical") if failed else "",
        _chip(f"{skipped} skipped", "unknown") if skipped else "",
        _chip(f"{len(display)} recorded outputs", "info"),
    ]))
    table = _table(
        display, ["record_type", "artifact_name", "validation_name", "comparison_scope",
                  "source_system", "status", "reason"],
        renderers={"status": lambda value: str(value)},
    )
    return _section("Stage 3 output status", tone, headline, table, source_note=artifact.path.name)


#%%
STYLES = """
:root {
  color-scheme: light dark;
  --ground: #f6f5f2;
  --surface: #ffffff;
  --surface-sunken: #edece8;
  --ink: #1b1d22;
  --ink-soft: #575c66;
  --ink-faint: #838a95;
  --rule: #d9d8d2;
  --accent: #2f5d62;
  --good: #2c6e49;
  --good-bg: #e3efe6;
  --critical: #9b2c2c;
  --critical-bg: #f6e4e2;
  --unknown: #8a5a12;
  --unknown-bg: #f6ecd9;
  --info: #3c5a80;
  --info-bg: #e6ebf3;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground: #16181c;
    --surface: #1e2127;
    --surface-sunken: #24272e;
    --ink: #eceef1;
    --ink-soft: #b0b6c0;
    --ink-faint: #838b97;
    --rule: #333842;
    --accent: #6fb3ac;
    --good: #7fc79b;
    --good-bg: #1d3227;
    --critical: #e79a94;
    --critical-bg: #3a2020;
    --unknown: #dcb26a;
    --unknown-bg: #362a15;
    --info: #9db6d8;
    --info-bg: #1f2733;
  }
}
:root[data-theme="dark"] {
  --ground: #16181c; --surface: #1e2127; --surface-sunken: #24272e;
  --ink: #eceef1; --ink-soft: #b0b6c0; --ink-faint: #838b97; --rule: #333842;
  --accent: #6fb3ac; --good: #7fc79b; --good-bg: #1d3227; --critical: #e79a94;
  --critical-bg: #3a2020; --unknown: #dcb26a; --unknown-bg: #362a15;
  --info: #9db6d8; --info-bg: #1f2733;
}
:root[data-theme="light"] {
  --ground: #f6f5f2; --surface: #ffffff; --surface-sunken: #edece8;
  --ink: #1b1d22; --ink-soft: #575c66; --ink-faint: #838a95; --rule: #d9d8d2;
  --accent: #2f5d62; --good: #2c6e49; --good-bg: #e3efe6; --critical: #9b2c2c;
  --critical-bg: #f6e4e2; --unknown: #8a5a12; --unknown-bg: #f6ecd9;
  --info: #3c5a80; --info-bg: #e6ebf3;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.mono, code, .num, td.num, table { font-variant-numeric: tabular-nums; }
.mono, code {
  font-family: ui-monospace, "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace;
  font-size: 0.9em;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 40px 24px 80px; display: flex;
        flex-direction: column; gap: 28px; }
header.masthead { border-bottom: 2px solid var(--accent); padding-bottom: 20px;
                  display: flex; flex-direction: column; gap: 6px; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.14em; font-size: 11px;
           color: var(--accent); font-weight: 600; }
h1 { margin: 0; font-size: clamp(26px, 3.4vw, 38px); line-height: 1.15; text-wrap: balance;
     letter-spacing: -0.015em; }
.lede { margin: 6px 0 0; color: var(--ink-soft); max-width: 68ch; }
h2 { font-size: 15px; margin: 0; letter-spacing: -0.005em; }
h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
     color: var(--ink-soft); margin: 22px 0 8px; }
.run-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1px;
            background: var(--rule); border: 1px solid var(--rule); border-radius: 3px;
            overflow: hidden; }
.run-cell { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column;
            gap: 4px; min-width: 0; }
.run-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
             color: var(--ink-faint); }
.run-value { font-size: 14px; overflow-wrap: anywhere; }
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }
.panel { background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
         border-left: 4px solid var(--rule); }
.panel--critical { border-left-color: var(--critical); }
.panel--unknown { border-left-color: var(--unknown); }
.panel--good { border-left-color: var(--good); }
.panel--info { border-left-color: var(--info); }
summary { list-style: none; cursor: pointer; padding: 14px 18px; display: flex; gap: 16px;
          align-items: baseline; flex-wrap: wrap; justify-content: space-between; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.panel__title { font-weight: 650; font-size: 15px; }
.panel__title::before { content: "▸ "; color: var(--ink-faint); }
details[open] .panel__title::before { content: "▾ "; }
.panel__headline { display: flex; gap: 6px; flex-wrap: wrap; }
.panel__body { padding: 0 18px 20px; border-top: 1px solid var(--rule); }
.panel__body > :first-child { margin-top: 14px; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 11.5px;
        font-weight: 600; letter-spacing: 0.02em; white-space: nowrap; }
.chip--good { background: var(--good-bg); color: var(--good); }
.chip--critical { background: var(--critical-bg); color: var(--critical); }
.chip--unknown { background: var(--unknown-bg); color: var(--unknown); }
.chip--info { background: var(--info-bg); color: var(--info); }
.table-wrap { overflow-x: auto; border: 1px solid var(--rule); border-radius: 3px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; background: var(--surface-sunken); color: var(--ink-soft);
     font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600;
     padding: 8px 12px; position: sticky; top: 0; white-space: nowrap; }
td { padding: 7px 12px; border-top: 1px solid var(--rule); vertical-align: top;
     max-width: 460px; overflow-wrap: anywhere; }
tbody tr:hover td { background: var(--surface-sunken); }
td.num, th.num { text-align: right; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px;
         margin: 14px 0; }
.card { border: 1px solid var(--rule); border-top: 3px solid var(--rule); border-radius: 3px;
        padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; }
.card--good { border-top-color: var(--good); }
.card--critical { border-top-color: var(--critical); }
.card--unknown { border-top-color: var(--unknown); }
.card__value { font-size: 20px; font-weight: 650; }
.card--good .card__value { color: var(--good); }
.card--critical .card__value { color: var(--critical); }
.card--unknown .card__value { color: var(--unknown); }
.card__title { font-size: 13px; font-weight: 600; }
.card__note { font-size: 12px; color: var(--ink-soft); }
.card__file { font-size: 11px; color: var(--ink-faint); margin-top: 2px; }
.callout { background: var(--surface-sunken); border-left: 2px solid var(--accent);
           padding: 10px 14px; margin: 12px 0; font-size: 13.5px; color: var(--ink-soft); }
.source { font-size: 12px; color: var(--ink-faint); margin: 12px 0 6px; }
.empty { font-size: 13.5px; color: var(--ink-soft); font-style: italic; }
.empty--warn { color: var(--unknown); font-style: normal; }
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
button { font: inherit; font-size: 13px; padding: 6px 12px; border: 1px solid var(--rule);
         background: var(--surface); color: var(--ink); border-radius: 3px; cursor: pointer; }
button:hover { border-color: var(--accent); color: var(--accent); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
footer { color: var(--ink-faint); font-size: 12.5px; border-top: 1px solid var(--rule);
         padding-top: 16px; }
@media (max-width: 640px) { .wrap { padding: 24px 14px 60px; } }
"""

SCRIPT = """
document.querySelectorAll('[data-toggle-all]').forEach(function (button) {
  button.addEventListener('click', function () {
    var open = button.dataset.toggleAll === 'open';
    document.querySelectorAll('.panel details').forEach(function (item) { item.open = open; });
    button.dataset.toggleAll = open ? 'close' : 'open';
    button.textContent = open ? 'Collapse all sections' : 'Expand all sections';
  });
});
"""


def _body_html(manifest: dict, artifacts: dict[str, Artifact]) -> str:
    """Assemble the report body."""
    header, freshness = _run_header(manifest, artifacts)
    generated = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    sections = [
        _code_freshness_section(artifacts),
        _hierarchy_validation_section(artifacts["common_esto_validation"]),
        _anchor_section(artifacts["anchor_validation"]),
        _structural_section(artifacts),
        _rollup_section(artifacts["rollup_validation"]),
        _frontier_section(artifacts["frontier_check"]),
        _gap_section(artifacts["actionable_gaps"]),
        _workbook_section(artifacts),
        _output_status_section(artifacts["output_status"]),
        _section("Artifact freshness", "info",
                 _chip(f"{sum(1 for a in artifacts.values() if a.exists)} of "
                       f"{len(artifacts)} artifacts present", "info"),
                 freshness or '<p class="empty">No manifest to compare against.</p>',
                 source_note=str(RESULTS_ROOT)),
    ]
    return (
        '<div class="wrap">'
        '<header class="masthead">'
        '<span class="eyebrow">leap_mappings &middot; Stage 3 run health</span>'
        "<h1>Mapping pipeline diagnostics</h1>"
        '<p class="lede">What the latest Common ESTO run says about itself, read straight from its '
        "canonical summary artifacts. Checks that were skipped are reported as not validated, never "
        "as passes; a QA file is only called clean when the file exists and is empty.</p>"
        "</header>"
        f"{header}"
        '<div class="toolbar"><button type="button" data-toggle-all="open">Expand all sections</button>'
        f'<span class="source">Report generated {escape(generated)}</span></div>'
        + "".join(sections)
        + "<footer>Read-only. This report never writes to the mapping workbook and never "
        "recalculates pipeline values &mdash; every number here is copied from a "
        "<code>leap_mappings/results</code> artifact.</footer>"
        "</div>"
    )


def render_report() -> dict[str, str]:
    """Write the standalone health report and its artifact-body twin."""
    manifest = load_manifest()
    artifacts = load_artifacts()
    body = _body_html(manifest, artifacts)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    fragment = f"<title>Mapping pipeline diagnostics</title>\n<style>{STYLES}</style>\n{body}\n<script>{SCRIPT}</script>"
    document = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Mapping pipeline diagnostics</title>\n"
        f"<style>{STYLES}</style>\n</head>\n<body>\n{body}\n<script>{SCRIPT}</script>\n</body>\n</html>\n"
    )
    page_path = OUTPUT_ROOT / "mapping_pipeline_health.html"
    body_path = OUTPUT_ROOT / "mapping_pipeline_health_body.html"
    page_path.write_text(document, encoding="utf-8")
    body_path.write_text(fragment, encoding="utf-8")
    print(f"Artifacts read: {sum(1 for a in artifacts.values() if a.exists)}/{len(artifacts)}")
    for artifact in artifacts.values():
        if not artifact.exists:
            print(f"  missing: {artifact.path}")
        elif artifact.error:
            print(f"  unreadable: {artifact.path} -> {artifact.error}")
    print(page_path)
    return {"page": str(page_path), "body": str(body_path)}


#%%
if __name__ == "__main__":
    render_report()

#%%
