"""Dashboard contract loading and structure/additivity separation tests."""

import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.hierarchy_subtotal_contract_loader import (
    diagnostic_status_labels,
    load_hierarchy_subtotal_contract,
)


def _contract(root: Path) -> Path:
    member = root / "canonical_source_pairs.csv"
    payload = b"dataset_id,axis_1_node_id,axis_2_node_id,pair_is_subtotal\nninth,parent,leaf,True\n"
    member.write_bytes(payload)
    import hashlib

    manifest = {
        "contract_name": "aperc_hierarchy_subtotal_contract",
        "schema_version": "hierarchy_subtotal_contract_v1",
        "build_id": "build-1",
        "validation_result": "passed",
        "inputs": [{"path": "mapping.xlsx", "sha256": "abc"}],
        "members": {
            "canonical_source_pairs": {
                "path": member.name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "row_count": 1,
            }
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_selected_contract_loads_and_stale_selection_fails_closed(tmp_path: Path) -> None:
    root = _contract(tmp_path)
    manifest, frames = load_hierarchy_subtotal_contract(root, expected_build_id="build-1")
    assert manifest["build_id"] == "build-1"
    assert bool(frames["canonical_source_pairs"].iloc[0]["pair_is_subtotal"])
    with pytest.raises(ValueError, match="build_id"):
        load_hierarchy_subtotal_contract(root, expected_build_id="stale")


def test_dashboard_labels_structure_and_additivity_separately() -> None:
    labels = diagnostic_status_labels(
        pd.Series({"pair_is_subtotal": "True"}),
        pd.DataFrame([{"status": "failed"}]),
    )
    assert labels == {
        "structural_subtotal": "YES",
        "children_add_to_parent_in_context": "NO",
    }
