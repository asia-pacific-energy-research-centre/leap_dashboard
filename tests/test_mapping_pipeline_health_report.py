from pathlib import Path
import sys

import pandas as pd
import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import render_mapping_pipeline_health_report as report  # noqa: E402


def _artifact(key: str, name: str, frame: pd.DataFrame, *, exists: bool = True) -> report.Artifact:
    return report.Artifact(
        key=key,
        path=Path(name),
        label=key,
        frame=frame,
        exists=exists,
        mtime=pd.Timestamp("2026-07-27 13:38"),
    )


def test_skipped_hierarchy_check_is_reported_as_not_validated() -> None:
    summary = pd.DataFrame([
        {"validation_name": "common_esto_product_hierarchy", "validation_axis": "product",
         "source_system": "ESTO", "status": "skipped", "checks_performed": "0",
         "eligible_parent_count": "0", "mismatch_count": "0", "raw_mismatch_row_count": "0",
         "reason": "No eligible parent/child checks were found."},
        {"validation_name": "common_esto_flow_hierarchy", "validation_axis": "flow",
         "source_system": "LEAP", "status": "passed", "checks_performed": "44",
         "eligible_parent_count": "3", "mismatch_count": "0", "raw_mismatch_row_count": "0",
         "reason": "All eligible parent/child checks matched."},
    ])

    html = report._hierarchy_validation_section(_artifact("v", "s.csv", summary))

    assert "1 not validated" in html
    assert "It is not a pass" in html
    assert "1 passed" in html


def test_anchor_headline_never_sums_across_overlapping_scopes() -> None:
    summary = pd.DataFrame([
        {"validation_axis": "flow", "comparison_scope": "esto_leap", "source_system": "LEAP",
         "eligible": "2564", "passed": "2381", "failed": "183", "skipped": "14040",
         "status": "failed"},
        {"validation_axis": "flow", "comparison_scope": "esto_extended_leap", "source_system": "LEAP",
         "eligible": "2564", "passed": "2381", "failed": "183", "skipped": "14040",
         "status": "failed"},
    ])

    html = report._anchor_section(_artifact("a", "a.csv", summary))

    assert "2 of 2 scope checks failing" in html
    assert "366" not in html  # the two overlapping scopes must never be added together
    assert "ESTO Extended basis" in html
    assert "Ordinary ESTO basis" in html


def test_missing_qa_file_is_unknown_rather_than_clean() -> None:
    artifacts = {
        key: _artifact(key, f"{key}.csv", pd.DataFrame(), exists=False)
        for key in ["structural_summary", "structural_ambiguous", "structural_unresolved",
                    "structural_conflicting", "structural_cyclic", "structural_duplicate"]
    }

    html = report._structural_section(artifacts)

    assert "state unknown" in html
    assert "clean" not in html


def test_empty_qa_file_is_reported_clean() -> None:
    artifacts = {
        key: _artifact(key, f"{key}.csv", pd.DataFrame())
        for key in ["structural_summary", "structural_ambiguous", "structural_unresolved",
                    "structural_conflicting", "structural_cyclic", "structural_duplicate"]
    }

    html = report._structural_section(artifacts)

    assert "clean" in html
    assert "state unknown" not in html


def test_frontier_section_shows_only_violations() -> None:
    frontier = pd.DataFrame([
        {"comparison_scope": "esto_leap", "non_expanding_rollup_id": "gas",
         "rolled_flow_label": "09.06 Gas processing plants", "declared_child_flow_labels": "10.01.02",
         "check_status": "ok", "violation_reason": "", "violating_common_row_ids": ""},
        {"comparison_scope": "esto_leap", "non_expanding_rollup_id": "coal",
         "rolled_flow_label": "09.08 Coal transformation", "declared_child_flow_labels": "10.02.01",
         "check_status": "violation", "violation_reason": "child expands frontier",
         "violating_common_row_ids": "row_1"},
    ])

    html = report._frontier_section(_artifact("f", "f.csv", frontier))

    assert "1 violations" in html
    assert "child expands frontier" in html
    assert "09.06 Gas processing plants" not in html  # passing rows are not listed


def test_material_gaps_are_ranked_by_absolute_value() -> None:
    gaps = pd.DataFrame([
        {"leap_flow": "Small flow", "leap_product": "Coal", "rows": "10", "value_sum": "5.0"},
        {"leap_flow": "Big negative", "leap_product": "Crude oil", "rows": "77",
         "value_sum": "-1144754.0"},
    ])

    html = report._gap_section(_artifact("g", "g.csv", gaps))

    assert html.index("Big negative") < html.index("Small flow")
    assert "materiality queue to triage" in html


def test_code_newer_than_artifacts_is_reported_as_superseded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        report, "pipeline_commits_since",
        lambda cutoff: ([{"commit": "eb3a293", "committed": "2026-07-27 14:14:15 +0900",
                          "subject": "preserve ESTO Extended rollup source identity"}], ""),
    )

    html = report._code_freshness_section({"a": _artifact("a", "a.csv", pd.DataFrame())})

    assert "produced by superseded code" in html
    assert "eb3a293" in html
    assert "panel--critical" in html


def test_no_newer_commit_reports_artifacts_as_current(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "pipeline_commits_since", lambda cutoff: ([], ""))

    html = report._code_freshness_section({"a": _artifact("a", "a.csv", pd.DataFrame())})

    assert "artifacts match current code" in html
    assert "superseded" not in html


@pytest.mark.skipif(not report.MANIFEST_PATH.exists(), reason="mapping artifacts not available")
def test_artifact_mtimes_are_local_time_so_they_compare_with_git_dates() -> None:
    artifacts = report.load_artifacts()
    present = [artifact for artifact in artifacts.values() if artifact.mtime is not None]

    assert present
    for artifact in present:
        expected = pd.Timestamp.fromtimestamp(artifact.path.stat().st_mtime)
        assert artifact.mtime == expected


@pytest.mark.skipif(not report.MANIFEST_PATH.exists(), reason="mapping artifacts not available")
def test_report_renders_against_real_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "OUTPUT_ROOT", tmp_path)

    result = report.render_report()

    page = Path(result["page"]).read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "Mapping pipeline diagnostics" in page
    assert Path(result["body"]).read_text(encoding="utf-8").startswith("<title>")
