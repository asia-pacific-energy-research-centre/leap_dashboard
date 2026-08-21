import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.dashboard_page_fragment import (
    build_body_fragment,
    provenance_banner_html,
    write_body_fragment,
)
from codebase import mapping_pipeline_provenance as provenance


DOCUMENT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mapping diagnostics</title>
<style>body { color: #111; }</style>
</head>
<body>
<div class="shell"><header><a href="index.html">&larr; Dashboard overview</a><h1>Mapping diagnostics</h1></header>
<p>Rollup value <span id="value">-34,193.16</span></p>
<a href="https://example.org/spec">External spec</a>
<a href="#rollups">Jump to rollups</a>
<script>console.log('kept');</script>
</div>
</body>
</html>
"""


def _write_output_contract(root: Path, run_id: str = "contract_run") -> Path:
    """Write the identity fields needed by lightweight provenance checks."""
    fact_path = root / "fact.csv"
    metadata_path = root / "metadata.csv"
    fact_path.write_text("value\n1\n", encoding="utf-8")
    metadata_path.write_text("label\nrow\n", encoding="utf-8")
    manifest = {
        "contract_version": provenance.OUTPUT_CONTRACT_VERSION,
        "run_id": run_id,
        "run_timestamp_utc": "2026-07-28T00:00:00+00:00",
        "observed_rows_only": True,
        "fact": {"path": fact_path.name},
        "metadata": {"path": metadata_path.name},
    }
    manifest_path = root / "common_esto_output_contract.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_fragment_drops_the_document_wrapper_but_keeps_styles_and_scripts() -> None:
    fragment = build_body_fragment(DOCUMENT)

    lowered = fragment.lower()
    for tag in ["<!doctype", "<html", "<body", "</head>"]:
        assert tag not in lowered
    assert "body { color: #111; }" in fragment
    assert "<script>console.log('kept');</script>" in fragment
    assert "-34,193.16" in fragment
    assert "<title>Mapping diagnostics</title>" in fragment


def test_relative_page_links_are_neutralized_but_external_and_anchor_links_survive() -> None:
    fragment = build_body_fragment(DOCUMENT)

    assert 'href="index.html"' not in fragment
    assert "Dashboard overview" in fragment
    assert 'href="https://example.org/spec"' in fragment
    assert 'href="#rollups"' in fragment


def test_local_link_neutralization_can_be_disabled() -> None:
    fragment = build_body_fragment(DOCUMENT, neutralize_local_links=False)

    assert 'href="index.html"' in fragment


def test_banner_is_inserted_ahead_of_the_content() -> None:
    fragment = build_body_fragment(DOCUMENT, banner_html="<div>stale</div>", title="Snapshot")

    assert fragment.index("<div>stale</div>") < fragment.index("Mapping diagnostics</h1>")
    assert "<title>Snapshot</title>" in fragment


def test_write_body_fragment_writes_beside_the_page(tmp_path: Path) -> None:
    page = tmp_path / "mapping_diagnostics.html"
    page.write_text(DOCUMENT, encoding="utf-8")

    fragment_path = write_body_fragment(page)

    assert fragment_path == tmp_path / "mapping_diagnostics_body.html"
    assert "-34,193.16" in fragment_path.read_text(encoding="utf-8")


def test_mappings_root_defaults_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(provenance.MAPPINGS_ROOT_ENV_VAR, raising=False)
    default = Path("C:/somewhere/leap_mappings")

    assert provenance.resolve_mappings_root(default) == default


def test_mappings_root_override_points_at_a_worktree(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "results").mkdir()
    monkeypatch.setenv(provenance.MAPPINGS_ROOT_ENV_VAR, str(tmp_path))

    assert provenance.resolve_mappings_root(Path("C:/somewhere/leap_mappings")) == tmp_path


def test_mappings_root_override_without_results_fails_loudly(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(provenance.MAPPINGS_ROOT_ENV_VAR, str(tmp_path))

    with pytest.raises(ValueError, match="no results/ directory"):
        provenance.resolve_mappings_root(Path("C:/somewhere/leap_mappings"))


def test_selected_output_contract_supplies_provenance_run_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_output_contract(tmp_path, run_id="contract_123")
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "1")
    monkeypatch.setenv(provenance.OUTPUT_CONTRACT_PATH_ENV_VAR, str(manifest_path))
    monkeypatch.setattr(provenance, "pipeline_commits_since", lambda root, cutoff: ([], ""))

    manifest = provenance.selected_run_manifest(tmp_path)
    message, tone = provenance.provenance_message(tmp_path)

    assert manifest["_manifest_kind"] == "output_contract"
    assert manifest["run_id"] == "contract_123"
    assert tone == "info"
    assert "Common ESTO output contract" in message
    assert "contract_123" in message


def test_selected_run_metadata_is_compact_and_explicit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = _write_output_contract(tmp_path, run_id="contract_456")
    monkeypatch.setenv("COMMON_ESTO_USE_OUTPUT_CONTRACT", "1")
    monkeypatch.setenv(
        "COMMON_ESTO_OUTPUT_CONTRACT_PATH",
        str(manifest_path),
    )

    metadata = provenance.selected_run_metadata(tmp_path)

    assert metadata["mapping_run_id"] == "contract_456"
    assert metadata["mapping_manifest_kind"] == "output_contract"
    assert metadata["mapping_manifest_path"] == str(manifest_path)


def test_selected_run_metadata_uses_matching_stage3_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = _write_output_contract(tmp_path, run_id="contract_789")
    stage3_path = (
        tmp_path / "results" / "common_esto" / "stage3_run_manifest.json"
    )
    stage3_path.parent.mkdir(parents=True, exist_ok=True)
    stage3_path.write_text(
        json.dumps({"run_id": "contract_789", "status": "completed"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("COMMON_ESTO_USE_OUTPUT_CONTRACT", "1")
    monkeypatch.setenv(
        "COMMON_ESTO_OUTPUT_CONTRACT_PATH",
        str(manifest_path),
    )

    metadata = provenance.selected_run_metadata(tmp_path)

    assert metadata["mapping_run_status"] == "completed"


def test_legacy_stage3_identity_remains_available_by_explicit_opt_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage3_path = tmp_path / "results" / "common_esto" / "stage3_run_manifest.json"
    stage3_path.parent.mkdir(parents=True)
    stage3_path.write_text(json.dumps({"run_id": "legacy_run"}), encoding="utf-8")
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "0")
    monkeypatch.delenv(provenance.OUTPUT_CONTRACT_PATH_ENV_VAR, raising=False)

    manifest = provenance.selected_run_manifest(tmp_path)

    assert manifest["_manifest_kind"] == "stage3"
    assert manifest["run_id"] == "legacy_run"


def test_invalid_selected_contract_does_not_fall_back_to_stage3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage3_path = tmp_path / "results" / "common_esto" / "stage3_run_manifest.json"
    stage3_path.parent.mkdir(parents=True)
    stage3_path.write_text(json.dumps({"run_id": "legacy_run"}), encoding="utf-8")
    selected_path = tmp_path / "missing_contract.json"
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "true")
    monkeypatch.setenv(provenance.OUTPUT_CONTRACT_PATH_ENV_VAR, str(selected_path))

    manifest = provenance.selected_run_manifest(tmp_path)
    message, tone = provenance.provenance_message(tmp_path)

    assert manifest["_missing"] is True
    assert manifest["_manifest_kind"] == "output_contract"
    assert "legacy_run" not in message
    assert "selected Common ESTO output contract" in message
    assert tone == "warning"


def test_failed_latest_stage3_attempt_marks_selected_contract_as_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_output_contract(tmp_path, run_id="last_successful_contract")
    stage3_path = tmp_path / "results" / "common_esto" / "stage3_run_manifest.json"
    stage3_path.parent.mkdir(parents=True)
    stage3_path.write_text(
        json.dumps({"run_id": "failed_attempt", "status": "failed"}),
        encoding="utf-8",
    )
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "1")
    monkeypatch.setenv(provenance.OUTPUT_CONTRACT_PATH_ENV_VAR, str(manifest_path))

    message, tone = provenance.provenance_message(tmp_path)

    assert tone == "warning"
    assert "Preserved snapshot, not the latest pipeline attempt" in message
    assert "last_successful_contract" in message
    assert "failed_attempt" in message
    assert "last successful snapshot" in message


def test_superseded_artifacts_produce_a_warning_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "0")
    monkeypatch.setattr(provenance, "stage3_manifest", lambda root: {"run_id": "run_abc"})
    monkeypatch.setattr(provenance, "artifact_mtime", lambda path: pd.Timestamp("2026-07-27 13:00"))
    monkeypatch.setattr(
        provenance, "pipeline_commits_since",
        lambda root, cutoff: ([{"commit": "eb3a293", "committed": "2026-07-27 14:14:15 +0900",
                                "subject": "preserve ESTO Extended rollup source identity"}], ""),
    )

    message, tone = provenance.provenance_message(Path("."))

    assert tone == "warning"
    assert "superseded code" in message
    assert "eb3a293" in message
    assert "run_abc" in message
    assert "background:#f6e4e2" in provenance_banner_html(message, tone=tone)


def test_current_artifacts_produce_an_informational_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "0")
    monkeypatch.setattr(provenance, "stage3_manifest", lambda root: {"run_id": "run_abc"})
    monkeypatch.setattr(provenance, "artifact_mtime", lambda path: pd.Timestamp("2026-07-27 13:00"))
    monkeypatch.setattr(provenance, "pipeline_commits_since", lambda root, cutoff: ([], ""))

    message, tone = provenance.provenance_message(Path("."))

    assert tone == "info"
    assert "superseded" not in message
    assert "no mapping-pipeline code commit is newer" in message


def test_unanswerable_provenance_is_a_warning_not_a_clean_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(provenance.USE_OUTPUT_CONTRACT_ENV_VAR, "0")
    monkeypatch.setattr(provenance, "stage3_manifest", lambda root: {"run_id": "run_abc"})
    monkeypatch.setattr(provenance, "artifact_mtime", lambda path: pd.Timestamp("2026-07-27 13:00"))
    monkeypatch.setattr(provenance, "pipeline_commits_since", lambda root, cutoff: ([], "git log failed"))

    message, tone = provenance.provenance_message(Path("."))

    assert tone == "warning"
    assert "could not be checked" in message


def test_missing_manifest_is_reported_as_unknown_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provenance, "stage3_manifest",
                        lambda root: {"_missing": True, "_path": "no/such/manifest.json"})
    monkeypatch.setattr(provenance, "artifact_mtime", lambda path: None)

    message, tone = provenance.provenance_message(Path("."))

    assert tone == "warning"
    assert "unknown provenance" in message
