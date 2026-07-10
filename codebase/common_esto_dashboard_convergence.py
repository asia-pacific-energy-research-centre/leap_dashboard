#%%
"""Optional capacity-unmet convergence page for the Common ESTO dashboard."""

#%%
from __future__ import annotations

import re
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


CONVERGENCE_NUMERIC_COLUMNS = [
    "pass_count",
    "gap_at_first_pass",
    "gap_at_current_pass",
    "gap_closure_pct",
    "gap_delta_last_pass",
    "allocated_cumulative",
    "clipped_total_current",
    "unresolved_count_current",
]


#%%
######### FUNCTIONS #########
def load_capacity_unmet_convergence(csv_path: Path) -> pd.DataFrame:
    """Load capacity-unmet convergence history with legacy run-id tolerance."""
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=object).fillna("")
    if "run_id" not in df.columns:
        df.insert(0, "run_id", "")
    for column in CONVERGENCE_NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "timestamp_utc" in df.columns:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
    else:
        df["timestamp_utc"] = pd.NaT
    return df


def _infer_legacy_segments(df: pd.DataFrame) -> pd.DataFrame:
    """Add inferred segment ids for legacy rows that predate run_id."""
    out = df.copy()
    if out.empty:
        out["inferred_run_id"] = []
        return out
    segments: list[str] = []
    segment_number = 1
    previous_pass: float | None = None
    for value in out["pass_count"].tolist():
        current_pass = float(value) if pd.notna(value) else 0.0
        if previous_pass is not None and current_pass <= previous_pass:
            segment_number += 1
        segments.append(f"legacy_segment_{segment_number}")
        previous_pass = current_pass
    out["inferred_run_id"] = segments
    return out


