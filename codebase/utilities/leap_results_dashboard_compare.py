"""
Visual regression comparison for rendered balance dashboards.

The dashboard renderer writes each page's charts as a Plotly JSON bundle under
chart_bundles/. This module snapshots those bundles before a re-render, then
rebuilds the same dashboard pages with the previous run's series overlaid as
faded dotted "(prev)" traces in the previous series' own colors. That makes the
effect of code changes visible chart-by-chart in the familiar chart formats,
instead of having to judge correctness from raw CSV deltas.

Outputs (under <publish_dir>/comparison/):
- dashboards/*.html        copies of the current dashboard pages with a banner
- chart_bundles/*.js[on]   merged bundles: current traces + faded prev traces
- comparison_summary.csv   per-trace delta table (page, chart, trace, status)
- index.html               pages ranked by how much their charts changed

Stacked-area charts cannot be overlaid as a second stack without becoming
unreadable, so previous-run stacked traces are converted to dotted cumulative
boundary lines: they sit exactly on the old stack boundaries and align visually
with the new stacked areas.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

_BUNDLE_SUFFIX = "__charts.json"
_PREV_NAME_SUFFIX = " (prev)"
_PREV_ALPHA = 0.45
_FALLBACK_RGB = (110, 110, 110)
_PROVENANCE_FILENAME = "build_provenance.json"


# ---------------------------------------------------------------------------
# Build provenance — git commit tracking
# ---------------------------------------------------------------------------

def _git_commit_hash(repo_root: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root) if repo_root else None,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _git_is_ancestor(older_commit: str, newer_commit: str, repo_root: Path | None = None) -> bool | None:
    """Return True if older_commit is an ancestor of newer_commit (or equal), None on error."""
    if not older_commit or not newer_commit:
        return None
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older_commit, newer_commit],
            capture_output=True,
            cwd=str(repo_root) if repo_root else None,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return None


def write_build_provenance(output_dir: Path, economy: str, stage_flags: dict[str, bool]) -> Path:
    """Write a provenance record capturing the git commit and run metadata."""
    provenance = {
        "git_commit": _git_commit_hash(),
        "produced_at_utc": datetime.now(timezone.utc).isoformat(),
        "economy": economy,
        "stage_flags": stage_flags,
    }
    path = Path(output_dir) / _PROVENANCE_FILENAME
    path.write_text(json.dumps(provenance, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _read_provenance(directory: Path) -> dict[str, Any]:
    path = directory / _PROVENANCE_FILENAME
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}

_BANNER_HTML = (
    '<div style="position:sticky;top:0;z-index:9999;background:#fff3cd;'
    "border-bottom:1px solid #d4b106;padding:6px 14px;"
    'font:13px/1.4 system-ui,sans-serif;color:#5c4400;">'
    "Comparison view &mdash; faded dotted &ldquo;(prev)&rdquo; series show the "
    "previous run; solid series show the current run.{extra}</div>"
)


# ---------------------------------------------------------------------------
# Color and trace restyling helpers
# ---------------------------------------------------------------------------

def _to_rgba(color: object, alpha: float) -> str:
    text = str(color or "").strip()
    match = re.match(r"^#([0-9a-fA-F]{6})$", text)
    if match:
        value = match.group(1)
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},{alpha})"
    match = re.match(r"^#([0-9a-fA-F]{3})$", text)
    if match:
        value = match.group(1)
        r, g, b = (int(ch * 2, 16) for ch in value)
        return f"rgba({r},{g},{b},{alpha})"
    match = re.match(r"^rgba?\(([^)]+)\)$", text)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) >= 3:
            return f"rgba({parts[0]},{parts[1]},{parts[2]},{alpha})"
    r, g, b = _FALLBACK_RGB
    return f"rgba({r},{g},{b},{alpha})"


def _restyle_prev_trace(trace: dict[str, Any], stack_totals: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Return a faded dotted copy of a previous-run trace.

    Stacked traces are converted to cumulative boundary lines; stack_totals
    carries the running per-x totals for each stackgroup across calls.
    """
    out = copy.deepcopy(trace)
    name = str(out.get("name") or "").strip()
    out["name"] = (name or "series") + _PREV_NAME_SUFFIX
    out["legendgroup"] = "prev_run"

    stackgroup = str(out.pop("stackgroup", "") or "")
    line = dict(out.get("line") or {})
    marker = dict(out.get("marker") or {})
    base_color = line.get("color") or marker.get("color") or out.get("fillcolor")

    if stackgroup:
        totals = stack_totals.setdefault(stackgroup, {})
        xs = list(out.get("x") or [])
        ys = list(out.get("y") or [])
        boundary: list[float] = []
        for x, y in zip(xs, ys):
            key = str(x)
            running = totals.get(key, 0.0) + (0.0 if y is None else float(y))
            totals[key] = running
            boundary.append(running)
        out["y"] = boundary
        out.pop("fillcolor", None)
        out["fill"] = "none"
        out["mode"] = "lines"
        line["width"] = max(float(line.get("width") or 0.0), 1.4)

    rgba = _to_rgba(base_color, _PREV_ALPHA)
    line["color"] = rgba
    line["dash"] = "dot"
    out["line"] = line
    if marker or "markers" in str(out.get("mode") or ""):
        marker["color"] = rgba
        marker_line = dict(marker.get("line") or {})
        if marker_line.get("color"):
            marker_line["color"] = _to_rgba(marker_line.get("color"), _PREV_ALPHA)
            marker["line"] = marker_line
        out["marker"] = marker
    return out


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------

