import json
from pathlib import Path

import pandas as pd

from codebase.utilities.leap_results_dashboard_compare import (
    _restyle_prev_trace,
    _to_rgba,
    build_comparison_dashboard,
    snapshot_dashboard_baseline,
)


def test_to_rgba_handles_hex_rgb_and_fallback():
    assert _to_rgba("#1f77b4", 0.45) == "rgba(31,119,180,0.45)"
    assert _to_rgba("#abc", 0.5) == "rgba(170,187,204,0.5)"
    assert _to_rgba("rgb(10, 20, 30)", 0.4) == "rgba(10,20,30,0.4)"
    assert _to_rgba("rgba(10, 20, 30, 0.9)", 0.4) == "rgba(10,20,30,0.4)"
    assert _to_rgba(None, 0.4) == "rgba(110,110,110,0.4)"


def test_restyle_prev_trace_fades_and_dots_line_traces():
    trace = {
        "name": "LEAP TGT",
        "mode": "lines+markers",
        "line": {"color": "#17becf", "dash": "solid"},
        "marker": {"symbol": "circle", "color": "#17becf"},
        "x": [2022, 2023],
        "y": [1.0, 2.0],
    }
    out = _restyle_prev_trace(trace, {})
    assert out["name"] == "LEAP TGT (prev)"
    assert out["line"]["dash"] == "dot"
    assert out["line"]["color"] == "rgba(23,190,207,0.45)"
    assert out["marker"]["color"] == "rgba(23,190,207,0.45)"
    # Original trace must not be mutated.
    assert trace["name"] == "LEAP TGT"
    assert trace["line"]["dash"] == "solid"


def test_restyle_prev_trace_converts_stacked_traces_to_cumulative_boundaries():
    stack_totals: dict[str, dict[str, float]] = {}
    first = _restyle_prev_trace(
        {
            "name": "Coal",
            "mode": "lines",
            "stackgroup": "leap_target",
            "fillcolor": "#111111",
            "line": {"width": 0.7, "color": "#111111"},
            "x": [2022, 2023],
            "y": [1.0, 2.0],
        },
        stack_totals,
    )
    second = _restyle_prev_trace(
        {
            "name": "Gas",
            "mode": "lines",
            "stackgroup": "leap_target",
            "fillcolor": "#222222",
            "line": {"width": 0.7, "color": "#222222"},
            "x": [2022, 2023],
            "y": [10.0, 20.0],
        },
        stack_totals,
    )
    assert first["y"] == [1.0, 2.0]
    assert second["y"] == [11.0, 22.0]
    for boundary in (first, second):
        assert "stackgroup" not in boundary
        assert boundary["fill"] == "none"
        assert "fillcolor" not in boundary
        assert boundary["mode"] == "lines"
        assert boundary["line"]["dash"] == "dot"


def _write_site(root: Path, bundle_name: str, charts: dict) -> None:
    bundles = root / "chart_bundles"
    dashboards = root / "dashboards"
    bundles.mkdir(parents=True, exist_ok=True)
    dashboards.mkdir(parents=True, exist_ok=True)
    payload = {"dashboard_path": "Demand", "charts": charts}
    (bundles / bundle_name).write_text(json.dumps(payload), encoding="utf-8")
    page_name = bundle_name.removesuffix("__charts.json") + ".html"
    (dashboards / page_name).write_text(
        "<html><body><div>page</div></body></html>", encoding="utf-8"
    )


def _chart(y_values: list[float]) -> dict:
    return {
        "data": [
            {
                "name": "LEAP TGT",
                "mode": "lines+markers",
                "line": {"color": "#17becf", "dash": "solid"},
                "x": [2022, 2023],
                "y": y_values,
            }
        ],
        "layout": {"title": {"text": "Demand - Coal"}},
        "config": {"responsive": True},
    }


def test_snapshot_and_build_comparison_flags_changed_series(tmp_path):
    publish = tmp_path / "publish"
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"

    # Previous run, snapshotted as baseline.
    _write_site(publish, "node__Demand__charts.json", {"chart_a": _chart([1.0, 2.0])})
    assert snapshot_dashboard_baseline(publish, baseline)

    # Current run: chart_a changed, chart_b is new.
    _write_site(
        publish,
        "node__Demand__charts.json",
        {"chart_a": _chart([1.0, 3.0]), "chart_b": _chart([5.0, 6.0])},
    )

    result = build_comparison_dashboard(publish, baseline, comparison)
    summary = pd.read_csv(result["comparison_summary_csv"])
    status_by_chart = dict(zip(summary["chart_key"], summary["status"]))
    assert status_by_chart == {"chart_a": "changed", "chart_b": "chart_added"}
    changed_row = summary[summary["chart_key"].eq("chart_a")].iloc[0]
    assert changed_row["max_abs_delta"] == 1.0
    assert str(int(float(changed_row["max_delta_year"]))) == "2023"

    merged = json.loads(
        (comparison / "chart_bundles" / "node__Demand__charts.json").read_text(encoding="utf-8")
    )
    names = [t["name"] for t in merged["charts"]["chart_a"]["data"]]
    assert names == ["LEAP TGT", "LEAP TGT (prev)"]
    annotations = merged["charts"]["chart_a"]["layout"]["annotations"]
    assert any("changed vs prev" in a["text"] for a in annotations)

    page_html = (comparison / "dashboards" / "node__Demand.html").read_text(encoding="utf-8")
    assert "Comparison view" in page_html
    assert (comparison / "index.html").exists()


def test_build_comparison_skips_without_baseline(tmp_path):
    publish = tmp_path / "publish"
    _write_site(publish, "node__Demand__charts.json", {"chart_a": _chart([1.0, 2.0])})
    result = build_comparison_dashboard(publish, tmp_path / "missing_baseline", tmp_path / "comparison")
    assert result == {}


def test_pinned_baseline_is_not_overwritten(tmp_path):
    publish = tmp_path / "publish"
    baseline = tmp_path / "baseline"
    _write_site(publish, "node__Demand__charts.json", {"chart_a": _chart([1.0, 2.0])})
    assert snapshot_dashboard_baseline(publish, baseline)

    _write_site(publish, "node__Demand__charts.json", {"chart_a": _chart([9.0, 9.0])})
    assert not snapshot_dashboard_baseline(publish, baseline, overwrite=False)

    pinned = json.loads(
        (baseline / "chart_bundles" / "node__Demand__charts.json").read_text(encoding="utf-8")
    )
    assert pinned["charts"]["chart_a"]["data"][0]["y"] == [1.0, 2.0]
