"""Strict compatibility tests for the opt-in Common ESTO output contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from codebase.common_esto_dashboard_data import (
    CONTRACT_FACT_COLUMNS,
    CONTRACT_FACT_KEY_COLUMNS,
    CONTRACT_JOINED_COLUMNS,
    CONTRACT_METADATA_COLUMNS,
    CONTRACT_METADATA_KEY_COLUMNS,
    OUTPUT_CONTRACT_VERSION,
    filter_common_esto_data,
    load_common_esto_data,
)


def _representative_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return dense 20_USA and sparse 02_BD rows sharing canonical metadata."""
    fact = pd.DataFrame(
        [
            ["esto_leap_ninth", "ESTO", "20_USA", "historical", 2022, "row_production_gas", 10.0],
            ["esto_leap_ninth", "LEAP", "20_USA", "Target", 2022, "row_production_gas", 11.0],
            ["esto_leap_ninth", "NINTH", "20_USA", "reference", 2030, "row_production_gas", 12.0],
            ["esto_leap_ninth", "ESTO", "20_USA", "historical", 2022, "row_road_gasoline", -4.0],
            ["esto_leap_ninth", "ESTO", "02_BD", "historical", 2022, "row_production_gas", 1.0],
            ["esto_leap_ninth", "LEAP", "02_BD", "Target", 2030, "row_production_gas", 2.0],
        ],
        columns=CONTRACT_FACT_COLUMNS,
    )
    metadata = pd.DataFrame(
        [
            [
                "esto_leap_ninth",
                "row_production_gas",
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
                "row_road_gasoline",
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _member_declaration(
    path: Path,
    *,
    columns: list[str],
    key_columns: list[str],
) -> dict[str, object]:
    return {
        "path": path.name,
        "format": "csv",
        "columns": columns,
        "key_columns": key_columns,
        "row_count": len(pd.read_csv(path)),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _write_contract(
    root: Path,
    fact: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    manifest_updates: dict[str, object] | None = None,
) -> Path:
    fact_path = root / "common_esto_fact.csv"
    metadata_path = root / "common_esto_metadata.csv"
    fact.to_csv(fact_path, index=False)
    metadata.to_csv(metadata_path, index=False)
    manifest = {
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "run_id": "contract_fixture_run",
        "run_timestamp_utc": "2026-07-28T00:00:00+00:00",
        "observed_rows_only": True,
        "fact": _member_declaration(
            fact_path,
            columns=CONTRACT_FACT_COLUMNS,
            key_columns=CONTRACT_FACT_KEY_COLUMNS,
        ),
        "metadata": _member_declaration(
            metadata_path,
            columns=CONTRACT_METADATA_COLUMNS,
            key_columns=CONTRACT_METADATA_KEY_COLUMNS,
        ),
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    manifest_path = root / "common_esto_output_contract.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _legacy_frame(fact: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    joined = fact.merge(
        metadata,
        on=CONTRACT_METADATA_KEY_COLUMNS,
        how="left",
        validate="many_to_one",
    )
    return joined[CONTRACT_JOINED_COLUMNS]


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(CONTRACT_FACT_KEY_COLUMNS).reset_index(drop=True)


def test_contract_matches_legacy_for_dense_and_sparse_economies(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    manifest_path = _write_contract(tmp_path, fact, metadata)
    legacy_path = tmp_path / "legacy.csv"
    _legacy_frame(fact, metadata).to_csv(legacy_path, index=False)

    legacy = load_common_esto_data(legacy_path)
    contract = load_common_esto_data(
        legacy_path,
        output_contract_path=manifest_path,
    )

    pd.testing.assert_frame_equal(
        _sorted(contract),
        _sorted(legacy)[CONTRACT_JOINED_COLUMNS + ["measure", "unit"]],
        check_dtype=False,
    )
    assert len(filter_common_esto_data(contract, "esto_leap_ninth", "20USA")) == 4
    brunei = filter_common_esto_data(contract, "esto_leap_ninth", "02BD")
    assert len(brunei) == 2
    assert set(brunei["economy"]) == {"02_BD"}
    assert 2025 not in set(brunei["year"])


def test_contract_requires_explicit_opt_in(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    manifest_path = _write_contract(tmp_path, fact, metadata)
    legacy = _legacy_frame(fact, metadata)
    legacy["value"] = 999.0
    legacy_path = tmp_path / "legacy.csv"
    legacy.to_csv(legacy_path, index=False)

    default_result = load_common_esto_data(legacy_path)
    contract_result = load_common_esto_data(
        legacy_path,
        output_contract_path=manifest_path,
    )

    assert set(default_result["value"]) == {999.0}
    assert 999.0 not in set(contract_result["value"])


def test_selected_missing_contract_member_never_falls_back(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    manifest_path = _write_contract(tmp_path, fact, metadata)
    legacy_path = tmp_path / "legacy.csv"
    _legacy_frame(fact, metadata).to_csv(legacy_path, index=False)
    (tmp_path / "common_esto_fact.csv").unlink()

    with pytest.raises(FileNotFoundError, match="fact member"):
        load_common_esto_data(legacy_path, output_contract_path=manifest_path)


@pytest.mark.parametrize("declared_path", ["C:/outside/fact.csv", "../fact.csv"])
def test_contract_rejects_absolute_or_escaping_member_paths(
    tmp_path: Path,
    declared_path: str,
) -> None:
    fact, metadata = _representative_frames()
    manifest_path = _write_contract(tmp_path, fact, metadata)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["fact"]["path"] = declared_path
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="relative|escapes"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_duplicate_fact_key(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    fact = pd.concat([fact, fact.iloc[[0]]], ignore_index=True)
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="fact key is not unique"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_orphan_metadata(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    orphan = metadata.iloc[[0]].copy()
    orphan["common_row_id"] = "row_without_observations"
    metadata = pd.concat([metadata, orphan], ignore_index=True)
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="orphan compound keys"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_fact_row_without_metadata(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    fact.loc[0, "common_row_id"] = "row_without_metadata"
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="no metadata row"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_conflicting_metadata_key(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    conflict = metadata.iloc[[0]].copy()
    conflict["common_flow_label"] = "01 Conflicting production label"
    metadata = pd.concat([metadata, conflict], ignore_index=True)
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="conflicting rows"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_identical_duplicate_metadata_key(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    metadata = pd.concat([metadata, metadata.iloc[[0]]], ignore_index=True)
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="metadata compound key is not unique"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


@pytest.mark.parametrize(
    ("manifest_update", "message"),
    [
        ({"contract_version": "future"}, "Unsupported Common ESTO"),
        ({"observed_rows_only": False}, "observed_rows_only"),
    ],
)
def test_contract_rejects_invalid_manifest_semantics(
    tmp_path: Path,
    manifest_update: dict[str, object],
    message: str,
) -> None:
    fact, metadata = _representative_frames()
    manifest_path = _write_contract(
        tmp_path,
        fact,
        metadata,
        manifest_updates=manifest_update,
    )

    with pytest.raises(ValueError, match=message):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_non_numeric_years_and_values(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    fact = fact.astype({"year": object, "value": object})
    fact.loc[0, "year"] = "not-a-year"
    fact.loc[1, "value"] = "not-a-value"
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="invalid years"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)


def test_contract_rejects_non_numeric_values(tmp_path: Path) -> None:
    fact, metadata = _representative_frames()
    fact = fact.astype({"value": object})
    fact.loc[0, "value"] = "not-a-value"
    manifest_path = _write_contract(tmp_path, fact, metadata)

    with pytest.raises(ValueError, match="invalid numeric values"):
        load_common_esto_data(Path("unused.csv"), output_contract_path=manifest_path)