def _trace_value_map(trace: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for x, y in zip(list(trace.get("x") or []), list(trace.get("y") or [])):
        if y is None:
            continue
        try:
            values[str(x)] = float(y)
        except (TypeError, ValueError):
            continue
    return values


def _pair_traces_by_name(
    new_traces: list[dict[str, Any]],
    prev_traces: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]]:
    """Pair traces between runs by legend name, in order of repeated names."""

    def _grouped(traces: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for trace in traces:
            grouped.setdefault(str(trace.get("name") or "").strip(), []).append(trace)
        return grouped

    new_by_name = _grouped(new_traces)
    prev_by_name = _grouped(prev_traces)
    pairs: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []
    for name in list(new_by_name) + [n for n in prev_by_name if n not in new_by_name]:
        news = new_by_name.get(name, [])
        prevs = prev_by_name.get(name, [])
        for idx in range(max(len(news), len(prevs))):
            pairs.append(
                (
                    name,
                    news[idx] if idx < len(news) else None,
                    prevs[idx] if idx < len(prevs) else None,
                )
            )
    return pairs


def _trace_delta_row(
    name: str,
    new_trace: dict[str, Any] | None,
    prev_trace: dict[str, Any] | None,
    abs_tolerance: float,
    rel_tolerance: float,
) -> dict[str, object]:
    new_values = _trace_value_map(new_trace) if new_trace is not None else {}
    prev_values = _trace_value_map(prev_trace) if prev_trace is not None else {}
    keys = set(new_values) | set(prev_values)
    max_abs_delta = 0.0
    delta_year = ""
    scale = max((abs(v) for v in list(new_values.values()) + list(prev_values.values())), default=0.0)
    for key in keys:
        delta = abs(new_values.get(key, 0.0) - prev_values.get(key, 0.0))
        if delta > max_abs_delta:
            max_abs_delta = delta
            delta_year = key
    changed = max_abs_delta > max(abs_tolerance, rel_tolerance * scale)
    if new_trace is None:
        status = "trace_removed"
    elif prev_trace is None:
        status = "trace_added"
    else:
        status = "changed" if changed else "unchanged"
    return {
        "trace": name,
        "status": status,
        "max_abs_delta": max_abs_delta,
        "max_delta_year": delta_year,
        "series_scale": scale,
    }


# ---------------------------------------------------------------------------
# Snapshot and build
# ---------------------------------------------------------------------------

def snapshot_dashboard_baseline(
    publish_dir: Path | str,
    baseline_dir: Path | str,
    *,
    overwrite: bool = True,
) -> bool:
    """Copy the current chart bundles and dashboard pages into baseline_dir.

    Call this before re-rendering so the previous run's outputs survive the
    renderer's stale-file cleanup. Returns False when there is nothing to
    snapshot or an existing baseline is being kept (overwrite=False).
    """
    publish = Path(publish_dir)
    baseline = Path(baseline_dir)
    bundle_files = sorted((publish / "chart_bundles").glob(f"*{_BUNDLE_SUFFIX}"))
    if not bundle_files:
        print("[INFO] Comparison baseline: no existing chart bundles to snapshot.")
        return False
    if not overwrite and (baseline / "chart_bundles").exists():
        print(f"[INFO] Comparison baseline pinned; keeping existing snapshot: {baseline}")
        return False

    if baseline.exists():
        shutil.rmtree(baseline)
    (baseline / "chart_bundles").mkdir(parents=True, exist_ok=True)
    for bundle in bundle_files:
        shutil.copy2(bundle, baseline / "chart_bundles" / bundle.name)
    dashboards = publish / "dashboards"
    if dashboards.exists():
        (baseline / "dashboards").mkdir(parents=True, exist_ok=True)
        for page in dashboards.glob("*.html"):
            shutil.copy2(page, baseline / "dashboards" / page.name)
    provenance_src = publish / _PROVENANCE_FILENAME
    if provenance_src.exists():
        shutil.copy2(provenance_src, baseline / _PROVENANCE_FILENAME)
    print(f"[INFO] Comparison baseline snapshot: {len(bundle_files)} bundles -> {baseline}")
    return True


def _load_bundles(bundles_dir: Path) -> dict[str, dict[str, Any]]:
    bundles: dict[str, dict[str, Any]] = {}
    for path in sorted(bundles_dir.glob(f"*{_BUNDLE_SUFFIX}")):
        try:
            bundles[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] Comparison: skipping unreadable bundle {path.name}: {exc}")
    return bundles


def _annotate(layout: dict[str, Any], text: str, color: str) -> None:
    annotations = list(layout.get("annotations") or [])
    annotations.append(
        {
            "text": text,
            "xref": "paper",
            "yref": "paper",
            "x": 1.0,
            "y": 1.08,
            "xanchor": "right",
            "showarrow": False,
            "font": {"color": color, "size": 12},
        }
    )
    layout["annotations"] = annotations


def _merge_chart(
    chart_key: str,
    new_chart: dict[str, Any] | None,
    prev_chart: dict[str, Any] | None,
    abs_tolerance: float,
    rel_tolerance: float,
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    new_traces = list((new_chart or {}).get("data") or [])
    prev_traces = list((prev_chart or {}).get("data") or [])

    rows: list[dict[str, object]] = []
    for name, new_trace, prev_trace in _pair_traces_by_name(new_traces, prev_traces):
        row = _trace_delta_row(name, new_trace, prev_trace, abs_tolerance, rel_tolerance)
        row["chart_key"] = chart_key
        rows.append(row)

    stack_totals: dict[str, dict[str, float]] = {}
    overlay = [_restyle_prev_trace(trace, stack_totals) for trace in prev_traces]

    merged = copy.deepcopy(new_chart if new_chart is not None else prev_chart) or {}
    merged["data"] = (new_traces if new_chart is not None else []) + overlay
    layout = dict(merged.get("layout") or {})
    changed_count = sum(1 for row in rows if row["status"] != "unchanged")
    if new_chart is None:
        _annotate(layout, "chart removed vs previous run", "#d62728")
        for row in rows:
            row["status"] = "chart_removed"
    elif prev_chart is None:
        _annotate(layout, "new chart (no baseline)", "#1f77b4")
        for row in rows:
            row["status"] = "chart_added"
    elif changed_count:
        _annotate(layout, f"{changed_count}/{len(rows)} series changed vs prev", "#d62728")
    merged["layout"] = layout
    return merged, rows


def _write_bundle(payload: dict[str, Any], bundles_dir: Path, bundle_name: str) -> None:
    payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    (bundles_dir / bundle_name).write_text(payload_json, encoding="utf-8")
    js_name = bundle_name.removesuffix(".json") + ".js"
    (bundles_dir / js_name).write_text(
        "window.BALANCE_CHART_BUNDLE_DATA=" + payload_json.replace("</", "<\\/") + ";\n",
        encoding="utf-8",
    )


def _copy_page_with_banner(source: Path, target: Path, extra_note: str = "") -> None:
    html = source.read_text(encoding="utf-8")
    banner = _BANNER_HTML.format(extra=f" {extra_note}" if extra_note else "")
    html, count = re.subn(r"(<body[^>]*>)", lambda m: m.group(1) + banner, html, count=1)
    if not count:
        html = banner + html
    target.write_text(html, encoding="utf-8")


def _page_name_for_bundle(bundle_name: str) -> str:
    return bundle_name.removesuffix(_BUNDLE_SUFFIX) + ".html"


def _provenance_html(
    baseline_prov: dict[str, Any],
    current_prov: dict[str, Any],
) -> str:
    """Return an HTML block summarising both provenances with any staleness warnings."""
    def _fmt(prov: dict[str, Any], label: str) -> str:
        commit = str(prov.get("git_commit") or "unknown")[:12] or "unknown"
        produced = str(prov.get("produced_at_utc") or "unknown")
        flags = prov.get("stage_flags") or {}
        skipped = [k for k, v in flags.items() if not v]
        skipped_note = f" <em>(skipped: {', '.join(skipped)})</em>" if skipped else ""
        return f"<strong>{escape(label)}:</strong> commit <code>{escape(commit)}</code>, produced {escape(produced)}{skipped_note}"

    lines = [
        "<div style='font:13px/1.6 system-ui,sans-serif;background:#f4f6f8;border:1px solid #ddd;padding:10px 14px;margin-bottom:16px;border-radius:4px;'>",
        "<strong>Build provenance</strong><br>",
    ]
    if baseline_prov:
        lines.append(_fmt(baseline_prov, "Baseline (prev run)") + "<br>")
    else:
        lines.append("<em>Baseline provenance not recorded (outputs pre-date provenance tracking).</em><br>")
    if current_prov:
        lines.append(_fmt(current_prov, "Current run") + "<br>")
    else:
        lines.append("<em>Current provenance not recorded.</em><br>")

    baseline_commit = str(baseline_prov.get("git_commit") or "").strip()
    current_commit = str(current_prov.get("git_commit") or "").strip()
    if baseline_commit and current_commit and baseline_commit != current_commit:
        is_anc = _git_is_ancestor(baseline_commit, current_commit)
        if is_anc is False:
            # baseline is NOT an ancestor of current — baseline may have been
            # produced after (or on a different branch from) the current code.
            lines.append(
                "<span style='color:#d62728;font-weight:bold;'>⚠ WARNING: baseline commit is not an ancestor of "
                "the current commit. The baseline may have been produced AFTER the current code, or on a "
                "different branch. This comparison may be misleading.</span><br>"
            )
        elif is_anc is None:
            lines.append("<em>(Could not determine commit ancestry — git unavailable or commits not in local history.)</em><br>")
    lines.append("</div>")
    return "\n".join(lines)


def _write_comparison_index(
    comparison_dir: Path,
    summary: pd.DataFrame,
    pages_without_baseline: list[str],
    baseline_prov: dict[str, Any],
    current_prov: dict[str, Any],
) -> Path:
    rows_html: list[str] = []
    if not summary.empty:
        page_stats = (
            summary.assign(is_changed=summary["status"].ne("unchanged"))
            .groupby("page", as_index=False)
            .agg(
                changed_series=("is_changed", "sum"),
                total_series=("status", "size"),
                max_abs_delta=("max_abs_delta", "max"),
            )
            .sort_values(["changed_series", "max_abs_delta"], ascending=False)
        )
        for row in page_stats.itertuples(index=False):
            style = "" if row.changed_series else ' style="color:#888;"'
            rows_html.append(
                f'<tr{style}><td><a href="dashboards/{escape(str(row.page))}">{escape(str(row.page))}</a></td>'
                f"<td>{int(row.changed_series)}</td><td>{int(row.total_series)}</td>"
                f"<td>{row.max_abs_delta:.6g}</td></tr>"
            )
    extra = ""
    if pages_without_baseline:
        items = "".join(f"<li>{escape(name)}</li>" for name in sorted(pages_without_baseline))
        extra = f"<h2>Pages without baseline</h2><ul>{items}</ul>"
    provenance_block = _provenance_html(baseline_prov, current_prov)
    index_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Dashboard comparison vs previous run</title>
<style>
body {{ font: 14px/1.5 system-ui, sans-serif; margin: 24px; color: #222; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ddd; padding: 4px 10px; text-align: left; }}
th {{ background: #f4f6f8; }}
</style></head><body>
<h1>Dashboard comparison vs previous run</h1>
{provenance_block}
<p>Solid series = current run; faded dotted &ldquo;(prev)&rdquo; series = previous run.
Full per-series deltas: <a href="comparison_summary.csv">comparison_summary.csv</a></p>
<table><tr><th>Page</th><th>Changed series</th><th>Total series</th><th>Max |delta|</th></tr>
{''.join(rows_html)}
</table>
{extra}
</body></html>
"""
    index_path = comparison_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return index_path


def build_comparison_dashboard(
    publish_dir: Path | str,
    baseline_dir: Path | str,
    comparison_dir: Path | str,
    *,
    abs_tolerance: float = 1e-9,
    rel_tolerance: float = 1e-6,
) -> dict[str, str]:
    """Build the comparison site from the current render and the baseline snapshot.

    Returns paths to the comparison index, dashboards dir, and summary CSV.
    Empty dict when no baseline snapshot is available.
    """
    publish = Path(publish_dir)
    baseline = Path(baseline_dir)
    comparison = Path(comparison_dir)

    new_bundles = _load_bundles(publish / "chart_bundles")
    prev_bundles = _load_bundles(baseline / "chart_bundles")
    if not prev_bundles:
        print(f"[INFO] Comparison skipped: no baseline bundles under {baseline}.")
        return {}
    if not new_bundles:
        print(f"[INFO] Comparison skipped: no rendered bundles under {publish}.")
        return {}

    if comparison.exists():
        shutil.rmtree(comparison)
    bundles_out = comparison / "chart_bundles"
    dashboards_out = comparison / "dashboards"
    bundles_out.mkdir(parents=True, exist_ok=True)
    dashboards_out.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    pages_without_baseline: list[str] = []

    for bundle_name in sorted(set(new_bundles) | set(prev_bundles)):
        new_payload = new_bundles.get(bundle_name)
        prev_payload = prev_bundles.get(bundle_name)
        page_name = _page_name_for_bundle(bundle_name)
        new_charts = dict((new_payload or {}).get("charts") or {})
        prev_charts = dict((prev_payload or {}).get("charts") or {})

        merged_charts: dict[str, Any] = {}
        for chart_key in list(new_charts) + [k for k in prev_charts if k not in new_charts]:
            merged, rows = _merge_chart(
                chart_key,
                new_charts.get(chart_key),
                prev_charts.get(chart_key),
                abs_tolerance,
                rel_tolerance,
            )
            merged_charts[chart_key] = merged
            for row in rows:
                row["page"] = page_name
                summary_rows.append(row)

        payload = {
            "dashboard_path": (new_payload or prev_payload or {}).get("dashboard_path", ""),
            "charts": merged_charts,
        }
        _write_bundle(payload, bundles_out, bundle_name)

        if new_payload is None:
            # Page disappeared in the current run: reuse the baseline page so the
            # faded-only charts remain visible in the comparison site.
            prev_page = baseline / "dashboards" / page_name
            if prev_page.exists():
                _copy_page_with_banner(
                    prev_page,
                    dashboards_out / page_name,
                    extra_note="<strong>This page no longer exists in the current run.</strong>",
                )
        elif prev_payload is None:
            pages_without_baseline.append(page_name)

    # Copy current dashboard pages (and non-HTML support files) with the banner.
    source_dashboards = publish / "dashboards"
    if source_dashboards.exists():
        for item in source_dashboards.iterdir():
            if item.is_dir():
                continue
            if item.suffix.lower() == ".html":
                _copy_page_with_banner(item, dashboards_out / item.name)
            else:
                shutil.copy2(item, dashboards_out / item.name)

    summary = pd.DataFrame(
        summary_rows,
        columns=["page", "chart_key", "trace", "status", "max_abs_delta", "max_delta_year", "series_scale"],
    )
    if not summary.empty:
        summary = summary.sort_values(["status", "max_abs_delta"], ascending=[True, False])
    baseline_prov = _read_provenance(baseline)
    current_prov = _read_provenance(publish)

    summary_path = comparison / "comparison_summary.csv"
    summary.to_csv(summary_path, index=False)
    index_path = _write_comparison_index(comparison, summary, pages_without_baseline, baseline_prov, current_prov)

    changed = summary[summary["status"].ne("unchanged")] if not summary.empty else summary
    print(
        f"[INFO] Comparison dashboard written: {index_path} "
        f"({len(changed)} changed/added/removed series across "
        f"{changed['page'].nunique() if not changed.empty else 0} pages)"
    )
    return {
        "comparison_index": str(index_path),
        "comparison_dashboards_dir": str(dashboards_out),
        "comparison_summary_csv": str(summary_path),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Snapshot or build the dashboard comparison site.")
    parser.add_argument("output_dir", help="Workflow output dir for an economy, e.g. outputs/USA")
    parser.add_argument("--baseline-dir", default=None, help="Baseline snapshot dir (default: <output_dir>/supporting_files/comparison_baseline)")
    parser.add_argument("--snapshot", action="store_true", help="Snapshot the current bundles as baseline instead of building the comparison")
    args = parser.parse_args(argv)

    publish = Path(args.output_dir)
    baseline = Path(args.baseline_dir) if args.baseline_dir else publish / "supporting_files" / "comparison_baseline"
    if args.snapshot:
        snapshot_dashboard_baseline(publish, baseline)
        return 0
    result = build_comparison_dashboard(publish, baseline, publish / "comparison")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
