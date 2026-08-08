from pathlib import Path

import pandas as pd

import codebase.common_esto_dashboard_mapping_diagnostics as diagnostics


def test_selected_hierarchy_contract_does_not_replace_rollup_catalogue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Registered rollup badges must come from mapping-owned rollup_edges.csv."""
    mappings_root = tmp_path / "leap_mappings"
    rollup_root = mappings_root / "results" / "mapping_relationships"
    rollup_root.mkdir(parents=True)

    tree = pd.DataFrame([
        {
            "axis": "flow",
            "code": "09 Total transformation sector",
            "label": "09 Total transformation sector",
            "level": 1,
            "parent_code": "",
        },
        {
            "axis": "flow",
            "code": "09.01-09.02 Power sector",
            "label": "09.01-09.02 Power sector",
            "level": 2,
            "parent_code": "09 Total transformation sector",
        },
        *[
            {
                "axis": "flow",
                "code": label,
                "label": label,
                "level": 3,
                "parent_code": "09.01-09.02 Power sector",
            }
            for label in [
                "09.01.01,09.02.01 Electricity plants",
                "09.01.02,09.02.02 CHP plants",
                "09.01.03,09.02.03 Heat plants",
            ]
        ],
    ])
    catalogue_rows = []
    for short_name, label in [
        ("electricity", "09.01.01,09.02.01 Electricity plants"),
        ("chp", "09.01.02,09.02.02 CHP plants"),
        ("heat", "09.01.03,09.02.03 Heat plants"),
    ]:
        catalogue_rows.append({
            "source_system": "ESTO",
            "rollup_mode": "EXPANDING",
            "rollup_id": f"rollup_{short_name}",
            "rolled_flow_label": label,
            "input_flow": f"raw_{short_name}",
            "parent_flow_label": "09.01-09.02 Power sector",
            "child_flow_labels": f"raw_{short_name}",
        })
    pd.DataFrame(catalogue_rows).to_csv(rollup_root / "rollup_edges.csv", index=False)

    contract_rollups = pd.DataFrame([{
        "source_system": "ESTO",
        "rollup_mode": "EXPANDING",
        "rollup_id": "contract_wrong_chp",
        "rolled_flow_label": "09.01.02,09.02.02 CHP plants",
        "input_flow": "09.01.02.01 Coal CHP",
    }])
    monkeypatch.setattr(
        diagnostics,
        "load_mapping_diagnostics_contract",
        lambda _root: {
            "tree": tree,
            "validation": pd.DataFrame(),
            "rollups": contract_rollups,
            "build_id": "test-contract",
        },
    )

    layout = {
        "dashboards": tmp_path / "dashboards",
        "supporting": tmp_path / "supporting",
    }
    for path in layout.values():
        path.mkdir()

    result = diagnostics.write_mapping_diagnostics_page(
        layout,
        mappings_root,
        dashboard_updated_label="test",
        economy="20USA",
    )
    html = Path(result["page"]).read_text(encoding="utf-8")

    assert "rollup_electricity" in html
    assert "rollup_chp" in html
    assert "rollup_heat" in html
    assert "contract_wrong_chp" not in html
