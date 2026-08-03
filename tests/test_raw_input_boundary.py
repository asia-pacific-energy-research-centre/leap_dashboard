from pathlib import Path
import os
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_workflow_uses_common_esto_and_only_derived_convergence_input() -> None:
    source = (REPO_ROOT / "codebase" / "common_esto_dashboard_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "common_esto_comparison_data.csv" in source
    assert '"leap_initialisation"' in source
    assert '"outputs"' in source
    assert '"leap_exports"' in source
    assert "leap balances exports" not in source.lower()


def test_dashboard_does_not_require_local_raw_balance_export_directory() -> None:
    # A legacy folder may remain during migration; production code must not
    # require it or select it as an input.
    workflow_source = (REPO_ROOT / "codebase" / "common_esto_dashboard_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "data\\leap balances exports" not in workflow_source.lower()
    assert "data/leap balances exports" not in workflow_source.lower()


def test_workflow_defaults_are_non_mutating() -> None:
    environment = os.environ.copy()
    for variable in (
        "COMMON_ESTO_UPDATE_DATA",
        "COMMON_ESTO_PUBLISH_TO_DOCS",
        "COMMON_ESTO_INCLUDE_CAPACITY_UNMET_CONVERGENCE",
        "COMMON_ESTO_USE_OUTPUT_CONTRACT",
    ):
        environment.pop(variable, None)
    environment["COMMON_ESTO_RUN_DASHBOARD_WORKFLOW"] = "0"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.path.insert(0, 'codebase'); "
                "import common_esto_dashboard_workflow as workflow; "
                "print(workflow.UPDATE_DATA, workflow.PUBLISH_TO_DOCS, "
                "workflow.INCLUDE_CAPACITY_UNMET_CONVERGENCE, "
                "workflow.USE_OUTPUT_CONTRACT)"
            ),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "False False False False" in result.stdout


def test_batch_and_qa_scripts_accept_isolated_output_path_overrides() -> None:
    batch_source = (
        REPO_ROOT / "scripts" / "render_common_esto_dashboard_all_economies.py"
    ).read_text(encoding="utf-8")
    readiness_source = (
        REPO_ROOT / "scripts" / "check_common_esto_dashboard_publish_ready.py"
    ).read_text(encoding="utf-8")
    noise_source = (
        REPO_ROOT / "scripts" / "analyze_common_esto_dashboard_page_noise.py"
    ).read_text(encoding="utf-8")

    assert "COMMON_ESTO_LEGACY_INPUT_PATH" in batch_source
    assert "COMMON_ESTO_COMMON_ROWS_PATH" in batch_source
    assert "COMMON_ESTO_DASHBOARD_OUTPUT_ROOT" in batch_source
    assert "COMMON_ESTO_DASHBOARD_OUTPUT_ROOT" in readiness_source
    assert "COMMON_ESTO_DASHBOARD_OUTPUT_ROOT" in noise_source
