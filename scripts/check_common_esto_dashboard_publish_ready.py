#%%
"""Check Common ESTO dashboard files before manually publishing to docs."""

#%%
import json
from pathlib import Path


#%%
# Stable paths.
REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve(path: str | Path) -> Path:
    """Resolve repo-relative paths while staying notebook-safe."""
    clean_path = str(path).replace("\\", "/")
    path_obj = Path(clean_path)
    if path_obj.is_absolute():
        return path_obj
    return REPO_ROOT / path_obj


#%%
# User-tuned constants.
DASHBOARD_ROOT = _resolve("outputs/common_esto_dashboard/20USA")
EXPECTED_PAGE_KEYS = [
    "index",
    "total_demand",
    "supply",
    "bunkers",
    "power",
    "other_transformation",
    "refining",
    "industry",
    "transport",
    "buildings",
    "others",
    "non_energy",
]
DIAGNOSTIC_PAGE_KEYS = [
    "transport_leap_vs_ninth",
    "datacentres_leap_vs_ninth",
]
RUN_PUBLISH_READY_CHECK = True


#%%
def check_html_pages(dashboard_root: Path, expected_page_keys: list[str]) -> list[str]:
    """Return missing or empty expected dashboard HTML page errors."""
    errors: list[str] = []
    dashboards_dir = dashboard_root / "dashboards"
    for page_key in expected_page_keys:
        page_path = dashboards_dir / f"{page_key}.html"
        if not page_path.exists():
            errors.append(f"Missing HTML page: {page_path}")
        elif page_path.stat().st_size == 0:
            errors.append(f"Empty HTML page: {page_path}")
    return errors


def check_diagnostic_pages_hidden(dashboard_root: Path, diagnostic_page_keys: list[str]) -> list[str]:
    """Return errors for diagnostic pages that are present in default output."""
    errors: list[str] = []
    for page_key in diagnostic_page_keys:
        page_path = dashboard_root / "dashboards" / f"{page_key}.html"
        bundle_path = dashboard_root / "chart_bundles" / f"{page_key}__charts.json"
        if page_path.exists():
            errors.append(f"Diagnostic HTML page is present by default: {page_path}")
        if bundle_path.exists():
            errors.append(f"Diagnostic chart bundle is present by default: {bundle_path}")
    return errors


def check_chart_bundles(dashboard_root: Path, expected_page_keys: list[str]) -> list[str]:
    """Return missing or empty Plotly bundle errors for non-index pages."""
    errors: list[str] = []
    bundles_dir = dashboard_root / "chart_bundles"
    for page_key in expected_page_keys:
        if page_key == "index":
            continue
        bundle_path = bundles_dir / f"{page_key}__charts.json"
        if not bundle_path.exists():
            errors.append(f"Missing chart bundle: {bundle_path}")
            continue
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Could not read chart bundle {bundle_path}: {exc}")
            continue
        charts = bundle.get("charts", {})
        if not charts:
            errors.append(f"No charts found in bundle: {bundle_path}")
            continue
        for chart_key, figure in charts.items():
            traces = figure.get("data", [])
            if not traces:
                errors.append(f"Chart has no Plotly traces: {bundle_path} :: {chart_key}")
                continue
            if not any(trace.get("x") and trace.get("y") for trace in traces):
                errors.append(f"Chart has no non-empty x/y payload: {bundle_path} :: {chart_key}")
    return errors


def check_supporting_files(dashboard_root: Path) -> list[str]:
    """Return errors for missing human-audit files that should exist before publishing."""
    errors: list[str] = []
    required_files = [
        dashboard_root / "supporting_files" / "chart_manifest.csv",
        dashboard_root / "supporting_files" / "page_assignment_summary.csv",
        dashboard_root / "supporting_files" / "sign_semantics_summary.csv",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Missing supporting audit file: {path}")
        elif path.stat().st_size == 0:
            errors.append(f"Empty supporting audit file: {path}")
    return errors


def build_publish_checklist(dashboard_root: Path) -> list[str]:
    """Return the manual publishing checklist text."""
    return [
        "Review the rendered dashboard index in outputs/common_esto_dashboard/20USA/dashboards/index.html.",
        "Review supporting_files/chart_manifest.csv for page counts and noisy pages.",
        "Leave PUBLISH_TO_DOCS = False for fixture refreshes and ordinary render checks.",
        "Only when ready to publish, set PUBLISH_TO_DOCS = True in codebase/common_esto_dashboard/common_esto_dashboard_workflow.py.",
        "Run C:\\Users\\Work\\miniconda3\\python.exe codebase\\common_esto_dashboard\\common_esto_dashboard_workflow.py.",
        f"Inspect docs/{dashboard_root.name}/dashboards/index.html after the copy.",
        "Commit the docs/ serving assets together with the scoped source/config changes being published.",
        "Set PUBLISH_TO_DOCS back to False after publishing.",
    ]


def run_publish_ready_check(
    dashboard_root: Path,
    expected_page_keys: list[str],
    diagnostic_page_keys: list[str],
) -> dict[str, object]:
    """Run all publish-readiness checks and print a manual checklist."""
    errors: list[str] = []
    errors.extend(check_html_pages(dashboard_root, expected_page_keys))
    errors.extend(check_diagnostic_pages_hidden(dashboard_root, diagnostic_page_keys))
    errors.extend(check_chart_bundles(dashboard_root, expected_page_keys))
    errors.extend(check_supporting_files(dashboard_root))

    checklist = build_publish_checklist(dashboard_root)
    if errors:
        print("Common ESTO publish readiness check failed:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Common ESTO publish readiness check passed.")
    print("\nManual publish checklist:")
    for step_number, step in enumerate(checklist, start=1):
        print(f"{step_number}. {step}")
    return {"ok": not errors, "errors": errors, "checklist": checklist}


#%%
try:
    if RUN_PUBLISH_READY_CHECK:
        PUBLISH_READY_RESULT = run_publish_ready_check(
            DASHBOARD_ROOT,
            EXPECTED_PAGE_KEYS,
            DIAGNOSTIC_PAGE_KEYS,
        )
        if not PUBLISH_READY_RESULT["ok"]:
            raise RuntimeError("Common ESTO dashboard is not ready to publish.")
    else:
        print("Set RUN_PUBLISH_READY_CHECK = True to check publish readiness.")
except Exception as exc:
    print("Common ESTO publish readiness check failed.")
    print(f"Error: {exc}")
    raise

#%%
