#%%
"""Strict consumer for the mappings-owned hierarchy/subtotal contract."""

#%%
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


CONTRACT_NAME = "aperc_hierarchy_subtotal_contract"
SCHEMA_VERSION = "hierarchy_subtotal_contract_v1"


def load_hierarchy_subtotal_contract(
    contract_dir: Path,
    expected_build_id: str | None = None,
    expected_input_hashes: dict[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, pd.DataFrame]]:
    """Load one explicitly selected build and fail without fallback."""
    contract_dir = Path(contract_dir)
    manifest_path = contract_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Selected hierarchy contract is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_name") != CONTRACT_NAME:
        raise ValueError("Selected hierarchy contract has the wrong contract name")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Selected hierarchy contract schema is incompatible")
    if manifest.get("validation_result") != "passed":
        raise ValueError("Selected hierarchy contract is invalid")
    if expected_build_id and manifest.get("build_id") != expected_build_id:
        raise ValueError("Selected hierarchy contract build_id does not match")
    actual_inputs = {
        Path(item["path"]).name: item["sha256"]
        for item in manifest.get("inputs", [])
    }
    for name, expected_hash in (expected_input_hashes or {}).items():
        if actual_inputs.get(name) != expected_hash:
            raise ValueError(f"Selected hierarchy contract input mismatch for {name}")

    frames: dict[str, pd.DataFrame] = {}
    for name, declaration in manifest.get("members", {}).items():
        path = contract_dir / declaration["path"]
        if not path.exists():
            raise FileNotFoundError(f"Hierarchy contract member is missing: {path}")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != declaration["sha256"]:
            raise ValueError(f"Hierarchy contract member hash mismatch: {name}")
        frame = pd.read_csv(path, dtype=object)
        if len(frame) != int(declaration["row_count"]):
            raise ValueError(f"Hierarchy contract member row count mismatch: {name}")
        frames[name] = frame
    return manifest, frames


def diagnostic_status_labels(
    pair_row: pd.Series,
    conformance_rows: pd.DataFrame,
) -> dict[str, str]:
    """Keep structural and contextual additivity labels visibly separate."""
    structural = "YES" if str(pair_row.get("pair_is_subtotal", "")).casefold() == "true" else "NO"
    if conformance_rows.empty:
        additivity = "UNAVAILABLE"
    elif (conformance_rows["status"].astype(str) == "failed").any():
        additivity = "NO"
    elif (conformance_rows["status"].astype(str) == "passed").all():
        additivity = "YES"
    else:
        additivity = "INCOMPLETE / UNAVAILABLE"
    return {
        "structural_subtotal": structural,
        "children_add_to_parent_in_context": additivity,
    }


#%%
