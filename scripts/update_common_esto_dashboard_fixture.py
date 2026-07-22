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


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


#%%
# User-tuned constants.
LEAP_MAPPINGS_ROOT = _resolve(os.getenv("LEAP_MAPPINGS_ROOT", DEFAULT_LEAP_MAPPINGS_ROOT))
SOURCE_COMMON_ESTO_DIR = LEAP_MAPPINGS_ROOT / "results" / "common_esto"
FIXTURE_DIR = _resolve("tests/fixtures/common_esto_dashboard")

SOURCE_COMPARISON_FILE = SOURCE_COMMON_ESTO_DIR / "common_esto_comparison_data.csv"
SOURCE_COMMON_ROWS_FILE = SOURCE_COMMON_ESTO_DIR / "common_esto_rows.csv"

FIXTURE_COMPARISON_FILE = FIXTURE_DIR / "common_esto_comparison_data_sample.csv"
FIXTURE_COMMON_ROWS_FILE = FIXTURE_DIR / "common_esto_rows.csv"
FIXTURE_ECONOMY = "20_USA"
CHUNKSIZE = 200_000
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


#%%
def check_source_files() -> None:
    """Validate that the latest mapping pipeline outputs are available."""
    missing = [
        path
        for path in [SOURCE_COMPARISON_FILE, SOURCE_COMMON_ROWS_FILE]
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


def write_economy_comparison_fixture(source_path: Path, destination_path: Path, economy: str) -> None:
    """Write a compact single-economy fixture preserving all scopes and labels."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    compact_economy = str(economy).replace("_", "")
    economy_keys = {str(economy), compact_economy}
    filtered_chunks = []
    for chunk in pd.read_csv(source_path, chunksize=CHUNKSIZE, low_memory=False):
        if "economy" not in chunk.columns:
            raise ValueError(f"Source comparison file is missing required 'economy' column: {source_path}")
        filtered = chunk[chunk["economy"].astype(str).isin(economy_keys)].copy()
        if filtered.empty:
            continue
        filtered["economy"] = str(economy)
        filtered_chunks.append(filtered)
    if not filtered_chunks:
        raise ValueError(f"No rows found for economy {economy} in {source_path}")
    full_fixture = pd.concat(filtered_chunks, ignore_index=True)
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
    write_economy_comparison_fixture(SOURCE_COMPARISON_FILE, FIXTURE_COMPARISON_FILE, FIXTURE_ECONOMY)
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
    run_weekly_fixture_update()
except Exception as exc:
    print("Common ESTO dashboard fixture update failed.")
    print(f"Error: {exc}")
    raise

#%%
