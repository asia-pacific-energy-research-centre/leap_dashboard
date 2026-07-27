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


def test_superseded_artifacts_produce_a_warning_banner(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(provenance, "stage3_manifest", lambda root: {"run_id": "run_abc"})
    monkeypatch.setattr(provenance, "artifact_mtime", lambda path: pd.Timestamp("2026-07-27 13:00"))
    monkeypatch.setattr(provenance, "pipeline_commits_since", lambda root, cutoff: ([], ""))

    message, tone = provenance.provenance_message(Path("."))

    assert tone == "info"
    assert "superseded" not in message
    assert "no mapping-pipeline code commit is newer" in message


def test_unanswerable_provenance_is_a_warning_not_a_clean_result(monkeypatch: pytest.MonkeyPatch) -> None:
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
