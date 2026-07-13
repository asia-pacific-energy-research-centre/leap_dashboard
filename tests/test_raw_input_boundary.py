from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_workflow_uses_common_esto_and_only_derived_convergence_input() -> None:
    source = (REPO_ROOT / "codebase" / "common_esto_dashboard_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "common_esto_comparison_data.csv" in source
    assert "leap_initialisation\\outputs\\leap_exports" in source
    assert "leap balances exports" not in source.lower()


def test_dashboard_does_not_require_local_raw_balance_export_directory() -> None:
    # A legacy folder may remain during migration; production code must not
    # require it or select it as an input.
    workflow_source = (REPO_ROOT / "codebase" / "common_esto_dashboard_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "data\\leap balances exports" not in workflow_source.lower()
    assert "data/leap balances exports" not in workflow_source.lower()
