#%%
"""Adapt the mappings-owned hierarchy contract for dashboard diagnostics."""

#%%
from __future__ import annotations

from pathlib import Path

import pandas as pd

from codebase.hierarchy_subtotal_contract_loader import (
    load_hierarchy_subtotal_contract,
)


def load_mapping_diagnostics_contract(
    mappings_root: Path,
) -> dict[str, object] | None:
    """Return canonical Common ESTO tree and conformance rows when selected.

    Absence means no contract has been selected yet. Once a manifest exists,
    strict loading is authoritative and any invalid member raises instead of
    silently falling back to legacy tree or validation files.
    """
    contract_dir = (
        Path(mappings_root)
        / "results"
        / "hierarchy_subtotal_contract"
        / "current"
    )
    if not (contract_dir / "manifest.json").exists():
        return None
    manifest, frames = load_hierarchy_subtotal_contract(contract_dir)
    nodes = frames.get("axis_nodes", pd.DataFrame())
    edges = frames.get("declared_relationship_edges", pd.DataFrame())
    diagnostics = frames.get("value_conformance_diagnostics", pd.DataFrame())

    common_nodes = nodes[
        nodes.get("dataset_id", pd.Series(dtype=object)).astype(str).eq(
            "common_esto"
        )
        & nodes.get("axis_id", pd.Series(dtype=object)).astype(str).eq("axis_1")
    ].copy()
    common_tree = pd.DataFrame({
        "dataset": "common_esto",
        "axis": "flow",
        "code": common_nodes.get("node_id", pd.Series(dtype=object)),
        "label": common_nodes.get("node_label", pd.Series(dtype=object)),
        "level": pd.to_numeric(
            common_nodes.get("depth", pd.Series(dtype=object)),
            errors="coerce",
        ).fillna(0).astype(int),
        "parent_code": common_nodes.get(
            "parent_node_id", pd.Series(dtype=object)
        ).fillna(""),
        "is_leaf": common_nodes.get(
            "is_leaf", pd.Series(dtype=object)
        ),
        "is_subtotal": common_nodes.get(
            "is_structural_parent", pd.Series(dtype=object)
        ),
    })

    common_diagnostics = diagnostics[
        diagnostics.get("dataset_id", pd.Series(dtype=object)).astype(str).eq(
            "common_esto"
        )
    ].copy()
    common_diagnostics["validation_axis"] = (
        common_diagnostics.get("validation_axis", pd.Series(dtype=object))
        .astype(str)
        .map({"axis_1": "flow", "axis_2": "product"})
        .fillna(common_diagnostics.get("validation_axis", ""))
    )
    common_diagnostics = common_diagnostics.rename(columns={
        "parent_node_id": "parent_code",
        "fixed_opposite_axis_node_id": "other_axis_value",
        "year_or_period": "year",
        "child_sum": "children_sum",
        "signed_difference": "difference",
        "absolute_difference": "abs_error",
    })
    common_edges = edges[
        edges.get("dataset_id", pd.Series(dtype=object)).astype(str).eq(
            "common_esto"
        )
        & edges.get("axis_id", pd.Series(dtype=object)).astype(str).eq("axis_1")
    ].copy()
    mode_lookup = {
        "additive_synthetic_rollup": "EXPANDING",
        "expanding_rollup": "EXPANDING",
        "non_expanding_replacement": "NON_EXPANDING",
        "detached_diagnostic_boundary": "DETACHED",
    }
    common_edges["rollup_mode"] = common_edges.get(
        "relationship_type", pd.Series(dtype=object)
    ).astype(str).map(mode_lookup)
    rollup_edges = common_edges[common_edges["rollup_mode"].notna()].copy()
    display_parent_lookup = (
        common_nodes.drop_duplicates("node_id")
        .set_index("node_id")
        .get("display_parent_node_id", pd.Series(dtype=object))
        .fillna("")
        .astype(str)
        .to_dict()
    )
    if rollup_edges.empty:
        rollups = pd.DataFrame()
    else:
        grouped_children = (
            rollup_edges.groupby(
                ["parent_node_id", "rollup_mode"],
                dropna=False,
            )["child_node_id"]
            .agg(lambda values: ";".join(sorted(set(map(str, values)))))
            .to_dict()
        )
        rollups = pd.DataFrame({
            "source_system": "ESTO",
            "include": True,
            "rollup_mode": rollup_edges["rollup_mode"],
            "rollup_id": (
                "contract:"
                + rollup_edges["parent_node_id"].astype(str)
                + ":"
                + rollup_edges["rollup_mode"].astype(str)
            ),
            "rolled_flow_label": rollup_edges["parent_node_id"],
            "input_flow": rollup_edges["child_node_id"],
            "parent_flow_label": rollup_edges["parent_node_id"].astype(str).map(
                display_parent_lookup
            ).fillna(""),
            "child_flow_labels": [
                grouped_children.get((str(parent), str(mode)), "")
                for parent, mode in zip(
                    rollup_edges["parent_node_id"],
                    rollup_edges["rollup_mode"],
                )
            ],
            "note": "Canonical hierarchy contract relationship",
        }).drop_duplicates()
    return {
        "manifest": manifest,
        "tree": common_tree.reset_index(drop=True),
        "validation": common_diagnostics.reset_index(drop=True),
        "rollups": rollups.reset_index(drop=True),
        "build_id": str(manifest["build_id"]),
    }


#%%
