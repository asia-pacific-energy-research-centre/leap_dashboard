"""Focused contract/legacy tests for remaining Common ESTO consumer readers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy

import pandas as pd
import pytest

from codebase.common_esto_dashboard_data import (
    CONTRACT_FACT_COLUMNS,
    CONTRACT_FACT_KEY_COLUMNS,
    CONTRACT_JOINED_COLUMNS,
    CONTRACT_METADATA_COLUMNS,
    CONTRACT_METADATA_KEY_COLUMNS,
    OUTPUT_CONTRACT_VERSION,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    fact = pd.DataFrame(
        [
            ["esto_leap_ninth", "ESTO", "20_USA", "historical", 2022, "production_gas", 10.0],
            ["esto_leap_ninth", "LEAP", "20_USA", "Target", 2030, "production_gas", 12.0],
            ["esto_leap_ninth", "ESTO", "20_USA", "historical", 2060, "road_gasoline", -4.0],
            ["esto_leap_ninth", "ESTO", "02_BD", "historical", 2022, "production_gas", 1.0],
        ],
        columns=CONTRACT_FACT_COLUMNS,
    )
    metadata = pd.DataFrame(
        [
            [
                "esto_leap_ninth",
                "production_gas",
                "01",
                "Production",
                "01 Production",
                "08.01",
                "Natural gas",
                "08.01 Natural gas",
                "exact_esto_row",
                True,
                False,
                False,
                "",
                "",
                "",
                "",
            ],
            [
                "esto_leap_ninth",
                "road_gasoline",
                "15.01-15.02",
                "Road",
                "15.01-15.02 Road",
                "07.01-07.02",
                "Motor gasoline",
                "07.01-07.02 Motor gasoline",
                "connected_component_rollup",
                False,
                True,
                False,
                "",
                "connected_component",
                "Road",
                "road_motor_gasoline",
            ],
        ],
        columns=CONTRACT_METADATA_COLUMNS,
    )
    return fact, metadata


def _member(path: Path, columns: list[str], keys: list[str]) -> dict[str, object]:
    return {
        "path": path.name,
        "format": "csv",
        "columns": columns,
        "key_columns": keys,
        "row_count": len(pd.read_csv(path)),
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_inputs(root: Path) -> tuple[Path, Path]:
    fact, metadata = _frames()
    fact_path = root / "fact.csv"
    metadata_path = root / "metadata.csv"
    fact.to_csv(fact_path, index=False)
    metadata.to_csv(metadata_path, index=False)
    manifest = {
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "run_id": "consumer_fixture_run",
        "run_timestamp_utc": "2026-07-28T00:00:00+00:00",
        "observed_rows_only": True,
        "fact": _member(fact_path, CONTRACT_FACT_COLUMNS, CONTRACT_FACT_KEY_COLUMNS),
        "metadata": _member(
            metadata_path,
            CONTRACT_METADATA_COLUMNS,
            CONTRACT_METADATA_KEY_COLUMNS,
        ),
    }
    manifest_path = root / "common_esto_output_contract.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    legacy = fact.merge(
        metadata,
        on=CONTRACT_METADATA_KEY_COLUMNS,
        how="left",
        validate="many_to_one",
    )[CONTRACT_JOINED_COLUMNS]
    legacy_path = root / "legacy.csv"
    legacy.to_csv(legacy_path, index=False)
    return legacy_path, manifest_path


def _load_script(path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("COMMON_ESTO_RUN_SANKEY_ROUTING_QA", "0")
    monkeypatch.setenv("COMMON_ESTO_RUN_FIXTURE_UPDATE", "0")
    return runpy.run_path(str(path))


def test_sankey_reader_contract_matches_legacy_and_preserves_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = _load_script(
        repo_root / "scripts" / "check_common_esto_sankey_routing.py",
        monkeypatch,
    )
    legacy_path, manifest_path = _write_inputs(tmp_path)

    legacy = script["load_candidate_rows"](
        legacy_path,
        "20USA",
        "esto_leap_ninth",
    )
    contract = script["load_candidate_rows"](
        tmp_path / "missing_legacy.csv",
        "20_USA",
        "esto_leap_ninth",
        output_contract_path=manifest_path,
    )

    expected_columns = [
        "comparison_scope",
        "economy",
        "common_flow_code",
        "common_flow_label",
        "common_product_code",
        "common_product_label",
        "row_count",
        "min_value",
        "max_value",
        "total_abs_value",
    ]
    assert list(legacy.columns) == expected_columns
    assert list(contract.columns) == expected_columns
    pd.testing.assert_frame_equal(
        legacy.sort_values(expected_columns[:6]).reset_index(drop=True),
        contract.sort_values(expected_columns[:6]).reset_index(drop=True),
        check_dtype=False,
    )


def test_sankey_selected_invalid_contract_never_uses_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = _load_script(
        repo_root / "scripts" / "check_common_esto_sankey_routing.py",
        monkeypatch,
    )
    legacy_path, _ = _write_inputs(tmp_path)

    with pytest.raises(FileNotFoundError, match="output contract not found"):
        script["load_candidate_rows"](
            legacy_path,
            "20USA",
            "esto_leap_ninth",
            output_contract_path=tmp_path / "missing_contract.json",
        )


def test_fixture_updater_contract_matches_legacy_and_preserves_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = _load_script(
        repo_root / "scripts" / "update_common_esto_dashboard_fixture.py",
        monkeypatch,
    )
    legacy_path, manifest_path = _write_inputs(tmp_path)
    legacy_output = tmp_path / "legacy_fixture.csv"
    contract_output = tmp_path / "contract_fixture.csv"

    script["write_economy_comparison_fixture"](
        legacy_path,
        legacy_output,
        "20_USA",
    )
    script["write_economy_comparison_fixture"](
        tmp_path / "missing_legacy.csv",
        contract_output,
        "20_USA",
        output_contract_path=manifest_path,
    )

    legacy = pd.read_csv(legacy_output)
    contract = pd.read_csv(contract_output)
    assert list(legacy.columns) == CONTRACT_JOINED_COLUMNS
    assert list(contract.columns) == CONTRACT_JOINED_COLUMNS
    pd.testing.assert_frame_equal(legacy, contract, check_dtype=False)
    assert set(contract["year"]) == {2022, 2030, 2060}


def test_fixture_updater_selected_invalid_contract_never_uses_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = _load_script(
        repo_root / "scripts" / "update_common_esto_dashboard_fixture.py",
        monkeypatch,
    )
    legacy_path, _ = _write_inputs(tmp_path)

    with pytest.raises(FileNotFoundError, match="output contract not found"):
        script["write_economy_comparison_fixture"](
            legacy_path,
            tmp_path / "fixture.csv",
            "20USA",
            output_contract_path=tmp_path / "missing_contract.json",
        )
