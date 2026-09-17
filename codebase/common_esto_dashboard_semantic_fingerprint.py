#%%
"""Build a compact, deterministic semantic fingerprint of a dashboard render.

The fingerprint deliberately reads the renderer's structured outputs rather
than HTML.  It is small enough to embed in an archive and rich enough to locate
page-, chart-, and series-level changes without loading the full dashboard.
"""

from __future__ import annotations

#%%
import base64
import gzip
import hashlib
import io
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


#%%
SCHEMA_VERSION = 2
DEFAULT_NUMERIC_PRECISION = 9
ANCHOR_YEARS = (2022, 2023)
BASELINE_YEAR_RANGE = (2010, 2060)


def _canonical_number(value: object, precision: int) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    number = round(number, precision)
    if number == 0:
        return 0
    if number.is_integer():
        return int(number)
    return number


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _decode_array(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "bdata" in value and "dtype" in value:
        array = np.frombuffer(base64.b64decode(str(value["bdata"])), dtype=str(value["dtype"]))
        return array.tolist()
    return []


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: object) -> bool:
    return _text(value).casefold() in {"1", "true", "yes"}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _unique_text(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame.columns:
        return []
    return sorted({_text(value) for value in frame[column] if _text(value)})


def _numeric_summary(values: list[object], precision: int) -> dict[str, object]:
    numbers = [number for value in values if (number := _canonical_number(value, precision)) is not None]
    if not numbers:
        return {"count": 0, "minimum": None, "maximum": None, "sum": 0}
    return {
        "count": len(numbers),
        "minimum": min(numbers),
        "maximum": max(numbers),
        "sum": _canonical_number(sum(numbers), precision),
    }


def _series_record(
    trace: dict[str, object],
    trace_meta: dict[str, object],
    precision: int,
) -> tuple[dict[str, object], dict[str, str]]:
    x_values = _decode_array(trace.get("x"))
    y_values = _decode_array(trace.get("y"))
    point_count = max(len(x_values), len(y_values))
    if not x_values:
        x_values = [None] * point_count
    if not y_values:
        y_values = [None] * point_count
    points = [
        [_canonical_number(x, precision), _canonical_number(y, precision)]
        for x, y in zip(x_values, y_values)
    ]
    year_values = [point[0] for point in points if isinstance(point[0], int)]
    nonzero_years = [
        point[0]
        for point in points
        if isinstance(point[0], int) and isinstance(point[1], (int, float)) and point[1] != 0
    ]
    anchors = {
        str(year): next((point[1] for point in points if point[0] == year), None)
        for year in ANCHOR_YEARS
    }
    identity = {
        "source_system": _text(trace_meta.get("source_system")).upper(),
        "scenario": _text(trace_meta.get("scenario")),
        "metric": _text(trace_meta.get("metric")) or "both",
        "role": _text(trace_meta.get("role")),
        "category": _text(trace_meta.get("category")),
        "trace_name": _text(trace.get("name")),
        "trace_type": _text(trace.get("type")),
        "stackgroup": _text(trace.get("stackgroup")),
    }
    raw_visibility = trace.get("visible", True)
    visible = raw_visibility is not False and _text(raw_visibility).casefold() not in {
        "false",
        "legendonly",
    }
    record: dict[str, object] = {
        **identity,
        "visible": visible,
        "point_count": point_count,
        "first_year": min(year_values) if year_values else None,
        "last_year": max(year_values) if year_values else None,
        "first_nonzero_year": min(nonzero_years) if nonzero_years else None,
        "last_nonzero_year": max(nonzero_years) if nonzero_years else None,
        "anchors": anchors,
        "values": _numeric_summary([point[1] for point in points], precision),
        "normalized_series_sha256": _sha256(points),
    }
    return record, identity


def _stack_summaries(series_with_points: list[tuple[dict, list[list[object]]]], precision: int) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
    for series, points in series_with_points:
        if not series.get("stackgroup"):
            continue
        key = (
            str(series.get("source_system", "")),
            str(series.get("scenario", "")),
            str(series.get("metric", "both")),
        )
        for year, value in points:
            if isinstance(year, int) and isinstance(value, (int, float)):
                bucket = grouped[key][year]
                if value >= 0:
                    bucket[0] += float(value)
                else:
                    bucket[1] += float(value)
    summaries: list[dict] = []
    for (source, scenario, metric), values in sorted(grouped.items()):
        points = [
            [
                year,
                _canonical_number(positive, precision),
                _canonical_number(negative, precision),
                _canonical_number(positive + negative, precision),
            ]
            for year, (positive, negative) in sorted(values.items())
        ]
        years = [point[0] for point in points]
        summaries.append({
            "source_system": source,
            "scenario": scenario,
            "metric": metric,
            "first_year": min(years) if years else None,
            "last_year": max(years) if years else None,
            "anchors": {
                str(year): next((point[3] for point in points if point[0] == year), None)
                for year in ANCHOR_YEARS
            },
            "positive_anchors": {
                str(year): next((point[1] for point in points if point[0] == year), None)
                for year in ANCHOR_YEARS
            },
            "negative_anchors": {
                str(year): next((point[2] for point in points if point[0] == year), None)
                for year in ANCHOR_YEARS
            },
            "normalized_stack_sha256": _sha256(points),
        })
    return summaries


def _chart_record(
    manifest_row: dict[str, object],
    figure: dict[str, object] | None,
    precision: int,
) -> dict[str, object]:
    figure = figure or {}
    layout = figure.get("layout", {}) if isinstance(figure.get("layout", {}), dict) else {}
    layout_meta = layout.get("meta", {}) if isinstance(layout.get("meta", {}), dict) else {}
    trace_meta = layout_meta.get("trace_meta", [])
    if not isinstance(trace_meta, list):
        trace_meta = []
    raw_series: list[tuple[dict, dict, list[list[object]]]] = []
    for index, trace in enumerate(figure.get("data", [])):
        if not isinstance(trace, dict):
            continue
        meta = trace_meta[index] if index < len(trace_meta) and isinstance(trace_meta[index], dict) else {}
        record, identity = _series_record(trace, meta, precision)
        x_values = _decode_array(trace.get("x"))
        y_values = _decode_array(trace.get("y"))
        points = [
            [_canonical_number(x, precision), _canonical_number(y, precision)]
            for x, y in zip(x_values, y_values)
        ]
        raw_series.append((record, identity, points))
    raw_series.sort(key=lambda item: (_canonical_json(item[1]), item[0]["normalized_series_sha256"]))
    occurrences: dict[str, int] = defaultdict(int)
    series: list[dict] = []
    for record, identity, _ in raw_series:
        identity_hash = _sha256(identity)[:16]
        occurrences[identity_hash] += 1
        record["series_id"] = f"{identity_hash}:{occurrences[identity_hash]}"
        series.append(record)

    residual_fields = {
        key: (_canonical_number(value, precision) if _canonical_number(value, precision) is not None else _text(value))
        for key, value in manifest_row.items()
        if any(token in key.casefold() for token in ("residual", "reconciliation", "coverage_gap"))
        and _text(value)
    }
    record = {
        "chart_key": _text(manifest_row.get("chart_key")),
        "page_key": _text(manifest_row.get("page_key")),
        "page_label": _text(manifest_row.get("page_label")),
        "chart_type": _text(manifest_row.get("chart_type")),
        "suppressed": _truthy(manifest_row.get("suppressed")),
        "flow_label": _text(manifest_row.get("common_flow_label")),
        "product_label": _text(manifest_row.get("common_product_label")),
        "row_count": _canonical_number(manifest_row.get("row_count"), 0),
        "series": series,
        "stack_summaries": _stack_summaries(
            [(series_record, points) for series_record, _, points in raw_series], precision
        ),
        "manifest_residuals": residual_fields,
    }
    record["chart_sha256"] = _sha256(record)
    return record


def _bundle_charts(
    chart_bundles: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, list[str]]]:
    charts: dict[str, dict[str, object]] = {}
    raw_locations: dict[str, list[str]] = defaultdict(list)
    for path in sorted(chart_bundles.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bundle_charts = payload.get("charts", {})
        if not isinstance(bundle_charts, dict):
            raise ValueError(f"Invalid charts object: {path}")
        page_key = path.stem.removesuffix("__charts")
        for raw_key, figure in bundle_charts.items():
            if not isinstance(figure, dict):
                continue
            raw_key = str(raw_key)
            qualified_key = f"{page_key}::{raw_key}"
            if qualified_key in charts:
                raise ValueError(f"Chart key appears twice within page {page_key}: {raw_key}")
            charts[qualified_key] = figure
            raw_locations[raw_key].append(page_key)
    return charts, {
        key: sorted(locations)
        for key, locations in raw_locations.items()
        if len(locations) > 1
    }


def _year_coverage(bundle_charts: dict[str, dict[str, object]]) -> dict[str, object]:
    observed_years = sorted(
        {
            year
            for figure in bundle_charts.values()
            for trace in figure.get("data", [])
            if isinstance(trace, dict)
            for value in _decode_array(trace.get("x"))
            if isinstance((year := _canonical_number(value, 0)), int)
        }
    )
    first_year = min(observed_years) if observed_years else None
    last_year = max(observed_years) if observed_years else None
    continuous = bool(observed_years) and observed_years == list(
        range(first_year, last_year + 1)
    )
    baseline_first_year, baseline_last_year = BASELINE_YEAR_RANGE
    missing_baseline_years = sorted(
        set(range(baseline_first_year, baseline_last_year + 1)) - set(observed_years)
    )
    baseline_coverage_complete = not missing_baseline_years
    if observed_years == list(ANCHOR_YEARS):
        classification = "smoke_only"
    elif baseline_coverage_complete:
        classification = "baseline_full_horizon"
    else:
        classification = "partial_horizon"
    return {
        "observed_years": observed_years,
        "first_year": first_year,
        "last_year": last_year,
        "is_continuous": continuous,
        "classification": classification,
        "baseline_expected_first_year": baseline_first_year,
        "baseline_expected_last_year": baseline_last_year,
        "baseline_coverage_complete": baseline_coverage_complete,
        "missing_baseline_years": missing_baseline_years,
    }


def build_semantic_fingerprint(
    layout: dict[str, Path],
    *,
    identity: dict[str, object] | None = None,
    base_year: int = 2022,
    numeric_precision: int = DEFAULT_NUMERIC_PRECISION,
) -> dict[str, object]:
    """Return the semantic fingerprint for an already completed render."""
    manifest = _read_csv(layout["supporting"] / "chart_manifest.csv")
    assignments = _read_csv(layout["supporting"] / "page_assignment_summary.csv")
    if "chart_key" not in manifest.columns:
        raise ValueError("chart_manifest.csv lacks chart_key")
    required_identity = {"page_key", "chart_key"}
    if not required_identity.issubset(manifest.columns):
        raise ValueError("chart_manifest.csv lacks page_key or chart_key")
    duplicate_identity = manifest.duplicated(["page_key", "chart_key"], keep=False)
    if duplicate_identity.any():
        duplicates = sorted(
            f"{row.page_key}::{row.chart_key}"
            for row in manifest.loc[duplicate_identity, ["page_key", "chart_key"]].itertuples(index=False)
        )
        raise ValueError(f"Duplicate chart keys within a page: {duplicates}")
    bundle_charts, duplicate_raw_bundle_keys = _bundle_charts(layout["chart_bundles"])
    charts: dict[str, dict[str, object]] = {}
    for _, row in manifest.sort_values(["page_key", "chart_key"], kind="stable").iterrows():
        qualified_key = f"{row['page_key']}::{row['chart_key']}"
        charts[qualified_key] = _chart_record(
            row.to_dict(), bundle_charts.get(qualified_key), numeric_precision
        )

    page_keys = sorted(
        set(_unique_text(manifest, "page_key")) | set(_unique_text(assignments, "page_key"))
    )
    pages: dict[str, dict[str, object]] = {}
    for page_key in page_keys:
        manifest_page = manifest[manifest.get("page_key", pd.Series(dtype=str)).eq(page_key)]
        assignment_page = assignments[assignments.get("page_key", pd.Series(dtype=str)).eq(page_key)]
        page_chart_keys = sorted(
            key for key, chart in charts.items() if chart["page_key"] == page_key
        )
        page_series = [
            series
            for key in page_chart_keys
            for series in charts[key]["series"]
        ]
        first_year_values = pd.to_numeric(assignment_page.get("first_year", pd.Series(dtype=str)), errors="coerce").dropna()
        last_year_values = pd.to_numeric(assignment_page.get("last_year", pd.Series(dtype=str)), errors="coerce").dropna()
        row_counts = pd.to_numeric(assignment_page.get("row_count", pd.Series(dtype=str)), errors="coerce").fillna(0)
        page = {
            "label": (_unique_text(manifest_page, "page_label") or _unique_text(assignment_page, "page_label") or [page_key])[0],
            "chart_keys": page_chart_keys,
            "flow_categories": sorted(set(_unique_text(manifest_page, "common_flow_label")) | set(_unique_text(assignment_page, "common_flow_label"))),
            "product_categories": _unique_text(manifest_page, "common_product_label"),
            "routing_statuses": _unique_text(assignment_page, "routing_status"),
            "comparison_scopes": sorted(set(_unique_text(manifest_page, "comparison_scope")) | set(_unique_text(assignment_page, "comparison_scope"))),
            "source_systems": sorted({str(series["source_system"]) for series in page_series if series["source_system"]}),
            "scenarios": sorted({str(series["scenario"]) for series in page_series if series["scenario"]}),
            "first_year": int(first_year_values.min()) if not first_year_values.empty else None,
            "last_year": int(last_year_values.max()) if not last_year_values.empty else None,
            "assigned_row_count": int(row_counts.sum()),
        }
        page["page_sha256"] = _sha256({
            "coverage": {key: value for key, value in page.items() if key not in {"chart_keys"}},
            "charts": {key: charts[key]["chart_sha256"] for key in page_chart_keys},
        })
        pages[page_key] = page

    resolved_identity = {
        "dashboard_key": layout["root"].name,
        "economy": layout["root"].name.split("__", 1)[0],
        "comparison_scope": (_unique_text(manifest, "comparison_scope") or [""])[0],
        "base_year": int(base_year),
        **(identity or {}),
    }
    fingerprint: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "numeric_precision": numeric_precision,
        "anchor_years": list(ANCHOR_YEARS),
        "year_coverage": _year_coverage(bundle_charts),
        "identity": resolved_identity,
        "inventory": {
            "page_count": len(pages),
            "chart_count": len(charts),
            "suppressed_chart_count": sum(bool(chart["suppressed"]) for chart in charts.values()),
            "bundle_chart_count": len(bundle_charts),
            "duplicate_raw_chart_keys_across_pages": duplicate_raw_bundle_keys,
            "unmanifested_bundle_chart_keys": sorted(set(bundle_charts) - set(charts)),
            "missing_unsuppressed_bundle_chart_keys": sorted(
                key for key, chart in charts.items() if not chart["suppressed"] and key not in bundle_charts
            ),
        },
        "pages": pages,
        "charts": charts,
    }
    fingerprint["document_sha256"] = _sha256(fingerprint)
    return fingerprint


def write_semantic_fingerprint(
    layout: dict[str, Path],
    *,
    identity: dict[str, object] | None = None,
    base_year: int = 2022,
    numeric_precision: int = DEFAULT_NUMERIC_PRECISION,
) -> Path:
    """Write and return ``_verification/semantic_fingerprint.json.gz``."""
    fingerprint = build_semantic_fingerprint(
        layout,
        identity=identity,
        base_year=base_year,
        numeric_precision=numeric_precision,
    )
    output_path = layout["verification"] / "semantic_fingerprint.json.gz"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as compressed:
        compressed.write(_canonical_json(fingerprint))
    output_path.write_bytes(buffer.getvalue())
    return output_path


#%%
