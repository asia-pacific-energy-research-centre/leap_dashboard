#%%
"""Update Common ESTO dashboard sample fixtures and run smoke checks."""

#%%
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd


#%%
# Stable paths.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEAP_MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
MODULE_ROOT = REPO_ROOT / "codebase"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from common_esto_dashboard_data import (  # noqa: E402
    ALL_SCOPES,
    filter_common_esto_data,
    load_common_esto_data,
)


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


def _env_bool(name: str, default: bool) -> bool:
    """Read a simple boolean environment toggle."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y"}


#%%
# User-tuned constants.
LEAP_MAPPINGS_ROOT = _resolve(os.getenv("LEAP_MAPPINGS_ROOT", DEFAULT_LEAP_MAPPINGS_ROOT))
SOURCE_COMMON_ESTO_DIR = LEAP_MAPPINGS_ROOT / "results" / "common_esto"
FIXTURE_DIR = _resolve("tests/fixtures/common_esto_dashboard")

SOURCE_COMPARISON_FILE = SOURCE_COMMON_ESTO_DIR / "common_esto_comparison_data.csv"
OUTPUT_CONTRACT_PATH = _resolve(
    os.getenv(
        "COMMON_ESTO_OUTPUT_CONTRACT_PATH",
        SOURCE_COMMON_ESTO_DIR / "common_esto_output_contract.json",
    )
)
USE_OUTPUT_CONTRACT = _env_bool("COMMON_ESTO_USE_OUTPUT_CONTRACT", default=False)
SOURCE_COMMON_ROWS_FILE = SOURCE_COMMON_ESTO_DIR / "common_esto_rows.csv"

FIXTURE_COMPARISON_FILE = FIXTURE_DIR / "common_esto_comparison_data_sample.csv"
FIXTURE_COMMON_ROWS_FILE = FIXTURE_DIR / "common_esto_rows.csv"
FIXTURE_ECONOMY = "20_USA"
REPRESENTATIVE_YEARS = [2022, 2030, 2060]
COVERAGE_COLUMNS = [
    "comparison_scope",
    "source_system",
    "scenario",
    "common_flow_label",
    "common_product_label",
    "common_row_basis",
    "is_exact_row",
    "requires_rollup",
]

RUN_SMOKE_TEST = True
RUN_FULL_DASHBOARD_RENDER = True
UPDATE_COMMON_ESTO_FIXTURES = True
RUN_WEEKLY_FIXTURE_UPDATE = _env_bool("COMMON_ESTO_RUN_FIXTURE_UPDATE", default=True)


#%%
def check_source_files() -> None:
    """Validate that the latest mapping pipeline outputs are available."""
    selected_comparison_input = (
        OUTPUT_CONTRACT_PATH if USE_OUTPUT_CONTRACT else SOURCE_COMPARISON_FILE
    )
    missing = [
        path
        for path in [selected_comparison_input, SOURCE_COMMON_ROWS_FILE]
        if not path.exists()
    ]
    if missing:
        joined = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing common ESTO source output files:\n{joined}")


def copy_fixture_file(source_path: Path, destination_path: Path) -> None:
    """Copy one source output into the tracked fixture folder."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    print(f"Updated {destination_path}")
    print(f"  from {source_path}")


def write_economy_comparison_fixture(
    source_path: Path,
    destination_path: Path,
    economy: str,
    *,
    output_contract_path: Path | None = None,
) -> None:
    """Write a compact single-economy fixture preserving all scopes and labels."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = load_common_esto_data(
        source_path,
        output_contract_path=output_contract_path,
    )
    # Fixtures represent legacy-shaped raw input data that other tests feed
    # back into load_common_esto_data themselves (which adds measure/unit
    # fresh at that point) - writing those derived columns into the fixture
    # file would change its schema for no reason and is not what "the latest
    # common ESTO dashboard inputs" means.
    source = source.drop(columns=[c for c in ("measure", "unit") if c in source.columns])
    full_fixture = filter_common_esto_data(
        source,
        comparison_scope=ALL_SCOPES,
        economy=economy,
    )
    if full_fixture.empty:
        raise ValueError(f"No rows found for economy {economy} in {source_path}")
    full_fixture["economy"] = str(economy)
    missing_columns = [column for column in COVERAGE_COLUMNS + ["year"] if column not in full_fixture.columns]
    if missing_columns:
        raise ValueError(f"Source comparison file is missing fixture columns: {missing_columns}")
    representative = full_fixture[full_fixture["year"].isin(REPRESENTATIVE_YEARS)]
    full_fixture["_abs_value"] = full_fixture["value"].abs()
    coverage = (
        full_fixture.sort_values(["_abs_value", "year"], ascending=[False, True])
        .drop_duplicates(subset=COVERAGE_COLUMNS, keep="first")
        .drop(columns=["_abs_value"])
    )
    compact_fixture = (
        pd.concat([representative, coverage], ignore_index=True)
        .drop_duplicates()
        .sort_values(COVERAGE_COLUMNS + ["year"], kind="stable")
    )
    compact_fixture.to_csv(destination_path, index=False)
    print(f"Updated {destination_path}")
    print(f"  from {source_path}")
    print(f"  economy {economy}: {len(full_fixture):,} source rows -> {len(compact_fixture):,} fixture rows")


def update_common_esto_fixtures() -> None:
    """Copy the latest common ESTO dashboard inputs into tracked fixtures."""
    check_source_files()
    write_economy_comparison_fixture(
        SOURCE_COMPARISON_FILE,
        FIXTURE_COMPARISON_FILE,
        FIXTURE_ECONOMY,
        output_contract_path=OUTPUT_CONTRACT_PATH if USE_OUTPUT_CONTRACT else None,
    )
    copy_fixture_file(SOURCE_COMMON_ROWS_FILE, FIXTURE_COMMON_ROWS_FILE)


def run_command(command: list[str], environment: dict[str, str] | None = None) -> None:
    """Run a subprocess from the repo root and raise on failure."""
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True, env=environment)


def run_common_esto_checks() -> None:
    """Run the smoke test and optional full dashboard render."""
    if RUN_SMOKE_TEST:
        run_command([sys.executable, "-m", "pytest", "tests/test_common_esto_dashboard.py"])
    if RUN_FULL_DASHBOARD_RENDER:
        render_environment = os.environ.copy()
        render_environment.update({
            "COMMON_ESTO_INPUT_DATA_PATH": str(FIXTURE_COMPARISON_FILE),
            "COMMON_ESTO_ROWS_PATH": str(FIXTURE_COMMON_ROWS_FILE),
            "COMMON_ESTO_USE_OUTPUT_CONTRACT": "0",
            "COMMON_ESTO_ECONOMIES": "20USA",
            "COMMON_ESTO_UPDATE_DATA": "0",
            "COMMON_ESTO_PUBLISH_TO_DOCS": "0",
        })
        run_command([
            sys.executable,
            "codebase/common_esto_dashboard_workflow.py",
        ], environment=render_environment)


def run_weekly_fixture_update() -> None:
    """Update weekly fixtures and verify the dashboard still renders."""
    if UPDATE_COMMON_ESTO_FIXTURES:
        update_common_esto_fixtures()
    run_common_esto_checks()


#%%
try:
    if RUN_WEEKLY_FIXTURE_UPDATE:
        run_weekly_fixture_update()
    else:
        print("Set COMMON_ESTO_RUN_FIXTURE_UPDATE=1 to refresh fixtures.")
except Exception as exc:
    print("Common ESTO dashboard fixture update failed.")
    print(f"Error: {exc}")
    raise

#%%
