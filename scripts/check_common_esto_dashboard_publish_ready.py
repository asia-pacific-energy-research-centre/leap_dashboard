#%%
"""Check Common ESTO dashboard files before manually publishing to docs."""

#%%
import csv
import json
import os
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
DASHBOARD_OUTPUT_ROOT = _resolve(
    os.getenv("COMMON_ESTO_DASHBOARD_OUTPUT_ROOT", "outputs/common_esto_dashboard")
)
DASHBOARD_ROOT = DASHBOARD_OUTPUT_ROOT / "20USA"
CHECK_ALL_RENDERED_DASHBOARDS = True
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
def find_rendered_dashboard_roots(output_root: Path) -> list[Path]:
    """Return rendered economy dashboard roots under the Common ESTO output folder."""
    if not output_root.exists():
        return []
    roots = []
    for path in output_root.iterdir():
        if not path.is_dir():
            continue
        if (path / "dashboards" / "index.html").exists():
            roots.append(path)
    return sorted(roots, key=lambda item: item.name)


def expected_pages_from_manifest(dashboard_root: Path) -> list[str]:
    """Return expected dashboard page keys from the rendered chart manifest."""
    manifest_path = dashboard_root / "supporting_files" / "chart_manifest.csv"
    if not manifest_path.exists():
        return []
    page_keys: set[str] = {"index"}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            page_key = str(row.get("page_key", "")).strip()
            if page_key:
                page_keys.add(page_key)
    return sorted(page_keys)


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
        f"Review the rendered dashboard index in {dashboard_root / 'dashboards' / 'index.html'}.",
        "Review supporting_files/chart_manifest.csv for page counts and noisy pages in each rendered economy.",
        "Leave PUBLISH_TO_DOCS = False for fixture refreshes and ordinary render checks.",
        "Only when ready to publish, set PUBLISH_TO_DOCS = True in codebase/common_esto_dashboard_workflow.py.",
        "Run C:\\Users\\Work\\miniconda3\\python.exe codebase\\common_esto_dashboard_workflow.py.",
        f"Inspect docs/{dashboard_root.name}/dashboards/index.html after the copy.",
        "Commit the docs/ serving assets together with the scoped source/config changes being published.",
        "Set PUBLISH_TO_DOCS back to False after publishing.",
    ]


def check_one_dashboard_root(
    dashboard_root: Path,
    expected_page_keys: list[str],
    diagnostic_page_keys: list[str],
) -> list[str]:
    """Run publish-readiness checks for one rendered dashboard root."""
    errors: list[str] = []
    errors.extend(check_html_pages(dashboard_root, expected_page_keys))
    errors.extend(check_diagnostic_pages_hidden(dashboard_root, diagnostic_page_keys))
    errors.extend(check_chart_bundles(dashboard_root, expected_page_keys))
    errors.extend(check_supporting_files(dashboard_root))
    return errors


def run_publish_ready_check(
    dashboard_root: Path,
    expected_page_keys: list[str],
    diagnostic_page_keys: list[str],
) -> dict[str, object]:
    """Run publish-readiness checks for one dashboard and print a manual checklist."""
    errors = check_one_dashboard_root(dashboard_root, expected_page_keys, diagnostic_page_keys)

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


def run_all_publish_ready_checks(output_root: Path, diagnostic_page_keys: list[str]) -> dict[str, object]:
    """Run publish-readiness checks for every rendered dashboard under output_root."""
    roots = find_rendered_dashboard_roots(output_root)
    errors: list[str] = []
    checked: list[str] = []
    if not roots:
        errors.append(f"No rendered dashboards found under: {output_root}")
    for root in roots:
        expected_page_keys = expected_pages_from_manifest(root)
        if not expected_page_keys:
            errors.append(f"Could not derive expected pages from manifest: {root}")
            continue
        root_errors = check_one_dashboard_root(root, expected_page_keys, diagnostic_page_keys)
        errors.extend([f"{root.name}: {error}" for error in root_errors])
        checked.append(root.name)

    checklist = build_publish_checklist(output_root / "20USA")
    if errors:
        print("Common ESTO publish readiness check failed:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Common ESTO publish readiness check passed.")
    print(f"Rendered dashboards checked: {', '.join(checked) if checked else '(none)'}")
    print("\nManual publish checklist:")
    for step_number, step in enumerate(checklist, start=1):
        print(f"{step_number}. {step}")
    return {"ok": not errors, "errors": errors, "checked": checked, "checklist": checklist}


#%%
try:
    if RUN_PUBLISH_READY_CHECK:
        if CHECK_ALL_RENDERED_DASHBOARDS:
            PUBLISH_READY_RESULT = run_all_publish_ready_checks(
                DASHBOARD_OUTPUT_ROOT,
                DIAGNOSTIC_PAGE_KEYS,
            )
        else:
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
