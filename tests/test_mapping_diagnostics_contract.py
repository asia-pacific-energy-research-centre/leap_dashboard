from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.mapping_diagnostics_contract import (
    load_mapping_diagnostics_contract,
)


def _write_contract(root: Path) -> Path:
    contract_dir = root / "results" / "hierarchy_subtotal_contract" / "current"
    contract_dir.mkdir(parents=True)
    members = {
        "axis_nodes": pd.DataFrame([
            {
                "dataset_id": "common_esto",
                "axis_id": "axis_1",
                "node_id": "09 Total transformation sector",
                "node_label": "09 Total transformation sector",
                "depth": 1,
                "parent_node_id": "",
                "is_leaf": False,
                "is_structural_parent": True,
            },
            {
                "dataset_id": "common_esto",
                "axis_id": "axis_1",
                "node_id": "09.06 Gas processing plants",
                "node_label": "09.06 Gas processing plants",
                "depth": 2,
                "parent_node_id": "09 Total transformation sector",
                "is_leaf": True,
                "is_structural_parent": False,
            },
            {
                "dataset_id": "common_esto",
                "axis_id": "axis_1",
                "node_id": "09.06 Gas processing plants (including own use)",
                "node_label": "09.06 Gas processing plants (including own use)",
                "depth": 2,
                "display_parent_node_id": "09 Total transformation sector",
                "parent_node_id": "",
                "is_leaf": True,
                "is_structural_parent": False,
            },
        ]),
        "declared_relationship_edges": pd.DataFrame([{
            "dataset_id": "common_esto",
            "axis_id": "axis_1",
            "parent_node_id": "09.06 Gas processing plants (including own use)",
            "child_node_id": "09.06 Gas processing plants",
            "relationship_type": "non_expanding_replacement",
        }]),
        "value_conformance_diagnostics": pd.DataFrame([{
            "dataset_id": "common_esto",
            "validation_axis": "axis_1",
            "parent_node_id": "09 Total transformation sector",
            "fixed_opposite_axis_node_id": "08.01 Natural gas",
            "year_or_period": 2050,
            "child_sum": 9,
            "signed_difference": 1,
            "absolute_difference": 1,
            "source_system": "NINTH",
            "economy": "20_USA",
            "status": "failed",
            "reason": "difference_exceeds_tolerance",
        }]),
    }
    declarations = {}
    for name, frame in members.items():
        path = contract_dir / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        payload = path.read_bytes()
        declarations[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "row_count": len(frame),
        }
    manifest = {
        "contract_name": "aperc_hierarchy_subtotal_contract",
        "schema_version": "hierarchy_subtotal_contract_v1",
        "validation_result": "passed",
        "build_id": "build-1",
        "members": declarations,
    }
    (contract_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return contract_dir


def test_contract_adapter_exposes_canonical_tree_and_common_conformance(
    tmp_path: Path,
) -> None:
    _write_contract(tmp_path)

    selected = load_mapping_diagnostics_contract(tmp_path)

    assert selected is not None
    assert selected["build_id"] == "build-1"
    tree = selected["tree"]
    assert tree.loc[0, "is_subtotal"]
    assert tree.loc[1, "parent_code"] == "09 Total transformation sector"
    validation = selected["validation"]
    assert validation.loc[0, "validation_axis"] == "flow"
    assert validation.loc[0, "parent_code"] == "09 Total transformation sector"
    assert validation.loc[0, "source_system"] == "NINTH"
    rollups = selected["rollups"]
    assert rollups.loc[0, "rollup_mode"] == "NON_EXPANDING"
    assert (
        rollups.loc[0, "parent_flow_label"]
        == "09 Total transformation sector"
    )


def test_contract_adapter_fails_closed_after_manifest_selection(
    tmp_path: Path,
) -> None:
    contract_dir = _write_contract(tmp_path)
    member = contract_dir / "axis_nodes.csv"
    member.write_text(member.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_mapping_diagnostics_contract(tmp_path)