def select_latest_convergence_run(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Return the latest run rows and display run id."""
    if df.empty:
        return df.copy(), ""
    with_run_id = df[df["run_id"].astype(str).str.strip() != ""].copy()
    if not with_run_id.empty:
        latest_timestamp = with_run_id.groupby("run_id")["timestamp_utc"].max().sort_values().index[-1]
        run_df = with_run_id[with_run_id["run_id"] == latest_timestamp].copy()
        return run_df.sort_values(["pass_count", "timestamp_utc"]), str(latest_timestamp)

    legacy = _infer_legacy_segments(df)
    latest_segment = str(legacy["inferred_run_id"].iloc[-1])
    run_df = legacy[legacy["inferred_run_id"] == latest_segment].copy()
    return run_df.sort_values(["pass_count", "timestamp_utc"]), latest_segment


def _build_convergence_figure(run_df: pd.DataFrame, run_label: str) -> go.Figure:
    """Build the main pass-by-pass convergence figure."""
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Gap trajectory",
            "Closure percentage",
            "Allocated and clipped totals",
            "Unresolved fuel count",
        ],
        vertical_spacing=0.16,
        horizontal_spacing=0.10,
    )
    x_values = run_df["pass_count"]
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=run_df["gap_at_current_pass"],
            mode="lines+markers",
            name="Current gap",
            line={"color": "#2563eb", "width": 3},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=run_df["gap_delta_last_pass"],
            name="Last-pass gap delta",
            marker={"color": "#64748b"},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=run_df["gap_closure_pct"],
            mode="lines+markers",
            name="Closure %",
            line={"color": "#059669", "width": 3},
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=run_df["allocated_cumulative"],
            mode="lines+markers",
            name="Allocated cumulative",
            line={"color": "#7c3aed", "width": 3},
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=run_df["clipped_total_current"],
            name="Clipped current",
            marker={"color": "#dc2626"},
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=run_df["unresolved_count_current"],
            mode="lines+markers",
            name="Unresolved fuels",
            line={"color": "#ea580c", "width": 3},
        ),
        row=2,
        col=2,
    )
    fig.update_layout(
        title=f"Capacity-unmet convergence: {run_label}",
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=760,
        margin={"l": 60, "r": 24, "t": 86, "b": 52},
        legend={"orientation": "h", "y": -0.10},
    )
    fig.update_xaxes(title_text="Pass")
    fig.update_yaxes(gridcolor="#e5e7eb", zerolinecolor="#cbd5e1")
    return fig


def _build_unresolved_table(run_df: pd.DataFrame) -> str:
    """Return compact HTML for unresolved fuels in the latest pass."""
    if run_df.empty or "unresolved_fuels_current" not in run_df.columns:
        return "<p>No unresolved fuel detail found in the convergence CSV.</p>"
    latest = run_df.iloc[-1]
    fuels = [
        item.strip()
        for item in str(latest.get("unresolved_fuels_current") or "").split(";")
        if item.strip()
    ]
    if not fuels:
        return "<p>No unresolved fuels in the latest recorded pass.</p>"
    items = "".join(f"<li>{escape(fuel)}</li>" for fuel in fuels)
    return f"<ul>{items}</ul>"


def _index_card_html(page_file: str, run_label: str, row_count: int) -> str:
    return (
        '<li style="margin-bottom:8px;">'
        f'<a href="{escape(page_file)}" style="font-weight:600;">Capacity-unmet convergence</a> '
        f'<span style="color:#6b7280;font-size:13px;">({escape(run_label)}, {row_count} pass rows)</span>'
        "</li>"
    )


def append_convergence_link_to_index(index_path: Path, page_file: str, run_label: str, row_count: int) -> None:
    """Add the convergence page link to the generated dashboard index."""
    path = Path(index_path)
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")
    marker = "</ul>"
    card = _index_card_html(page_file, run_label, row_count)
    if "capacity_unmet_convergence.html" in html:
        html = re.sub(
            r'<li style="margin-bottom:8px;"><a href="capacity_unmet_convergence\.html".*?</li>',
            card,
            html,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(html, encoding="utf-8")
        return
    if marker in html:
        html = html.replace(marker, card + marker, 1)
    else:
        html = html.replace("</body>", card + "</body>", 1)
    path.write_text(html, encoding="utf-8")


def write_capacity_unmet_convergence_page(
    convergence_csv_path: Path,
    layout: dict[str, Path],
    *,
    enabled: bool,
) -> dict[str, object] | None:
    """Write an optional dashboard page for the latest capacity-unmet run."""
    if not enabled:
        return None
    history_df = load_capacity_unmet_convergence(Path(convergence_csv_path))
    if history_df.empty:
        print(f"[CONVERGENCE] No capacity-unmet convergence history found at {convergence_csv_path}.")
        return None
    run_df, run_label = select_latest_convergence_run(history_df)
    if run_df.empty:
        print(f"[CONVERGENCE] Capacity-unmet convergence history has no usable run rows: {convergence_csv_path}.")
        return None

    layout["supporting"].mkdir(parents=True, exist_ok=True)
    layout["dashboards"].mkdir(parents=True, exist_ok=True)
    history_out = layout["supporting"] / "capacity_unmet_convergence_history.csv"
    latest_out = layout["supporting"] / "capacity_unmet_convergence_latest_run.csv"
    history_df.to_csv(history_out, index=False)
    run_df.to_csv(latest_out, index=False)

    fig = _build_convergence_figure(run_df, run_label)
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    latest = run_df.iloc[-1]
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Capacity-unmet convergence</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin:0; background:#f4f6f8; color:#111827; }}
    .shell {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .topline {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap; }}
    .back-link {{ color:#2563eb; font-size:13px; text-decoration:none; }}
    .metric-row {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:18px 0; }}
    .metric {{ background:white; border:1px solid #d8dee4; border-radius:8px; padding:12px 14px; }}
    .metric-label {{ color:#64748b; font-size:12px; }}
    .metric-value {{ font-size:20px; font-weight:700; margin-top:4px; }}
    .panel {{ background:white; border:1px solid #d8dee4; border-radius:8px; padding:14px; margin-top:16px; }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topline">
      <div>
        <h1 style="margin:0;">Capacity-unmet convergence</h1>
        <p style="margin:6px 0 0;color:#64748b;">Latest run: {escape(run_label)}</p>
      </div>
      <a class="back-link" href="index.html">Back to dashboard index</a>
    </div>
    <div class="metric-row">
      <div class="metric"><div class="metric-label">Pass rows</div><div class="metric-value">{len(run_df)}</div></div>
      <div class="metric"><div class="metric-label">Current gap</div><div class="metric-value">{float(latest.get("gap_at_current_pass") or 0):,.2f}</div></div>
      <div class="metric"><div class="metric-label">Closure</div><div class="metric-value">{float(latest.get("gap_closure_pct") or 0):,.1f}%</div></div>
      <div class="metric"><div class="metric-label">Unresolved fuels</div><div class="metric-value">{int(float(latest.get("unresolved_count_current") or 0))}</div></div>
    </div>
    <div class="panel">{chart_html}</div>
    <div class="panel">
      <h2 style="margin:0 0 8px 0;font-size:18px;">Latest unresolved fuels</h2>
      {_build_unresolved_table(run_df)}
    </div>
  </div>
</body>
</html>
"""
    page_path = layout["dashboards"] / "capacity_unmet_convergence.html"
    page_path.write_text(html, encoding="utf-8")
    append_convergence_link_to_index(layout["dashboards"] / "index.html", page_path.name, run_label, len(run_df))
    print(f"[CONVERGENCE] Capacity-unmet convergence page: {page_path}")
    return {
        "page": str(page_path),
        "history_csv": str(history_out),
        "latest_run_csv": str(latest_out),
        "run_label": run_label,
        "pass_rows": int(len(run_df)),
    }


#%%
