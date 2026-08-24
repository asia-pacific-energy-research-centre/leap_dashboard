#%%
"""Measure full Version 1/Version 2 rendering against trace-only Version 1.

Run this notebook-safe script with representative comparison data before
updating the deployed runtime estimate. It verifies exact Version 1 chart
bundle equivalence as part of the measurement; chart-bundle bytes include the
chart keys, values, years, units, source/scenario labels, and Plotly metadata.
"""

#%%
from __future__ import annotations

import sys
import tempfile
import time
import tracemalloc
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase.common_esto_dashboard_portable import (  # noqa: E402
    render_common_esto_comparison_traces,
    render_common_esto_dashboard,
)


#%%
def directory_size_bytes(path: Path) -> int:
    """Return the size of generated files without following directory links."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def assert_bundle_equivalence(full_root: Path, trace_root: Path) -> int:
    """Require exact Version 1 bundles before reporting a benchmark result."""
    full_bundles = full_root / "chart_bundles"
    trace_bundles = trace_root / "chart_bundles"
    full_names = sorted(path.name for path in full_bundles.glob("*.json"))
    trace_names = sorted(path.name for path in trace_bundles.glob("*.json"))
    if full_names != trace_names:
        raise AssertionError(("Chart bundle names differ", full_names, trace_names))
    for name in full_names:
        if (full_bundles / name).read_bytes() != (trace_bundles / name).read_bytes():
            raise AssertionError(f"Version 1 bundle differs: {name}")
    return len(full_names)


def _measure(render_function, **kwargs: object) -> tuple[dict[str, object], float, int]:
    """Measure elapsed time and Python-managed peak memory for one render."""
    tracemalloc.start()
    started = time.perf_counter()
    result = render_function(**kwargs)
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak_bytes


def benchmark_version_comparison(
    *,
    economy: str,
    comparison_data_path: Path | str,
    common_rows_path: Path | str,
    template_path: Path | str,
    series_config_path: Path | str,
    output_root: Path | str,
    min_year: int = 2010,
    max_year: int = 2060,
) -> dict[str, float | int]:
    """Return measured full/full and trace-only/full comparison costs."""
    target = Path(output_root)
    shared = {
        "economy": economy,
        "comparison_data_path": comparison_data_path,
        "common_rows_path": common_rows_path,
        "template_path": template_path,
        "series_config_path": series_config_path,
        "min_year": min_year,
        "max_year": max_year,
        "dashboard_updated_label": "benchmark",
    }
    full_v1, full_v1_seconds, full_v1_peak = _measure(
        render_common_esto_dashboard, output_root=target / "two_full" / "version_1", **shared
    )
    _, full_v2_seconds, full_v2_peak = _measure(
        render_common_esto_dashboard, output_root=target / "two_full" / "version_2", **shared
    )
    traces_v1, trace_v1_seconds, trace_v1_peak = _measure(
        render_common_esto_comparison_traces, output_root=target / "lightweight" / "version_1", **shared
    )
    _, lightweight_v2_seconds, lightweight_v2_peak = _measure(
        render_common_esto_dashboard, output_root=target / "lightweight" / "version_2", **shared
    )
    full_root = Path(str(full_v1["output_root"]))
    trace_root = Path(str(traces_v1["comparison_trace_root"]))
    bundle_count = assert_bundle_equivalence(full_root, trace_root)
    return {
        "two_full_seconds": round(full_v1_seconds + full_v2_seconds, 3),
        "trace_only_plus_full_seconds": round(trace_v1_seconds + lightweight_v2_seconds, 3),
        "two_full_peak_python_bytes": max(full_v1_peak, full_v2_peak),
        "trace_only_peak_python_bytes": max(trace_v1_peak, lightweight_v2_peak),
        "full_v1_output_bytes": directory_size_bytes(full_root),
        "trace_only_v1_output_bytes": directory_size_bytes(trace_root),
        "equivalent_chart_bundle_count": bundle_count,
    }


#%%
RUN_BENCHMARK = False

if __name__ == "__main__" and RUN_BENCHMARK:
    result = benchmark_version_comparison(
        economy="20_USA",
        comparison_data_path=REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard" / "common_esto_comparison_data_sample.csv",
        common_rows_path=REPO_ROOT / "tests" / "fixtures" / "common_esto_dashboard" / "common_esto_rows.csv",
        template_path=REPO_ROOT / "config" / "common_esto_dashboard" / "common_esto_dashboard_template.json",
        series_config_path=REPO_ROOT / "config" / "common_esto_dashboard" / "series_config.json",
        output_root=Path(tempfile.gettempdir()) / "dashq063_benchmark",
        min_year=2020,
        max_year=2030,
    )
    print(result)

#%%
