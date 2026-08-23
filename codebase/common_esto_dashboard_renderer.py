#%%
"""Render a static dashboard from common ESTO comparison data."""

#%%
import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

try:  # pragma: no cover - import shim
    from common_esto_dashboard_guide import build_guide_fragments
except ModuleNotFoundError:  # pragma: no cover - import shim
    from codebase.common_esto_dashboard_guide import build_guide_fragments

# The emissions module imports this one lazily inside its functions, so this
# top-level import stays acyclic. Both spellings are supported because the
# workflow puts codebase/ on sys.path while tests import codebase as a package.
try:  # pragma: no cover - import shim
    from common_esto_dashboard_emissions import build_emissions_page, emissions_page_enabled
except ModuleNotFoundError:  # pragma: no cover - import shim
    from codebase.common_esto_dashboard_emissions import (
        build_emissions_page,
        emissions_page_enabled,
    )

try:  # pragma: no cover - import shim
    from common_esto_dashboard_data import ninth_base_year_for_rows
except ModuleNotFoundError:  # pragma: no cover - import shim
    from codebase.common_esto_dashboard_data import ninth_base_year_for_rows


def _chart_unit(df: pd.DataFrame, default: str = "PJ") -> str:
    """Return the unit carried by a chart's rows, falling back to PJ.

    Every existing input is PJ-denominated energy data (see ``DEFAULT_UNIT``
    in ``common_esto_dashboard_data.py``); this reads the unit each chart's
    own rows carry rather than assuming it, so hover text and axis labels
    stay correct if a future series carries a different one. A frame with no
    ``unit`` column, or a genuinely mixed one (should not happen post
    ``_keep_one_measure_for_energy_balance_charts``), falls back to
    ``default`` rather than guessing.
    """
    if df.empty or "unit" not in df.columns:
        return default
    values = df["unit"].dropna().astype(str)
    if values.empty:
        return default
    mode = values.mode()
    return str(mode.iloc[0]) if not mode.empty else default


CODE_MATCH_COLUMNS = [
    "common_flow_code",
    "common_flow_label",
    "component_flow_code",
    "component_esto_flow",
    "component_flow_name",
]

# Page-root ownership is resolved from the common axis itself. Component names
# and display labels remain available to the legacy keyword fallback, but must
# not turn a coincidental number in prose into a hierarchy match.
PAGE_ROOT_CODE_COLUMN = "common_flow_code"

LABEL_MATCH_COLUMNS = [
    "common_flow_label",
    "common_flow_name",
    "component_esto_flow",
    "component_flow_name",
]

SUMMARY_COMPONENT_COLUMNS = [
    "component_esto_flow",
    "component_esto_product",
    "component_flow_code",
    "component_flow_name",
    "component_product_code",
    "component_product_name",
]



#%%
def safe_slug(value: object) -> str:
    """Convert a label into a stable file-safe slug."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "item"


_PUBLIC_PAGE_FILES = {
    "total_demand": "energy_balance_overview.html",
    "others": "other_demand.html",
}


def page_file_name(page_key: object) -> str:
    """Return the public HTML filename for an internal dashboard page key."""
    clean_key = safe_slug(page_key)
    return _PUBLIC_PAGE_FILES.get(clean_key, f"{clean_key}.html")


def write_legacy_page_redirect(
    dashboards_directory: Path,
    page_key: object,
) -> None:
    """Keep old generated links working after a public page-file rename."""
    clean_key = safe_slug(page_key)
    public_file = page_file_name(clean_key)
    legacy_file = f"{clean_key}.html"
    if legacy_file == public_file or not (dashboards_directory / public_file).is_file():
        return
    (dashboards_directory / legacy_file).write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"refresh\" content=\"0; url={escape(public_file)}\">"
        f"<link rel=\"canonical\" href=\"{escape(public_file)}\">"
        "<title>Opening dashboard</title></head><body>"
        f"<a href=\"{escape(public_file)}\">Open the dashboard</a>"
        "</body></html>",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def join_unique_text(values: pd.Series) -> str:
    """Join unique non-empty values in stable display order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for part in str(value or "").split(";"):
            text = part.strip()
            if not text or text.lower() == "nan":
                continue
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
    return "; ".join(out)


def series_key(source_system: object, scenario: object) -> str:
    """Create a stable series key."""
    return f"{source_system}|{scenario}".strip("|")


def series_label_from_values(source_system: object, scenario: object, series_labels: dict[str, str]) -> str:
    """Return a display label for a source/scenario series."""
    key = series_key(source_system, scenario)
    if key in series_labels:
        return series_labels[key]
    key_casefold_map = {str(k).casefold(): v for k, v in series_labels.items()}
    return key_casefold_map.get(key.casefold(), key)


def dataset_display_name(source_system: object) -> str:
    """Return the short dataset name used in chart notes."""
    names = {
        "ESTO": "ESTO",
        "ESTO_EXTENDED": "ESTO Extended",
        "LEAP": "LEAP",
        "NINTH": "9th edition",
    }
    source = str(source_system).strip().upper()
    return names.get(source, source or "unknown dataset")


def stacked_area_dataset_note(sources: set[str], subject: str) -> str:
    """Describe the dataset(s) contributing the stacked traces."""
    if not sources:
        return "Stacked areas: no detailed dataset available."
    normalized_sources = {str(source).strip().upper() for source in sources}
    if normalized_sources == {"ESTO"}:
        return (
            f"Stacked areas: ESTO historical {subject} detail through the base year; "
            "no detailed projection dataset is available."
        )
    names = ", ".join(dataset_display_name(source) for source in sorted(sources))
    return f"Stacked areas: {names} {subject} detail for the selected scenario."


def aggregate_only_tfec_note(
    stacked_sources: set[str],
    primary_source: object,
) -> str:
    """Explain when LEAP's aggregate-only demand prevents a true TFEC split."""
    if (
        str(primary_source).strip().casefold() == "leap"
        and "LEAP" not in {str(source).strip().upper() for source in stacked_sources}
        and "NINTH" in {str(source).strip().upper() for source in stacked_sources}
    ):
        return (
            " Warning: LEAP demand detail is aggregate-only for this economy, "
            "so the stacked projection uses the 9th-edition demand frontier. "
            "The LEAP TFEC line cannot remove non-energy use unless that branch "
            "is separately modelled and mapped; treat this TFEC comparison as "
            "including any non-energy demand retained in the aggregate."
        )
    return ""


def series_label(row: pd.Series, series_labels: dict[str, str]) -> str:
    """Return a display label for a source/scenario series."""
    return series_label_from_values(row["source_system"], row["scenario"], series_labels)


def scenario_toggle_tag(source_system: object, scenario: object) -> str:
    """Classify a series for the REF/TGT dashboard toggle.

    ESTO historical rows are tagged "esto" and always stay visible; LEAP/9th
    rows are tagged "ref" or "tgt" so the client-side toggle can show/hide
    them. Anything else falls back to "esto" (always visible) rather than
    silently disappearing under either toggle state.
    """
    scenario_text = str(scenario or "").strip().casefold()
    if scenario_text == "reference":
        return "ref"
    if scenario_text == "target":
        return "tgt"
    return "esto"


def trace_meta_entry(
    source_system: object, scenario: object, active_visible: bool | str = True, metric: str = "both"
) -> dict:
    """Build one entry of a figure's trace_meta list (see scenario_toggle_tag).

    ``metric`` carries a second, independent dimension used only by the
    TFC/TFEC sector chart ("tfc"/"tfec"/"both"); every other chart leaves it
    at the default "both" so the REF/TGT toggle is the only axis that applies.
    """
    return {
        "source_system": str(source_system).strip().upper(),
        "tag": scenario_toggle_tag(source_system, scenario),
        "metric": metric,
        "active_visible": active_visible,
    }


def chart_dataset_tokens_from_figure(figure: go.Figure) -> str:
    """Return source systems represented by actual non-empty figure traces.

    Chart-card filtering is a statement about what the user can see, not every
    source row supplied to the builder before frontier and fallback selection.
    ``trace_meta`` is therefore the authority after chart construction.
    """
    meta = figure.layout.meta
    trace_meta = meta.get("trace_meta", []) if isinstance(meta, dict) else []
    tokens: set[str] = set()
    for position, trace in enumerate(figure.data):
        if position >= len(trace_meta):
            continue
        source = str(trace_meta[position].get("source_system", "")).strip().upper()
        if not source:
            continue
        x_values = getattr(trace, "x", None)
        y_values = getattr(trace, "y", None)
        if x_values is not None and len(x_values) == 0:
            continue
        if y_values is not None and len(y_values) == 0:
            continue
        tokens.add(source)
    return ",".join(sorted(tokens))


def code_candidate_text(value: object) -> str:
    """Return the leading ESTO-style code expression from a label or code field."""
    text = str(value or "").strip()
    if not text:
        return ""
    first_token = text.split(maxsplit=1)[0]
    return first_token if re.search(r"\d", first_token) else ""


def split_code_range(chunk: str) -> tuple[str, str | None]:
    """Split a comma chunk into start/end codes where it represents a range."""
    clean = str(chunk or "").strip()
    if "-" not in clean:
        return clean, None
    start, end = clean.split("-", maxsplit=1)
    return start.strip(), end.strip()


def parse_code_expression(code_or_label: object) -> list[dict[str, str]]:
    """Parse a generated/common ESTO code expression into component/range records.

    Examples understood by this function include:
    - 07.12-07.17,07.99 Petroleum products
    - 09.01.01,09.02.01 Electricity plants
    - 08,08.01-08.04,08.99 Refinery and blending transfers

    The function does not expand ranges. It preserves each range as start/end
    codes so page rules can match generated labels mechanically.
    """
    code_text = code_candidate_text(code_or_label)
    if not code_text:
        return []
    records: list[dict[str, str]] = []
    for chunk in code_text.split(","):
        start, end = split_code_range(chunk)
        if not re.match(r"^\d", start):
            continue
        records.append({"raw": chunk.strip(), "start": start, "end": end or ""})
    return records


def get_code_parts(code_or_label: object) -> list[str]:
    """Extract representative ESTO-style code parts from a code expression."""
    records = parse_code_expression(code_or_label)
    return [record["start"] for record in records if record.get("start")]


def canonical_code(code_or_label: object) -> str:
    """Return the first exact code represented in a common ESTO code expression."""
    parts = get_code_parts(code_or_label)
    return parts[0] if parts else ""


def code_depth(code_or_label: object) -> int:
    """Return the maximum apparent hierarchy depth for an ESTO code expression."""
    records = parse_code_expression(code_or_label)
    if not records:
        return 0
    codes = []
    for record in records:
        codes.append(record["start"])
        if record.get("end"):
            codes.append(record["end"])
    return max(code.count(".") + 1 for code in codes if code)


def code_prefix(code_or_label: object, level: int) -> str:
    """Return a hierarchy prefix at the requested level."""
    code = canonical_code(code_or_label)
    if not code:
        return ""
    parts = code.split(".")
    if len(parts) < level:
        return ""
    return ".".join(parts[:level])


def code_matches_prefix(code: str, prefix: str) -> bool:
    """Return True when one ESTO code sits at or below a prefix."""
    clean_code = str(code or "").strip()
    clean_prefix = str(prefix or "").strip()
    if not clean_code or not clean_prefix:
        return False
    return clean_code == clean_prefix or clean_code.startswith(clean_prefix + ".")


def code_range_matches_prefix(start_code: str, end_code: str, prefix: str) -> bool:
    """Return True when either end of a generated range matches a prefix.

    Ranges are normally made within one parent, so checking the start and end is
    enough for page assignment without expanding every possible code.
    """
    if code_matches_prefix(start_code, prefix):
        return True
    if end_code and code_matches_prefix(end_code, prefix):
        return True
    return False


def code_expression_matches_prefix(code_or_label: object, prefix: str) -> bool:
    """Return True when any component/range in a code expression matches a prefix."""
    if str(code_or_label or "").strip() == str(prefix or "").strip():
        return True
    for record in parse_code_expression(code_or_label):
        if code_range_matches_prefix(record.get("start", ""), record.get("end", ""), prefix):
            return True
    return False


def code_expression_matches_any_prefix(code_or_label: object, prefixes: list[object]) -> bool:
    """Return True when a code expression matches any configured prefix."""
    return any(code_expression_matches_prefix(code_or_label, str(prefix)) for prefix in prefixes)


def _numeric_code_parts(code: object) -> tuple[int, ...] | None:
    """Return comparable numeric segments for one ESTO code."""
    clean = str(code or "").strip()
    if not clean:
        return None
    parts = clean.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _code_is_within_record(code: object, record: dict[str, str]) -> bool:
    """Return True when one exact code is represented by a parsed code record."""
    clean_code = str(code or "").strip()
    start = str(record.get("start", "")).strip()
    end = str(record.get("end", "")).strip()
    if not clean_code or not start:
        return False
    if not end:
        return code_matches_prefix(clean_code, start)

    code_parts = _numeric_code_parts(clean_code)
    start_parts = _numeric_code_parts(start)
    end_parts = _numeric_code_parts(end)
    if code_parts is None or start_parts is None or end_parts is None:
        return clean_code in {start, end}
    if len(start_parts) != len(end_parts) or len(code_parts) < len(start_parts):
        return False
    comparable_code = code_parts[:len(start_parts)]
    return start_parts <= comparable_code <= end_parts


def _code_expression_contains_expression(parent: object, child: object) -> bool:
    """Return True when every component of `child` belongs to `parent`."""
    parent_records = parse_code_expression(parent)
    child_records = parse_code_expression(child)
    if not parent_records or not child_records:
        return False
    for child_record in child_records:
        endpoints = [child_record.get("start", "")]
        if child_record.get("end"):
            endpoints.append(child_record["end"])
        if not all(
            any(_code_is_within_record(endpoint, parent_record) for parent_record in parent_records)
            for endpoint in endpoints
        ):
            return False
    return True


LNG_HISTORICAL_COVERAGE_NOTE = (
    "Note: ESTO historical data do not contain all LNG activity, so a large "
    "change between the base year and projections can be expected and does not "
    "indicate a dashboard or mapping error;"
)


def chart_note_with_lng_coverage(note: str, chart_df: pd.DataFrame) -> str:
    """Append the LNG coverage warning when a chart contains flow 09.06.02."""
    if chart_df.empty:
        return str(note or "")
    flow_columns = [
        column
        for column in ("common_flow_code", "component_flow_code", "common_flow_label")
        if column in chart_df.columns
    ]
    contains_lng_activity = any(
        code_expression_matches_prefix(value, "09.06.02")
        for column in flow_columns
        for value in chart_df[column].dropna().unique()
    )
    clean_note = str(note or "").strip()
    if not contains_lng_activity or LNG_HISTORICAL_COVERAGE_NOTE in clean_note:
        return clean_note
    return f"{clean_note} {LNG_HISTORICAL_COVERAGE_NOTE}".strip()


def _flow_subtree_is_page_complete(
    assigned_df: pd.DataFrame,
    page_key: str,
    root_code: object,
) -> bool:
    """Return True when every routed descendant of a flow root stays on one page."""
    required = {"common_flow_code", "_page_key"}
    if assigned_df.empty or not required.issubset(assigned_df.columns):
        return False
    root_expression = code_candidate_text(root_code)
    if not root_expression:
        return False
    routed_nodes = assigned_df[["common_flow_code", "_page_key"]].drop_duplicates()
    descendants = routed_nodes[
        routed_nodes["common_flow_code"].apply(
            lambda value: _code_expression_contains_expression(
                root_expression,
                code_candidate_text(value),
            )
        )
    ]
    if descendants.empty:
        return False
    routed_pages = {
        safe_slug(value)
        for value in descendants["_page_key"].dropna().astype(str)
        if str(value).strip()
    }
    return routed_pages == {safe_slug(page_key)}


def _is_compound_code_expression(value: object) -> bool:
    """Return True for a comma list or inclusive range of ESTO codes."""
    records = parse_code_expression(value)
    return len(records) > 1 or any(record.get("end") for record in records)


def code_axis_for_group_col(group_col: str) -> str | None:
    """Return the colour-map axis for a grouping column, or None if not code-named."""
    if "product" in group_col:
        return "product"
    if "flow" in group_col:
        return "flow"
    return None


def flow_name_without_code(flow_label: object) -> str:
    """Remove the leading ESTO code expression from a flow label."""
    text = str(flow_label or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 and code_candidate_text(text) else text


def section_order_key(label: object) -> tuple[object, ...]:
    """Sort coded sections by their leading ESTO code, then uncoded labels by name."""
    text = str(label or "").strip()
    records = parse_code_expression(text)
    if records:
        numeric_parts = _numeric_code_parts(records[0].get("start", ""))
        if numeric_parts is not None:
            return (0, numeric_parts, text.casefold())
    return (1, (), flow_name_without_code(text).casefold(), text.casefold())


def _section_tree_order_key(
    section_label: object,
    node_labels: list[object],
) -> tuple[object, ...]:
    """Order a rendered section by its first visible navigation node.

    Section headings are often descriptive page groupings rather than coded
    ESTO labels. Using the first visible child keeps the body in the same
    order as the numeric/alphabetical navigation chips.
    """
    node_keys = [section_order_key(label) for label in node_labels]
    return min(node_keys) if node_keys else section_order_key(section_label)


def sign_note_for_chart(df: pd.DataFrame) -> str:
    """Return a compact sign-convention note for chart titles."""
    required = {"sign_convention", "expected_sign", "positive_value_meaning", "negative_value_meaning"}
    if df.empty or not required.issubset(set(df.columns)):
        return ""
    rules = (
        df[["sign_convention", "expected_sign", "positive_value_meaning", "negative_value_meaning"]]
        .drop_duplicates()
        .sort_values(["sign_convention", "expected_sign"])
        .to_dict("records")
    )
    if len(rules) == 1:
        rule = rules[0]
        expected_sign = str(rule.get("expected_sign", "both"))
        if expected_sign == "positive":
            return f"Sign: + = {rule['positive_value_meaning']}"
        if expected_sign == "negative":
            return f"Sign: - = {rule['negative_value_meaning']}"
        return f"Signs: + = {rule['positive_value_meaning']}; - = {rule['negative_value_meaning']}"
    if len(rules) <= 3:
        labels = ", ".join(str(rule["sign_convention"]) for rule in rules)
        return f"Signs vary by flow: {labels}. Hover points for sign meaning."
    return "Signs vary by flow. Hover points for sign meaning."


def title_with_sign_note(title: str, df: pd.DataFrame) -> str:
    """Add a short sign-convention subtitle to a chart title."""
    note = sign_note_for_chart(df)
    if not note:
        return title
    return f"{title}<br><sup>{escape(note)}</sup>"


def normalise_rule_list(rule: dict, new_key: str, legacy_key: str) -> list[object]:
    """Return rule values from the current or legacy config key."""
    values = rule.get(new_key, rule.get(legacy_key, []))
    if values is None:
        return []
    return values if isinstance(values, list) else [values]


def text_columns_mask(df: pd.DataFrame, columns: list[str], patterns: list[object]) -> pd.Series:
    """Return rows where any available text column contains any pattern."""
    mask = pd.Series(False, index=df.index)
    for pattern in patterns:
        if pattern in (None, ""):
            continue
        regex = re.escape(str(pattern))
        for column in columns:
            if column not in df.columns:
                continue
            mask = mask | df[column].astype(str).str.contains(regex, case=False, na=False, regex=True)
    return mask


def regex_columns_mask(df: pd.DataFrame, columns: list[str], patterns: list[object]) -> pd.Series:
    """Return rows where any available text column matches any configured regex."""
    mask = pd.Series(False, index=df.index)
    for pattern in patterns:
        if pattern in (None, ""):
            continue
        for column in columns:
            if column not in df.columns:
                continue
            mask = mask | df[column].astype(str).str.contains(str(pattern), case=False, na=False, regex=True)
    return mask


def code_columns_mask(df: pd.DataFrame, columns: list[str], prefixes: list[object]) -> pd.Series:
    """Return rows where any code-expression column matches any prefix."""
    mask = pd.Series(False, index=df.index)
    if not prefixes:
        return mask
    for column in columns:
        if column not in df.columns:
            continue
        mask = mask | df[column].apply(lambda value: code_expression_matches_any_prefix(value, prefixes))
    return mask


def rule_mask(df: pd.DataFrame, rule: dict) -> pd.Series:
    """Return rows matching a page recogniser rule.

    Rules match generated code expressions, not just literal labels. This allows
    labels such as `09.01.01,09.02.01 Electricity plants` to match the power page
    even though the generated label is not an exact original ESTO row.
    """
    code_columns = rule.get("code_match_columns") or CODE_MATCH_COLUMNS
    label_columns = rule.get("label_match_columns") or LABEL_MATCH_COLUMNS
    include_prefixes = normalise_rule_list(rule, "include_flow_code_prefixes", "flow_code_prefixes")
    include_keywords = normalise_rule_list(rule, "include_flow_keywords", "flow_keywords")
    include_regexes = normalise_rule_list(rule, "include_flow_regexes", "flow_regexes")
    exclude_prefixes = normalise_rule_list(rule, "exclude_flow_code_prefixes", "")
    exclude_keywords = normalise_rule_list(rule, "exclude_flow_keywords", "")
    exclude_regexes = normalise_rule_list(rule, "exclude_flow_regexes", "")

    include_mask = pd.Series(False, index=df.index)
    include_mask = include_mask | code_columns_mask(df, code_columns, include_prefixes)
    include_mask = include_mask | text_columns_mask(df, label_columns, include_keywords)
    include_mask = include_mask | regex_columns_mask(df, label_columns, include_regexes)

    exclude_mask = pd.Series(False, index=df.index)
    exclude_mask = exclude_mask | code_columns_mask(df, code_columns, exclude_prefixes)
    exclude_mask = exclude_mask | text_columns_mask(df, label_columns, exclude_keywords)
    exclude_mask = exclude_mask | regex_columns_mask(df, label_columns, exclude_regexes)
    return include_mask & ~exclude_mask


def sorted_page_rules(page_rules: list[dict]) -> list[dict]:
    """Return page rules in explicit priority order while preserving list order ties."""
    indexed = list(enumerate(page_rules))
    indexed.sort(key=lambda item: (int(item[1].get("priority", 9999)), item[0]))
    return [rule for _, rule in indexed]


def _matching_root_depth(code_expression: object, prefixes: list[object]) -> tuple[int, str]:
    """Return the deepest configured root represented by *code_expression*.

    Matching is hierarchical and boundary-safe: root ``14`` matches ``14`` or
    ``14.*``, never ``5.14`` or ``114``. A compound/range category is tested as
    one expression so every page can state only its highest-level roots.
    """
    records = parse_code_expression(code_expression)
    matches: list[str] = []
    for raw_prefix in prefixes:
        prefix = str(raw_prefix or "").strip()
        if not prefix:
            continue
        for record in records:
            if code_range_matches_prefix(
                record.get("start", ""), record.get("end", ""), prefix
            ) or (
                record.get("end", "")
                and _code_is_within_record(prefix, record)
            ):
                matches.append(prefix)
                break
    if not matches:
        return 0, ""
    selected = max(matches, key=lambda value: (code_depth(value), len(value), value))
    return code_depth(selected), selected


def _routing_special_case_mask(df: pd.DataFrame, special_case: dict) -> pd.Series:
    """Return rows selected by one explicit routing special case."""
    match = special_case.get("match", {}) or {}
    mask = pd.Series(True, index=df.index)
    has_selector = False

    exact_code = str(match.get("common_flow_code_exact", "")).strip()
    if exact_code:
        has_selector = True
        mask = mask & df.get(
            "common_flow_code", pd.Series("", index=df.index)
        ).astype(str).str.strip().eq(exact_code)

    prefixes = match.get("common_flow_code_prefixes", []) or []
    if prefixes:
        has_selector = True
        mask = mask & df.get(
            "common_flow_code", pd.Series("", index=df.index)
        ).apply(lambda value: code_expression_matches_any_prefix(value, prefixes))

    keywords = match.get("common_flow_keywords", []) or []
    if keywords:
        has_selector = True
        mask = mask & text_columns_mask(df, LABEL_MATCH_COLUMNS, keywords)

    return mask if has_selector else pd.Series(False, index=df.index)


def _compound_component_pages(code_expression: object, page_rules: list[dict]) -> set[str]:
    """Resolve each compound endpoint independently to its deepest page root."""
    resolved_pages: set[str] = set()
    for record in parse_code_expression(code_expression):
        endpoints = [record.get("start", "")]
        if record.get("end"):
            endpoints.append(record["end"])
        for endpoint in endpoints:
            endpoint_candidates: list[tuple[int, str]] = []
            for rule in page_rules:
                prefixes = normalise_rule_list(
                    rule, "include_flow_code_prefixes", "flow_code_prefixes"
                )
                depth, _ = _matching_root_depth(endpoint, prefixes)
                if depth:
                    endpoint_candidates.append((depth, str(rule.get("page_key", "page"))))
            if not endpoint_candidates:
                continue
            best_depth = max(item[0] for item in endpoint_candidates)
            resolved_pages.update(
                page for depth, page in endpoint_candidates if depth == best_depth
            )
    return resolved_pages


def assign_pages(
    df: pd.DataFrame,
    page_rules: list[dict],
    routing_special_cases: list[dict] | None = None,
) -> pd.DataFrame:
    """Assign rows by explicit special case, then most-specific page root.

    Code roots are authoritative. Label keywords remain a compatibility
    fallback only for rows that have no root match. Rows with equally specific
    roots on different pages remain unassigned and are marked ``ambiguous`` so
    a new exact special case can resolve them deliberately.
    """
    out = df.copy()
    out["_page_key"] = "unassigned"
    out["_page_label"] = "Unassigned"
    out["_section_key"] = "unassigned"
    out["_section_label"] = "Unassigned"
    out["_page_rule_priority"] = ""
    out["_page_rule_note"] = "No sector/page recogniser matched this generated flow label or component code."
    out["_routing_status"] = "unassigned"
    out["_routing_candidates"] = ""
    out["_routing_special_case"] = ""
    remaining = pd.Series(True, index=out.index)

    # Exact, documented exceptions are evaluated before ordinary roots. They
    # cover compound/temporary categories that cannot be owned by one root.
    for special_case in routing_special_cases or []:
        if not special_case.get("enabled", True):
            continue
        if str(special_case.get("action", "route")) != "route":
            continue
        mask = _routing_special_case_mask(out, special_case) & remaining
        if not mask.any():
            continue
        page_key = str(special_case.get("page_key", "unassigned"))
        page_label = str(special_case.get("page_label", page_key))
        out.loc[mask, "_page_key"] = page_key
        out.loc[mask, "_page_label"] = page_label
        out.loc[mask, "_section_key"] = str(special_case.get("section_key", page_key))
        out.loc[mask, "_section_label"] = str(special_case.get("section_label", page_label))
        out.loc[mask, "_page_rule_priority"] = "special"
        out.loc[mask, "_page_rule_note"] = str(special_case.get("reason", ""))
        out.loc[mask, "_routing_status"] = "special_case"
        out.loc[mask, "_routing_special_case"] = str(special_case.get("case_id", ""))
        remaining = remaining & ~mask

    # Resolve ordinary hierarchy roots without relying on rule ordering. The
    # deepest matching root wins; ties on the same page are harmless.
    root_candidates: dict[object, list[tuple[int, str, dict]]] = {}
    for rule in page_rules:
        prefixes = normalise_rule_list(rule, "include_flow_code_prefixes", "flow_code_prefixes")
        if not prefixes:
            continue
        exclude_prefixes = normalise_rule_list(rule, "exclude_flow_code_prefixes", "")
        for index in out.index[remaining]:
            code_expression = out.at[index, PAGE_ROOT_CODE_COLUMN] if PAGE_ROOT_CODE_COLUMN in out.columns else ""
            if exclude_prefixes and code_expression_matches_any_prefix(code_expression, exclude_prefixes):
                continue
            depth, root = _matching_root_depth(code_expression, prefixes)
            if depth:
                root_candidates.setdefault(index, []).append((depth, root, rule))

    for index, candidates in root_candidates.items():
        component_pages = _compound_component_pages(
            out.at[index, PAGE_ROOT_CODE_COLUMN], page_rules
        )
        if len(component_pages) > 1:
            out.at[index, "_routing_status"] = "ambiguous"
            out.at[index, "_routing_candidates"] = "; ".join(sorted(component_pages))
            out.at[index, "_page_rule_note"] = (
                "Compound category components resolve to different pages; "
                "add an explicit routing special case."
            )
            remaining.at[index] = False
            continue
        best_depth = max(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_depth]
        page_keys = {str(item[2].get("page_key", "page")) for item in best}
        out.at[index, "_routing_candidates"] = "; ".join(
            sorted(f"{item[2].get('page_key', 'page')}:{item[1]}" for item in best)
        )
        if len(page_keys) != 1:
            out.at[index, "_routing_status"] = "ambiguous"
            out.at[index, "_page_rule_note"] = "Equally specific page roots matched different pages."
            remaining.at[index] = False
            continue
        # Preserve config order only to choose display metadata when several
        # roots belonging to the same page tie.
        _, root, rule = best[0]
        page_key = str(rule.get("page_key", "page"))
        page_label = str(rule.get("page_label", rule.get("page_key", "Page")))
        out.at[index, "_page_key"] = page_key
        out.at[index, "_page_label"] = page_label
        out.at[index, "_section_key"] = str(rule.get("section_key", page_key))
        out.at[index, "_section_label"] = str(rule.get("section_label", page_label))
        out.at[index, "_page_rule_priority"] = f"root:{root}"
        out.at[index, "_page_rule_note"] = str(rule.get("rule_note", ""))
        out.at[index, "_routing_status"] = "page_root"
        remaining.at[index] = False

    # Retain keyword compatibility for categories that no configured root can
    # recognise. It is visibly recorded and never overrides a root assignment.
    for rule in sorted_page_rules(page_rules):
        keywords = normalise_rule_list(rule, "include_flow_keywords", "flow_keywords")
        regexes = normalise_rule_list(rule, "include_flow_regexes", "flow_regexes")
        if not keywords and not regexes:
            continue
        keyword_rule = dict(rule)
        keyword_rule["flow_code_prefixes"] = []
        keyword_rule["include_flow_code_prefixes"] = []
        mask = rule_mask(out, keyword_rule) & remaining
        if not mask.any():
            continue
        page_key = str(rule.get("page_key", "page"))
        page_label = str(rule.get("page_label", page_key))
        out.loc[mask, "_page_key"] = page_key
        out.loc[mask, "_page_label"] = page_label
        out.loc[mask, "_section_key"] = str(rule.get("section_key", page_key))
        out.loc[mask, "_section_label"] = str(rule.get("section_label", page_label))
        out.loc[mask, "_page_rule_priority"] = str(rule.get("priority", ""))
        out.loc[mask, "_page_rule_note"] = str(rule.get("rule_note", ""))
        out.loc[mask, "_routing_status"] = "keyword_fallback"
        remaining = remaining & ~mask
    return out


def _metadata_tokens(value: object) -> set[str]:
    """Return normalized tokens from semicolon-delimited component metadata."""
    return {
        part.strip()
        for part in str(value or "").split(";")
        if part.strip()
    }


def _rollup_contributor_codes(value: object) -> set[str]:
    """Return codes from upstream ``SOURCE: code label`` contributor metadata."""
    codes: set[str] = set()
    for contributor in str(value or "").split("|"):
        label = contributor.split(":", 1)[-1].strip()
        code = canonical_code(label)
        if code:
            codes.add(code)
    return codes


def prepare_other_transformation_page_rows(
    page_df: pd.DataFrame,
    comparison_context_df: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Apply the declared presentation boundary for Other transformation.

    Transformation rows keep the own use embedded in LEAP auxiliary-fuel
    inputs and therefore receive an explicit inclusive display label. Exact
    own-use rows already represented by an upstream ``(including own use)``
    Common ESTO boundary are suppressed from the residual own-use section.
    This consumes component and non-expanding-rollup contributor metadata
    emitted by ``leap_mappings``; it does not recreate rollup membership in
    dashboard configuration.
    """
    if page_df.empty or not config.get("enabled", False):
        return page_df

    out = page_df.copy()
    context = comparison_context_df if not comparison_context_df.empty else out
    inclusive_mask = context["common_flow_label"].astype(str).str.contains(
        "(including own use)", case=False, regex=False
    )
    inclusive_context = context[inclusive_mask]

    absorbed_own_use_codes: set[str] = set()
    if "component_flow_code" in inclusive_context.columns:
        for value in inclusive_context["component_flow_code"]:
            absorbed_own_use_codes.update(
                code
                for token in _metadata_tokens(value)
                if (code := canonical_code(token)).startswith("10.01")
            )
    if "non_expanding_contributor_inputs" in inclusive_context.columns:
        for value in inclusive_context["non_expanding_contributor_inputs"]:
            absorbed_own_use_codes.update(
                code
                for code in _rollup_contributor_codes(value)
                if code.startswith("10.01")
            )

    codes = out["common_flow_code"].map(canonical_code)
    labels = out["common_flow_label"].astype(str)
    already_inclusive = labels.str.contains(
        "(including own use)", case=False, regex=False
    )

    # Prefer the real inclusive Common ESTO row only when the same source
    # series and product actually publish that replacement. An inclusive row
    # in ESTO must not suppress a plain LEAP leaf that carries the projection.
    replacement_context_columns = [
        column
        for column in ("comparison_scope", "source_system", "economy", "scenario")
        if column in out.columns and column in inclusive_context.columns
    ]
    for product_column in ("common_product_code", "common_product_label"):
        if product_column in out.columns and product_column in inclusive_context.columns:
            replacement_context_columns.append(product_column)
            break

    def boundary_keys(frame: pd.DataFrame) -> pd.MultiIndex:
        key_frame = pd.DataFrame(index=frame.index)
        for column in replacement_context_columns:
            key_frame[column] = (
                frame[column].fillna("").astype(str).str.strip().str.casefold()
            )
        key_frame["_boundary_flow_code"] = frame["common_flow_code"].map(canonical_code)
        return pd.MultiIndex.from_frame(key_frame)

    has_inclusive_replacement = boundary_keys(out).isin(
        boundary_keys(inclusive_context).drop_duplicates()
    )
    duplicate_plain_boundary = (
        has_inclusive_replacement
        & codes.str.startswith("09")
        & ~already_inclusive
    )
    absorbed_exact_own_use = codes.isin(absorbed_own_use_codes) & ~already_inclusive
    out = out[~(duplicate_plain_boundary | absorbed_exact_own_use)].copy()
    if out.empty:
        return out

    codes = out["common_flow_code"].map(canonical_code)
    standalone_own_use_codes = {
        str(code).strip()
        for code in config.get("standalone_own_use_flow_codes", [])
        if str(code).strip()
    }
    if standalone_own_use_codes:
        # The Common ESTO export does not always retain the contributor
        # metadata needed above. Keep only the own-use branches that are
        # genuinely standalone; all process-linked 10.01.xx rows belong to
        # their 09.xx ``(including own use)`` boundary.
        own_use_mask = codes.str.startswith("10.01")
        out = out[~own_use_mask | codes.isin(standalone_own_use_codes)].copy()
        if out.empty:
            return out

    codes = out["common_flow_code"].map(canonical_code)
    labels = out["common_flow_label"].astype(str)
    already_inclusive = labels.str.contains(
        "(including own use)", case=False, regex=False
    )
    transformation_mask = codes.str.startswith("09")
    if config.get("append_inclusive_transformation_label", True):
        out.loc[transformation_mask & ~already_inclusive, "common_flow_label"] = (
            labels[transformation_mask & ~already_inclusive]
            + " (including own use)"
        )

    section_rules = config.get("section_labels", {})
    out.loc[transformation_mask, "_section_label"] = str(
        section_rules.get("transformation", "Other transformation (including own use)")
    )
    out.loc[codes.str.startswith("10.01"), "_section_label"] = str(
        section_rules.get("own_use", "Other energy-sector own use")
    )
    out.loc[codes.str.startswith("10.02"), "_section_label"] = str(
        section_rules.get("losses", "Transmission and distribution losses")
    )
    out.loc[codes.str.startswith("08"), "_section_label"] = str(
        section_rules.get("transfers", "Transfers")
    )
    return out


def page_keys_without_required_source(
    assigned_df: pd.DataFrame,
    required_page_keys: list[object],
    source_system: object,
) -> set[str]:
    """Return configured pages that do not contain the required source.

    This is a page-visibility rule, not a routing rule. In particular, exact
    code 17 always routes to Non-energy, while the page is published only once
    usable LEAP rows exist there.
    """
    source_key = str(source_system).strip().casefold()
    missing: set[str] = set()
    for raw_page_key in required_page_keys:
        page_key = str(raw_page_key)
        page_rows = assigned_df[assigned_df["_page_key"].astype(str).eq(page_key)]
        has_source = (
            not page_rows.empty
            and page_rows["source_system"].astype(str).str.casefold().eq(source_key).any()
        )
        if not has_source:
            missing.add(page_key)
    return missing


def build_page_assignment_summary(assigned_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise how generated/common rows were assigned to dashboard pages."""
    if assigned_df.empty:
        return pd.DataFrame()
    group_columns = [
        "comparison_scope",
        "_page_key",
        "_page_label",
        "_section_key",
        "_section_label",
        "_routing_status",
        "_routing_candidates",
        "_routing_special_case",
        "_page_rule_priority",
        "_page_rule_note",
        "common_flow_code",
        "common_flow_label",
    ]
    available_columns = [column for column in group_columns if column in assigned_df.columns]
    aggregations: dict[str, object] = {
        "row_count": ("value", "size"),
        "product_count": ("common_product_label", "nunique"),
        "source_system_count": ("source_system", "nunique"),
        "scenario_count": ("scenario", "nunique"),
        "first_year": ("year", "min"),
        "last_year": ("year", "max"),
    }
    for column in SUMMARY_COMPONENT_COLUMNS:
        if column in assigned_df.columns:
            aggregations[column] = (column, join_unique_text)
    return (
        assigned_df.groupby(available_columns, as_index=False)
        .agg(**aggregations)
        .rename(columns={
            "_page_key": "page_key",
            "_page_label": "page_label",
            "_section_key": "section_key",
            "_section_label": "section_label",
            "_routing_status": "routing_status",
            "_routing_candidates": "routing_candidates",
            "_routing_special_case": "routing_special_case",
            "_page_rule_priority": "page_rule_priority",
            "_page_rule_note": "page_rule_note",
        })
        .sort_values(["page_key", "common_flow_code", "common_flow_label"])
    )


def get_existing_flow_nodes(page_df: pd.DataFrame) -> pd.DataFrame:
    """Return unique flow nodes with code metadata."""
    nodes = page_df[["common_flow_code", "common_flow_label"]].drop_duplicates().copy()
    nodes["canonical_code"] = nodes["common_flow_code"].apply(canonical_code)
    nodes["depth"] = nodes["common_flow_code"].apply(code_depth)
    nodes["flow_name"] = nodes["common_flow_label"].apply(flow_name_without_code)
    if "source_system" in page_df.columns:
        label_sources = page_df.groupby("common_flow_label")["source_system"].agg(
            lambda values: frozenset(str(value) for value in values)
        )
        nodes["source_systems"] = nodes["common_flow_label"].map(label_sources)
    else:
        nodes["source_systems"] = [frozenset({""})] * len(nodes)
    if "is_non_expanding_rollup" in page_df.columns:
        rollup_flags = page_df.groupby("common_flow_label")["is_non_expanding_rollup"].agg(
            lambda values: bool(_metadata_bool(values).any())
        )
        nodes["is_non_expanding_rollup"] = nodes["common_flow_label"].map(rollup_flags).fillna(False)
    return nodes[nodes["canonical_code"] != ""].reset_index(drop=True)


def node_label_for_prefix(nodes: pd.DataFrame, prefix: str, fallback_name: str = "") -> str:
    """Return a readable label for a hierarchy prefix."""
    exact = nodes[nodes["canonical_code"] == prefix]
    if not exact.empty:
        return str(exact.iloc[0]["common_flow_label"])
    matching = nodes[nodes["canonical_code"].astype(str).str.startswith(prefix + ".")]
    if not matching.empty:
        name = fallback_name or str(matching.iloc[0]["flow_name"])
        return f"{prefix} {name}"
    return f"{prefix} {fallback_name}".strip()


def preferred_collapsed_flow_label(
    nodes: pd.DataFrame,
    labels_by_source: dict[str, list[str]],
) -> str:
    """Return the real label when a generated overview is one logical flow.

    Sources can name the same comparison boundary differently. Oil refining,
    for example, is ``09.07 Oil refineries`` in LEAP and ``09.07 Oil
    refineries (including own use)`` in the boundary-adjusted ESTO views. When
    those are the only labels in a generated prefix card, use the preferred
    actual boundary label instead of inventing a label for the broader prefix.
    """
    selected_labels = {
        str(label)
        for source_labels in labels_by_source.values()
        for label in source_labels
    }
    if not selected_labels:
        return ""

    selected = nodes[
        nodes["common_flow_label"].astype(str).isin(selected_labels)
    ].copy()
    if selected.empty or set(selected["common_flow_label"].astype(str)) != selected_labels:
        return ""

    selected["_logical_code"] = selected["common_flow_code"].map(canonical_code)
    selected["_logical_name"] = (
        selected["common_flow_label"].map(flow_name_without_code)
        .str.casefold()
        .str.replace(" (including own use)", "", regex=False)
        .str.strip()
    )
    if selected["_logical_code"].nunique() != 1 or selected["_logical_name"].nunique() != 1:
        return ""

    boundary_adjusted = selected[
        selected["common_flow_label"].astype(str).str.casefold().str.contains(
            "including own use", regex=False
        )
    ]
    candidates = boundary_adjusted if not boundary_adjusted.empty else selected
    preferred = min(
        candidates.to_dict("records"),
        key=lambda row: (
            code_depth(row["_logical_code"]),
            str(row["_logical_code"]),
            str(row["common_flow_label"]),
        ),
    )
    return str(preferred["common_flow_label"])


def _frontier_labels_for_subtree(subtree: pd.DataFrame, target_level: int) -> list[str]:
    """Return flow labels forming a non-double-counting frontier within one subtree."""
    def expression_reaches_target_level(value: object) -> bool:
        """Treat any endpoint at the target depth as the compound node's level."""
        endpoints = []
        for record in parse_code_expression(value):
            endpoints.append(str(record.get("start", "")).strip())
            if record.get("end"):
                endpoints.append(str(record["end"]).strip())
        return any(code_depth(endpoint) == target_level for endpoint in endpoints)

    exact_at_target = subtree[
        subtree["common_flow_code"].apply(expression_reaches_target_level)
    ].copy()
    selected_labels: list[str] = []
    covered_prefixes: list[str] = []
    for _, node in exact_at_target.sort_values("canonical_code").iterrows():
        selected_labels.append(str(node["common_flow_label"]))
        covered_prefixes.append(str(node["canonical_code"]))

    deeper = subtree[subtree["depth"] > target_level].copy()
    for _, node in deeper.sort_values("canonical_code").iterrows():
        code = str(node["canonical_code"])
        if any(code.startswith(prefix + ".") for prefix in covered_prefixes):
            continue
        selected_labels.append(str(node["common_flow_label"]))
    if not selected_labels:
        selected_labels = subtree["common_flow_label"].astype(str).tolist()
    return sorted(set(selected_labels))


def _flow_subtree_nodes(nodes: pd.DataFrame, parent_prefix: str) -> pd.DataFrame:
    """Return a prefix subtree closed over intersecting compound code ranges.

    A compound common row is one comparison boundary even when its first code
    is also a generated hierarchy prefix. For example, 16.01-16.02 Buildings
    is canonicalized to 16.01, but a 16.01 overview must not omit 16.02
    Residential. Expand through the compound boundary so duplicate-card
    detection can compare the complete source-specific frontiers.
    """
    subtree_mask = nodes["canonical_code"].astype(str).apply(
        lambda value: value == parent_prefix or value.startswith(parent_prefix + ".")
    )
    while True:
        subtree = nodes[subtree_mask].copy()
        compound_codes = subtree.loc[
            subtree["common_flow_code"].map(_is_compound_code_expression),
            "common_flow_code",
        ].astype(str).drop_duplicates()
        if compound_codes.empty:
            return subtree
        expanded_mask = nodes["common_flow_code"].apply(
            lambda candidate: any(
                _code_expression_contains_expression(parent, candidate)
                for parent in compound_codes
            )
        )
        next_mask = subtree_mask | expanded_mask
        if next_mask.equals(subtree_mask):
            return subtree
        subtree_mask = next_mask


def frontier_flow_labels(nodes: pd.DataFrame, parent_prefix: str, target_level: int) -> dict[str, list[str]]:
    """Return, per source system, flow labels forming a non-double-counting frontier.

    The frontier must be computed independently per source system because
    sources decompose the same subtree differently: LEAP reports a combined
    "09.01-09.02 Power sector" rollup, while NINTH/ESTO only report the
    per-plant-type children (09.01.01 Electricity plants, ...). A rollup node
    may only suppress descendant rows for sources that actually carry the
    rollup - a shared frontier would silently drop the other sources'
    descendant rows from the aggregate.
    """
    subtree = _flow_subtree_nodes(nodes, parent_prefix)
    if subtree.empty:
        return {}

    sources = sorted({source for systems in subtree["source_systems"] for source in systems})
    labels_by_source: dict[str, list[str]] = {}
    for source in sources:
        source_subtree = subtree[subtree["source_systems"].apply(lambda systems: source in systems)]

        # A generated intermediate chart may have a real, observed
        # NON_EXPANDING boundary at its own prefix.  Prefer that boundary for
        # the source instead of descending to the target-level children.  The
        # latter is normally the right choice for a hierarchy-only parent, but
        # it drops separately mapped contributors (for example LNG
        # demand-side own use) from an inclusive 09.06.02 chart.
        parent_rows = source_subtree[
            source_subtree["canonical_code"].astype(str).eq(str(parent_prefix))
        ]
        if "is_non_expanding_rollup" in parent_rows.columns:
            parent_rows = parent_rows[_metadata_bool(parent_rows["is_non_expanding_rollup"])]
        else:
            parent_rows = parent_rows.iloc[0:0]
        # Ninth's broad 09.06 row contains only the gas-side input while its
        # LNG output is reported in the observed 09.06.02 child.  Do not use
        # that incomplete parent as a comparator for the inclusive 09.06
        # summary; resolve its child frontier instead.
        use_parent_boundary = not (
            str(parent_prefix) == "09.06"
            and str(source).casefold() == "ninth"
        )
        if use_parent_boundary and not parent_rows.empty:
            boundary_rows = parent_rows[
                parent_rows["common_flow_label"].astype(str).str.casefold().str.contains(
                    "including own use", regex=False
                )
            ]
            preferred_rows = boundary_rows if not boundary_rows.empty else parent_rows
            labels = sorted(preferred_rows["common_flow_label"].astype(str).unique())
            if labels:
                labels_by_source[source] = labels
                continue

        labels = _frontier_labels_for_subtree(source_subtree, target_level)
        if labels:
            labels_by_source[source] = labels
    return labels_by_source


def area_spec_rows(df: pd.DataFrame, area_spec: dict[str, object]) -> pd.DataFrame:
    """Select the rows an area spec aggregates, honoring per-source frontiers."""
    labels_by_source = area_spec.get("source_flow_labels_by_system") or {}
    if labels_by_source and "source_system" in df.columns:
        mask = pd.Series(False, index=df.index)
        source_col = df["source_system"].astype(str)
        for source, labels in labels_by_source.items():
            mask = mask | ((source_col == source) & df["common_flow_label"].isin(labels))
        return df[mask]
    source_flow_labels = [str(value) for value in area_spec["source_flow_labels"]]
    return df[df["common_flow_label"].isin(source_flow_labels)]


def _has_nonzero_values(values: pd.Series, tolerance: float = 1e-12) -> bool:
    """Return whether a chart series contains a meaningful non-zero value."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    return bool((numeric.abs() > tolerance).any())


def effective_chart_suppression_threshold(
    template: dict,
    rows: pd.DataFrame | None = None,
) -> float:
    """Return the magnitude threshold for the active comparison basis.

    ESTO Extended is a structural comparison basis: its additional categories
    can be populated only by LEAP while the ESTO Extended and Ninth values are
    zero. Keep every non-zero category in those dashboards. Completely empty
    charts are still omitted later when their figures contain no traces.
    """
    chart_config = template.get("chart_generation", {})
    configured = float(chart_config.get("suppression_threshold", 1.0))
    active_scope = str(template.get("_active_comparison_scope", "")).strip()
    if not active_scope and rows is not None and "comparison_scope" in rows.columns:
        scopes = {
            str(value).strip()
            for value in rows["comparison_scope"].dropna().unique()
            if str(value).strip()
        }
        if len(scopes) == 1:
            active_scope = next(iter(scopes))
    if active_scope.startswith("esto_extended_"):
        return 0.0
    return configured


def _add_signed_stack_traces(
    fig: go.Figure,
    x_values: pd.Series,
    y_values: pd.Series,
    stackgroup_prefix: str,
    trace_name: str,
    visible: bool,
    hovertemplate: str,
    line_color: str = "",
) -> int:
    """Add one logical area series to separate positive and negative stacks.

    A product can change sign over time. Plotly assigns ``stackgroup`` per
    trace, not per point, so choosing a stack from the series-wide sum makes
    the opposite-sign years overlap other areas. Split at zero while keeping
    one legend item and one legend group for the logical series.
    """
    numeric_values = pd.to_numeric(y_values, errors="coerce").fillna(0.0)
    return _add_preseparated_signed_stack_traces(
        fig=fig,
        x_values=x_values,
        signed_parts=[
            ("pos", numeric_values.clip(lower=0.0)),
            ("neg", numeric_values.clip(upper=0.0)),
        ],
        stackgroup_prefix=stackgroup_prefix,
        trace_name=trace_name,
        visible=visible,
        hovertemplate=hovertemplate,
        line_color=line_color,
    )


def _add_preseparated_signed_stack_traces(
    fig: go.Figure,
    x_values: pd.Series,
    signed_parts: list[tuple[str, pd.Series]],
    stackgroup_prefix: str,
    trace_name: str,
    visible: bool,
    hovertemplate: str,
    line_color: str = "",
) -> int:
    """Add already-separated gross positive and negative category totals."""
    active_parts = [
        (sign, values)
        for sign, values in signed_parts
        if _has_nonzero_values(values)
    ]
    legend_group = f"{stackgroup_prefix}::{trace_name}"
    for part_index, (sign, values) in enumerate(active_parts):
        trace = go.Scatter(
            x=x_values,
            y=values,
            mode="lines",
            stackgroup=f"{stackgroup_prefix}_{sign}",
            name=trace_name,
            visible=True if visible else False,
            legendgroup=legend_group,
            showlegend=part_index == 0,
            hovertemplate=hovertemplate,
        )
        if line_color:
            trace.line.color = line_color
        fig.add_trace(trace)
    return len(active_parts)


def _comparison_projection_area_rows(
    df: pd.DataFrame,
    *,
    scenario_name: str,
    primary_source: str,
    comparison_source: str,
    base_year: int,
    group_col: str,
    detail_col: str,
    detail_minimum: int = 2,
    value_col: str = "value",
) -> tuple[pd.DataFrame, str]:
    """Return comparison historical rows plus detailed projected rows.

    The area charts use the union of nonzero historical and projected
    categories. Choose the most detailed available projection source, while
    retaining genuine ESTO-only historical categories so the historical stack
    reconciles to its comparison total line.
    """
    candidates = [primary_source, "NINTH", "LEAP", "ESTO"]
    source_column = df["source_system"].astype(str).str.casefold()
    scenario_column = df["scenario"].astype(str).str.casefold()
    # Extended comparison scopes use the same historical ESTO observations
    # under the ESTO_EXTENDED source label. The area-chart callers retain the
    # legacy ESTO default for ordinary scopes, so resolve that label here when
    # the filtered frame contains only the Extended comparison source.
    available_sources = set(source_column.unique())
    comparison_key = comparison_source.casefold()
    if (
        comparison_key == "esto"
        and "esto" not in available_sources
        and "esto_extended" in available_sources
    ):
        comparison_source = "ESTO_EXTENDED"
    selected_source = ""
    projected = df.iloc[0:0].copy()
    ninth_base_year = ninth_base_year_for_rows(df, base_year)
    for source_name in candidates:
        projection_base_year = (
            ninth_base_year
            if source_name.casefold() == "ninth"
            else base_year
        )
        source_rows = df[
            source_column.eq(source_name.casefold())
            & scenario_column.eq(scenario_name.casefold())
            & df["year"].gt(projection_base_year)
        ]
        if source_rows.empty or source_rows[detail_col].nunique(dropna=True) < detail_minimum:
            continue
        selected_source = source_name
        projected = source_rows
        break
    historical = df[
        source_column.eq(comparison_source.casefold())
        & df["year"].le(base_year)
    ].copy()
    if not selected_source:
        # A two-way LEAP+ESTO basis can legitimately have only an aggregate
        # LEAP projection (for example All demand aggregated in China). Keep
        # the real ESTO composition through the base year instead of blanking
        # the entire area chart; the aggregate LEAP total line remains visible
        # after the base year and the chart note explains the missing detail.
        return historical, comparison_source if not historical.empty else ""

    projected_gross = pd.to_numeric(projected[value_col], errors="coerce").fillna(0.0).abs()
    historical_gross = pd.to_numeric(historical[value_col], errors="coerce").fillna(0.0).abs()
    projected_active = projected.assign(_gross_value=projected_gross).groupby(
        group_col, dropna=False
    )["_gross_value"].sum()
    historical_active = historical.assign(_gross_value=historical_gross).groupby(
        group_col, dropna=False
    )["_gross_value"].sum()
    active_groups = projected_active.loc[projected_active > 1e-12].index.union(
        historical_active.loc[historical_active > 1e-12].index
    )
    projected = projected[projected[group_col].isin(active_groups)]
    historical = historical[historical[group_col].isin(active_groups)]
    return pd.concat([historical, projected], ignore_index=True), selected_source


def area_chart_allowed_for_demand_coverage(
    page_key: str,
    area_df: pd.DataFrame,
    template: dict,
) -> bool:
    """Keep all available Common ESTO categories eligible for charting.

    Placeholder representation is presentation metadata.  The Common ESTO
    facts and hierarchy frontier, not a static LEAP-branch setting, decide
    whether an overview can render.
    """
    return True


def placeholder_only_demand_flow_prefixes(page_key: str, template: dict) -> list[str]:
    """Return Common ESTO flow prefixes with no detailed LEAP representation."""
    coverage = template.get("leap_demand_sector_coverage", {}) or {}
    placeholder_only_pages = coverage.get("_placeholder_only_page_branches", {}) or {}
    active_components = {
        str(component).strip()
        for component in placeholder_only_pages.get(page_key, [])
        if str(component).strip()
    }
    component_prefixes = coverage.get("placeholder_component_flow_prefixes", {}) or {}
    return [
        str(prefix).strip()
        for component in active_components
        for prefix in component_prefixes.get(component, [])
        if str(prefix).strip()
    ]


def aggregate_only_demand_page_active(page_key: str, template: dict) -> bool:
    """Return whether a demand page must show its placeholder total only."""
    coverage = template.get("leap_demand_sector_coverage", {}) or {}
    configured_pages = {
        str(value).strip()
        for value in coverage.get("show_aggregate_only_page_keys", [])
        if str(value).strip()
    }
    active_pages = coverage.get("_aggregate_only_page_branches", {}) or {}
    return page_key in configured_pages and bool(active_pages.get(page_key))


def placeholder_demand_root_prefixes(page_key: str, template: dict) -> set[str]:
    """Return top-level Common ESTO roots retained for a placeholder page."""
    prefixes = placeholder_only_demand_flow_prefixes(page_key, template)
    return {code_prefix(prefix, 1) for prefix in prefixes if code_prefix(prefix, 1)}


def drop_placeholder_only_demand_detail_rows(
    page_key: str,
    page_df: pd.DataFrame,
    template: dict,
) -> pd.DataFrame:
    """Remove child rows represented only by an active demand placeholder.

    The page-level aggregate remains useful while ``All demand aggregated`` is
    active. Its child Common flows do not: charts below the page aggregate
    would look like LEAP supplied a sector/fuel breakdown when it supplied
    only the broad placeholder. Partial-detail components stay visible because
    their coverage audit records real LEAP detail.
    """
    prefixes = placeholder_only_demand_flow_prefixes(page_key, template)
    if page_df.empty or not prefixes or "common_flow_code" not in page_df.columns:
        return page_df.copy()
    placeholder_mask = page_df["common_flow_code"].apply(
        lambda code: code_expression_matches_any_prefix(code, prefixes)
    )
    return page_df.loc[~placeholder_mask].copy()


def area_spec_is_placeholder_only_demand_child(
    page_key: str,
    area_spec: dict[str, object],
    template: dict,
) -> bool:
    """Return whether an overview spec is a child of a placeholder-only branch."""
    source_root_code = str(area_spec.get("aggregate_flow_prefix") or "").strip()
    if not source_root_code:
        source_root_code = code_candidate_text(area_spec.get("aggregate_flow_label", ""))
    if aggregate_only_demand_page_active(page_key, template):
        root_prefixes = placeholder_demand_root_prefixes(page_key, template)
        if source_root_code in root_prefixes:
            return False
        return code_depth(source_root_code) > 1
    return code_expression_matches_any_prefix(
        source_root_code,
        placeholder_only_demand_flow_prefixes(page_key, template),
    )


def equivalent_flow_labels_by_source(df: pd.DataFrame, flow_label: str) -> dict[str, list[str]]:
    """Match a displayed flow name to source-specific equivalent labels."""
    target_name = flow_name_without_code(flow_label).casefold()
    target_name = target_name.replace(" (including own use)", "").strip()
    labels_by_source: dict[str, list[str]] = {}
    for source, source_df in df.groupby("source_system", dropna=False):
        labels = []
        for label in source_df["common_flow_label"].dropna().astype(str).unique():
            source_name = flow_name_without_code(label).casefold()
            source_name = source_name.replace(" (including own use)", "").strip()
            if source_name == target_name:
                labels.append(label)
        if labels:
            labels_by_source[str(source)] = sorted(labels)
    return labels_by_source


def _non_overlapping_common_row_frontier(df: pd.DataFrame) -> pd.DataFrame:
    """Choose one observed, non-overlapping common-row frontier.

    The canonical all-rows contract deliberately preserves both a named
    aggregate and the additive detail frontier that represents the same energy.
    Dashboard aggregates must choose one of those alternatives. For each
    source/economy/scenario series, retain an observed compound common category
    or explicitly flagged NON_EXPANDING subtotal and remove contained rows for
    every year in that series.

    Selection is series-specific: if a source never publishes the subtotal row,
    its detail frontier remains available. If the subtotal is absent in only
    some years because its components cancel to exact zero, those years remain
    on the subtotal frontier instead of falling back to overlapping detail.
    """
    required = {"is_non_expanding_rollup", "source_system", "scenario", "year"}
    if df.empty or not required.issubset(df.columns):
        return df

    work = df.copy()
    work["_frontier_row_number"] = range(len(work))
    subtotal_mask = _metadata_bool(work["is_non_expanding_rollup"])

    context_columns = [
        column
        for column in ["comparison_scope", "source_system", "economy", "scenario"]
        if column in work.columns
    ]
    drop_row_numbers: set[int] = set()

    # Some generated comparison categories are aggregate-backed without being
    # NON_EXPANDING rollups. For example, the LEAP all-demand placeholder is
    # represented by common flow 16.03-16.05,17 while its 16.03-16.04 and 16.05
    # components remain available as separate comparison views. Use the common
    # axis expression itself to choose one series-specific frontier, so a
    # detached aggregate and its contained categories cannot be added together.
    # Detached generated aggregates currently exist on the flow axis. Do not
    # infer the same relationship from compound product labels: ranges such as
    # petroleum-products groupings are ordinary disjoint chart categories and
    # must not suppress signed transfer inputs. Explicit NON_EXPANDING product
    # rollups remain handled by the metadata-backed passes below.
    for axis_name, opposite_axis_name in (("flow", "product"),):
        axis_column = f"common_{axis_name}_code"
        opposite_column = f"common_{opposite_axis_name}_code"
        if axis_column not in work.columns or opposite_column not in work.columns:
            continue

        categories = work[[axis_column, opposite_column]].drop_duplicates()
        parent_categories = categories[
            categories[axis_column].map(_is_compound_code_expression)
        ]
        membership_rows: list[dict[str, str]] = []
        for opposite_code, same_opposite_parents in parent_categories.groupby(
            opposite_column, dropna=False, sort=False
        ):
            candidate_codes = categories.loc[
                categories[opposite_column].eq(opposite_code), axis_column
            ].astype(str).drop_duplicates()
            for parent_code in same_opposite_parents[axis_column].astype(str):
                for detail_code in candidate_codes:
                    if (
                        detail_code != parent_code
                        and _code_expression_contains_expression(parent_code, detail_code)
                    ):
                        membership_rows.append({
                            opposite_column: str(opposite_code),
                            "_frontier_parent_common_code": parent_code,
                            axis_column: detail_code,
                        })
        if not membership_rows:
            continue

        memberships = pd.DataFrame(membership_rows).drop_duplicates()
        observed_parents = work[
            [*context_columns, opposite_column, axis_column]
        ].drop_duplicates().rename(columns={axis_column: "_frontier_parent_common_code"})
        observed_details = work[
            ["_frontier_row_number", *context_columns, opposite_column, axis_column]
        ]
        observed_matches = observed_details.merge(
            memberships,
            on=[opposite_column, axis_column],
            how="inner",
        ).merge(
            observed_parents,
            on=[*context_columns, opposite_column, "_frontier_parent_common_code"],
            how="inner",
        )
        drop_row_numbers.update(observed_matches["_frontier_row_number"].astype(int))

    # The split parent and detail rows normally retain the same compressed
    # hierarchy coordinates even though their common_row_id values differ.
    axis_columns = [
        column for column in ["common_flow_code", "common_product_code"] if column in work.columns
    ]
    if len(axis_columns) == 2:
        key_columns = context_columns + axis_columns
        subtotal_keys = work.loc[subtotal_mask, key_columns].drop_duplicates()
        detail_keys = work.loc[~subtotal_mask, ["_frontier_row_number", *key_columns]]
        axis_matches = detail_keys.merge(subtotal_keys, on=key_columns, how="inner")
        drop_row_numbers.update(axis_matches["_frontier_row_number"].astype(int))

    # NON_EXPANDING subtotal membership can also be encoded directly in the
    # component-axis expression rather than in an aggregate-group id. For
    # example, Transport non-road uses 15.01,15.03-15.06 while its additive
    # alternative retains the individual 15.01/15.03/... rows. Match those
    # component codes within the same observation and opposite-axis category.
    for axis_name, opposite_axis_name in (("flow", "product"), ("product", "flow")):
        if not subtotal_mask.any():
            break
        axis_component_column = f"component_{axis_name}_code"
        axis_common_column = f"common_{axis_name}_code"
        opposite_common_column = f"common_{opposite_axis_name}_code"
        if axis_common_column not in work.columns or opposite_common_column not in work.columns:
            continue

        axis_expression_column = f"_frontier_{axis_name}_expression"
        opposite_expression_column = f"_frontier_{opposite_axis_name}_expression"
        work[axis_expression_column] = work.get(
            axis_component_column, pd.Series("", index=work.index)
        ).fillna("").astype(str).str.strip()
        work[axis_expression_column] = work[axis_expression_column].where(
            work[axis_expression_column].ne(""),
            work[axis_common_column].fillna("").astype(str).str.strip(),
        )
        # Use the shared comparison coordinate on the opposite axis. Its raw
        # component list can legitimately differ between alternative common
        # rows (for example 07.05 versus 07.04;07.05) even though both occupy
        # the same common product category.
        work[opposite_expression_column] = (
            work[opposite_common_column].fillna("").astype(str).str.strip()
        )

        # Build the structural parent/detail relationships once from unique
        # categories, then join them to observation keys. Re-evaluating the
        # same code expressions for every source/year fact row is prohibitively
        # expensive on production economy datasets.
        categories = work[
            [axis_expression_column, opposite_expression_column]
        ].drop_duplicates()
        parent_expressions = work.loc[
            subtotal_mask,
            [axis_expression_column, opposite_expression_column],
        ].drop_duplicates()
        parent_expressions = parent_expressions[
            parent_expressions[axis_expression_column].map(_is_compound_code_expression)
        ]
        membership_rows: list[dict[str, str]] = []
        for opposite_expression, same_opposite_parents in parent_expressions.groupby(
            opposite_expression_column, dropna=False, sort=False
        ):
            candidate_expressions = categories.loc[
                categories[opposite_expression_column].eq(opposite_expression),
                axis_expression_column,
            ].astype(str).drop_duplicates()
            for parent_expression in same_opposite_parents[axis_expression_column].astype(str):
                for detail_expression in candidate_expressions:
                    if (
                        detail_expression != parent_expression
                        and _code_expression_contains_expression(parent_expression, detail_expression)
                    ):
                        membership_rows.append({
                            opposite_expression_column: str(opposite_expression),
                            "_frontier_parent_expression": parent_expression,
                            axis_expression_column: detail_expression,
                        })
        if not membership_rows:
            continue

        memberships = pd.DataFrame(membership_rows).drop_duplicates()
        observed_parents = work.loc[
            subtotal_mask,
            [*context_columns, opposite_expression_column, axis_expression_column],
        ].drop_duplicates().rename(
            columns={axis_expression_column: "_frontier_parent_expression"}
        )
        observed_details = work.loc[
            ~subtotal_mask,
            ["_frontier_row_number", *context_columns, opposite_expression_column, axis_expression_column],
        ]
        observed_matches = observed_details.merge(
            memberships,
            on=[opposite_expression_column, axis_expression_column],
            how="inner",
        ).merge(
            observed_parents,
            on=[*context_columns, opposite_expression_column, "_frontier_parent_expression"],
            how="inner",
        )
        drop_row_numbers.update(
            observed_matches["_frontier_row_number"].astype(int)
        )

    # Source aggregate membership is the explicit link when display/hierarchy
    # coordinates differ between the parent and detail common rows.
    membership_column = "source_aggregate_group_ids"
    if membership_column in work.columns:
        membership_text = work[membership_column].fillna("").astype(str).str.strip()
        subtotal_memberships = work.loc[
            subtotal_mask & membership_text.ne(""),
            [*context_columns, membership_column],
        ].copy()
        detail_memberships = work.loc[
            ~subtotal_mask & membership_text.ne(""),
            ["_frontier_row_number", *context_columns, membership_column],
        ].copy()
        if not subtotal_memberships.empty and not detail_memberships.empty:
            subtotal_memberships["_aggregate_group_id"] = (
                subtotal_memberships.pop(membership_column).str.split(";")
            )
            detail_memberships["_aggregate_group_id"] = (
                detail_memberships.pop(membership_column).str.split(";")
            )
            subtotal_memberships = subtotal_memberships.explode("_aggregate_group_id")
            detail_memberships = detail_memberships.explode("_aggregate_group_id")
            subtotal_memberships["_aggregate_group_id"] = (
                subtotal_memberships["_aggregate_group_id"].astype(str).str.strip()
            )
            detail_memberships["_aggregate_group_id"] = (
                detail_memberships["_aggregate_group_id"].astype(str).str.strip()
            )
            subtotal_memberships = subtotal_memberships[
                subtotal_memberships["_aggregate_group_id"].ne("")
            ].drop_duplicates()
            membership_matches = detail_memberships.merge(
                subtotal_memberships,
                on=[*context_columns, "_aggregate_group_id"],
                how="inner",
            )
            drop_row_numbers.update(
                membership_matches["_frontier_row_number"].astype(int)
            )

    if not drop_row_numbers:
        return df
    selected = work[~work["_frontier_row_number"].isin(drop_row_numbers)].copy()
    helper_columns = [
        column for column in selected.columns
        if column == "_frontier_row_number" or column.startswith("_frontier_flow_expression")
        or column.startswith("_frontier_product_expression")
    ]
    return selected.drop(columns=helper_columns)


def _non_overlapping_flow_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one non-overlapping flow frontier for each source/scenario.

    Common ESTO output can contain both an exact transformation row and a
    generated boundary-adjusted row (for example, oil refineries including
    own use).  Those rows are valid comparison views individually, but adding
    them to one stacked aggregate double-counts the same components.  Prefer
    the boundary-adjusted label when it is available, and otherwise prefer a
    parent code over its child codes.
    """
    required = {"common_flow_code", "common_flow_label", "source_system"}
    if df.empty or not required.issubset(df.columns):
        return df

    work = df.copy()
    work["_flow_code"] = work["common_flow_code"].map(canonical_code)
    work["_flow_name"] = (
        work["common_flow_label"].map(flow_name_without_code)
        .str.casefold()
        .str.replace(" (including own use)", "", regex=False)
        .str.strip()
    )
    work["_is_boundary_adjusted"] = work["common_flow_label"].astype(str).str.casefold().str.contains(
        "including own use", regex=False
    )
    keep = pd.Series(True, index=work.index)

    context_columns = [
        column
        for column in ("comparison_scope", "economy", "source_system", "scenario")
        if column in work.columns
    ]
    category_rows = work[context_columns + ["common_flow_label", "_flow_code", "_flow_name", "_is_boundary_adjusted"]].drop_duplicates()
    replacements: dict[str, str] = {}
    for flow_name, same_name in category_rows.groupby("_flow_name", dropna=False):
        same_name = same_name.copy()
        boundary_rows = same_name[same_name["_is_boundary_adjusted"]]
        candidates = boundary_rows if not boundary_rows.empty else same_name
        preferred = min(
            candidates.to_dict("records"),
            key=lambda row: (code_depth(row["_flow_code"]), str(row["_flow_code"]), str(row["common_flow_label"])),
        )
        preferred_code = str(preferred["_flow_code"])
        preferred_label = str(preferred["common_flow_label"])
        same_name_mask = work["_flow_name"] == flow_name
        keep.loc[same_name_mask & (work["_flow_code"] != preferred_code)] = False
        replacements.update({str(label): preferred_label for label in same_name["common_flow_label"]})

    # If a parent flow and its child are both present, retain the parent in an
    # aggregate-by-flow chart. Detail charts remain responsible for showing the
    # child categories individually.
    # Parent/child overlap is meaningful only within one source/scenario
    # surface.  Comparing all rows together can let a LEAP parent suppress
    # the detailed ESTO historical rows that are needed before the base year.
    kept_categories = category_rows[category_rows["common_flow_label"].isin(replacements)]
    if context_columns:
        context_groups = kept_categories.groupby(context_columns, dropna=False, sort=False)
    else:
        context_groups = [(None, kept_categories)]
    for context_key, context_categories in context_groups:
        context_codes = context_categories["_flow_code"].astype(str).tolist()
        context_mask = pd.Series(True, index=work.index)
        if context_columns:
            context_values = context_key if isinstance(context_key, tuple) else (context_key,)
            for column, value in zip(context_columns, context_values):
                context_mask &= work[column].eq(value)
        for _, category in context_categories.iterrows():
            code = str(category["_flow_code"])
            if code and any(
                other != code and code_matches_prefix(code, other)
                for other in context_codes
            ):
                keep.loc[context_mask & (work["_flow_code"] == code)] = False

    result = work.loc[keep].copy()
    result["common_flow_label"] = result["common_flow_label"].map(replacements).fillna(result["common_flow_label"])
    return result.drop(columns=["_flow_code", "_flow_name", "_is_boundary_adjusted"])


def _leaf_flow_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep mapping-terminal or deepest flow categories per source/scenario.

    This is the inverse of the parent-first aggregate frontier above. It is
    intended for charts whose categories should expose the hierarchy leaves.
    Mapping-owned NON_EXPANDING rollups are terminal comparison leaves even
    when their display code has deeper nodes in the raw ESTO hierarchy. The
    terminal codes apply across sources in the same comparison surface, so an
    ESTO boundary such as 09.06.02 (including own use) also keeps the equivalent
    LEAP projection on 09.06.02 instead of relabelling it as .01 detail. Callers
    must still use an authoritative non-overlapping boundary for net lines.
    """
    required = {"common_flow_code", "common_flow_label", "source_system"}
    if df.empty or not required.issubset(df.columns):
        return df

    work = df.copy()
    work["_leaf_row_number"] = range(len(work))
    terminal_context_columns = [
        column
        for column in ("comparison_scope", "economy")
        if column in work.columns
    ]

    def terminal_rollup_codes_for(context_rows: pd.DataFrame) -> set[str]:
        """Return the most specific declared rollups on this comparison surface."""
        if "is_non_expanding_rollup" not in work.columns:
            return set()
        surface_rows = work
        for column in terminal_context_columns:
            context_value = context_rows.iloc[0][column]
            if pd.isna(context_value):
                surface_rows = surface_rows[surface_rows[column].isna()]
            else:
                surface_rows = surface_rows[surface_rows[column].eq(context_value)]
        declared_codes = {
            str(code).strip()
            for code in surface_rows.loc[
                _metadata_bool(surface_rows["is_non_expanding_rollup"]),
                "common_flow_code",
            ]
            if str(code).strip()
        }
        # A broad presentation subtotal must not replace a more specific
        # declared comparison boundary nested beneath it.
        return {
            code
            for code in declared_codes
            if not any(
                other != code
                and _code_expression_contains_expression(code, other)
                for other in declared_codes
            )
        }
    context_columns = [
        column
        for column in ("comparison_scope", "source_system", "economy", "scenario")
        if column in work.columns
    ]
    grouped_rows = [(None, work)]
    if context_columns:
        grouped_rows = list(work.groupby(context_columns, dropna=False, sort=False))

    keep_row_numbers: set[int] = set()
    for _, context_rows in grouped_rows:
        terminal_rollup_codes = terminal_rollup_codes_for(context_rows)
        categories = context_rows[
            ["common_flow_code", "common_flow_label"]
        ].drop_duplicates().copy()
        categories["_flow_name"] = (
            categories["common_flow_label"].map(flow_name_without_code)
            .str.casefold()
            .str.replace(" (including own use)", "", regex=False)
            .str.strip()
        )
        categories["_is_boundary_adjusted"] = (
            categories["common_flow_label"].astype(str).str.casefold()
            .str.contains("including own use", regex=False)
        )

        preferred_labels: set[str] = set()
        for _, same_name in categories.groupby("_flow_name", dropna=False):
            boundary_rows = same_name[same_name["_is_boundary_adjusted"]]
            candidates = boundary_rows if not boundary_rows.empty else same_name
            preferred = max(
                candidates.to_dict("records"),
                key=lambda row: (
                    code_depth(row["common_flow_code"]),
                    str(row["common_flow_code"]),
                    str(row["common_flow_label"]),
                ),
            )
            preferred_labels.add(str(preferred["common_flow_label"]))

        categories = categories[
            categories["common_flow_label"].astype(str).isin(preferred_labels)
        ]
        categories["_is_terminal_rollup"] = categories[
            "common_flow_code"
        ].astype(str).str.strip().isin(terminal_rollup_codes)
        terminal_records = categories[
            categories["_is_terminal_rollup"]
        ].to_dict("records")
        leaf_labels: set[str] = set()
        category_records = categories.to_dict("records")
        for category in category_records:
            parent_code = category["common_flow_code"]
            if bool(category["_is_terminal_rollup"]):
                leaf_labels.add(str(category["common_flow_label"]))
                continue
            is_inside_terminal_rollup = any(
                str(terminal["common_flow_code"]) != str(parent_code)
                and _code_expression_contains_expression(
                    terminal["common_flow_code"],
                    parent_code,
                )
                for terminal in terminal_records
            )
            has_observed_child = any(
                str(other["common_flow_code"]) != str(parent_code)
                and _code_expression_contains_expression(
                    parent_code,
                    other["common_flow_code"],
                )
                for other in category_records
            )
            if not has_observed_child and not is_inside_terminal_rollup:
                leaf_labels.add(str(category["common_flow_label"]))

        keep_row_numbers.update(
            context_rows.loc[
                context_rows["common_flow_label"].astype(str).isin(leaf_labels),
                "_leaf_row_number",
            ].astype(int)
        )

    return work[
        work["_leaf_row_number"].isin(keep_row_numbers)
    ].drop(columns=["_leaf_row_number"])


def pick_area_specs(page_df: pd.DataFrame, template: dict) -> list[dict[str, object]]:
    """Choose aggregate area charts from the flow hierarchy."""
    nodes = get_existing_flow_nodes(page_df)
    if nodes.empty:
        return []
    chart_config = template.get("chart_generation", {})
    area_chart_flow_labels = {
        str(code): str(label)
        for code, label in chart_config.get("area_chart_flow_labels", {}).items()
    }
    deep_min_depth = int(chart_config.get("deep_chain_min_depth", 3))
    max_depth = int(nodes["depth"].max())
    level_count = 2 if max_depth >= deep_min_depth else 1
    level_count = int(chart_config.get("top_levels_for_deep_chains", level_count)) if max_depth >= deep_min_depth else int(chart_config.get("top_levels_for_other_chains", level_count))
    max_area_charts = int(chart_config.get("max_area_charts_per_page", 30))

    specs: list[dict[str, object]] = []
    used_group_keys: set[tuple[int, str]] = set()
    used_label_sets: set[frozenset[tuple[str, str]]] = set()
    for level in range(1, level_count + 1):
        prefixes = sorted({code_prefix(code, level) for code in nodes["canonical_code"] if code_prefix(code, level)})
        for prefix in prefixes:
            group_key = (level, prefix)
            if group_key in used_group_keys:
                continue
            labels_by_source = frontier_flow_labels(nodes, prefix, level + 1 if level == 1 else level)
            labels = sorted({label for source_labels in labels_by_source.values() for label in source_labels})
            if not labels:
                continue
            # A prefix whose frontier resolves to the exact same leaf flows as an
            # already-emitted card is a redundant rollup (e.g. a "10" card and a
            # "10.01" card that both fall back to the single leaf "10.01.01" when
            # the intermediate codes have no data of their own). Skip it rather
            # than rendering two identical charts under different titles.
            label_set = frozenset((source, label) for source, source_labels in labels_by_source.items() for label in source_labels)
            if label_set in used_label_sets:
                used_group_keys.add(group_key)
                continue
            # Some hierarchy prefixes are synthetic in Common ESTO output and
            # therefore have no exact row from which to obtain their proper
            # parent name. Do not borrow the first descendant's name for those
            # prefixes; use the configured ESTO hierarchy label instead.
            label = area_chart_flow_labels.get(prefix, "")
            if not label:
                label = preferred_collapsed_flow_label(nodes, labels_by_source)
            if not label:
                label = node_label_for_prefix(nodes, prefix)
            specs.append(
                {
                    "area_level": level,
                    "aggregate_flow_prefix": prefix,
                    "aggregate_flow_label": label,
                    "source_flow_labels": labels,
                    "source_flow_labels_by_system": labels_by_source,
                }
            )
            used_group_keys.add(group_key)
            used_label_sets.add(label_set)
            if len(specs) >= max_area_charts:
                return specs
    return specs


def area_chart_display_label(
    source_aggregate_label: str,
    page_scope_overview_label: str,
    subtree_is_page_complete: bool,
) -> str:
    """Keep a mapped aggregate's precise label unless the page defines an override."""
    if not subtree_is_page_complete and page_scope_overview_label:
        return page_scope_overview_label
    return source_aggregate_label


_WHITE_BACKGROUND_LAYOUT: dict[str, object] = {"paper_bgcolor": "white", "plot_bgcolor": "white"}

# Dark and muted categorical colours that remain visible on white Plotly
# backgrounds. In particular, avoid the default bright lime / neon greens:
# those are difficult to distinguish both from the background and from nearby
# stacked areas. The sequence is deliberately long because product charts
# often contain many traces; colours repeat only after every distinct option.
_PRODUCT_COLORWAY: list[str] = [
    "#3B6FB6",  # blue
    "#C65D28",  # burnt orange
    "#7A5195",  # purple
    "#B64C67",  # muted red
    "#007C78",  # dark teal
    "#9A6B2F",  # brown
    "#5A7D3A",  # olive, not lime
    "#8B5A9F",  # violet
    "#3A7CA5",  # steel blue
    "#A63D40",  # brick red
    "#6E6E6E",  # neutral grey
    "#9B7000",  # dark gold
    "#00758A",  # blue teal
    "#9D4E93",  # plum
    "#8C564B",  # umber
    "#486581",  # slate blue
    "#A8465B",  # rose
    "#2F855A",  # forest green
    "#7B5E57",  # taupe
    "#5B6C8F",  # blue grey
]

CODE_COLORS_PATH = Path(__file__).resolve().parents[1] / "config" / "common_esto_dashboard" / "code_colors.json"


def set_code_colors_path(path: Path | str | None) -> Path:
    """Point the colour map at *path* and invalidate the cached load.

    The default resolves ``config/`` relative to the repository root, which is
    correct in a checkout. A distributed package keeps its configuration in an
    external folder that is not laid out that way, so it sets the path
    explicitly at start-up. Passing ``None`` restores the repository default.
    """
    global CODE_COLORS_PATH
    if path is None:
        CODE_COLORS_PATH = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "common_esto_dashboard"
            / "code_colors.json"
        )
    else:
        CODE_COLORS_PATH = Path(str(path).replace("\\", "/"))
    load_code_colors.cache_clear()
    return CODE_COLORS_PATH


@lru_cache(maxsize=1)
def load_code_colors() -> dict[str, dict[str, str]]:
    """Load the per-axis ESTO code colour map, tolerating an absent config."""
    if not CODE_COLORS_PATH.exists():
        return {"product": {}, "flow": {}, "common": {}, "plotting": {}}
    payload = load_json(CODE_COLORS_PATH)
    return {
        "product": dict(payload.get("product", {})),
        "flow": dict(payload.get("flow", {})),
        "common": {
            axis: dict(values)
            for axis, values in dict(payload.get("common", {})).items()
            if isinstance(values, dict)
        },
        "plotting": {
            axis: dict(values)
            for axis, values in dict(payload.get("plotting", {})).items()
            if isinstance(values, dict)
        },
        "source": dict(payload.get("_source_plotting_colors", {})),
    }


def color_for_plotting_name(name: object, axis: str) -> str:
    """Resolve a workbook plotting category colour case-insensitively."""
    text = str(name or "").strip().casefold()
    if not text:
        return ""
    axis_color = next(
        (color for label, color in load_code_colors().get("plotting", {}).get(axis, {}).items()
         if str(label).casefold() == text),
        "",
    )
    if axis_color:
        return axis_color
    return next(
        (color for label, color in load_code_colors().get("source", {}).items()
         if str(label).casefold() == text),
        "",
    )


def color_for_code(code_or_label: object, axis: str) -> str:
    """Resolve a common ESTO label or code to its axis colour, or "" if unmapped.

    Multi-component Common ESTO expressions use their configured perceptual
    average. Exact categories use their ESTO code colour, walking up the
    hierarchy when an unseen sub-code needs to inherit its family colour.
    """
    text = str(code_or_label or "").strip()
    expression_match = re.match(r"^([0-9.]+(?:[-,][0-9.]+)+)", text)
    if expression_match:
        common_color = load_code_colors().get("common", {}).get(axis, {}).get(expression_match.group(1), "")
        if common_color:
            return common_color
    colors = load_code_colors().get(axis, {})
    code = canonical_code(code_or_label)
    while code:
        if code in colors:
            return colors[code]
        if "." not in code:
            break
        code = code.rsplit(".", 1)[0]
    label = text.split(maxsplit=1)[1] if " " in text else ""
    return color_for_plotting_name(label, axis)


def _apply_code_colors(fig: go.Figure, axis: str) -> None:
    """Give traces stable colours, resolving configured colour collisions."""
    used_colors: set[str] = set()
    assigned_by_name: dict[str, str] = {}
    for trace in fig.data:
        trace_name = str(getattr(trace, "name", ""))
        name_key = trace_name.casefold()
        color = assigned_by_name.get(name_key, color_for_code(trace_name, axis))
        if not color:
            continue
        if name_key not in assigned_by_name and color.casefold() in {value.casefold() for value in used_colors}:
            color = next((candidate for candidate in _PRODUCT_COLORWAY if candidate.casefold() not in {value.casefold() for value in used_colors}), color)
        assigned_by_name[name_key] = color
        used_colors.add(color)
        if getattr(trace, "line", None) is not None:
            trace.line.color = color
        if getattr(trace, "fillcolor", None) is not None or getattr(trace, "stackgroup", None):
            trace.fillcolor = color


# Keep comparison totals visually stable even when a chart has a different
# number or ordering of stacked product traces. These colours are the
# colour-blind-friendly Okabe-Ito blue, vermillion, and green.
_TOTAL_SERIES_COLORS: dict[str, str] = {
    "ESTO": "#0072B2",
    "LEAP": "#D55E00",
    "NINTH": "#009E73",
    "9TH": "#009E73",
}

_TOTAL_SERIES_STYLES: dict[str, dict[str, str]] = {
    "ESTO": {"dash": "dot", "marker_symbol": "circle"},
    "LEAP": {"dash": "dash", "marker_symbol": "diamond"},
    "NINTH": {"dash": "dashdot", "marker_symbol": "square"},
    "9TH": {"dash": "dashdot", "marker_symbol": "square"},
}


def _apply_total_series_chrome(fig: go.Figure) -> None:
    """Give ESTO, LEAP, and 9th comparison lines stable visual roles.

    Matches on source-name substring alone, not a fixed suffix: comparison
    lines are named "{label} <suffix>" with suffixes that vary by chart
    ("total", "supply total", "supply (01-03)", "demand (TFC)"), so a
    " total" test silently missed most of them and left them on the
    positional colorway.

    Stacked traces are skipped explicitly. They are named for a product,
    sector, or flow rather than a source, so they do not collide today --
    no label in the current 104 flow / 75 product universe contains a
    source name -- but they take their colour from the code map and must
    keep it if a future label ever does.
    """
    for trace in fig.data:
        trace_name = str(getattr(trace, "name", ""))
        if getattr(trace, "stackgroup", None):
            continue
        source = next((key for key in _TOTAL_SERIES_COLORS if key.casefold() in trace_name.casefold()), None)
        if source is None:
            continue
        configured_series = load_code_colors().get("plotting", {}).get("series", {})
        color = next(
            (
                configured_color
                for label, configured_color in sorted(
                    configured_series.items(), key=lambda item: len(str(item[0])), reverse=True
                )
                if trace_name.casefold().startswith(str(label).casefold())
            ),
            _TOTAL_SERIES_COLORS[source],
        )
        style = _TOTAL_SERIES_STYLES[source]
        trace_line = getattr(trace, "line", None)
        if trace_line is not None:
            trace_line.color = color
            trace_line.width = max(float(trace_line.width or 0), 2.25)
            trace_line.dash = style["dash"]
        if getattr(trace, "marker", None) is not None:
            trace.marker.color = color
            if hasattr(trace.marker, "size"):
                trace.marker.size = max(float(trace.marker.size or 0), 6.0)
            if hasattr(trace.marker, "symbol"):
                trace.marker.symbol = style["marker_symbol"]
            trace.marker.line.color = "#ffffff"
            trace.marker.line.width = max(float(trace.marker.line.width or 0), 1.5)
        trace_mode = str(getattr(trace, "mode", "") or "")
        if "lines" in trace_mode and "markers" not in trace_mode:
            trace.mode = "lines+markers"


def apply_chart_chrome(fig: go.Figure, base_year: int | None = None, code_axis: str | None = None) -> go.Figure:
    """Apply the shared white background and base-year marker to a chart.

    Pass code_axis ("product"/"flow") when the stacked traces are named with
    common ESTO labels, so they take their colour from the code map instead of
    the positional colorway. The colorway stays as the fallback for traces the
    map does not cover.
    """
    fig.update_layout(**_WHITE_BACKGROUND_LAYOUT, colorway=_PRODUCT_COLORWAY)
    fig.update_xaxes(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
    fig.update_yaxes(
        gridcolor="#e5e7eb",
        zerolinecolor="#4b5563",
        zerolinewidth=2.5,
    )
    fig.update_layout(
        # Plotly may omit the legend when scenario/dataset filtering leaves a
        # single visible trace. Keep it so the remaining line or area always
        # identifies itself explicitly.
        showlegend=True,
        legend={
            "font": {"size": 11},
            "bgcolor": "rgba(255,255,255,0.84)",
            "bordercolor": "rgba(148,163,184,0.45)",
            "borderwidth": 1,
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
            "groupclick": "togglegroup",
            "tracegroupgap": 3,
        }
    )
    if code_axis:
        _apply_code_colors(fig, code_axis)
    # Runs after the code colours so comparison total lines keep their stable
    # source colour even when their name parses as a code expression.
    _apply_total_series_chrome(fig)
    if base_year is not None:
        fig.add_vline(
            x=base_year,
            line_dash="dot",
            line_color="#6b7280",
            annotation_text=f"Base year {base_year}",
            annotation_position="top right",
            annotation_font_size=10,
            annotation_font_color="#6b7280",
        )
    return fig


def build_area_chart(
    df: pd.DataFrame,
    area_spec: dict[str, object],
    series_labels: dict[str, str],
    template: dict,
    group_col: str = "common_product_label",
    title_prefix: str = "Aggregate by product",
) -> go.Figure:
    """Build a stacked product area chart with dataset-comparison total lines.

    The stacked area colors switch datasets at the base year: ESTO actuals
    fill the area through base_year, then the primary LEAP scenario fills it
    from base_year onward. If a segment's dataset has no rows for this flow,
    that segment is left blank rather than falling back to another dataset.

    Two full stacks are built - one per primary scenario (Reference/Target) -
    each embedding the same ESTO pre-base-year segment, tagged "ref"/"tgt" so
    only one is visible at a time and the client-side REF/TGT toggle can swap
    between them.
    """
    chart_df = _non_overlapping_common_row_frontier(area_spec_rows(df, area_spec))
    if "flow" in group_col:
        chart_df = _non_overlapping_flow_rows(chart_df)
    chart_unit = _chart_unit(chart_df)
    chart_config = template.get("chart_generation", {})
    comparison_source = str(chart_config.get("comparison_source_system", "ESTO"))
    base_year = int(chart_config.get("base_year", 2023))
    primary_source = str(chart_config.get("primary_area_source_system", "LEAP"))
    default_scenario = str(chart_config.get("primary_area_scenario", "Target"))

    pre_base_df = chart_df[
        (chart_df["source_system"].astype(str).str.casefold() == comparison_source.casefold())
        & (chart_df["year"] <= base_year)
    ]

    # Use the union of nonzero ESTO-history and LEAP-projection categories.
    # Historical-only fuels must remain in the pre-base stack so its envelope
    # reconciles to the ESTO total line; they naturally end at the base year.
    projected_rows = chart_df[
        (chart_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (chart_df["scenario"].astype(str).str.casefold().isin({"reference", "target"}))
        & (chart_df["year"] > base_year)
    ].copy()
    projected_rows["_gross_value"] = pd.to_numeric(
        projected_rows["value"], errors="coerce"
    ).fillna(0.0).abs()
    projected_groups = projected_rows.groupby(group_col, dropna=False)["_gross_value"].sum()
    historical_rows = pre_base_df.copy()
    historical_rows["_gross_value"] = pd.to_numeric(
        historical_rows["value"], errors="coerce"
    ).fillna(0.0).abs()
    historical_groups = historical_rows.groupby(group_col, dropna=False)["_gross_value"].sum()
    active_groups = projected_groups.loc[projected_groups > 1e-12].index.union(
        historical_groups.loc[historical_groups > 1e-12].index
    )
    pre_base_df = pre_base_df[pre_base_df[group_col].isin(active_groups)]

    fig = go.Figure()
    trace_meta: list[dict] = []
    for scenario_name in ("Reference", "Target"):
        post_base_df = chart_df[
            (chart_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
            & (chart_df["scenario"].astype(str).str.casefold() == scenario_name.casefold())
            & (chart_df["year"] > base_year)
            & (chart_df[group_col].isin(active_groups))
        ]
        area_df = pd.concat([pre_base_df, post_base_df], ignore_index=True)
        if area_df.empty:
            continue
        tag = scenario_toggle_tag(primary_source, scenario_name)
        is_default = scenario_name.casefold() == default_scenario.casefold()
        signed_area_df = area_df.copy()
        signed_values = pd.to_numeric(signed_area_df["value"], errors="coerce").fillna(0.0)
        signed_area_df["_positive_value"] = signed_values.clip(lower=0.0)
        signed_area_df["_negative_value"] = signed_values.clip(upper=0.0)
        group_df = (
            signed_area_df.groupby([group_col, "year"], as_index=False)[
                ["_positive_value", "_negative_value"]
            ]
            .sum()
            .sort_values([group_col, "year"])
        )
        for group_label, group in group_df.groupby(group_col, dropna=False):
            if not (
                _has_nonzero_values(group["_positive_value"])
                or _has_nonzero_values(group["_negative_value"])
            ):
                continue
            trace_count = _add_preseparated_signed_stack_traces(
                fig=fig,
                x_values=group["year"],
                signed_parts=[
                    ("pos", group["_positive_value"]),
                    ("neg", group["_negative_value"]),
                ],
                stackgroup_prefix=f"scenario_{tag}",
                trace_name=str(group_label),
                visible=is_default,
                hovertemplate=(
                    "%{x}<br>Signed value: %{y:,.2f}"
                    + chart_unit
                    + "<extra>"
                    + escape(str(group_label))
                    + "</extra>"
                ),
            )
            trace_meta.extend(
                trace_meta_entry(primary_source, scenario_name, True)
                for _ in range(trace_count)
            )

    total_df = (
        chart_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum().sort_values(["source_system", "scenario", "year"])
    )
    for (source_system, scenario), group in total_df.groupby(["source_system", "scenario"], dropna=False):
        # Every dataset gets an explicit signed-sum total line, including ones
        # already drawn as stacked area colors above (ESTO, primary LEAP
        # scenario): when a group's components have mixed signs, the stack is
        # split into separate pos/neg stackgroups (see comment above), so the
        # stack alone no longer shows a single net total line to compare
        # against ESTO/NINTH totals.
        # Non-comparison-source totals (LEAP and NINTH) include the base-year
        # point when supplied. Keeping that point beside ESTO makes any
        # calibration gap visible, while earlier backcast years remain hidden.
        if str(source_system).casefold() != comparison_source.casefold():
            group = group[group["year"] >= base_year]
        if group.empty:
            continue
        label = series_label_from_values(source_system, scenario, series_labels)
        fig.add_trace(
            go.Scatter(
                x=group["year"],
                y=group["value"],
                mode="lines+markers",
                name=f"{label} total",
                line={"dash": "dash"},
            )
        )
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    fig.update_layout(
        title=title_with_sign_note(f"{title_prefix}: {area_spec['aggregate_flow_label']}", chart_df),
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        # Product legends can contain 20+ entries. Keeping them above the plot
        # made the legend collide with the title in narrow overview cards.
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": chart_note_with_lng_coverage(
                (
                    f"Stacked areas: {dataset_display_name(comparison_source)} historical through "
                    f"{base_year}; {dataset_display_name(primary_source)} projection after {base_year}."
                ),
                chart_df,
            ),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis=code_axis_for_group_col(group_col))
    return fig


def _build_section_aggregate_charts(
    page_df: pd.DataFrame,
    page_key: str,
    page_label: str,
    parent_flow_labels: set[str],
    template: dict,
    series_labels: dict[str, str],
) -> tuple[dict[str, go.Figure], list[dict], list[dict]]:
    """Build the two aggregate area charts (by product, by flow) shown at the top of each section.

    Replaces the old page-wide "By product" section: each real section (e.g.
    Transfers) already breaks down into per-flow/product line charts, so these
    aggregates summarise everything non-subtotal within just that section.
    """
    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    non_parent_df = page_df[~page_df["common_flow_label"].isin(parent_flow_labels)]
    if non_parent_df.empty:
        return charts, chart_rows, manifest_rows

    chart_config = template.get("chart_generation", {})
    primary_source = str(chart_config.get("primary_area_source_system", "LEAP"))
    primary_scenario = str(chart_config.get("primary_area_scenario", "Target"))
    comparison_source = str(chart_config.get("comparison_source_system", "ESTO"))
    base_year = int(chart_config.get("base_year", 2023))
    ninth_source = str(chart_config.get("ninth_source_system", "NINTH"))
    suppression_threshold = effective_chart_suppression_threshold(template, page_df)

    flow_section = non_parent_df.groupby("common_flow_label")["_section_label"].agg(lambda s: s.mode().iloc[0])
    section_flows: dict[str, list[str]] = {}
    for flow_label, section_label in flow_section.items():
        section_flows.setdefault(str(section_label), []).append(str(flow_label))

    ordered_sections: list[str] = []
    for flow_label in non_parent_df["common_flow_label"]:
        section_label = str(flow_section.get(flow_label, page_label))
        if section_label not in ordered_sections:
            ordered_sections.append(section_label)

    other_transformation_config = template.get("other_transformation_page", {})
    is_other_transformation_page = page_key == safe_slug(
        other_transformation_config.get("page_key", "other_transformation")
    )
    overview_summaries = {
        str(item.get("section_label", "")).strip().casefold(): {
            "group_by": str(item.get("group_by", "product")).strip().casefold(),
            "order": order,
        }
        for order, item in enumerate(
            other_transformation_config.get("overview_summaries", [])
        )
        if str(item.get("section_label", "")).strip()
    }
    if is_other_transformation_page and overview_summaries:
        existing_order = {label: order for order, label in enumerate(ordered_sections)}
        ordered_sections.sort(
            key=lambda label: (
                overview_summaries.get(
                    label.casefold(), {"order": len(overview_summaries)}
                )["order"],
                existing_order[label],
            )
        )

    for section_label in ordered_sections:
        overview_summary = overview_summaries.get(section_label.casefold())
        if is_other_transformation_page and overview_summaries and not overview_summary:
            continue
        flow_labels = sorted(set(section_flows.get(section_label, [])))
        if not flow_labels:
            continue
        area_spec = {
            "aggregate_flow_prefix": "",
            "aggregate_flow_label": section_label,
            "source_flow_labels": flow_labels,
        }
        area_df = page_df[page_df["common_flow_label"].isin(flow_labels)]
        effective_flow_rows = _non_overlapping_flow_rows(
            _non_overlapping_common_row_frontier(area_df)
        )
        effective_flow_count = effective_flow_rows["common_flow_label"].nunique(
            dropna=True
        )
        overview_group_by = ""
        if overview_summary:
            overview_group_by = str(overview_summary["group_by"])
            if overview_group_by == "flow_or_product":
                overview_group_by = "flow" if effective_flow_count > 1 else "product"
        for group_col, group_noun, title_prefix, manifest_flow, manifest_product in (
            ("common_product_label", "product", "Aggregate by product", section_label, "All products"),
            ("common_flow_label", "flow", "Aggregate by flow", "All flows", section_label),
        ):
            if overview_summary and group_noun != overview_group_by:
                continue
            chart_key = f"chart__area__section__{safe_slug(page_key)}__{safe_slug(section_label)}__{group_noun}"
            metrics = compute_ranking_metrics(area_df, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            redundant_single_flow = group_noun == "flow" and effective_flow_count <= 1
            suppressed = (
                metrics["total_abs_value"] < suppression_threshold
                or redundant_single_flow
            )
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": "Overview" if overview_summary else section_label,
                "chart_type": "stacked_area",
                "chart_key": chart_key,
                "common_flow_label": manifest_flow,
                "common_product_label": manifest_product,
                "row_count": int(len(area_df)),
                "source_flow_labels": "; ".join(flow_labels),
                "sign_note": sign_note_for_chart(area_df),
                "suppressed": suppressed,
                **metrics,
            })
            if suppressed:
                continue
            figure = build_area_chart(
                page_df,
                area_spec,
                series_labels,
                template,
                group_col=group_col,
                title_prefix=title_prefix,
            )
            if not figure.data:
                manifest_rows[-1]["suppressed"] = True
                continue
            charts[chart_key] = figure
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": f"{title_prefix}: {section_label}",
                "product_label": f"{title_prefix}: {section_label}",
                "section_label": "Overview" if overview_summary else section_label,
                "navigation_root_label": section_label if overview_summary else "",
                "navigation_root_section_label": section_label if overview_summary else "",
                "datasets": chart_dataset_tokens_from_figure(figure),
                "stacked_area_note": stacked_area_note_from_figure(figure),
                **metrics,
            })
    return charts, chart_rows, manifest_rows


def _build_flow_group_aggregate_charts(
    page_df: pd.DataFrame,
    page_key: str,
    page_label: str,
    parent_flow_labels: set[str],
    template: dict,
    series_labels: dict[str, str],
) -> tuple[dict[str, go.Figure], list[dict], list[dict]]:
    """Build per-subsection aggregate area charts (by product, by sub-flow).

    Mirrors _build_section_aggregate_charts but at the finer common_flow_label
    granularity, so a subsection like "Electricity plants" opens with its own
    totals rather than only per-product small multiples. Only sections that
    actually split into multiple flow-group subsections (the same threshold
    line_section_tree/_line_sections_html use for the h3 headings) get these
    charts - a section that's already a single flow would just duplicate the
    section-level aggregate. The by-sub-flow breakdown only appears when a
    flow's rows actually resolve to more than one distinct component flow
    (i.e. the common flow label is a rollup of several raw ESTO/LEAP flows).
    """
    page_df = drop_placeholder_only_demand_detail_rows(page_key, page_df, template)
    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    non_parent_df = page_df[~page_df["common_flow_label"].isin(parent_flow_labels)]
    if non_parent_df.empty:
        return charts, chart_rows, manifest_rows

    chart_config = template.get("chart_generation", {})
    primary_source = str(chart_config.get("primary_area_source_system", "LEAP"))
    primary_scenario = str(chart_config.get("primary_area_scenario", "Target"))
    comparison_source = str(chart_config.get("comparison_source_system", "ESTO"))
    base_year = int(chart_config.get("base_year", 2023))
    ninth_source = str(chart_config.get("ninth_source_system", "NINTH"))
    suppression_threshold = effective_chart_suppression_threshold(template, page_df)
    synthetic_intermediate_labels = {
        str(code).strip(): str(label).strip()
        for code, label in chart_config.get(
            "synthetic_intermediate_flow_labels", {}
        ).items()
        if str(code).strip() and str(label).strip()
    }

    page_df = page_df.copy()
    if "component_flow_name" in page_df.columns:
        subflow_label = page_df["component_flow_name"].astype(str).str.strip()
        subflow_label = subflow_label.where(subflow_label != "", page_df["common_flow_label"])
    else:
        subflow_label = page_df["common_flow_label"]
    page_df["_subflow_label"] = subflow_label

    flow_section = non_parent_df.groupby("common_flow_label")["_section_label"].agg(lambda s: s.mode().iloc[0])

    # Parent rows are omitted from the detail charts so users cannot add a
    # hierarchy parent to its children. Replace each omitted parent with one
    # aggregate-by-product summary built from a source-specific frontier. A
    # source that publishes the parent contributes that row; a source that
    # publishes only children contributes its non-overlapping child rows.
    # Parents whose descendants cross page sections (for example the broad
    # flow-10 boundary spanning own use and losses) are intentionally skipped.
    flow_nodes = get_existing_flow_nodes(page_df)
    parent_prefixes: list[str] = []
    for _, node in flow_nodes.iterrows():
        flow_label = str(node["common_flow_label"])
        prefix = str(node["canonical_code"])
        # A compound boundary can begin at this prefix while extending into a
        # sibling branch. It is valid for its full-page overview, but cannot
        # act as the parent of a narrower subsection. Otherwise, for example,
        # the 16.01 card combines LEAP's 16.01-16.02 Buildings rollup with
        # Ninth's 16.01 commercial rows.
        if not _code_expression_contains_expression(
            prefix,
            node["common_flow_code"],
        ):
            continue
        if flow_label in parent_flow_labels and prefix not in parent_prefixes:
            parent_prefixes.append(prefix)
    for prefix in synthetic_intermediate_labels:
        descendant_count = flow_nodes[
            flow_nodes["canonical_code"].astype(str).str.startswith(prefix + ".")
        ]["common_flow_label"].nunique()
        if descendant_count >= 1 and prefix not in parent_prefixes:
            parent_prefixes.append(prefix)
    parent_prefixes.sort(key=lambda value: (code_depth(value), value))

    for parent_prefix in parent_prefixes:
        # Top-level roots are already represented by page overview cards and
        # can be split across routed pages. A flow-09 subsection on Other
        # transformation, for example, would be only a partial transformation
        # total because Power and Refining own more-specific branches.
        if code_depth(parent_prefix) == 1:
            continue
        descendants = flow_nodes[
            flow_nodes["canonical_code"].astype(str).str.startswith(parent_prefix + ".")
        ]
        if descendants.empty:
            continue
        labels_by_source = frontier_flow_labels(
            flow_nodes,
            parent_prefix,
            code_depth(parent_prefix) + 1,
        )
        source_flow_labels = sorted(
            {
                str(label)
                for source_labels in labels_by_source.values()
                for label in source_labels
            }
        )
        if not source_flow_labels:
            continue
        area_spec = {
            "aggregate_flow_prefix": parent_prefix,
            "aggregate_flow_label": "",
            "source_flow_labels": source_flow_labels,
            "source_flow_labels_by_system": labels_by_source,
        }
        aggregate_df = area_spec_rows(page_df, area_spec)
        if aggregate_df.empty:
            continue
        section_labels = [
            str(value)
            for value in aggregate_df["_section_label"].dropna().unique()
            if str(value).strip()
        ]
        if len(section_labels) != 1:
            continue
        section_label = section_labels[0]
        exact_parent_nodes = flow_nodes[
            (flow_nodes["canonical_code"].astype(str) == parent_prefix)
            & flow_nodes["common_flow_label"].astype(str).isin(parent_flow_labels)
        ]
        parent_candidates = exact_parent_nodes["common_flow_label"].astype(str).tolist()
        configured_parent_label = synthetic_intermediate_labels.get(parent_prefix, "")
        if configured_parent_label:
            parent_label = configured_parent_label
        elif parent_candidates:
            parent_label = min(
                parent_candidates,
                key=lambda value: (
                    "including own use" not in value.casefold(),
                    len(value),
                    value,
                ),
            )
        else:
            parent_label = node_label_for_prefix(flow_nodes, parent_prefix)
        area_spec["aggregate_flow_label"] = parent_label

        chart_key = (
            f"chart__area__flowgroup_parent__{safe_slug(page_key)}__"
            f"{safe_slug(parent_prefix)}__product"
        )
        metrics = compute_ranking_metrics(
            aggregate_df,
            primary_source,
            primary_scenario,
            comparison_source,
            base_year=base_year,
            ninth_source=ninth_source,
        )
        suppressed = metrics["total_abs_value"] < suppression_threshold
        manifest_rows.append({
            "page_key": page_key,
            "page_label": page_label,
            "section_label": section_label,
            "chart_type": "stacked_area",
            "chart_key": chart_key,
            "common_flow_label": parent_label,
            "common_product_label": "All products",
            "row_count": int(len(aggregate_df)),
            "source_flow_labels": " | ".join(source_flow_labels),
            "sign_note": sign_note_for_chart(aggregate_df),
            "suppressed": suppressed,
            **metrics,
        })
        if suppressed:
            continue
        figure = build_area_chart(
            page_df,
            area_spec,
            series_labels,
            template,
            group_col="common_product_label",
            title_prefix="Aggregate by product",
        )
        if not figure.data:
            manifest_rows[-1]["suppressed"] = True
            continue
        charts[chart_key] = figure
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "stacked_area",
            "title": f"Aggregate by product: {parent_label}",
            "product_label": f"Aggregate by product: {parent_label}",
            "section_label": section_label,
            "flow_group_label": parent_label,
            "datasets": chart_dataset_tokens_from_figure(figure),
            "stacked_area_note": stacked_area_note_from_figure(figure),
            **metrics,
        })

    ordered_flows: list[str] = []
    for flow_label in non_parent_df["common_flow_label"]:
        flow_label = str(flow_label)
        if flow_label not in ordered_flows:
            ordered_flows.append(flow_label)

    flows_per_section: dict[str, int] = {}
    for flow_label in ordered_flows:
        section_label = str(flow_section.get(flow_label, page_label))
        flows_per_section[section_label] = flows_per_section.get(section_label, 0) + 1

    for flow_label in ordered_flows:
        section_label = str(flow_section.get(flow_label, page_label))
        if flows_per_section.get(section_label, 0) < 2:
            continue
        flow_df = page_df[page_df["common_flow_label"].astype(str) == flow_label]
        if flow_df.empty:
            continue
        area_spec = {
            "aggregate_flow_prefix": "",
            "aggregate_flow_label": flow_label,
            "source_flow_labels": [flow_label],
            "source_flow_labels_by_system": equivalent_flow_labels_by_source(page_df, flow_label),
        }
        group_specs = [("common_product_label", "product", "Aggregate by product", flow_label, "All products")]
        if flow_df["_subflow_label"].nunique(dropna=True) > 1:
            group_specs.append(("_subflow_label", "subflow", "Aggregate by sub-flow", flow_label, "All sub-flows"))
        for group_col, group_noun, title_prefix, manifest_flow, manifest_product in group_specs:
            chart_key = f"chart__area__flowgroup__{safe_slug(page_key)}__{safe_slug(flow_label)}__{group_noun}"
            metrics = compute_ranking_metrics(flow_df, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            suppressed = metrics["total_abs_value"] < suppression_threshold
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": section_label,
                "chart_type": "stacked_area",
                "chart_key": chart_key,
                "common_flow_label": manifest_flow,
                "common_product_label": manifest_product,
                "row_count": int(len(flow_df)),
                "source_flow_labels": flow_label,
                "sign_note": sign_note_for_chart(flow_df),
                "suppressed": suppressed,
                **metrics,
            })
            if suppressed:
                continue
            figure = build_area_chart(
                page_df,
                area_spec,
                series_labels,
                template,
                group_col=group_col,
                title_prefix=title_prefix,
            )
            if not figure.data:
                manifest_rows[-1]["suppressed"] = True
                continue
            charts[chart_key] = figure
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": f"{title_prefix}: {flow_label}",
                "product_label": f"{title_prefix}: {flow_label}",
                "section_label": section_label,
                "flow_group_label": flow_label,
                "datasets": chart_dataset_tokens_from_figure(figure),
                "stacked_area_note": stacked_area_note_from_figure(figure),
                **metrics,
            })
    return charts, chart_rows, manifest_rows


def compute_diff_series(
    pair_df: pd.DataFrame,
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    comparison_source: str = "ESTO",
    ninth_source: str = "NINTH",
    base_year: int = 2023,
) -> tuple[pd.Series, pd.Series]:
    """Return (hist_diff, proj_diff) year-indexed Series for LEAP minus comparison.

    hist_diff covers years <= base_year (LEAP minus ESTO).
    proj_diff covers years > base_year (LEAP minus NINTH mean).
    Years with no LEAP data are excluded entirely.
    """
    by_year = pair_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    model = by_year[
        (by_year["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (by_year["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
    ].set_index("year")["value"]
    if model.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    hist_comp = by_year[
        by_year["source_system"].astype(str).str.casefold() == comparison_source.casefold()
    ].groupby("year")["value"].mean()
    proj_comp = by_year[
        by_year["source_system"].astype(str).str.casefold() == ninth_source.casefold()
    ].groupby("year")["value"].mean()
    hist_years = model.index[model.index <= base_year].intersection(hist_comp.index)
    ninth_base_year = ninth_base_year_for_rows(pair_df, base_year)
    proj_years = model.index[model.index > ninth_base_year].intersection(proj_comp.index)
    hist_diff = (model.loc[hist_years] - hist_comp.loc[hist_years]).sort_index() if not hist_years.empty else pd.Series(dtype=float)
    proj_diff = (model.loc[proj_years] - proj_comp.loc[proj_years]).sort_index() if not proj_years.empty else pd.Series(dtype=float)
    return hist_diff, proj_diff


def compute_diff_series_by_scenario(
    pair_df: pd.DataFrame,
    primary_source: str = "LEAP",
    comparison_source: str = "ESTO",
    ninth_source: str = "NINTH",
    base_year: int = 2023,
    scenarios: tuple[str, ...] = ("Reference", "Target"),
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """Return (hist_diff_by_scenario, proj_diff_by_scenario) for each of ``scenarios``.

    Lets the REF/TGT toggle switch between both scenarios' diff traces
    instead of only ever computing the single build-time "primary" scenario.
    """
    hist_by_scenario: dict[str, pd.Series] = {}
    proj_by_scenario: dict[str, pd.Series] = {}
    for scenario_name in scenarios:
        hist_diff, proj_diff = compute_diff_series(
            pair_df, primary_source, scenario_name, comparison_source, ninth_source, base_year
        )
        hist_by_scenario[scenario_name] = hist_diff
        proj_by_scenario[scenario_name] = proj_diff
    return hist_by_scenario, proj_by_scenario


def build_product_chart(
    chart_df: pd.DataFrame,
    flow_label: str,
    product_label: str,
    series_labels: dict[str, str],
    *,
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    comparison_source: str = "ESTO",
    base_year: int | None = None,
) -> go.Figure:
    """Build a line chart for one common flow/product row."""
    chart_df = _non_overlapping_common_row_frontier(chart_df)
    chart_unit = _chart_unit(chart_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    for (source_system, scenario), group in chart_df.groupby(["source_system", "scenario"], dropna=False):
        # Non-comparison sources (LEAP, NINTH) publish a full outlook time
        # series including their own historical backcast (e.g. NINTH goes
        # back to 1980), not just projections. Only ESTO should draw the
        # historical range here; other sources start at the base year so their
        # calibration gap against ESTO remains visible.
        if base_year is not None and str(source_system).casefold() != comparison_source.casefold():
            source_base_year = (
                ninth_base_year_for_rows(chart_df, base_year)
                if str(source_system).casefold() == "ninth"
                else base_year
            )
            group = group[group["year"] >= source_base_year]
        if group.empty:
            continue
        label = series_label(group.iloc[0], series_labels)
        # A displayed product can represent several distinct Common ESTO
        # component rows. Plotting those component values directly gives
        # Plotly repeated x values and creates vertical saw-tooth spikes.
        # The card label is the aggregate category, so emit exactly one
        # signed sum for each source/scenario/year.
        aggregation: dict[str, object] = {"value": "sum"}
        for metadata_column in ["sign_status", "sign_interpretation"]:
            if metadata_column in group.columns:
                aggregation[metadata_column] = join_unique_text
        group = (
            group.groupby("year", as_index=False, dropna=False)
            .agg(aggregation)
            .sort_values("year")
        )
        if not _has_nonzero_values(group["value"]):
            continue
        customdata = None
        hovertemplate = "%{x}<br>Signed value: %{y:,.2f}" + chart_unit + "<extra>" + escape(label) + "</extra>"
        if {"sign_status", "sign_interpretation"}.issubset(set(group.columns)):
            customdata = group[["sign_status", "sign_interpretation"]].astype(str).values
            hovertemplate = (
                "%{x}<br>Signed value: %{y:,.2f} " + chart_unit +
                "<br>Sign status: %{customdata[0]}"
                "<br>Meaning: %{customdata[1]}"
                "<extra>" + escape(label) + "</extra>"
            )
        fig.add_trace(
            go.Scatter(
                x=group["year"],
                y=group["value"],
                mode="lines+markers",
                name=label,
                customdata=customdata,
                hovertemplate=hovertemplate,
            )
        )
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    fig.update_layout(
        title=title_with_sign_note(f"{flow_label} - {product_label}", chart_df),
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        # Legend below the plot, not above: long product legends collide
        # with the title otherwise (see build_area_chart).
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": chart_note_with_lng_coverage("", chart_df),
        },
    )
    apply_chart_chrome(fig, base_year)
    return fig


def build_base_year_product_bar(
    chart_df: pd.DataFrame,
    flow_label: str,
    series_labels: dict[str, str],
    base_year: int,
    comparison_scope_label: str = "",
    source_value_multipliers: dict[str, float] | None = None,
) -> go.Figure:
    """Build a grouped fuel bar chart for one base-year-only balance flow."""
    base_df = chart_df[chart_df["year"] == base_year].copy()
    base_df = _non_overlapping_common_row_frontier(base_df)
    chart_unit = _chart_unit(base_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    for (source_system, scenario), group in base_df.groupby(
        ["source_system", "scenario"], dropna=False
    ):
        source_key = str(source_system).strip().upper()
        multiplier = float((source_value_multipliers or {}).get(source_key, 1.0))
        grouped = (
            group.groupby("common_product_label", as_index=False, dropna=False)["value"]
            .sum()
            .sort_values("common_product_label")
        )
        grouped["value"] = grouped["value"] * multiplier
        if grouped.empty or not _has_nonzero_values(grouped["value"]):
            continue
        label = series_label(group.iloc[0], series_labels)
        source_color = _TOTAL_SERIES_COLORS.get(str(source_system).strip().upper(), "")
        fig.add_trace(
            go.Bar(
                x=grouped["common_product_label"],
                y=grouped["value"],
                name=label,
                marker_color=source_color or None,
                hovertemplate=(
                    "%{x}<br>Signed value: %{y:,.2f} "
                    + chart_unit
                    + "<extra>"
                    + escape(label)
                    + "</extra>"
                ),
            )
        )
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    scope_suffix = f" ({comparison_scope_label})" if comparison_scope_label else ""
    fig.update_layout(
        title=title_with_sign_note(
            f"{flow_label}: base year {base_year}{scope_suffix}",
            base_df,
        ),
        xaxis_title="Fuel",
        yaxis_title=f"Signed energy ({chart_unit})",
        barmode="group",
        margin={"l": 64, "r": 28, "t": 84, "b": 210},
        legend={"orientation": "h", "yanchor": "top", "y": -0.32, "xanchor": "left", "x": 0},
        meta={"trace_meta": trace_meta},
    )
    fig.update_xaxes(tickangle=-35, automargin=True)
    apply_chart_chrome(fig)
    return fig


def _build_supply_base_year_bar_charts(
    page_df: pd.DataFrame,
    page_key: str,
    page_label: str,
    flow_codes: list[str],
    base_year: int,
    suppression_threshold: float,
    primary_source: str,
    primary_scenario: str,
    comparison_source: str,
    ninth_source: str,
    series_labels: dict[str, str],
    comparison_scope: str = "",
    comparison_scope_label: str = "",
    ordinary_page_df: pd.DataFrame | None = None,
    source_value_multipliers_by_flow: dict[str, dict[str, float]] | None = None,
) -> tuple[dict[str, go.Figure], list[dict], list[dict], pd.DataFrame]:
    """Build base-year bars and return rows left for ordinary chart generation."""
    configured_codes = {canonical_code(value) for value in flow_codes if canonical_code(value)}
    if not configured_codes or page_df.empty:
        return {}, [], [], page_df

    balance_mask = page_df["common_flow_code"].map(canonical_code).isin(configured_codes)
    balance_df = page_df[balance_mask & page_df["year"].eq(base_year)].copy()
    ordinary_df = page_df if ordinary_page_df is None else ordinary_page_df
    ordinary_balance_mask = ordinary_df["common_flow_code"].map(canonical_code).isin(
        configured_codes
    )
    remaining_df = ordinary_df[~ordinary_balance_mask].copy()
    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []
    for flow_label, flow_df in balance_df.groupby("common_flow_label", sort=True):
        flow_label = str(flow_label)
        section_label = (
            str(flow_df["_section_label"].mode().iloc[0])
            if "_section_label" in flow_df.columns and not flow_df.empty
            else page_label
        )
        chart_key = f"chart__bar__base_year__{safe_slug(page_key)}__{safe_slug(flow_label)}"
        metrics = compute_ranking_metrics(
            flow_df,
            primary_source,
            primary_scenario,
            comparison_source,
            base_year=base_year,
            ninth_source=ninth_source,
        )
        suppressed = metrics["total_abs_value"] < suppression_threshold
        manifest_rows.append({
            "page_key": page_key,
            "page_label": page_label,
            "section_label": section_label,
            "chart_type": "bar",
            "chart_key": chart_key,
            "common_flow_label": flow_label,
            "common_product_label": (
                f"Base-year fuels ({base_year}, {comparison_scope_label})"
                if comparison_scope_label
                else f"Base-year fuels ({base_year})"
            ),
            "data_comparison_scope": comparison_scope,
            "row_count": int(len(flow_df)),
            "source_flow_labels": flow_label,
            "sign_note": sign_note_for_chart(flow_df),
            "suppressed": suppressed,
            **metrics,
        })
        if suppressed:
            continue
        figure = build_base_year_product_bar(
            flow_df,
            flow_label,
            series_labels,
            base_year,
            comparison_scope_label=comparison_scope_label,
            source_value_multipliers={
                str(source).strip().upper(): float(multiplier)
                for source, multiplier in (
                    (source_value_multipliers_by_flow or {}).get(
                        canonical_code(flow_label), {}
                    )
                ).items()
            },
        )
        if not figure.data:
            manifest_rows[-1]["suppressed"] = True
            continue
        charts[chart_key] = figure
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "bar",
            "title": (
                f"{flow_label}: base year {base_year} ({comparison_scope_label})"
                if comparison_scope_label
                else f"{flow_label}: base year {base_year}"
            ),
            "product_label": (
                f"Base-year fuel comparison ({comparison_scope_label}): {flow_label}"
                if comparison_scope_label
                else f"Base-year fuel comparison: {flow_label}"
            ),
            "section_label": section_label,
            "flow_group_label": flow_label,
            "datasets": chart_dataset_tokens_from_figure(figure),
            "data_comparison_scope": comparison_scope,
            **metrics,
        })
    return charts, chart_rows, manifest_rows, remaining_df


_PAGE_CSS = """
:root {
  color-scheme: light;
  --page-padding-x: clamp(12px, 1.8vw, 24px);
  --page-padding-y: clamp(14px, 1.8vw, 24px);
  --body-font-size: clamp(15px, 0.22vw + 14px, 18px);
  --title-font-size: clamp(24px, 0.75vw + 18px, 34px);
  --section-title-size: clamp(18px, 0.45vw + 14px, 24px);
}
html { background: #f4f6f8; }
body {
  font-family: Segoe UI, Arial, sans-serif;
  margin: 0;
  background: #f4f6f8;
  color: #111;
  font-size: var(--body-font-size);
  line-height: 1.45;
  min-width: 320px;
}
a { color: #0b3d5c; text-decoration: none; }
a:hover { text-decoration: underline; }
.page-shell { width: 100%; max-width: none; margin: 0 auto; padding: 0 var(--page-padding-x) 32px; box-sizing: border-box; }
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  margin: 0 0 14px 0;
  padding: var(--page-padding-y) 0 10px 0;
  background: rgba(244, 246, 248, 0.96);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #d8dee4;
}
.header-main-row { display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-start;gap:10px 16px; }
.header-side-controls {
  display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;
  gap:8px 10px;flex:1 1 460px;
}
.header-inline-controls {
  display:flex;align-items:center;gap:6px;justify-content:safe flex-end;
  flex:1 1 100%;flex-wrap:nowrap;margin-left:0;min-width:0;
  overflow-x:auto;overflow-y:hidden;padding-bottom:2px;
}
.dashboard-context { margin-top:6px;color:#4b5563;font-size:13px;line-height:1.35; }
.dashboard-updated { margin-left:10px;padding-left:10px;border-left:1px solid #c5ccd3;color:#64748b;white-space:nowrap; }
.dashboard-switcher {
  display:flex;align-items:center;gap:6px;flex-wrap:nowrap;
  font-size:12px;color:#4b5563;white-space:nowrap;
}
.dashboard-switcher select {
  max-width:220px;padding:5px 28px 5px 8px;border:1px solid #c5ccd3;border-radius:6px;
  background:#fff;color:#111;font:inherit;
}
.header-links { display: flex; flex-wrap: wrap; gap: 8px; }
.header-chip {
  flex: 0 0 auto;
  padding: 6px 8px;
  border: 1px solid #c5ccd3;
  border-radius: 6px;
  background: #fff;
  color: #0b3d5c;
  font-size: 13px;
  text-decoration: none;
  white-space: nowrap;
}
.header-chip[data-current="true"] {
  border-color:#1f6feb;
  box-shadow:0 0 0 2px rgba(31, 111, 235, 0.16);
  font-weight:700;
}
.header-nav-separator { flex:0 0 auto;color:#6b7280;font-weight:700;line-height:1.25;padding:6px 1px; }
.header-toggle {
  width: 30px; height: 30px;
  border: 1px solid #c5ccd3;
  border-radius: 999px;
  background: #fff;
  color: #0b3d5c;
  cursor: pointer;
}
.header-toggle-row { display:flex;justify-content:flex-end;gap:8px;margin-top:8px; }
.page-header.is-collapsed .header-collapsible { display: none; }
.page-header.is-collapsed { padding-bottom:0;background:transparent;backdrop-filter:none;border-bottom-color:transparent; }
.page-header.is-collapsed .header-toggle-row { margin-top:0; }
.jump-nav {
  margin-top:8px;padding-top:8px;border-top:1px solid #d8dee4;
  display:flex;flex-wrap:wrap;gap:8px 10px;align-items:flex-start;
}
.jump-nav-label { font-weight:600;color:#4b5563;font-size:12px;white-space:nowrap;padding-top:4px; }
.jump-nav-groups { display:flex;flex-direction:column;gap:6px;min-width:0;flex:1 1 640px; }
.jump-nav-row { display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;min-width:0; }
.jump-nav-row[data-level="2"] { padding-left:18px; }
.jump-nav-row[data-level="3"] { padding-left:36px; }
.jump-nav-row[data-level="4"] { padding-left:54px; }
.jump-chip {
  position:relative;display:inline-flex;align-items:center;gap:6px;
  padding:4px 9px;border:1px solid #c5ccd3;border-radius:999px;
  background:#fff;color:#0b3d5c;text-decoration:none;font-size:12px;line-height:1.25;
  box-shadow:0 1px 1px rgba(15,23,42,0.04);
}
.jump-chip::before { content:"";display:block;width:8px;height:8px;border-radius:999px;flex:0 0 auto;background:#94a3b8; }
.jump-chip[data-level="1"] { background:#fff4e6;border-color:#f2a65a;color:#7a3b00; }
.jump-chip[data-level="1"]::before { background:#f97316; }
.jump-chip[data-level="2"] { background:#ecfdf3;border-color:#86d5a6;color:#166534; }
.jump-chip[data-level="2"]::before { background:#22c55e; }
.jump-chip[data-level="3"] { background:#eff6ff;border-color:#93c5fd;color:#1e40af; }
.jump-chip[data-level="3"]::before { background:#3b82f6; }
.jump-chip[data-level="4"] { background:#f5edff;border-color:#c69af0;color:#4c1d70; }
.jump-chip[data-level="4"]::before { background:#9333ea; }
.visible-note { margin:8px 0 10px 0;padding:8px 12px;background:#fffbe6;border-left:3px solid #f0a500;border-radius:4px;font-size:13px;color:#5a3e00;line-height:1.5; }
.scenario-toggle {
  display:flex;align-items:center;gap:6px;flex-wrap:nowrap;
  font-size:12px;color:#4b5563;white-space:nowrap;
}
.scenario-toggle-buttons { display:flex;border:1px solid #c5ccd3;border-radius:999px;overflow:hidden; }
.scenario-toggle-btn {
  padding:5px 12px;border:none;background:#fff;color:#0b3d5c;font:inherit;font-size:12px;cursor:pointer;
}
.scenario-toggle-btn + .scenario-toggle-btn { border-left:1px solid #c5ccd3; }
.scenario-toggle-btn.active { background:#1f6feb;color:#fff;font-weight:700; }
.category-basis-switcher { display:flex;align-items:center;gap:6px;font-size:12px;color:#4b5563;white-space:nowrap; }
.category-basis-switcher span { font-weight:600; }
.category-basis-switcher select { max-width:210px;padding:5px 28px 5px 8px;border:1px solid #c5ccd3;border-radius:6px;background:#fff;color:#111;font:inherit; }
.dataset-filter {
  display:inline-flex;align-items:center;gap:4px;flex-wrap:nowrap;flex:0 0 auto;
  width:max-content;max-width:max-content;
  font-size:12px;color:#4b5563;
}
.dataset-filter-label { flex:0 0 auto;font-weight:600;line-height:1.2;text-align:right; }
.dataset-filter-buttons { display:flex;flex:0 0 auto;border:1px solid #c5ccd3;border-radius:999px;overflow:hidden; }
.dataset-filter-btn {
  padding:5px 12px;border:none;background:#fff;color:#0b3d5c;font:inherit;font-size:12px;cursor:pointer;
}
.dataset-filter-btn + .dataset-filter-btn { border-left:1px solid #c5ccd3; }
.dataset-filter-btn.active { background:#1f6feb;color:#fff;font-weight:700; }
.dataset-filter-clear { padding:4px 8px;border:0;background:transparent;color:#1f6feb;font:inherit;cursor:pointer; }
.dataset-filter-status { width:100%;text-align:right;color:#64748b;font-size:11px; }
.dataset-filter-status.is-empty { color:#9a3412;font-weight:600; }
.chart-card.dataset-filtered { display:none; }
.dataset-group-empty { display:none !important; }
.dashboard-grid {
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  gap:12px;
  align-items:start;
}
.dashboard-grid.overview-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
.dashboard-grid.expand-1 { grid-template-columns:minmax(0, 1fr); }
.dashboard-grid.expand-2 { grid-template-columns:repeat(2, minmax(0, 1fr)); }
.dashboard-grid.expand-3 { grid-template-columns:repeat(3, minmax(0, 1fr)); }
.chart-card { margin:0;padding:10px;border:1px solid #d0d7de;border-radius:8px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,0.05); }
.chart-caption { font-weight:600;margin-bottom:4px; }
.meta-subline { margin-top:-4px;margin-bottom:8px;color:#4b5563;font-size:12px; }
.area-data-note { margin:-3px 0 8px 0;color:#64748b;font-size:11px;line-height:1.3;font-style:italic; }
.chart-load-state { min-height:22px;margin:4px 0 6px 0;color:#64748b;font-size:12px; }
.chart-load-state[data-loaded="true"] { display:none; }
.lazy-chart-plot {
  width:100%;height:clamp(380px, 62vh, 1100px);
  border:1px solid #d0d7de;border-radius:6px;background:#fff;display:block;box-sizing:border-box;
}
.lazy-chart-plot.is-unloaded { background:#f8fafc; }
.section-heading { margin:18px 0 8px 0;font-size:var(--section-title-size);color:#23384d; }
.subsection-heading { margin:14px 0 6px 12px;font-size:15px;font-weight:600;color:#4c1d70;padding-left:8px;border-left:3px solid #c69af0; }
@media (max-width: 900px) {
  .dashboard-grid, .dashboard-grid.overview-grid { grid-template-columns:minmax(0, 1fr); }
  .dashboard-updated { display:block;margin:4px 0 0 0;padding:0;border-left:0;white-space:normal; }
}
@media (max-width: 600px) {
  .header-side-controls { flex:1 1 100%;min-width:0;justify-content:flex-start; }
  .header-inline-controls { margin-left:0;flex-wrap:wrap;justify-content:flex-start;width:100%; }
  .header-links { width:100%; }
  .dashboard-grid, .dashboard-grid.overview-grid { grid-template-columns:minmax(0, 1fr); }
  .lazy-chart-plot { height:420px; }
}
"""

_HEADER_TOGGLE_JS = """
(function() {
  var pageHeader = document.getElementById('page-header');
  var toggle = document.getElementById('header-toggle');
  if (!pageHeader || !toggle) return;
  var key = 'common-esto-header-collapsed';
  var apply = function(collapsed) {
    pageHeader.classList.toggle('is-collapsed', collapsed);
    toggle.textContent = collapsed ? '▾' : '▴';
    toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    toggle.setAttribute('aria-label', collapsed ? 'Expand header' : 'Collapse header');
  };
  var collapsed = false;
  try { collapsed = window.localStorage.getItem(key) === 'true'; } catch (e) {}
  apply(collapsed);
  toggle.addEventListener('click', function() {
    collapsed = !pageHeader.classList.contains('is-collapsed');
    apply(collapsed);
    try { window.localStorage.setItem(key, collapsed ? 'true' : 'false'); } catch (e) {}
  });
})();
"""

_SCENARIO_TOGGLE_HTML = """
<div class="scenario-toggle" role="group" aria-label="Scenario">
  <span>Scenario</span>
  <div class="scenario-toggle-buttons">
    <button type="button" class="scenario-toggle-btn" data-scenario-toggle="ref">Reference</button>
    <button type="button" class="scenario-toggle-btn" data-scenario-toggle="tgt">Target</button>
  </div>
</div>
"""

_SCENARIO_TOGGLE_JS = """
(function() {
  var key = 'common-esto-scenario-mode';
  var getMode = function() {
    try {
      var stored = window.localStorage.getItem(key);
      if (stored === 'ref' || stored === 'tgt') return stored;
    } catch (e) {}
    return 'tgt';
  };
  var setMode = function(mode) {
    try { window.localStorage.setItem(key, mode); } catch (e) {}
  };

  // Traces are tagged "esto" (always shown), or "ref"/"tgt" (LEAP/9th),
  // with an independent optional "metric" dimension used only by the
  // TFC/TFEC sector chart's own Plotly dropdown. See scenario_toggle_tag /
  // trace_meta_entry in common_esto_dashboard_renderer.py.
  var computeVisible = function(entry, scenarioMode, metricMode) {
    var scenarioOk = entry.tag === 'esto' || entry.tag === scenarioMode;
    var metricOk = !entry.metric || entry.metric === 'both' || entry.metric === metricMode;
    return (scenarioOk && metricOk) ? entry.active_visible : false;
  };

  window.applyScenarioMode = function(plot) {
    if (!window.Plotly || !plot || !plot.layout) return;
    var meta = plot.layout.meta && plot.layout.meta.trace_meta;
    if (!meta || !meta.length) return;
    var scenarioMode = getMode();
    var metricMode = plot._metricMode || 'tfc';
    var visible = meta.map(function(entry) { return computeVisible(entry, scenarioMode, metricMode); });
    window.Plotly.restyle(plot, {visible: visible});
  };

  var syncButtons = function() {
    var mode = getMode();
    document.querySelectorAll('[data-scenario-toggle]').forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.scenarioToggle === mode);
    });
  };
  syncButtons();

  document.querySelectorAll('[data-scenario-toggle]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      setMode(btn.dataset.scenarioToggle);
      syncButtons();
      document.querySelectorAll('.lazy-chart-plot[data-rendered="true"]').forEach(function(plot) {
        window.applyScenarioMode(plot);
      });
    });
  });
})();
"""

_DATASET_FILTER_JS = """
(function() {
  var filter = document.querySelector('[data-dataset-filter-group]');
  var buttons = Array.from(document.querySelectorAll('[data-dataset-filter]'));
  if (!filter || !buttons.length) return;
  var scope = filter.dataset.comparisonScope || 'default';
  var key = 'common-esto-dataset-filter:' + scope;
  var status = document.querySelector('[data-dataset-filter-status]');
  var clear = document.querySelector('[data-dataset-filter-clear]');
  var available = buttons.map(function(button) { return button.dataset.datasetFilter; });
  var active = [];
  try {
    var stored = JSON.parse(window.localStorage.getItem(key) || '[]');
    if (Array.isArray(stored)) {
      active = stored
        .map(function(d) { return String(d).toUpperCase(); })
        .filter(function(d) { return available.indexOf(d) !== -1; });
    }
  } catch (e) {}

  // A card stays visible only if it contains every highlighted (active) dataset.
  var apply = function() {
    buttons.forEach(function(btn) {
      var selected = active.indexOf(btn.dataset.datasetFilter) !== -1;
      btn.classList.toggle('active', selected);
      btn.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    var cards = Array.from(document.querySelectorAll('.chart-card[data-datasets]'));
    var visibleCount = 0;
    cards.forEach(function(card) {
      var have = (card.dataset.datasets || '').split(',').filter(Boolean);
      var hidden = active.some(function(d) { return have.indexOf(d) === -1; });
      card.classList.toggle('dataset-filtered', hidden);
      if (!hidden) visibleCount += 1;
    });
    document.querySelectorAll('[data-dataset-filter-section]').forEach(function(group) {
      var groupCards = Array.from(group.querySelectorAll('.chart-card[data-datasets]'));
      var hasVisibleCard = groupCards.some(function(card) {
        return !card.classList.contains('dataset-filtered');
      });
      group.classList.toggle('dataset-group-empty', groupCards.length > 0 && !hasVisibleCard);
    });
    if (status) {
      var selectedText = active.length ? ' containing ' + active.join(' + ') : '';
      status.textContent = visibleCount
        ? 'Showing ' + visibleCount + ' of ' + cards.length + ' charts' + selectedText + '.'
        : 'No charts on this page show every selected dataset (' + active.join(' + ') + '). Clear the chart filter to show all charts.';
      status.classList.toggle('is-empty', visibleCount === 0);
    }
    if (clear) clear.hidden = active.length === 0;
    try { window.localStorage.setItem(key, JSON.stringify(active)); } catch (e) {}
    if (window.Plotly) {
      document.querySelectorAll('.chart-card:not(.dataset-filtered) .lazy-chart-plot[data-rendered="true"]')
        .forEach(function(p) { window.Plotly.Plots.resize(p); });
    }
  };

  buttons.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var d = btn.dataset.datasetFilter;
      var i = active.indexOf(d);
      if (i === -1) { active.push(d); } else { active.splice(i, 1); }
      apply();
    });
  });
  if (clear) {
    clear.addEventListener('click', function() {
      active = [];
      apply();
    });
  }
  apply();
})();
"""

_LAZY_LOAD_JS = """
(function() {
  var plots = Array.from(document.querySelectorAll('.lazy-chart-plot[data-chart-key]'));
  if (!plots.length || !window.Plotly) return;
  var bundleData = window.COMMON_ESTO_CHART_BUNDLE_DATA;

  var setState = function(plot, text, loaded) {
    var state = plot.previousElementSibling;
    if (state && state.classList.contains('chart-load-state')) {
      state.dataset.loaded = loaded ? 'true' : 'false';
      state.textContent = text || '';
    }
  };

  var renderPlot = async function(plot) {
    if (plot.dataset.rendered === 'true' || plot.dataset.rendering === 'true') return;
    plot.dataset.rendering = 'true';
    setState(plot, 'Loading chart…', false);
    try {
      var bundle = bundleData;
      var chart = bundle && bundle.charts && bundle.charts[plot.dataset.chartKey];
      if (!chart) throw new Error('Missing chart: ' + plot.dataset.chartKey);
      await window.Plotly.newPlot(plot, chart.data || [], chart.layout || {}, {responsive: true});
      plot.dataset.rendered = 'true';
      plot.classList.remove('is-unloaded');
      setState(plot, '', true);
      window.Plotly.Plots.resize(plot);
      if (window.applyScenarioMode) {
        if (plot.on) {
          plot.on('plotly_buttonclicked', function(ev) {
            var label = (ev && ev.button && ev.button.label) || '';
            plot._metricMode = /TFEC/i.test(label) ? 'tfec' : 'tfc';
            window.applyScenarioMode(plot);
          });
        }
        window.applyScenarioMode(plot);
      }
    } catch (err) {
      plot.classList.add('is-unloaded');
      setState(plot, 'Chart failed: ' + (err.message || err), false);
    } finally {
      plot.dataset.rendering = 'false';
    }
  };

  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) { renderPlot(entry.target); observer.unobserve(entry.target); }
      });
    }, {rootMargin: '900px 0px'});
    plots.forEach(function(p) { observer.observe(p); });
  } else {
    plots.forEach(renderPlot);
  }

  window.addEventListener('resize', function() {
    plots.forEach(function(p) { if (p.dataset.rendered === 'true') window.Plotly.Plots.resize(p); });
  });
})();
"""

_DASHBOARD_SWITCHER_JS = """
(function() {
  document.querySelectorAll('[data-navigation-select]').forEach(function(select) {
    select.addEventListener('change', function() {
      var href = select.value;
      if (href) window.location.href = href;
    });
  });
})();
"""


def write_chart_bundle(charts: dict[str, go.Figure], output_path: Path) -> None:
    """Write a page-level Plotly chart bundle as JSON and JS."""
    assert_unique_line_trace_x(charts)
    payload = {
        "charts": {
            key: json.loads(json.dumps(figure, cls=PlotlyJSONEncoder))
            for key, figure in charts.items()
        }
    }
    payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    output_path.write_text(payload_json, encoding="utf-8")
    output_path.with_suffix(".js").write_text(
        "window.COMMON_ESTO_CHART_BUNDLE_DATA=" + payload_json.replace("</", "<\\/") + ";\n",
        encoding="utf-8",
    )


def assert_unique_line_trace_x(charts: dict[str, go.Figure]) -> None:
    """Block chart output when a line trace contains repeated x values."""
    failures: list[dict[str, object]] = []
    for chart_key, figure in charts.items():
        for trace_index, trace in enumerate(figure.data):
            mode = str(getattr(trace, "mode", "") or "")
            stackgroup = getattr(trace, "stackgroup", None)
            if "lines" not in mode and not stackgroup:
                continue
            x_values = getattr(trace, "x", None)
            if x_values is None:
                continue
            x_series = pd.Series(list(x_values), dtype=object)
            duplicate_mask = x_series.duplicated(keep=False)
            if not duplicate_mask.any():
                continue
            failures.append(
                {
                    "chart_key": chart_key,
                    "trace_index": trace_index,
                    "trace_name": str(getattr(trace, "name", "") or ""),
                    "duplicate_x_values": (
                        x_series.loc[duplicate_mask]
                        .drop_duplicates()
                        .head(10)
                        .tolist()
                    ),
                }
            )
    if failures:
        raise ValueError(
            "Dashboard line traces must contain at most one point per x "
            f"value. Examples: {failures[:10]}"
        )


def compute_ranking_metrics(
    pair_df: pd.DataFrame,
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    comparison_source: str = "ESTO",
    *,
    base_year: int = 2023,
    ninth_source: str = "NINTH",
    small_comparison_denominator: float = 1.0,
) -> dict[str, object]:
    """Compute sort ranking metrics for one flow/product chart.

    Uses ESTO as the comparison for years <= base_year and NINTH for years > base_year.
    Years where LEAP has no data are excluded from diff calculations rather than
    being treated as zero.
    """
    empty_metrics: dict[str, object] = {
        "total_abs_value": 0.0,
        "abs_diff": 0.0,
        "pct_diff": 0.0,
        "model_abs_value": 0.0,
        "comparison_abs_value": 0.0,
        "max_annual_absolute_difference": 0.0,
        "max_annual_percentage_difference": 0.0,
        "non_zero_year_count": 0,
        "unexpected_sign_count": 0,
        "ranking_warning": "missing_model;missing_comparison;sparse_model_series",
    }
    if pair_df.empty:
        return empty_metrics
    total_abs = float(pair_df["value"].abs().sum())
    by_year = pair_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    model = by_year[
        (by_year["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (by_year["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
    ].set_index("year")["value"]
    model_abs = float(model.abs().sum())
    non_zero_year_count = int((model.abs() > 1e-9).sum())
    warnings: list[str] = []
    if model.empty:
        warnings.extend(["missing_model", "missing_comparison", "sparse_model_series"])
        return {
            **empty_metrics,
            "total_abs_value": total_abs,
            "ranking_warning": ";".join(warnings),
        }
    if non_zero_year_count < 2:
        warnings.append("sparse_model_series")

    hist_comparison = by_year[
        by_year["source_system"].astype(str).str.casefold() == comparison_source.casefold()
    ].groupby("year")["value"].mean()
    proj_comparison = by_year[
        by_year["source_system"].astype(str).str.casefold() == ninth_source.casefold()
    ].groupby("year")["value"].mean()

    hist_years = model.index[model.index <= base_year].intersection(hist_comparison.index)
    ninth_base_year = ninth_base_year_for_rows(pair_df, base_year)
    proj_years = model.index[model.index > ninth_base_year].intersection(proj_comparison.index)

    all_diff_years = hist_years.union(proj_years)
    if all_diff_years.empty:
        warnings.append("missing_comparison")
        return {
            **empty_metrics,
            "total_abs_value": total_abs,
            "model_abs_value": model_abs,
            "non_zero_year_count": non_zero_year_count,
            "ranking_warning": ";".join(warnings),
        }

    diffs: list[pd.Series] = []
    comparisons: list[pd.Series] = []
    if not hist_years.empty:
        diffs.append((model.loc[hist_years] - hist_comparison.loc[hist_years]).abs())
        comparisons.append(hist_comparison.loc[hist_years])
    if not proj_years.empty:
        diffs.append((model.loc[proj_years] - proj_comparison.loc[proj_years]).abs())
        comparisons.append(proj_comparison.loc[proj_years])

    annual_diffs = pd.concat(diffs).sort_index() if diffs else pd.Series(dtype=float)
    paired_comparison = (
        pd.concat(comparisons).sort_index() if comparisons else pd.Series(dtype=float)
    )
    paired_model = model.loc[paired_comparison.index]
    comparison_abs = float(paired_comparison.abs().sum())
    abs_diff = float(annual_diffs.sum())

    usable_denominator = paired_comparison.abs() >= small_comparison_denominator
    small_denominator = ~usable_denominator
    if small_denominator.any():
        warnings.append("small_comparison_denominator")
    usable_comp_total = float(paired_comparison.loc[usable_denominator].abs().sum())
    usable_abs_diff = float(annual_diffs.loc[usable_denominator].sum())
    pct_diff = usable_abs_diff / usable_comp_total if usable_comp_total > 0 else 0.0
    annual_pct = (
        annual_diffs.loc[usable_denominator]
        / paired_comparison.loc[usable_denominator].abs()
    )
    unexpected_sign_count = int(
        (
            (paired_model.abs() > 1e-9)
            & (paired_comparison.abs() > 1e-9)
            & ((paired_model * paired_comparison) < 0)
        ).sum()
    )
    if unexpected_sign_count:
        warnings.append("unexpected_sign")

    return {
        "total_abs_value": total_abs,
        "abs_diff": abs_diff,
        "pct_diff": pct_diff,
        "model_abs_value": model_abs,
        "comparison_abs_value": comparison_abs,
        "max_annual_absolute_difference": (
            float(annual_diffs.max()) if not annual_diffs.empty else 0.0
        ),
        "max_annual_percentage_difference": (
            float(annual_pct.max()) if not annual_pct.empty else 0.0
        ),
        "non_zero_year_count": non_zero_year_count,
        "unexpected_sign_count": unexpected_sign_count,
        "ranking_warning": ";".join(warnings),
    }


RANKING_METRIC_DEFAULTS: dict[str, object] = {
    "model_abs_value": 0.0,
    "comparison_abs_value": 0.0,
    "max_annual_absolute_difference": 0.0,
    "max_annual_percentage_difference": 0.0,
    "non_zero_year_count": 0,
    "unexpected_sign_count": 0,
    "ranking_warning": "",
}


def finalize_chart_manifest(manifest_df: pd.DataFrame) -> pd.DataFrame:
    """Add complete, stable audit fields to the chart manifest."""
    finalized = manifest_df.copy()
    if "default_order" not in finalized.columns:
        if "page_key" in finalized.columns:
            finalized["default_order"] = finalized.groupby(
                "page_key", dropna=False, sort=False
            ).cumcount()
        else:
            finalized["default_order"] = range(len(finalized))

    missing_metric_rows = pd.Series(False, index=finalized.index)
    for column, default in RANKING_METRIC_DEFAULTS.items():
        if column not in finalized.columns:
            finalized[column] = default
            if column != "ranking_warning":
                missing_metric_rows[:] = True
            continue
        if column != "ranking_warning":
            missing_metric_rows = missing_metric_rows | finalized[column].isna()
        finalized[column] = finalized[column].fillna(default)

    warnings = finalized["ranking_warning"].fillna("").astype(str)
    warnings = warnings.mask(
        missing_metric_rows,
        warnings.map(lambda value: _append_warning(value, "ranking_metrics_unavailable")),
    )
    if "suppressed" in finalized.columns:
        suppressed = finalized["suppressed"].astype(str).str.casefold().isin(
            {"true", "1", "yes"}
        )
        warnings = warnings.mask(
            suppressed,
            warnings.map(lambda value: _append_warning(value, "suppressed")),
        )
    finalized["ranking_warning"] = warnings
    return finalized


def _append_warning(existing: str, warning: str) -> str:
    """Append one warning token without duplicates."""
    tokens = [token for token in str(existing).split(";") if token]
    if warning not in tokens:
        tokens.append(warning)
    return ";".join(tokens)


def _section_anchor(page_label: str, section_label: str, subsection_label: str | None = None) -> str:
    """Generate a stable HTML anchor id for a page section or subsection."""
    anchor = "sec-" + safe_slug(page_label) + "__" + safe_slug(section_label)
    if subsection_label:
        anchor = anchor + "__" + safe_slug(subsection_label)
    return anchor


def _nav_chips_html(all_pages: list[dict], current_file: str) -> str:
    """Build page-navigation chip HTML."""
    overview = ["total_demand"]
    demand = ["buildings", "industry", "transport", "others"]
    transform = ["power", "refining", "other_transformation"]
    supply = ["supply", "international_transport"]
    derived = ["emissions"]
    page_map = {p["page_key"]: p for p in all_pages}

    def chip(page_key: str) -> str:
        page = page_map.get(page_key)
        if not page:
            return ""
        is_current = page["file"] == current_file
        label = page.get("page_label") or page.get("label", page_key)
        return (
            f'<a href="{escape(page["file"])}" class="header-chip"'
            f' data-current="{"true" if is_current else "false"}">'
            f'{escape(label)}</a>'
        )

    sep = '<span class="header-nav-separator" aria-hidden="true">|</span>'
    parts: list[str] = []
    overview_chips = [chip(k) for k in overview if chip(k)]
    if overview_chips:
        parts.extend(overview_chips)
        parts.append(sep)
    for key in demand:
        h = chip(key)
        if h:
            parts.append(h)
    transform_chips = [chip(k) for k in transform if chip(k)]
    if transform_chips:
        parts.append(sep)
        parts.extend(transform_chips)
    supply_chips = [chip(k) for k in supply if chip(k)]
    if supply_chips:
        parts.append(sep)
        parts.extend(supply_chips)
    derived_chips = [chip(k) for k in derived if chip(k)]
    if derived_chips:
        parts.append(sep)
        parts.extend(derived_chips)
    remaining_keys = {p["page_key"] for p in all_pages} - set(overview + demand + transform + supply + derived)
    remaining_chips = [chip(k) for k in sorted(remaining_keys) if chip(k)]
    if remaining_chips:
        parts.append(sep)
        parts.extend(remaining_chips)
    return "".join(parts)


def _normalise_dashboard_switcher(series_config: dict, current_dashboard: str) -> list[dict[str, str]]:
    """Return configured dashboard switcher entries with the current dashboard included."""
    switcher = series_config.get("dashboard_switcher", {})
    if not switcher.get("enabled", False):
        return []

    dashboards = []
    for item in switcher.get("dashboards", []):
        dashboard_key = str(item.get("dashboard_key") or item.get("economy") or "").strip()
        label = str(item.get("label") or item.get("economy_label") or dashboard_key).strip()
        if not dashboard_key:
            continue
        dashboards.append({"dashboard_key": dashboard_key, "label": label or dashboard_key})

    if not any(item["dashboard_key"] == current_dashboard for item in dashboards):
        label = str(series_config.get("economy_label") or current_dashboard)
        dashboards.insert(0, {"dashboard_key": current_dashboard, "label": label})

    seen: set[str] = set()
    unique_dashboards: list[dict[str, str]] = []
    for item in dashboards:
        if item["dashboard_key"] in seen:
            continue
        seen.add(item["dashboard_key"])
        unique_dashboards.append(item)
    return unique_dashboards


def _current_dashboard_label(
    series_config: dict,
    dashboard_switcher: list[dict[str, str]],
    current_dashboard: str,
) -> str:
    """Return the display label for the dashboard currently being rendered."""
    for item in dashboard_switcher:
        if item["dashboard_key"] == current_dashboard:
            return item["label"]
    return str(series_config.get("economy_label") or current_dashboard)


def _dashboard_switcher_html(
    dashboards: list[dict[str, str]],
    current_dashboard: str,
    current_file: str,
    dashboard_key_suffix: str = "",
) -> str:
    """Build a static cross-economy switcher while retaining category scope."""
    if len(dashboards) <= 1:
        return ""

    options: list[str] = []
    for item in dashboards:
        dashboard_key = item["dashboard_key"]
        label = item["label"]
        target_dashboard_key = f"{dashboard_key}{dashboard_key_suffix}"
        href = (
            current_file
            if dashboard_key == current_dashboard
            else f"../../{escape(target_dashboard_key)}/dashboards/{escape(current_file)}"
        )
        selected = " selected" if dashboard_key == current_dashboard else ""
        options.append(f'<option value="{href}"{selected}>{escape(label)}</option>')

    return (
        '<label class="dashboard-switcher" data-guide-id="economy-switcher">'
        '<span>Economy</span>'
        f'<select data-navigation-select data-dashboard-switcher aria-label="Switch economy">{"".join(options)}</select>'
        '</label>'
    )


def _category_basis_switcher_html(
    category_basis_options: list[dict[str, str]],
    current_scope: str,
    current_file: str,
) -> str:
    """Build the comparison-scope selector for matching dashboard pages."""
    if len(category_basis_options) <= 1:
        return ""
    options: list[str] = []
    for item in category_basis_options:
        scope = str(item.get("comparison_scope", "")).strip()
        label = str(item.get("label", scope)).strip()
        dashboard_key = str(item.get("dashboard_key", "")).strip()
        if not scope or not dashboard_key:
            continue
        href = (
            current_file
            if scope == current_scope
            else f"../../{escape(dashboard_key)}/dashboards/{escape(current_file)}"
        )
        selected = " selected" if scope == current_scope else ""
        options.append(f'<option value="{href}"{selected}>{escape(label)}</option>')
    if len(options) <= 1:
        return ""
    return (
        '<label class="category-basis-switcher" data-guide-id="category-basis-switcher">'
        '<span>Comparison basis</span>'
        f'<select data-navigation-select data-category-basis-switcher aria-label="Choose the comparison basis">{"".join(options)}</select>'
        '</label>'
    )


_DATASET_DISPLAY_LABELS = {"NINTH": "Ninth"}

SHOW_DATASET_FILTER = False


def _dataset_filter_html(datasets: list[str], comparison_scope: str = "default") -> str:
    """Build the header dataset-filter button group.

    One toggle button per dataset configured for the active comparison scope.
    When a button is active (blue), chart cards lacking that dataset are hidden.

    Returns nothing while ``SHOW_DATASET_FILTER`` is off, which leaves the
    header without the control and the rest of the page untouched.
    """
    if not datasets or not SHOW_DATASET_FILTER:
        return ""
    buttons = "".join(
        f'<button type="button" class="dataset-filter-btn" data-dataset-filter="{escape(d)}" aria-pressed="false">'
        f'{escape(_DATASET_DISPLAY_LABELS.get(d, d))}</button>'
        for d in datasets
    )
    return (
        f'<div class="dataset-filter" role="group" aria-label="Charts containing dataset" data-dataset-filter-group data-comparison-scope="{escape(comparison_scope)}">'
        '<span class="dataset-filter-label">'
        "Charts containing:</span>"
        f'<div class="dataset-filter-buttons">{buttons}</div>'
        '<button type="button" class="dataset-filter-clear" data-dataset-filter-clear hidden>Clear</button>'
        '<span class="dataset-filter-status" data-dataset-filter-status aria-live="polite"></span>'
        '</div>'
    )


def _jump_nav_html(
    page_label: str,
    section_tree: list[tuple[str, list[dict[str, object]]]],
) -> str:
    """Build jump navigation from real visible flow nodes and levels.

    Page names and renderer-only section groups are not tree nodes, so they do
    not receive pills. Visible flow nodes are grouped by their effective tree
    level whether or not they have children: level 1 is orange, level 2 green,
    level 3 blue, and level 4 or deeper purple.
    """
    if not section_tree:
        return ""
    visible_nodes: list[dict[str, object]] = []
    for section_label, subsection_nodes in section_tree:
        for node in subsection_nodes:
            target = str(node.get("target") or "") or _section_anchor(
                page_label,
                section_label,
                str(node["label"]) if bool(node["use_subsection_anchor"]) else None,
            )
            visible_nodes.append({**node, "target": target})
    if not visible_nodes:
        return ""

    rows: list[str] = []
    for depth in sorted({int(node["depth"]) for node in visible_nodes}):
        level_nodes = sorted(
            (node for node in visible_nodes if int(node["depth"]) == depth),
            key=lambda node: section_order_key(node["label"]),
        )
        visual_level = min(max(depth, 1), 4)
        chips = "".join(
            f'<a href="#{escape(str(node["target"]))}" class="jump-chip" '
            f'data-level="{visual_level}" data-hierarchy-depth="{depth}">'
            f'{escape(str(node["label"]))}</a>'
            for node in level_nodes
        )
        rows.append(
            f'<div class="jump-nav-row" data-level="{visual_level}" '
            f'data-hierarchy-depth="{depth}">{chips}</div>'
        )
    return (
        f'<div class="jump-nav" data-guide-id="section-navigation"><span class="jump-nav-label">Sections:</span>'
        f'<div class="jump-nav-groups">{"".join(rows)}</div></div>'
    )


def stacked_area_note_from_figure(figure: go.Figure) -> str:
    """Read the renderer-supplied stacked-area dataset note from a figure."""
    meta = figure.layout.meta
    if isinstance(meta, dict):
        return str(meta.get("stacked_area_note", ""))
    return ""


def _area_charts_html(area_rows: list[dict], page_label: str) -> str:
    """Build HTML for the page-level overview (area) charts."""
    if not area_rows:
        return ""
    group_order: list[str] = []
    for row in area_rows:
        group_label = str(row.get("overview_group", "Overview"))
        if group_label not in group_order:
            group_order.append(group_label)

    sections: list[str] = []
    for group_label in group_order:
        group_rows = [
            row for row in area_rows
            if str(row.get("overview_group", "Overview")) == group_label
        ]
        grid_class = (
            "dashboard-grid overview-grid"
            if len(group_rows) > 1
            else "dashboard-grid expand-1"
        )
        cards = []
        for i, row in enumerate(group_rows):
            caption = escape(str(row.get("title", "")))
            key = escape(row["chart_key"])
            navigation_root_label = str(row.get("navigation_root_label") or "").strip()
            figure_id = (
                f' id="{escape(_overview_navigation_anchor(page_label, navigation_root_label))}"'
                if navigation_root_label
                else ""
            )
            cards.append(
                f'<figure{figure_id} class="chart-card" data-guide-id="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}" data-datasets="{escape(str(row.get("datasets", "")))}">'
                f'<figcaption class="chart-caption">{caption}</figcaption>'
                f'<div class="meta-subline">{escape(page_label)} &gt; {escape(group_label)}</div>'
                f'<div class="area-data-note">{escape(str(row.get("stacked_area_note", "")))}</div>'
                f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
                f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{caption}"></div>'
                f'</figure>'
            )
        grid_key = "overview" if group_label == "Overview" else f"overview-{safe_slug(group_label)}"
        sections.append(
            f'<section data-dataset-filter-section>'
            f'<h2 class="section-heading">{escape(group_label)}</h2>'
            f'<section class="section-sort-group">'
            f'<div class="{grid_class}" data-sortable-grid="{escape(grid_key)}">{"".join(cards)}</div>'
            f'</section>'
            f'</section>'
        )
    return "".join(sections)


def _grid_class_for(n: int) -> str:
    """Pick a chart-grid layout class based on card count."""
    if n == 1:
        return "dashboard-grid expand-1"
    if n == 2:
        return "dashboard-grid expand-2"
    if n == 3:
        return "dashboard-grid expand-3"
    return "dashboard-grid"


def _chart_cards_html(rows: list[dict], subline: str) -> str:
    """Build the chart-card <figure> markup for a set of rows sharing one subline."""
    cards = []
    for i, row in enumerate(rows):
        product_name = escape(str(row.get("product_label", row.get("title", ""))))
        key = escape(row["chart_key"])
        area_note = (
            f'<div class="area-data-note">{escape(str(row.get("stacked_area_note", "")))}</div>'
            if row.get("chart_type") == "stacked_area"
            else ""
        )
        cards.append(
            f'<figure class="chart-card" data-guide-id="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}" data-datasets="{escape(str(row.get("datasets", "")))}">'
            f'<figcaption class="chart-caption">{product_name}</figcaption>'
            f'<div class="meta-subline">{escape(subline)}</div>'
            f'{area_note}'
            f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
            f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{product_name}"></div>'
            f'</figure>'
        )
    return "".join(cards)


def _sort_bar_html() -> str:
    """Sorting controls are intentionally omitted from dense chart sections."""
    return ""


def _overview_navigation_anchor(page_label: str, flow_label: str) -> str:
    """Return the anchor for a real flow parent represented by an overview chart."""
    return "overview-" + safe_slug(page_label) + "__" + safe_slug(flow_label)


def line_section_tree(
    line_rows: list[dict],
    navigation_roots: list[dict[str, str]] | None = None,
) -> list[tuple[str, list[dict[str, object]]]]:
    """Return visible flow-tree nodes grouped by renderer section.

    Renderer sections can be page-oriented groups rather than real Common ESTO
    nodes, so only ``flow_group_label`` values become navigation pills. Levels
    are relative to the visible tree: aggregate roots with visible children are
    level 1, their immediate visible children are level 2, and so on. Real
    parent flows represented only by overview charts are restored through
    ``navigation_roots``. A page-defined overview aggregate can also parent a
    renderer section even when it has no ESTO code. Compound code expressions
    remain intact so manual rollups can contain their visible children.
    Unparented top-level codes stay at level 1; deeper orphan leaves in a
    multi-node section start at level 2.
    """
    tree: list[tuple[str, list[str]]] = []
    seen_sections: dict[str, list[str]] = {}
    for row in line_rows:
        section_label = str(row.get("section_label") or "Other")
        if section_label not in seen_sections:
            seen_sections[section_label] = []
            tree.append((section_label, seen_sections[section_label]))
        group = str(row.get("flow_group_label") or "").strip()
        if group and group not in seen_sections[section_label]:
            seen_sections[section_label].append(group)

    use_subsection_anchor = {
        section_label: len(groups) > 1
        for section_label, groups in tree
    }
    root_targets: dict[str, str] = {}
    section_root_labels: dict[str, str] = {}
    existing_groups = {group for groups in seen_sections.values() for group in groups}
    for root in navigation_roots or []:
        root_label = str(root.get("label") or "").strip()
        root_code = code_candidate_text(root_label)
        section_hint = str(root.get("section_label") or "").strip()
        if not root_label or root_label in existing_groups:
            continue
        if section_hint in seen_sections:
            seen_sections[section_hint].insert(0, root_label)
            existing_groups.add(root_label)
            root_targets[root_label] = str(root.get("target") or "").strip()
            section_root_labels[section_hint] = root_label
            continue
        if not root_code:
            continue
        scored_sections: list[tuple[int, int, str]] = []
        for order, (section_label, groups) in enumerate(tree):
            contained = sum(
                1
                for group in groups
                if _code_expression_contains_expression(root_code, code_candidate_text(group))
            )
            if contained:
                scored_sections.append((contained, -order, section_label))
        if not scored_sections:
            continue
        section_label = max(scored_sections)[2]
        seen_sections[section_label].insert(0, root_label)
        existing_groups.add(root_label)
        root_targets[root_label] = str(root.get("target") or "").strip()

    hierarchy_tree: list[tuple[str, list[dict[str, object]]]] = []
    for section_label, groups in tree:
        coded_groups = [(group, code_candidate_text(group)) for group in groups]
        coded_groups = [
            (group, code)
            for group, code in coded_groups
            if code or group in root_targets
        ]
        if not coded_groups:
            hierarchy_tree.append((section_label, []))
            continue
        code_by_group = dict(coded_groups)
        parent_by_group: dict[str, str] = {}
        for child_group, child_code in coded_groups:
            if not child_code:
                continue
            candidates = [
                (parent_group, parent_code)
                for parent_group, parent_code in coded_groups
                if parent_group != child_group
                and parent_code
                and parent_code != child_code
                and _code_expression_contains_expression(parent_code, child_code)
            ]
            if candidates:
                parent_by_group[child_group] = max(
                    candidates,
                    key=lambda item: (code_depth(item[1]), len(item[1])),
                )[0]

        section_root = section_root_labels.get(section_label, "")
        if section_root:
            for group, _code in coded_groups:
                if group != section_root and group not in parent_by_group:
                    parent_by_group[group] = section_root

        groups_with_children = set(parent_by_group.values())
        depth_by_group: dict[str, int] = {}

        def visible_depth(group: str, visiting: set[str] | None = None) -> int:
            if group in depth_by_group:
                return depth_by_group[group]
            visiting = set(visiting or set())
            if group in visiting:
                return 2
            visiting.add(group)
            parent = parent_by_group.get(group)
            if parent:
                depth = visible_depth(parent, visiting) + 1
            elif (
                group in groups_with_children
                or len(coded_groups) == 1
                or code_depth(code_by_group.get(group, "")) == 1
            ):
                depth = 1
            else:
                depth = 2
            depth_by_group[group] = depth
            return depth

        nodes: list[dict[str, object]] = []
        for group, code in coded_groups:
            nodes.append({
                "label": group,
                "code": code,
                "depth": visible_depth(group),
                "use_subsection_anchor": use_subsection_anchor.get(section_label, False),
                "target": root_targets.get(group, ""),
            })
        hierarchy_tree.append((section_label, nodes))
    hierarchy_tree.sort(
        key=lambda item: _section_tree_order_key(
            item[0], [node["label"] for node in item[1]]
        )
    )
    for _section_label, nodes in hierarchy_tree:
        nodes.sort(
            key=lambda node: (
                int(node["depth"]),
                section_order_key(node["label"]),
            )
        )
    return hierarchy_tree


def _mapping_cell(rows: pd.DataFrame, column: str) -> str:
    """Return sorted unique mapping labels for one guide-table cell."""
    if rows.empty or column not in rows.columns:
        return "—"
    values = sorted(
        {
            str(value).strip()
            for value in rows[column]
            if str(value).strip()
        },
        key=str.casefold,
    )
    return "\n".join(values) if values else "—"


def guide_page_mapping_table(
    chart_rows: list[dict],
    source_category_map: pd.DataFrame | None,
    comparison_scope: str,
    category_label: str = "sector",
    source_systems: list[str] | None = None,
) -> dict[str, object]:
    """Build a native-source provenance table for visible detail charts."""
    provenance_maps_supplied = source_category_map is not None
    mapping = (
        source_category_map.copy()
        if source_category_map is not None
        else pd.DataFrame()
    )
    if comparison_scope and not mapping.empty and "comparison_scope" in mapping.columns:
        mapping = mapping[
            mapping["comparison_scope"].astype(str) == comparison_scope
        ].copy()

    visible_pairs: list[tuple[str, str, str]] = []
    for row in chart_rows:
        if str(row.get("chart_type", "")) != "line":
            continue
        pair = (
            str(row.get("common_row_id") or "").strip(),
            str(row.get("flow_group_label") or row.get("section_label") or "").strip(),
            str(row.get("product_label") or "").strip(),
        )
        if pair[1] and pair[2] and pair not in visible_pairs:
            visible_pairs.append(pair)

    preferred_sources = ["ESTO", "LEAP", "NINTH"]
    requested_sources = {
        str(value).strip().upper()
        for value in (source_systems or [])
        if str(value).strip()
    }
    table_sources = (
        [source for source in preferred_sources if source in requested_sources]
        if requested_sources
        else preferred_sources
    )

    table_rows: list[list[str]] = []
    unavailable_row_count = 0
    for common_row_id, common_flow, common_product in visible_pairs:
        if not mapping.empty and common_row_id and "common_row_id" in mapping.columns:
            mapped = mapping[mapping["common_row_id"].astype(str) == common_row_id]
        elif not mapping.empty:
            mapped = mapping[
                (mapping["common_flow_label"].astype(str) == common_flow)
                & (mapping["common_product_label"].astype(str) == common_product)
            ]
        else:
            mapped = mapping

        source_cells: list[str] = []
        mapping_unavailable = mapped.empty
        if mapping_unavailable:
            unavailable_row_count += 1
        for source_system in table_sources:
            source_rows = (
                mapped[mapped["source_system"].astype(str).str.upper() == source_system]
                if not mapped.empty and "source_system" in mapped.columns
                else mapped
            )
            if mapping_unavailable:
                source_cells.extend(["Provenance unavailable*", "Provenance unavailable*"])
            else:
                source_cells.extend(
                    [
                        _mapping_cell(source_rows, "source_flow"),
                        _mapping_cell(source_rows, "source_product"),
                    ]
                )
        table_rows.append([common_flow, common_product, *source_cells])

    source_labels = {"ESTO": "ESTO", "LEAP": "LEAP", "NINTH": "9th"}
    headers = [f"Common {category_label}", "Common fuel"]
    for source_system in table_sources:
        source_label = source_labels[source_system]
        headers.extend(
            [f"{source_label} {category_label}", f"{source_label} fuel"]
        )

    note = ""
    if unavailable_row_count and not provenance_maps_supplied:
        note = (
            "* Native-source provenance files were not included in this app build, "
            "so source details cannot be shown. This does not mean these categories "
            "are unmapped."
        )
    elif unavailable_row_count:
        category_word = "category was" if unavailable_row_count == 1 else "categories were"
        note = (
            f"* {unavailable_row_count} displayed {category_word} not found in the "
            "supplied provenance maps. Regenerate the comparison data and mapping "
            "files together before interpreting those rows."
        )
    return {
        "caption": "Page categories and published source mappings",
        "headers": headers,
        "rows": table_rows,
        "note": note,
    }


def uses_combined_international_transport_placeholder(template: dict) -> bool:
    """Return whether Supply must use the combined bunker comparison row."""
    coverage = template.get("leap_demand_sector_coverage", {}) or {}
    page_branches = coverage.get("_aggregate_only_page_branches", {}) or {}
    sectors = {
        str(value).strip().casefold()
        for value in page_branches.get("supply", [])
        if str(value).strip()
    }
    return "international transport" in sectors


def guide_placeholder_status(page_key: str, template: dict) -> str:
    """Explain an active LEAP placeholder for one page."""
    power_interim_branches = [
        str(value)
        for value in template.get("_power_interim_placeholder_branches", [])
        if str(value).strip()
    ]
    if page_key == "power" and power_interim_branches:
        branch_text = ", ".join(f"'{value}'" for value in power_interim_branches)
        return (
            f"The yellow warning means LEAP is using the interim power placeholder "
            f"branches {branch_text} for at least part of the period shown. A placeholder "
            "is a temporary branch used when the corresponding completed power-sector "
            "branch is not available. It preserves the available power results, but the "
            "detailed technology structure may not yet be available. Treat missing detail "
            "as unavailable, not as zero."
        )
    coverage = template.get("leap_demand_sector_coverage", {}) or {}
    placeholder_branch = str(
        coverage.get("aggregate_placeholder_branch", "All demand aggregated")
    ).strip()
    page_branches = coverage.get("_aggregate_only_page_branches", {}) or {}
    sectors = [str(value) for value in page_branches.get(page_key, []) if str(value).strip()]
    if page_key == "supply" and uses_combined_international_transport_placeholder(template):
        return (
            "The yellow warning means LEAP currently supplies international transport "
            "through the combined 'All demand aggregated/International transport' "
            "placeholder. Supply therefore shows one combined 04-05 International "
            "transport (bunkers) section. Marine (04) and aviation (05) will return as "
            "separate sections when their separate source branches replace the placeholder."
        )
    if not sectors:
        return (
            "No aggregate LEAP placeholder is identified for this page in this economy. "
            "The sectors and fuels shown above come from the separately available mapped detail."
        )
    sector_text = ", ".join(sectors)
    return (
        f"The yellow warning means LEAP is using a placeholder for {sector_text}. "
        f"A placeholder is a broad total from the '{placeholder_branch}' branch, used "
        "until this part of the economy is modelled separately. It preserves the total "
        "but cannot provide sector or subsector detail, which is why detailed LEAP charts "
        "are missing. Treat that detail as unavailable, not as zero."
    )


def page_placeholder_note(page_key: str, template: dict) -> str:
    """Return a visible page-top note when a LEAP placeholder is active."""
    power_interim_branches = [
        str(value)
        for value in template.get("_power_interim_placeholder_branches", [])
        if str(value).strip()
    ]
    if page_key == "power" and power_interim_branches:
        branch_text = ", ".join(f"'{value}'" for value in power_interim_branches)
        return (
            f"LEAP placeholder in use: interim power branches {branch_text} supply "
            "at least part of the period shown. Detailed LEAP power technologies may "
            "not yet be available; missing detail should not be read as zero."
        )
    coverage = template.get("leap_demand_sector_coverage", {}) or {}
    page_branches = coverage.get("_aggregate_only_page_branches", {}) or {}
    sectors = [str(value) for value in page_branches.get(page_key, []) if str(value).strip()]
    if page_key == "supply" and uses_combined_international_transport_placeholder(template):
        return (
            "LEAP placeholder in use: 'All demand aggregated/International transport' "
            "provides only a combined international-transport value. This means marine "
            "(04) and aviation (05) cannot be viewed separately until the placeholder "
            "demand sector is replaced."
        )
    if not sectors:
        return ""
    placeholder_branch = str(
        coverage.get("aggregate_placeholder_branch", "All demand aggregated")
    ).strip()
    return (
        f"LEAP placeholder in use: '{placeholder_branch}' supplies "
        f"{', '.join(sectors)} on this page. Detailed LEAP sector and subsector "
        "values are not yet available; missing detail should not be read as zero."
    )


def guide_page_context(
    page_key: str,
    chart_rows: list[dict],
    template: dict,
    source_category_map: pd.DataFrame | None = None,
) -> dict:
    """Build economy- and scope-specific guide content from the rendered page."""
    mapping_table_pages = {
        "supply",
        "international_transport",
        "power",
        "refining",
        "other_transformation",
        "industry",
        "transport",
        "buildings",
        "others",
        "transport_leap_vs_ninth",
        "datacentres_leap_vs_ninth",
    }
    sector_pages = {
        "industry",
        "transport",
        "buildings",
        "others",
        "transport_leap_vs_ninth",
        "datacentres_leap_vs_ninth",
    }
    placeholder_status = guide_placeholder_status(page_key, template)
    placeholder_in_use = bool(page_placeholder_note(page_key, template))
    context = {
        "placeholder_status": placeholder_status,
        "placeholder_in_use": placeholder_in_use,
    }
    if page_key in mapping_table_pages:
        context["page_mapping_table"] = guide_page_mapping_table(
            chart_rows,
            source_category_map,
            str(template.get("_active_comparison_scope", "")),
            category_label="sector" if page_key in sector_pages else "flow",
            source_systems=list(template.get("_active_dataset_filter_options", [])),
        )
    return context


def _line_sections_html(line_rows: list[dict], page_label: str) -> str:
    """Build section-grouped HTML for line charts, with subsections keyed by flow."""
    if not line_rows:
        return ""
    seen: list[str] = []
    for row in line_rows:
        sl = str(row.get("section_label") or "Other")
        if sl not in seen:
            seen.append(sl)
    chunks: list[str] = []
    section_order = {
        section_label: _section_tree_order_key(
            section_label,
            [
                row.get("flow_group_label")
                for row in line_rows
                if str(row.get("section_label") or "Other") == section_label
                and str(row.get("flow_group_label") or "").strip()
            ],
        )
        for section_label in seen
    }
    for section_label in sorted(seen, key=section_order.get):
        section_rows = [r for r in line_rows if str(r.get("section_label") or "Other") == section_label]
        anchor = _section_anchor(page_label, section_label)

        flow_groups: list[str] = []
        for row in section_rows:
            group = str(row.get("flow_group_label") or "").strip()
            if group and group not in flow_groups:
                flow_groups.append(group)
        flow_groups.sort(key=section_order_key)

        if len(flow_groups) < 2:
            grid_class = _grid_class_for(len(section_rows))
            cards_html = _chart_cards_html(section_rows, f"{page_label} > {section_label}")
            body_html = (
                f'<section class="section-sort-group">'
                f'{_sort_bar_html()}'
                f'<div class="{grid_class}" data-sortable-grid="{escape(anchor)}">{cards_html}</div>'
                f'</section>'
            )
        else:
            direct_rows = [r for r in section_rows if not str(r.get("flow_group_label") or "").strip()]
            sub_chunks = []
            if direct_rows:
                grid_class = _grid_class_for(len(direct_rows))
                cards_html = _chart_cards_html(direct_rows, f"{page_label} > {section_label}")
                sub_chunks.append(
                    f'<section class="section-sort-group">'
                    f'{_sort_bar_html()}'
                    f'<div class="{grid_class}" data-sortable-grid="{escape(anchor)}">{cards_html}</div>'
                    f'</section>'
                )
            for group in flow_groups:
                group_rows = [r for r in section_rows if str(r.get("flow_group_label") or "").strip() == group]
                group_anchor = _section_anchor(page_label, section_label, group)
                grid_class = _grid_class_for(len(group_rows))
                cards_html = _chart_cards_html(group_rows, f"{page_label} > {section_label} > {group}")
                sub_chunks.append(
                    f'<section id="{group_anchor}" data-dataset-filter-section style="scroll-margin-top:150px;">'
                    f'<h3 class="subsection-heading">{escape(group)}</h3>'
                    f'<section class="section-sort-group">'
                    f'{_sort_bar_html()}'
                    f'<div class="{grid_class}" data-sortable-grid="{escape(group_anchor)}">{cards_html}</div>'
                    f'</section>'
                    f'</section>'
                )
            body_html = "".join(sub_chunks)

        chunks.append(
            f'<section id="{anchor}" data-dataset-filter-section style="scroll-margin-top:150px;">'
            f'<h2 class="section-heading">{escape(section_label)}</h2>'
            f'{body_html}'
            f'</section>'
        )
    return "".join(chunks)


def write_dashboard_page(
    page_config: dict,
    chart_rows: list[dict],
    bundle_js_name: str,
    output_path: Path,
    all_pages: list[dict] | None = None,
    economy_label: str = "",
    dashboard_switcher: list[dict[str, str]] | None = None,
    current_dashboard: str = "",
    page_note: str = "",
    dashboard_updated_label: str = "",
    category_basis_options: list[dict[str, str]] | None = None,
    current_comparison_scope: str = "",
    dataset_filter_options: list[str] | None = None,
    dashboard_key_suffix: str = "",
    guide_context: dict | None = None,
) -> None:
    """Write a polished HTML dashboard page with sticky header, lazy loading, and sorting."""
    page_label = str(page_config.get("page_label", "Dashboard"))
    page_file = output_path.name
    area_rows = [r for r in chart_rows if r.get("chart_type") == "stacked_area" and str(r.get("section_label")) == "Overview"]
    line_rows = [r for r in chart_rows if not (r.get("chart_type") == "stacked_area" and str(r.get("section_label")) == "Overview")]
    navigation_roots = [
        {
            "label": str(row["navigation_root_label"]),
            "target": _overview_navigation_anchor(
                page_label,
                str(row["navigation_root_label"]),
            ),
            "section_label": str(row.get("navigation_root_section_label") or ""),
        }
        for row in area_rows
        if str(row.get("navigation_root_label") or "").strip()
    ]
    section_tree = line_section_tree(line_rows, navigation_roots)

    page_datasets: list[str] = [
        str(token).strip().upper()
        for token in (dataset_filter_options or [])
        if str(token).strip()
    ]
    if not page_datasets:
        for r in chart_rows:
            for token in str(r.get("datasets", "")).split(","):
                token = token.strip().upper()
                if token and token not in page_datasets:
                    page_datasets.append(token)
    preferred_order = ["LEAP", "ESTO", "NINTH"]
    page_datasets.sort(key=lambda d: (preferred_order.index(d) if d in preferred_order else len(preferred_order), d))

    nav_chips = _nav_chips_html(all_pages or [], page_file)
    switcher_html = _dashboard_switcher_html(
        dashboard_switcher or [], current_dashboard, page_file, dashboard_key_suffix
    )
    category_basis_html = _category_basis_switcher_html(
        category_basis_options or [], current_comparison_scope, page_file
    )
    dataset_filter_html = _dataset_filter_html(page_datasets, current_comparison_scope)
    jump_nav = _jump_nav_html(page_label, section_tree)
    note_html = f'<div class="visible-note">{escape(page_note)}</div>' if page_note else ""
    overview_html = _area_charts_html(area_rows, page_label)
    sections_html = _line_sections_html(line_rows, page_label)
    economy_ctx = f"Economy: <strong>{escape(economy_label)}</strong>" if economy_label else ""
    if economy_ctx and dashboard_updated_label:
        economy_ctx = f'{economy_ctx}<span class="dashboard-updated">Updated: {escape(dashboard_updated_label)}</span>'
    guide = build_guide_fragments(
        "chart",
        str(page_config.get("page_key", "")),
        page_label,
        guide_context,
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(page_label)}</title>
  <style>{_PAGE_CSS}{guide["css"]}</style>
</head>
<body>
  <div class="page-shell">
    <header class="page-header" id="page-header">
      <div class="header-collapsible">
      <div class="header-main-row">
        <div style="min-width:220px;flex:1 1 320px;" data-guide-id="page-purpose">
          <h1 style="margin:0;font-size:24px;line-height:1.15;">{escape(page_label)}</h1>
          {f'<div class="dashboard-context" data-guide-id="economy-context">{economy_ctx}</div>' if economy_ctx else ""}
        </div>
        <div class="header-side-controls" data-guide-id="top-controls">
          {_SCENARIO_TOGGLE_HTML.replace('class="scenario-toggle"', 'class="scenario-toggle" data-guide-id="scenario-toggle"')}
          {switcher_html}
          {category_basis_html}
          {dataset_filter_html}
          <div class="header-inline-controls" data-guide-id="page-navigation">{nav_chips}</div>
        </div>
      </div>
      {jump_nav}
      </div>
      <div class="header-toggle-row">
        {guide["launch_button_html"]}
        <button id="header-toggle" class="header-toggle" type="button" aria-expanded="true" aria-label="Collapse header">&#9652;</button>
      </div>
    </header>
    <main class="page-body" data-guide-id="review-workflow">
      {note_html}
      {overview_html}
      {sections_html}
    </main>
  </div>
  {guide["dialog_html"]}
  <script>{_HEADER_TOGGLE_JS}</script>
  <script>{_DASHBOARD_SWITCHER_JS}</script>
  <script>{_SCENARIO_TOGGLE_JS}</script>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <script src="../chart_bundles/{escape(bundle_js_name)}"></script>
  <script>{_LAZY_LOAD_JS}</script>
  <script>{_DATASET_FILTER_JS}</script>
  <script>{guide["script"]}</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def write_index(
    pages: list[dict],
    output_path: Path,
    economy_label: str = "",
    dashboard_switcher: list[dict[str, str]] | None = None,
    current_dashboard: str = "",
    dashboard_updated_label: str = "",
    category_basis_options: list[dict[str, str]] | None = None,
    current_comparison_scope: str = "",
    dashboard_key_suffix: str = "",
    dataset_filter_options: list[str] | None = None,
) -> None:
    """Write the dashboard index page."""
    economy_heading = f" — {escape(economy_label)}" if economy_label else ""
    def _index_counts(p: dict) -> str:
        parts = [f'{p["area_chart_count"]} overview']
        if p.get("summary_chart_count"):
            parts.append(f'{p["summary_chart_count"]} summary')
        parts.append(f'{p["line_chart_count"]} detail')
        return ", ".join(parts)

    cards = "".join(
        f'<li style="margin-bottom:8px;">'
        f'<a href="{escape(p["file"])}" style="font-weight:600;">{escape(p["label"])}</a> '
        f'<span style="color:#6b7280;font-size:13px;">({_index_counts(p)})</span>'
        f'</li>'
        for p in pages
    )
    switcher_html = _dashboard_switcher_html(
        dashboard_switcher or [], current_dashboard, "index.html", dashboard_key_suffix
    )
    category_basis_html = _category_basis_switcher_html(
        category_basis_options or [], current_comparison_scope, "index.html"
    )
    source_labels = [
        _DATASET_DISPLAY_LABELS.get(str(source).upper(), str(source))
        for source in (dataset_filter_options or [])
    ]
    source_description = ", ".join(source_labels) if source_labels else "the configured sources"
    updated_html = (
        f'<p style="margin:0;color:#4b5563;font-size:13px;">Updated: {escape(dashboard_updated_label)}</p>'
        if dashboard_updated_label else ""
    )
    guide = build_guide_fragments("index", "index", f"Common ESTO Dashboard{economy_heading}")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Common ESTO Dashboard{economy_heading}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6f8; color: #111; }}
    .shell {{ max-width: 860px; margin: 0 auto; padding: 32px 24px; }}
    h1 {{ margin-bottom: 6px; }}
    .top-row {{ display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap; }}
    .dashboard-switcher {{ display:flex;align-items:center;gap:6px;font-size:13px;color:#4b5563;white-space:nowrap; }}
    .dashboard-switcher select {{ max-width:240px;padding:6px 28px 6px 8px;border:1px solid #c5ccd3;border-radius:6px;background:#fff;color:#111;font:inherit; }}
    .category-basis-switcher {{ display:flex;align-items:center;gap:6px;font-size:13px;color:#4b5563;white-space:nowrap; }}
    .category-basis-switcher select {{ max-width:240px;padding:6px 28px 6px 8px;border:1px solid #c5ccd3;border-radius:6px;background:#fff;color:#111;font:inherit; }}
    ul {{ list-style: none; padding: 0; margin-top: 20px; }}
    {guide["css"]}
  </style>
</head>
<body>
  <div class="shell">
    <div class="top-row" data-guide-id="index-purpose">
      <div>
        <h1>Common ESTO Dashboard{economy_heading}</h1>
        {updated_html}
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">{switcher_html}{category_basis_html}{guide["launch_button_html"]}</div>
    </div>
    <p style="color:#4b5563;">Charts are generated automatically from common ESTO flow/product rows.</p>
    <ul data-guide-id="page-list">{cards}</ul>
    <div data-guide-id="about-dashboard" style="margin-top:32px;border-top:1px solid #d8dee4;padding-top:24px;">
      <h2 style="margin:0 0 8px 0;font-size:18px;">About this dashboard</h2>
      <p style="margin:0 0 12px 0;color:#4b5563;font-size:13px;">This dashboard compares {escape(source_description)} on one shared set of flow/product
      categories (the "common ESTO" axis). A source's native flow and
      product codes are mapped onto the common axis in <code>leap_mappings</code>,
      so a chart here is always comparing like with like even when the three
      sources describe the same fuel or sector differently.</p>
      <p style="margin:0 0 12px 0;color:#4b5563;font-size:13px;">Every page is generated automatically from that shared data — nothing on
      this page is hand-edited, and re-running the generator overwrites it
      completely. See <code>codebase/common_esto_dashboard_workflow.py</code>
      in the <code>leap_dashboard</code> repository to reproduce or update it.</p>
      <p style="margin:0 0 12px 0;color:#4b5563;font-size:13px;">Some LEAP economies still report demand through <code>All demand aggregated</code> while detailed branches are being developed. The dashboard uses the mapping-owned coverage record to decide which sector pages are transitional, uses declared TFC/TFEC totals for balance lines, and keeps aggregate-only emissions as one clearly labelled series rather than inventing a sector split. See the Emissions note and the source-selection CSV for the level used by each source.</p>
      <p data-guide-id="sharing-note" style="margin:0;color:#4b5563;font-size:13px;">Each rendered economy is a self-contained set of static files: this page,
      the other pages linked above, a <code>chart_bundles/</code> folder holding
      each page's chart data, and a <code>supporting_files/</code> folder holding
      the CSVs behind the charts. Pages load their charts from
      <code>chart_bundles/</code> by a relative path, so <strong>copying a single
      <code>.html</code> file on its own will open the page but its charts will not
      draw</strong> — copy the whole economy folder (or the whole
      <code>dashboards/</code> + <code>chart_bundles/</code> pair) together
      whenever sharing a rendered dashboard.</p>
    </div>
    <div data-guide-id="model-guide" style="margin-top:32px;border-top:1px solid #d8dee4;padding-top:24px;">
      <h2 style="margin:0 0 8px 0;font-size:18px;">Model guide</h2>
      <p style="margin:0 0 16px 0;color:#4b5563;font-size:13px;">In the APERC LEAP system, the model is organised around the main LEAP branches of Demand, Transformation, and Resources. The dashboard sits outside LEAP and helps users check how these branches behave in the results, especially by comparing LEAP outputs with ESTO historical balances and 9th Outlook projections. The table below gives a short guide to the main model groups and how they should be understood when using either LEAP or the dashboard.</p>
      <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#f0f4f8;">
              <th style="text-align:left;padding:8px 10px;border:1px solid #d0d7de;white-space:nowrap;">Main group</th>
              <th style="text-align:left;padding:8px 10px;border:1px solid #d0d7de;">What it covers in LEAP</th>
              <th style="text-align:left;padding:8px 10px;border:1px solid #d0d7de;">Main dashboard purpose</th>
              <th style="text-align:left;padding:8px 10px;border:1px solid #d0d7de;">What users should understand</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Final energy demand from buildings, industry, transport, agriculture, fishing, and other demand sectors.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Shows how final energy use changes by sector, subsector, fuel, economy, and scenario.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Demand is where most end-use assumptions sit. Some sectors are simple activity &times; intensity models, while buildings, industry, and road transport contain more detailed structures.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Buildings demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Residential and commercial/public services demand, usually split into end uses, fuels, activity, and intensity.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check fuel use, sector totals, and whether modelled building demand remains consistent with expected energy balance trends.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Buildings is more detailed than a simple sector total. It is designed to preserve useful end-use and fuel-switching detail while still calibrating back to energy balance totals.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Industry demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Energy use by industrial subsector, with more detail for major energy-intensive activities and simpler treatment for smaller subsectors.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps compare industrial fuel use, subsector demand, and large changes against historical and projected values.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Industry is a hybrid model. Some parts are technology or process based, while others are simpler activity &times; intensity structures.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Road transport demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Passenger road and freight road transport. This includes vehicle stocks, sales, retirements, mileage, efficiency, vehicle types, engine types, and fuel use.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check road energy demand, vehicle stock, sales, turnover, fuel switching, and passenger/freight road trends.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Road transport is the most detailed demand model. It uses stock-flow logic, so changes in sales, retirements, mileage, and efficiency all affect future energy demand.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Non-road and international transport demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Domestic aviation, domestic navigation/shipping, rail, pipelines, non-specified transport, and international aviation and marine bunkers where represented.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check non-road fuel use, bunker demand, pipeline demand, and domestic aviation/shipping/rail trends.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Non-road transport is generally simpler than road transport. It is usually closer to an activity &times; intensity model, with calibration to ESTO energy totals where needed. International bunkers and pipelines are included here because they are transport-related flows but are not part of the road stock-flow model.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Other demand</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Agriculture, fishing, non-specified demand, and other relatively small final-demand sectors.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check whether smaller demand sectors remain stable, plausible, and aligned with the balance structure.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">These sectors are usually simpler and are mainly included to preserve the full energy balance structure.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Transformation</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Energy conversion sectors such as electricity generation, heat generation, refining, transfers, LNG regasification, NG liquefaction, gas processing, coal transformation, coke ovens, blast furnaces, and other transformation processes.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Shows transformation inputs, outputs, losses, efficiencies, and whether conversion sectors are producing plausible results.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Transformation is where fuels are converted into other fuels. Some modules are physical processes, while others mainly exist to reproduce the structure of the energy balance.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Power and heat</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Electricity and heat generation, including generation technologies, capacity, dispatch, load shapes, losses, and optimisation settings.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check electricity and heat output, generation mix, capacity, fuel inputs, losses, and unusual dispatch outcomes.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Power is the most complex transformation area because it may use NEMO optimisation inside LEAP. It usually needs more manual checking than simpler transformation sectors.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Refining</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Oil refining inputs, outputs, product yields, capacity assumptions, and refinery-related fuel production.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps check refinery feedstocks, oil product outputs, product balances, and whether refining capacity or output shares are creating plausible results.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Refining is kept separate because it is a major transformation process with a clear physical interpretation: one or more inputs are converted into multiple oil-product outputs. It needs careful checking because product output shares can create surplus or shortage issues.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Other transformation, including transfers</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">LNG regasification, NG liquefaction, gas processing/blending, coal transformation, coke ovens, blast furnaces, patent fuel plants, non-specified transformation, upstream liquids transfers, refinery/blending transfers, and transfers unallocated.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Helps identify unusual transformation outputs, transfer flows, capacity limits, shortfalls, surpluses, and fuel-balance problems.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">This group contains a mixture of physical processes and balance-structure modules. Transfers are included here because they mainly organise ESTO transfer flows and may contain simplified or non-physical input-output relationships used to preserve balance-table consistency.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Resources / supply</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Domestic production, imports, exports, primary resources, and secondary fuel trade.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Shows whether fuels are being supplied through the intended mix of domestic production, imports, exports, and transformation outputs.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Resources is where LEAP balances remaining fuel requirements. Imports and exports are useful diagnostics because they reveal whether the rest of the system is producing too much or too little.</td>
            </tr>
            <tr style="background:#fafbfc;">
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Reconciliation / QA</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">The whole-system checking process after LEAP has calculated demand, transformation, resources, imports, exports, and losses.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Highlights differences between LEAP results, ESTO historical balances, and 9th Outlook projections.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Reconciliation is not a separate LEAP branch. It is the checking layer that shows whether the integrated model is still aligned with the intended energy balance.</td>
            </tr>
            <tr>
              <td style="padding:8px 10px;border:1px solid #d0d7de;font-weight:600;white-space:nowrap;vertical-align:top;">Dashboard</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">External results and checking interface built from LEAP exports, ESTO data, and comparison datasets.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">Makes it easier to inspect sector totals, fuel totals, differences, percentage differences, and suspicious changes across the model.</td>
              <td style="padding:8px 10px;border:1px solid #d0d7de;vertical-align:top;">The dashboard is not the model itself. It is the main tool for reviewing whether the LEAP model behaves sensibly and whether further adjustment is needed.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {guide["dialog_html"]}
  <script>{_DASHBOARD_SWITCHER_JS}</script>
  <script>{guide["script"]}</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def _select_total_rows_by_source(
    demand_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    flow_code: str,
) -> pd.DataFrame:
    """Select authoritative top-level totals, with visible detail as fallback.

    Demand detail can contain overlapping parent, child, exact, and generated
    rollup views. Summing that detail is not a safe total. Prefer the declared
    top-level balance flow for every source and use visible detail only when a
    source does not publish the requested aggregate.
    """
    source_names = set(demand_df.get("source_system", pd.Series(dtype=str)).astype(str))
    source_names.update(overview_flow_df.get("source_system", pd.Series(dtype=str)).astype(str))
    selected: list[pd.DataFrame] = []
    flow_rows = overview_flow_df.iloc[0:0].copy()
    if not overview_flow_df.empty:
        flow_rows = overview_flow_df[
            overview_flow_df["common_flow_code"].astype(str).eq(str(flow_code))
        ]
    for source in sorted(source_names):
        source_demand = demand_df[demand_df["source_system"].astype(str).eq(source)]
        source_flow = flow_rows[flow_rows["source_system"].astype(str).eq(source)]
        if not source_flow.empty:
            selected.append(source_flow)
        elif not source_demand.empty:
            selected.append(source_demand)
    if not selected:
        return flow_rows if not flow_rows.empty else demand_df
    return pd.concat(selected, ignore_index=True)


def _domestic_tfc_totals(
    tfc_total_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return total final consumption on the domestic-demand boundary.

    LEAP's ``All demand aggregated`` parent currently includes its positive
    International transport child.  The latter is an international-bunker
    supply deduction, not a domestic demand sector, so remove its absolute
    value from LEAP's declared flow-12 comparison line.  ESTO and 9th rows
    already use the domestic TFC boundary and retain their declared values.
    """
    totals = tfc_total_df.groupby(
        ["source_system", "scenario", "year"], as_index=False
    )["value"].sum()
    if totals.empty or overview_flow_df.empty:
        return totals

    international_rows = overview_flow_df[
        overview_flow_df["common_flow_code"].astype(str).eq("04-05")
    ]
    if international_rows.empty:
        return totals
    international_totals = international_rows.groupby(
        ["source_system", "scenario", "year"], as_index=False
    )["value"].sum().rename(columns={"value": "_international_transport"})
    totals = totals.merge(
        international_totals,
        on=["source_system", "scenario", "year"],
        how="left",
    )
    leap_mask = totals["source_system"].astype(str).str.casefold().eq("leap")
    totals.loc[leap_mask, "value"] -= (
        totals.loc[leap_mask, "_international_transport"].fillna(0.0).abs()
    )
    return totals.drop(columns="_international_transport")


def _build_td_sector_chart(
    demand_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    sector_colors: dict[str, str],
    base_year: int | None = None,
) -> go.Figure:
    """Build final energy demand by sector with authoritative TFC totals.

    TFC (Total Final Consumption) includes all demand sectors (codes 14-17).
    TFEC remains deliberately unavailable until non-energy use can be separated
    from aggregated Other-sector LEAP demand, so this chart must not calculate
    a visible-detail substitute for flow 13.

    """
    chart_unit = _chart_unit(demand_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    stacked_sources: set[str] = set()
    resolved_base_year = 2023 if base_year is None else int(base_year)

    # The line below is the declared domestic TFC boundary. It is deliberately
    # separate from the stack: a discrepancy must expose a missing or
    # overlapping source category, never be hidden by a manufactured row.
    tfc_total_df = _select_total_rows_by_source(
        demand_df,
        overview_flow_df,
        flow_code="12",
    )
    tfc_totals = _domestic_tfc_totals(tfc_total_df, overview_flow_df)

    def stack_source(scenario_name: str) -> pd.DataFrame:
        """Return ESTO historical plus the most detailed projected source."""
        rows, _ = _comparison_projection_area_rows(
            demand_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=resolved_base_year,
            group_col="_page_key",
            detail_col="_page_key",
        )
        # Keep the sector stack on the same non-overlapping parent/child
        # frontier as the authoritative TFC/TFEC totals.  Without this,
        # historical ESTO rows such as Buildings plus its Commercial and
        # Residential children are summed together, while the projected LEAP
        # side may contain only the parent row.
        return _non_overlapping_flow_rows(_non_overlapping_common_row_frontier(rows))

    # Use the detailed source available for each scenario. LEAP is preferred,
    # but some economies only have aggregate LEAP demand and therefore need
    # the 9th-edition detail as the projection fallback.
    default_rows = stack_source(primary_scenario)
    sector_order = (
        default_rows.groupby(["_page_key", "_page_label"])["value"]
        .sum().abs().sort_values(ascending=False).reset_index()
    )

    for scenario_name in ("Reference", "Target"):
        scenario_df = stack_source(scenario_name)
        is_default = scenario_name.casefold() == primary_scenario.casefold()
        if scenario_df.empty or sector_order.empty:
            continue
        projected_source_rows, stack_source_name = _comparison_projection_area_rows(
            demand_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=resolved_base_year,
            group_col="_page_key",
            detail_col="_page_key",
        )
        projected_source_rows = _non_overlapping_flow_rows(
            _non_overlapping_common_row_frontier(projected_source_rows)
        )
        scenario_df = projected_source_rows
        if not stack_source_name:
            continue
        if (scenario_df["source_system"].astype(str).str.casefold() == "esto").any():
            stacked_sources.add("ESTO")
        stacked_sources.add(stack_source_name)
        for _, sector_row in sector_order.iterrows():
            page_key = str(sector_row["_page_key"])
            page_label = str(sector_row["_page_label"])
            sector_data = (
                scenario_df[scenario_df["_page_key"] == page_key]
                .groupby("year", as_index=False)["value"].sum()
                .sort_values("year")
            )
            if sector_data.empty:
                continue
            if not _has_nonzero_values(sector_data["value"]):
                continue
            color = sector_colors.get(page_key)
            trace_count = _add_signed_stack_traces(
                fig=fig,
                x_values=sector_data["year"],
                y_values=sector_data["value"],
                stackgroup_prefix=f"demand_{scenario_toggle_tag(stack_source_name, scenario_name)}",
                trace_name=page_label,
                visible=is_default,
                hovertemplate=(
                    "%{x}<br>%{y:,.2f}"
                    + chart_unit
                    + "<extra>"
                    + escape(page_label)
                    + "</extra>"
                ),
                line_color=color or "",
            )
            trace_meta.extend(
                trace_meta_entry(stack_source_name, scenario_name, True)
                for _ in range(trace_count)
            )

    # Explicit flow 12 is the reliable total. The displayed detail can contain
    # several valid hierarchy views and must not be added together.
    # Domestic TFC totals, incl. primary LEAP scenarios: the sector stack above
    # is split into pos/neg stackgroups when sectors have mixed signs, so it
    # no longer shows a single net total line on its own.
    for (src, scen), grp in tfc_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " (Domestic TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    fig.update_layout(
        title="Final energy demand by sector (Domestic TFC)",
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 100, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": (
                "Areas show domestic demand sectors; lines show domestic TFC totals by dataset and scenario. "
                + stacked_area_dataset_note(stacked_sources, "demand")
            ),
        },
    )
    apply_chart_chrome(fig, base_year)
    return fig


def _build_td_fuel_chart(
    demand_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    base_year: int | None = None,
) -> go.Figure:
    """Build final energy demand by fuel with authoritative TFC totals."""
    chart_unit = _chart_unit(demand_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    stacked_sources: set[str] = set()
    resolved_base_year = 2023 if base_year is None else int(base_year)

    def stack_source(scenario_name: str) -> pd.DataFrame:
        """Return ESTO historical plus the most detailed projected source."""
        rows, _ = _comparison_projection_area_rows(
            demand_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=resolved_base_year,
            group_col="common_product_label",
            detail_col="common_product_label",
        )
        return _non_overlapping_flow_rows(_non_overlapping_common_row_frontier(rows))

    # Product stacking order is computed from the default scenario and reused
    # for both scenarios so switching REF/TGT does not reshuffle the layers.
    default_rows = stack_source(primary_scenario)
    product_totals = (
        default_rows.groupby("common_product_label")["value"].sum().abs()
        .sort_values(ascending=False).index.tolist()
    )

    for scenario_name in ("Reference", "Target"):
        scenario_df = stack_source(scenario_name)
        is_default = scenario_name.casefold() == primary_scenario.casefold()
        if scenario_df.empty or not product_totals:
            continue
        scenario_df, stack_source_name = _comparison_projection_area_rows(
            demand_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=resolved_base_year,
            group_col="common_product_label",
            detail_col="common_product_label",
        )
        scenario_df = _non_overlapping_flow_rows(
            _non_overlapping_common_row_frontier(scenario_df)
        )
        if not stack_source_name:
            continue
        if (scenario_df["source_system"].astype(str).str.casefold() == "esto").any():
            stacked_sources.add("ESTO")
        stacked_sources.add(stack_source_name)
        product_by_year = scenario_df.groupby(["common_product_label", "year"], as_index=False)["value"].sum()
        for product in product_totals:
            grp = product_by_year[product_by_year["common_product_label"] == product].sort_values("year")
            if grp.empty:
                continue
            if not _has_nonzero_values(grp["value"]):
                continue
            lbl = str(product)
            trace_count = _add_signed_stack_traces(
                fig=fig,
                x_values=grp["year"],
                y_values=grp["value"],
                stackgroup_prefix=f"demand_{scenario_toggle_tag(stack_source_name, scenario_name)}",
                trace_name=lbl,
                visible=is_default,
                hovertemplate=(
                    "%{x}<br>%{y:,.2f}"
                    + chart_unit
                    + "<extra>"
                    + escape(lbl)
                    + "</extra>"
                ),
            )
            trace_meta.extend(
                trace_meta_entry(stack_source_name, scenario_name, True)
                for _ in range(trace_count)
            )

    # Use the same authoritative aggregate policy as the sector chart.
    tfc_total_df = _select_total_rows_by_source(
        demand_df,
        overview_flow_df,
        flow_code="12",
    )

    # Domestic demand total lines, incl. primary LEAP scenarios (see note in
    # _build_td_sector_chart on why the stacked fuel breakdown alone doesn't
    # show a single net total when fuels have mixed signs).
    comp_totals = _domestic_tfc_totals(tfc_total_df, overview_flow_df)
    for (src, scen), grp in comp_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " total (Domestic TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    fig.update_layout(
        title="Final energy demand by fuel (Domestic TFC)",
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": (
                "Areas show domestic demand fuels; lines show domestic TFC totals by dataset and scenario. "
                + stacked_area_dataset_note(stacked_sources, "fuel")
            ),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis="product")
    return fig


def _build_supply_stack_chart(
    supply_detail_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    group_col: str,
    chart_title: str,
    base_year: int | None = None,
    total_line_suffix: str = "supply total",
    composition_subject: str = "supply",
    flow_composition_note: str = "Areas show production, imports and exports",
    fuel_composition_note: str = "Areas show supply fuels",
    stack_prefix: str = "supply",
    preserve_gross_signs: bool = False,
    total_detail_df: pd.DataFrame | None = None,
    note_context_df: pd.DataFrame | None = None,
) -> go.Figure:
    """Build signed composition areas with same-boundary total lines.

    `group_col` is "common_flow_label" for a by-component
    (Production/Imports/Exports, ...) breakdown or
    "common_product_label" for a by-fuel breakdown. Supply's row set is whatever the
    caller filtered into supply_detail_df (total_demand_page.supply_codes), so adding
    codes there (e.g. bunkers 04/05) automatically adds new stacked series here.
    """
    chart_unit = _chart_unit(supply_detail_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    stacked_sources: set[str] = set()
    resolved_base_year = 2023 if base_year is None else int(base_year)

    def stack_source(scenario_name: str) -> tuple[pd.DataFrame, str]:
        return _comparison_projection_area_rows(
            supply_detail_df,
            scenario_name=scenario_name,
            primary_source=primary_source,
            comparison_source="ESTO",
            base_year=resolved_base_year,
            group_col=group_col,
            detail_col=group_col,
        )

    default_rows, _ = stack_source(primary_scenario)
    if preserve_gross_signs:
        group_totals = (
            default_rows.assign(
                _gross_value=pd.to_numeric(
                    default_rows["value"], errors="coerce"
                ).fillna(0.0).abs()
            )
            .groupby(group_col)["_gross_value"]
            .sum()
            .sort_values(ascending=False)
            .index.tolist()
        )
    else:
        group_totals = (
            default_rows.groupby(group_col)["value"].sum().abs()
            .sort_values(ascending=False).index.tolist()
        )

    for scenario_name in ("Reference", "Target"):
        scenario_df, stack_source_name = stack_source(scenario_name)
        is_default = scenario_name.casefold() == primary_scenario.casefold()
        if scenario_df.empty or not stack_source_name:
            continue
        if (scenario_df["source_system"].astype(str).str.casefold() == "esto").any():
            stacked_sources.add("ESTO")
        stacked_sources.add(stack_source_name)
        if preserve_gross_signs:
            signed_scenario_df = scenario_df.copy()
            signed_values = pd.to_numeric(
                signed_scenario_df["value"], errors="coerce"
            ).fillna(0.0)
            signed_scenario_df["_positive_value"] = signed_values.clip(lower=0.0)
            signed_scenario_df["_negative_value"] = signed_values.clip(upper=0.0)
            group_by_year = signed_scenario_df.groupby(
                [group_col, "year"], as_index=False
            )[["_positive_value", "_negative_value"]].sum()
        else:
            group_by_year = scenario_df.groupby(
                [group_col, "year"], as_index=False
            )["value"].sum()
        for group_value in group_totals:
            grp = group_by_year[group_by_year[group_col] == group_value].sort_values("year")
            if grp.empty:
                continue
            lbl = str(group_value)
            hovertemplate = (
                "%{x}<br>%{y:,.2f}"
                + chart_unit
                + "<extra>"
                + escape(lbl)
                + "</extra>"
            )
            if preserve_gross_signs:
                trace_count = _add_preseparated_signed_stack_traces(
                    fig=fig,
                    x_values=grp["year"],
                    signed_parts=[
                        ("pos", grp["_positive_value"]),
                        ("neg", grp["_negative_value"]),
                    ],
                    stackgroup_prefix=(
                        f"{stack_prefix}_"
                        f"{scenario_toggle_tag(stack_source_name, scenario_name)}"
                    ),
                    trace_name=lbl,
                    visible=is_default,
                    hovertemplate=hovertemplate,
                )
            else:
                if not _has_nonzero_values(grp["value"]):
                    continue
                trace_count = _add_signed_stack_traces(
                    fig=fig,
                    x_values=grp["year"],
                    y_values=grp["value"],
                    stackgroup_prefix=(
                        f"{stack_prefix}_"
                        f"{scenario_toggle_tag(stack_source_name, scenario_name)}"
                    ),
                    trace_name=lbl,
                    visible=is_default,
                    hovertemplate=hovertemplate,
                )
            trace_meta.extend(
                trace_meta_entry(stack_source_name, scenario_name, True)
                for _ in range(trace_count)
            )

    # Supply total lines, incl. primary LEAP scenarios (see note in
    # _build_td_sector_chart on why the stacked breakdown alone doesn't show
    # a single net total when components have mixed signs).
    total_rows = supply_detail_df if total_detail_df is None else total_detail_df
    comp_totals = total_rows.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in comp_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + f" {total_line_suffix}"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    composition_note = (
        flow_composition_note
        if group_col == "common_flow_label"
        else fuel_composition_note
    )
    fig.update_layout(
        title=chart_title,
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": chart_note_with_lng_coverage(
                (
                    f"{composition_note}; lines show signed net totals by dataset and scenario. "
                    + stacked_area_dataset_note(stacked_sources, composition_subject)
                ),
                supply_detail_df if note_context_df is None else note_context_df,
            ),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis=code_axis_for_group_col(group_col))
    return fig


def _metadata_bool(series: pd.Series) -> pd.Series:
    """Parse optional boolean metadata from CSV-safe values."""
    return series.astype(str).str.strip().str.casefold().isin({"true", "1", "yes"})


def _contains_metadata_token(series: pd.Series, token: str) -> pd.Series:
    """Match one exact token in a semicolon-delimited metadata column."""
    expected = str(token).strip().casefold()
    return series.fillna("").astype(str).apply(
        lambda value: expected in {
            part.strip().casefold() for part in value.split(";") if part.strip()
        }
    )


def select_transformation_total_rows(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Select the configured transformation rollup without using display labels.

    LEAP contributes the generated detail frontier. ESTO and Ninth contribute
    the exact parent row. Both are linked by source-aggregate membership emitted
    by the Common ESTO structure.
    """
    required = {"source_aggregate_labels", "is_exact_row", "requires_rollup"}
    if df.empty or not required.issubset(df.columns):
        return df.iloc[0:0].copy()

    rollup_label = str(config.get("source_aggregate_label", "")).strip()
    if not rollup_label:
        return df.iloc[0:0].copy()
    member_mask = _contains_metadata_token(df["source_aggregate_labels"], rollup_label)
    exact_mask = _metadata_bool(df["is_exact_row"])
    rollup_mask = _metadata_bool(df["requires_rollup"])
    generated_systems = {
        str(value).strip().casefold()
        for value in config.get("generated_source_systems", ["LEAP"])
    }
    system_is_generated = df["source_system"].astype(str).str.strip().str.casefold().isin(generated_systems)
    selection_mask = member_mask & (
        (system_is_generated & rollup_mask)
        | (~system_is_generated & exact_mask)
    )
    return df[selection_mask].copy()


def select_transformation_overview_rows(
    df: pd.DataFrame,
    config: dict,
    presentation_config: dict,
    prefer_leaf_flows: bool = False,
) -> pd.DataFrame:
    """Select one whole-system transformation/own-use/loss frontier.

    Select every row under the declared flow-code roots, then apply the same
    inclusive-own-use presentation policy used by Other transformation and the
    shared non-overlapping hierarchy frontiers. This works even when optional
    source-aggregate rollup metadata is unavailable in one comparison scope.
    """
    flow_code_prefixes = [
        str(value).strip()
        for value in config.get(
            "flow_code_prefixes",
            ["09", "08", "10.01", "10.02"],
        )
        if str(value).strip()
    ]
    overview_mask = df["common_flow_code"].apply(
        lambda value: code_expression_matches_any_prefix(value, flow_code_prefixes)
    )
    combined = df[overview_mask].copy()
    if combined.empty:
        return combined
    prepared = prepare_other_transformation_page_rows(
        combined,
        combined,
        presentation_config,
    )
    if prefer_leaf_flows:
        return _non_overlapping_common_row_frontier(_leaf_flow_rows(prepared))
    return _non_overlapping_flow_rows(
        _non_overlapping_common_row_frontier(prepared)
    )


def _build_balance_flow_total_chart(
    balance_df: pd.DataFrame,
    flow_label: str,
    series_labels: dict[str, str],
    base_year: int | None = None,
) -> go.Figure:
    """Build a signed total line for one top-level energy-balance flow."""
    chart_unit = _chart_unit(balance_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    totals = balance_df.groupby(
        ["source_system", "scenario", "year"], as_index=False
    )["value"].sum()
    for (source_system, scenario), group in totals.groupby(["source_system", "scenario"]):
        label = series_label_from_values(source_system, scenario, series_labels)
        ordered = group.sort_values("year")
        fig.add_trace(go.Scatter(
            x=ordered["year"],
            y=ordered["value"],
            mode="lines+markers",
            name=label,
            hovertemplate="%{x}<br>Signed value: %{y:,.2f}" + chart_unit + "<extra>" + escape(label) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    fig.update_layout(
        title=flow_label,
        xaxis_title="Year",
        yaxis_title=f"Signed energy balance ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={"trace_meta": trace_meta},
    )
    apply_chart_chrome(fig, base_year)
    return fig


def build_unmet_requirements_chart(
    unmet_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_scenario: str = "Target",
    base_year: int | None = None,
) -> go.Figure:
    """Build signed LEAP unmet requirements by Common ESTO fuel category."""
    chart_unit = _chart_unit(unmet_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    fuel_order = (
        unmet_df.assign(
            _gross_value=pd.to_numeric(unmet_df["value"], errors="coerce")
            .fillna(0.0)
            .abs()
        )
        .groupby("common_product_label")["_gross_value"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )
    scenarios = [str(value) for value in unmet_df["scenario"].dropna().unique()]
    default_scenario = next(
        (
            value
            for value in scenarios
            if value.casefold() == primary_scenario.casefold()
        ),
        scenarios[0] if scenarios else primary_scenario,
    )
    scenarios.sort(key=lambda value: (value.casefold() != default_scenario.casefold(), value))
    for scenario in scenarios:
        scenario_df = unmet_df[
            unmet_df["scenario"].astype(str).str.casefold().eq(scenario.casefold())
        ]
        visible = scenario.casefold() == default_scenario.casefold()
        for fuel_label in fuel_order:
            fuel_df = (
                scenario_df[scenario_df["common_product_label"].eq(fuel_label)]
                .groupby("year", as_index=False)["value"]
                .sum()
                .sort_values("year")
            )
            if fuel_df.empty or not _has_nonzero_values(fuel_df["value"]):
                continue
            trace_count = _add_signed_stack_traces(
                fig=fig,
                x_values=fuel_df["year"],
                y_values=fuel_df["value"],
                stackgroup_prefix=f"unmet_{scenario_toggle_tag('LEAP', scenario)}",
                trace_name=str(fuel_label),
                visible=visible,
                hovertemplate=(
                    "%{x}<br>%{y:,.2f}"
                    + chart_unit
                    + "<extra>"
                    + escape(str(fuel_label))
                    + "</extra>"
                ),
            )
            trace_meta.extend(trace_meta_entry("LEAP", scenario, True) for _ in range(trace_count))

    fig.update_layout(
        title="Unmet requirements by fuel",
        xaxis_title="Year",
        yaxis_title=f"Signed unmet requirement ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": (
                "Positive values show an energy shortage; negative values show surplus energy. "
                "Areas show LEAP Unmet Requirements by mapped Common ESTO fuel category."
            ),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis="product")
    return fig


def build_total_demand_page(
    assigned_df: pd.DataFrame,
    template: dict,
    series_labels: dict[str, str],
    layout: dict[str, Path],
    all_pages: list[dict],
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    economy_label: str = "",
    dashboard_switcher: list[dict[str, str]] | None = None,
    current_dashboard: str = "",
    dashboard_updated_label: str = "",
    unmet_requirements_df: pd.DataFrame | None = None,
) -> tuple[list[dict], dict | None]:
    """Build the total demand summary page (config-driven bespoke page).

    Generates composition charts without cross-side comparison overlays:
    - Final energy demand by sector, with authoritative TFC total lines
    - Final energy demand by fuel, with authoritative TFC total lines
    - Energy supply by component, with available-supply total lines
    - Energy supply by fuel, with available-supply total lines
    - Transformation, transfers, losses and own use by flow and by fuel

    Available supply is the signed sum of configured supply codes 01, 02 and 03
    (Production + Imports - Exports). Bunkers, stock changes and TFC demand are
    not overlaid on these supply-composition charts.

    This is a bespoke page — it aggregates across sector pages rather than
    operating on a single page's rows. The parameters (demand pages, supply
    codes, excluded sectors) are config-driven via the ``total_demand_page``
    key in the template, not hardcoded. See the plan doc section
    "Adding bespoke pages and charts" for how to create similar pages.

    Returns (manifest_rows, page_row_dict), or ([], None) if disabled.
    """
    config = template.get("total_demand_page", {})
    if not config.get("enabled", False):
        return [], None

    base_year = int(template.get("chart_generation", {}).get("base_year", 2023))
    demand_page_keys = [str(k) for k in config.get(
        "demand_page_keys", ["industry", "transport", "buildings", "others"]
    )]
    supply_codes = [str(c) for c in config.get("supply_codes", ["01", "02", "03"])]
    sector_colors: dict[str, str] = config.get("sector_colors", {
        "industry": "#3b82f6",
        "transport": "#f97316",
        "buildings": "#10b981",
        "others": "#8b5cf6",
    })
    page_label = str(config.get("page_label", "Energy balance overview"))

    demand_df = assigned_df[assigned_df["_page_key"].isin(demand_page_keys)].copy()
    if demand_df.empty:
        return [], None

    overview_flow_codes = [str(code) for code in config.get("overview_flow_codes", [])]
    overview_flow_df = assigned_df[
        assigned_df["_page_key"].eq("total_demand")
        & assigned_df["common_flow_code"].astype(str).isin(overview_flow_codes)
    ].copy()

    supply_detail_mask = assigned_df["common_flow_code"].apply(
        lambda c: code_expression_matches_any_prefix(c, supply_codes)
    )
    supply_detail_df = assigned_df[supply_detail_mask].copy()
    transformation_config = config.get("transformation_composition", {})
    transformation_df = pd.DataFrame()
    transformation_flow_df = pd.DataFrame()
    if transformation_config.get("enabled", False):
        transformation_df = select_transformation_overview_rows(
            assigned_df,
            transformation_config,
            template.get("other_transformation_page", {}),
        )
        transformation_flow_df = select_transformation_overview_rows(
            assigned_df,
            transformation_config,
            template.get("other_transformation_page", {}),
            prefer_leaf_flows=True,
        )
    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    demand_total_abs = float(demand_df["value"].abs().sum())
    chart_specs: list[dict] = [
        {
            "chart_key": "chart__area__total_demand__sector",
            "title": "Final energy demand by sector (TFC)",
            "overview_group": "Demand composition",
            "build": lambda: _build_td_sector_chart(demand_df, overview_flow_df, series_labels, primary_source, primary_scenario, sector_colors, base_year=base_year),
            "total_abs": demand_total_abs,
            "row_count": len(demand_df),
            "source_flow_labels": "; ".join(demand_page_keys),
        },
        {
            "chart_key": "chart__area__total_demand__fuel",
            "title": "Final energy demand by fuel (TFC)",
            "overview_group": "Demand composition",
            "build": lambda: _build_td_fuel_chart(demand_df, overview_flow_df, series_labels, primary_source, primary_scenario, base_year=base_year),
            "total_abs": demand_total_abs,
            "row_count": len(demand_df),
            "source_flow_labels": "; ".join(demand_page_keys),
        },
    ]
    if not supply_detail_df.empty:
        supply_total_abs = float(supply_detail_df["value"].abs().sum())
        chart_specs.append({
            "chart_key": "chart__area__total_demand__supply_component",
            "title": "Energy supply by balance component",
            "overview_group": "Supply composition",
            "build": lambda: _build_supply_stack_chart(
                supply_detail_df, series_labels, primary_source, primary_scenario,
                group_col="common_flow_label", chart_title="Energy supply by balance component", base_year=base_year,
            ),
            "total_abs": supply_total_abs,
            "row_count": len(supply_detail_df),
            "source_flow_labels": "; ".join(supply_codes),
        })
        chart_specs.append({
            "chart_key": "chart__area__total_demand__supply_fuel",
            "title": "Energy supply by fuel",
            "overview_group": "Supply composition",
            "build": lambda: _build_supply_stack_chart(
                supply_detail_df, series_labels, primary_source, primary_scenario,
                group_col="common_product_label", chart_title="Energy supply by fuel", base_year=base_year,
            ),
            "total_abs": supply_total_abs,
            "row_count": len(supply_detail_df),
            "source_flow_labels": "; ".join(supply_codes),
        })

    if not transformation_df.empty:
        transformation_total_abs = float(transformation_df["value"].abs().sum())
        transformation_group = "Transformation, transfers, losses and own use"
        transformation_prefixes = transformation_config.get(
            "flow_code_prefixes", ["09", "08", "10.01", "10.02"]
        )
        chart_specs.append({
            "chart_key": "chart__area__total_demand__transformation_flow",
            "title": f"{transformation_group} by flow",
            "overview_group": transformation_group,
            "build": lambda: _build_supply_stack_chart(
                transformation_flow_df,
                series_labels,
                primary_source,
                primary_scenario,
                group_col="common_flow_label",
                chart_title=f"{transformation_group} by flow",
                base_year=base_year,
                total_line_suffix="transformation/transfer/loss/own-use net total",
                composition_subject="flow",
                flow_composition_note=(
                    "Areas show signed transformation, transfer, own-use and loss flows"
                ),
                fuel_composition_note="Areas show fuels across the complete boundary",
                stack_prefix="transformation",
                preserve_gross_signs=True,
                total_detail_df=transformation_df,
            ),
            "total_abs": transformation_total_abs,
            "row_count": len(transformation_flow_df),
            "source_flow_labels": "; ".join(transformation_prefixes),
        })
        chart_specs.append({
            "chart_key": "chart__area__total_demand__transformation_fuel",
            "title": f"{transformation_group} by fuel",
            "overview_group": transformation_group,
            "build": lambda: _build_supply_stack_chart(
                transformation_df,
                series_labels,
                primary_source,
                primary_scenario,
                group_col="common_product_label",
                chart_title=f"{transformation_group} by fuel",
                base_year=base_year,
                total_line_suffix="transformation/transfer/loss/own-use net total",
                composition_subject="fuel",
                flow_composition_note=(
                    "Areas show signed transformation, transfer, own-use and loss flows"
                ),
                fuel_composition_note="Areas show fuels across the complete boundary",
                stack_prefix="transformation",
                preserve_gross_signs=True,
                note_context_df=transformation_flow_df,
            ),
            "total_abs": transformation_total_abs,
            "row_count": len(transformation_df),
            "source_flow_labels": "; ".join(transformation_prefixes),
        })
    # Keep this separate LEAP diagnostic at the bottom of the overview page,
    # after the mapped balance and transformation sections.
    unmet_requirements_df = (
        pd.DataFrame() if unmet_requirements_df is None else unmet_requirements_df.copy()
    )
    if not unmet_requirements_df.empty and _has_nonzero_values(unmet_requirements_df["value"]):
        unmet_total_abs = float(unmet_requirements_df["value"].abs().sum())
        chart_specs.append({
            "chart_key": "chart__area__total_demand__unmet_requirements",
            "title": "Unmet requirements by fuel",
            "overview_group": "Unmet requirements",
            "build": lambda: build_unmet_requirements_chart(
                unmet_requirements_df,
                series_labels,
                primary_scenario=primary_scenario,
                base_year=base_year,
            ),
            "total_abs": unmet_total_abs,
            "row_count": len(unmet_requirements_df),
            "source_flow_labels": "Unmet Requirements",
        })
    for spec in chart_specs:
        chart_key = spec["chart_key"]
        fig = spec["build"]()
        charts[chart_key] = fig
        title = spec["title"]
        total_abs = spec["total_abs"]
        chart_rows.append({
            "chart_key": chart_key, "chart_type": "stacked_area",
            "title": title, "product_label": title, "section_label": "Overview",
            "overview_group": spec["overview_group"],
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
            "datasets": chart_dataset_tokens_from_figure(fig),
            "stacked_area_note": stacked_area_note_from_figure(fig),
        })
        manifest_rows.append({
            "page_key": "total_demand", "page_label": page_label,
            "section_label": spec["overview_group"], "chart_type": "stacked_area",
            "chart_key": chart_key, "common_flow_label": title,
            "common_product_label": "All", "row_count": int(spec["row_count"]),
            "source_flow_labels": spec["source_flow_labels"],
            "sign_note": "", "suppressed": False,
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
            "diff_hist_json": "", "diff_proj_json": "",
        })

    for flow_code in overview_flow_codes:
        flow_df = overview_flow_df[overview_flow_df["common_flow_code"].astype(str) == flow_code]
        if flow_df.empty:
            continue
        flow_label = str(flow_df["common_flow_label"].mode().iloc[0])
        chart_key = f"chart__line__total_demand__{safe_slug(flow_code)}"
        balance_figure = _build_balance_flow_total_chart(
            flow_df, flow_label, series_labels, base_year=base_year
        )
        charts[chart_key] = balance_figure
        total_abs = float(flow_df["value"].abs().sum())
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "line",
            "title": flow_label,
            "product_label": flow_label,
            "section_label": "Energy balance totals",
            "total_abs_value": total_abs,
            "abs_diff": 0.0,
            "pct_diff": 0.0,
            "datasets": chart_dataset_tokens_from_figure(balance_figure),
        })
        manifest_rows.append({
            "page_key": "total_demand",
            "page_label": page_label,
            "section_label": "Energy balance totals",
            "chart_type": "line",
            "chart_key": chart_key,
            "common_flow_label": flow_label,
            "common_product_label": "All products",
            "row_count": int(len(flow_df)),
            "source_flow_labels": flow_label,
            "sign_note": "Signed total across all products.",
            "suppressed": False,
            "total_abs_value": total_abs,
            "abs_diff": 0.0,
            "pct_diff": 0.0,
            "diff_hist_json": "",
            "diff_proj_json": "",
        })

    # The LEAP-only Unmet Requirements diagnostic belongs after every mapped
    # overview and balance-total chart, not just after the composition charts.
    unmet_chart_key = "chart__area__total_demand__unmet_requirements"
    chart_rows[:] = (
        [row for row in chart_rows if row["chart_key"] != unmet_chart_key]
        + [row for row in chart_rows if row["chart_key"] == unmet_chart_key]
    )
    manifest_rows[:] = (
        [row for row in manifest_rows if row["chart_key"] != unmet_chart_key]
        + [row for row in manifest_rows if row["chart_key"] == unmet_chart_key]
    )

    bundle_name = "total_demand__charts.json"
    write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
    write_dashboard_page(
        {"page_key": "total_demand", "page_label": page_label},
        chart_rows=chart_rows,
        bundle_js_name=bundle_name.replace(".json", ".js"),
        output_path=layout["dashboards"] / page_file_name("total_demand"),
        all_pages=all_pages,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        dashboard_updated_label=dashboard_updated_label,
        **category_basis_ui_kwargs(template),
    )
    page_row = {
        "file": page_file_name("total_demand"), "label": page_label,
        "area_chart_count": sum(row["chart_type"] == "stacked_area" for row in chart_rows),
        "summary_chart_count": 0,
        "line_chart_count": sum(row["chart_type"] == "line" for row in chart_rows),
    }
    return manifest_rows, page_row


def _configured_scope_page_mask(df: pd.DataFrame, scope_page: dict) -> pd.Series:
    """Return rows matching a configured secondary or scope-specific page."""
    mask = pd.Series(True, index=df.index)
    scope = str(scope_page.get("comparison_scope", "")).strip()
    if scope and "comparison_scope" in df.columns:
        mask = mask & (df["comparison_scope"].astype(str) == scope)

    base_page_keys = [str(key) for key in scope_page.get("source_page_keys", [])]
    if base_page_keys and "_page_key" in df.columns:
        mask = mask & df["_page_key"].astype(str).isin(base_page_keys)

    include_prefixes = scope_page.get("include_flow_code_prefixes", [])
    include_keywords = scope_page.get("include_flow_keywords", [])
    if include_prefixes or include_keywords:
        include_mask = pd.Series(False, index=df.index)
        include_mask = include_mask | code_columns_mask(df, CODE_MATCH_COLUMNS, include_prefixes)
        include_mask = include_mask | text_columns_mask(df, LABEL_MATCH_COLUMNS, include_keywords)
        mask = mask & include_mask

    exclude_prefixes = scope_page.get("exclude_flow_code_prefixes", [])
    exclude_keywords = scope_page.get("exclude_flow_keywords", [])
    if exclude_prefixes or exclude_keywords:
        exclude_mask = pd.Series(False, index=df.index)
        exclude_mask = exclude_mask | code_columns_mask(df, CODE_MATCH_COLUMNS, exclude_prefixes)
        exclude_mask = exclude_mask | text_columns_mask(df, LABEL_MATCH_COLUMNS, exclude_keywords)
        mask = mask & ~exclude_mask
    return mask


def _line_chart_manifest_and_rows(
    page_df: pd.DataFrame,
    page_key: str,
    page_label: str,
    primary_source: str,
    primary_scenario: str,
    comparison_source: str,
    ninth_source: str,
    base_year: int,
    suppression_threshold: float,
    series_labels: dict[str, str],
    template: dict,
) -> tuple[dict[str, go.Figure], list[dict], list[dict]]:
    """Build section-aggregate and detail line chart records for a page dataframe."""
    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    flow_nodes = get_existing_flow_nodes(page_df)
    all_canonical = set(flow_nodes["canonical_code"].astype(str))
    parent_flow_labels: set[str] = set()
    for _, node in flow_nodes.iterrows():
        code = str(node["canonical_code"])
        if code and any(c.startswith(code + ".") for c in all_canonical if c != code):
            parent_flow_labels.add(str(node["common_flow_label"]))

    section_charts, section_chart_rows, section_manifest_rows = _build_section_aggregate_charts(
        page_df, page_key, page_label, parent_flow_labels, template, series_labels,
    )
    charts.update(section_charts)
    chart_rows.extend(section_chart_rows)
    manifest_rows.extend(section_manifest_rows)

    flow_group_charts, flow_group_chart_rows, flow_group_manifest_rows = _build_flow_group_aggregate_charts(
        page_df, page_key, page_label, parent_flow_labels, template, series_labels,
    )
    charts.update(flow_group_charts)
    chart_rows.extend(flow_group_chart_rows)
    manifest_rows.extend(flow_group_manifest_rows)

    pairs = page_df[["common_flow_label", "common_product_label"]].drop_duplicates().sort_values(["common_flow_label", "common_product_label"])
    for _, pair in pairs.iterrows():
        flow_label = pair["common_flow_label"]
        product_label = pair["common_product_label"]
        if flow_label in parent_flow_labels:
            continue
        pair_rows = page_df[
            (page_df["common_flow_label"] == flow_label)
            & (page_df["common_product_label"] == product_label)
        ]
        section_label = str(pair_rows["_section_label"].mode().iloc[0]) if not pair_rows.empty else page_label
        chart_key = f"chart__line__{safe_slug(flow_label)}__{safe_slug(product_label)}"
        if page_key:
            chart_key = f"{chart_key}__{safe_slug(page_key)}"
        metrics = compute_ranking_metrics(
            pair_rows,
            primary_source,
            primary_scenario,
            comparison_source,
            base_year=base_year,
            ninth_source=ninth_source,
        )
        suppressed = metrics["total_abs_value"] < suppression_threshold
        product_display = str(product_label)
        hist_diff_by_scenario, proj_diff_by_scenario = compute_diff_series_by_scenario(
            pair_rows, primary_source, comparison_source, ninth_source, base_year
        )
        hist_diff = hist_diff_by_scenario[primary_scenario]
        proj_diff = proj_diff_by_scenario[primary_scenario]
        manifest_rows.append({
            "page_key": page_key,
            "page_label": page_label,
            "section_label": section_label,
            "chart_type": "line",
            "chart_key": chart_key,
            "common_flow_label": flow_label,
            "common_product_label": product_label,
            "row_count": int(len(pair_rows)),
            "source_flow_labels": flow_label,
            "sign_note": sign_note_for_chart(pair_rows),
            "suppressed": suppressed,
            "diff_hist_json": hist_diff.to_json() if not hist_diff.empty else "",
            "diff_proj_json": proj_diff.to_json() if not proj_diff.empty else "",
            **metrics,
        })
        if suppressed:
            continue
        chart_figure = build_product_chart(
            pair_rows,
            flow_label,
            product_label,
            series_labels,
            primary_source=primary_source,
            primary_scenario=primary_scenario,
            comparison_source=comparison_source,
            base_year=base_year,
        )
        if not chart_figure.data:
            # A row can exist only at the base year for a non-comparison
            # source. Do not publish an empty chart placeholder; retain the
            # manifest row as suppressed so the omission remains auditable.
            manifest_rows[-1]["suppressed"] = True
            continue
        charts[chart_key] = chart_figure
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "line",
            "title": f"{flow_label} - {product_label}",
            "product_label": product_display,
            "section_label": section_label,
            "flow_group_label": str(flow_label),
            "datasets": chart_dataset_tokens_from_figure(chart_figure),
            **metrics,
        })
    return charts, chart_rows, manifest_rows


def build_scope_specific_pages(
    scope_df: pd.DataFrame,
    template: dict,
    series_labels: dict[str, str],
    layout: dict[str, Path],
    all_pages: list[dict],
    primary_source: str,
    primary_scenario: str,
    comparison_source: str,
    ninth_source: str,
    base_year: int,
    suppression_threshold: float,
    economy_label: str,
    dashboard_switcher: list[dict[str, str]] | None,
    current_dashboard: str,
    dashboard_updated_label: str = "",
) -> tuple[list[dict], list[dict]]:
    """Build optional pages for alternate comparison scopes such as LEAP vs 9th."""
    config = template.get("scope_specific_pages", {})
    if not config.get("enabled", False) or scope_df.empty:
        return [], []

    assigned_scope_df = assign_pages(
        scope_df,
        template.get("sector_pages", []),
        template.get("routing_special_cases", []),
    )
    manifest_rows: list[dict] = []
    page_rows: list[dict] = []

    for scope_page in config.get("pages", []):
        if not scope_page.get("enabled", True):
            continue
        page_key = safe_slug(scope_page.get("page_key", "scope_specific"))
        page_label = str(scope_page.get("page_label", page_key))
        page_df = assigned_scope_df[_configured_scope_page_mask(assigned_scope_df, scope_page)].copy()
        if page_df.empty:
            continue

        charts, chart_rows, page_manifest_rows = _line_chart_manifest_and_rows(
            page_df=page_df,
            page_key=page_key,
            page_label=page_label,
            primary_source=primary_source,
            primary_scenario=primary_scenario,
            comparison_source=str(scope_page.get("comparison_source_system", ninth_source)),
            ninth_source=ninth_source,
            base_year=base_year,
            suppression_threshold=suppression_threshold,
            series_labels=series_labels,
            template=template,
        )
        manifest_rows.extend(page_manifest_rows)
        if not charts:
            continue

        bundle_name = f"{page_key}__charts.json"
        write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
        page_file = page_file_name(page_key)
        write_dashboard_page(
            {"page_key": page_key, "page_label": page_label},
            chart_rows=chart_rows,
            bundle_js_name=bundle_name.replace(".json", ".js"),
            output_path=layout["dashboards"] / page_file,
            all_pages=all_pages,
            economy_label=economy_label,
            dashboard_switcher=dashboard_switcher,
            current_dashboard=current_dashboard,
            page_note=str(scope_page.get("page_note", "")),
            dashboard_updated_label=dashboard_updated_label,
            **category_basis_ui_kwargs(template),
        )
        page_rows.append({
            "file": page_file,
            "label": page_label,
            "area_chart_count": sum(r.get("chart_type") == "stacked_area" for r in chart_rows),
            "line_chart_count": sum(r.get("chart_type") == "line" for r in chart_rows),
        })
    return manifest_rows, page_rows


def drop_esto_post_base_year_rows(df: pd.DataFrame, comparison_source: str, base_year: int) -> pd.DataFrame:
    """Drop comparison-source (ESTO) rows after the base year.

    The wide input file zero-fills years ESTO has no historical data for, which
    would otherwise plot as a flat series of 0s stretching into the projection
    years. ESTO only reports actuals through base_year, so later rows are
    fill artifacts rather than real data.
    """
    if df.empty:
        return df
    is_comparison_source = df["source_system"].astype(str).str.casefold() == comparison_source.casefold()
    is_post_base_year = df["year"] > base_year
    return df[~(is_comparison_source & is_post_base_year)].copy()


def drop_excluded_flow_rows(
    df: pd.DataFrame,
    excluded_flow_code_prefixes: list[object],
    excluded_flow_labels: list[object] | None = None,
) -> pd.DataFrame:
    """Drop rows matching configured code prefixes or exact flow labels.

    Applies only to ``measure == "energy"`` rows: the exclusion list encodes
    energy-balance identity rules (supply/TFC/TFEC), which do not mean
    anything for a non-energy series. A frame without a ``measure`` column is
    treated as all-energy, matching behaviour before that column existed.
    """
    if df.empty:
        return df
    is_energy = (
        df["measure"].astype(str).eq("energy")
        if "measure" in df.columns
        else pd.Series(True, index=df.index)
    )
    excluded_mask = pd.Series(False, index=df.index)
    if excluded_flow_code_prefixes:
        excluded_mask = excluded_mask | (
            is_energy
            & df["common_flow_code"].apply(
                lambda value: code_expression_matches_any_prefix(value, excluded_flow_code_prefixes)
            )
        )
    excluded_labels = {
        str(value).strip().casefold()
        for value in (excluded_flow_labels or [])
        if str(value).strip()
    }
    if excluded_labels and "common_flow_label" in df.columns:
        excluded_mask = excluded_mask | (
            is_energy
            & df["common_flow_label"].fillna("").astype(str).str.strip().str.casefold().isin(
                excluded_labels
            )
        )
    return df[~excluded_mask].copy()


def _keep_one_measure_for_energy_balance_charts(df: pd.DataFrame) -> pd.DataFrame:
    """Restrict to a single measure before any source/scenario comparison logic runs.

    Every comparison this renderer draws (``comparison_source_system`` /
    ``ninth_source_system`` resolution, the TFC/TFEC identities, sign
    semantics) was written for one energy series compared against another. If
    a future caller's frame ever carried more than one ``measure`` value, a
    plain ``(source_system, scenario)`` match could pair a "LEAP energy" row
    against an "ESTO emissions" row with no error — same source system,
    different measure. Restricting to the dominant measure up front makes
    that impossible without threading ``measure`` through every one of this
    module's comparison call sites individually. Today every input is
    ``measure == "energy"`` (see ``DEFAULT_MEASURE`` in
    ``common_esto_dashboard_data``), so this is a no-op; a frame without a
    ``measure`` column passes through unchanged, matching behaviour before
    that column existed.
    """
    if df.empty or "measure" not in df.columns:
        return df
    measures = df["measure"].astype(str)
    dominant = measures.mode()
    if dominant.empty:
        return df
    return df[measures == dominant.iloc[0]].copy()


def assign_bespoke_overview_rows(
    assigned_df: pd.DataFrame,
    total_demand_config: dict,
) -> pd.DataFrame:
    """Move configured balance totals onto the one bespoke overview page."""
    out = assigned_df.copy()
    overview_flow_codes = {
        str(code) for code in total_demand_config.get("overview_flow_codes", [])
    }
    if not overview_flow_codes:
        return out
    overview_mask = out["common_flow_code"].astype(str).isin(overview_flow_codes)
    out.loc[overview_mask, "_page_key"] = "total_demand"
    out.loc[overview_mask, "_page_label"] = str(
        total_demand_config.get("page_label", "Energy balance overview")
    )
    out.loc[overview_mask, "_section_key"] = "total_demand"
    out.loc[overview_mask, "_section_label"] = "Energy balance totals"
    out.loc[overview_mask, "_page_rule_priority"] = "bespoke"
    out.loc[overview_mask, "_page_rule_note"] = (
        "Configured top-level balance flow shown on the Energy balance overview page."
    )
    out.loc[overview_mask, "_routing_status"] = "bespoke_page"
    out.loc[overview_mask, "_routing_candidates"] = "total_demand"
    return out


def category_basis_ui_kwargs(template: dict) -> dict[str, object]:
    """Return renderer-only category-basis controls attached by the workflow."""
    return {
        "category_basis_options": template.get("_category_basis_options", []),
        "current_comparison_scope": str(template.get("_active_comparison_scope", "")),
        "dataset_filter_options": template.get("_active_dataset_filter_options", []),
        "dashboard_key_suffix": str(template.get("_dashboard_key_suffix", "")),
    }


def render_dashboard(
    df: pd.DataFrame,
    template: dict,
    series_config: dict,
    layout: dict[str, Path],
    scope_df: pd.DataFrame | None = None,
    dashboard_updated_label: str = "",
    additional_pages: list[dict[str, str]] | None = None,
    source_category_map: pd.DataFrame | None = None,
    unmet_requirements_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Render page bundles, dashboard pages, and a chart manifest."""
    series_labels = series_config.get("series_labels", {})
    current_dashboard = str(template.get("_current_dashboard_key", layout["root"].name))
    dashboard_switcher = _normalise_dashboard_switcher(series_config, current_dashboard)
    economy_label = _current_dashboard_label(series_config, dashboard_switcher, current_dashboard)
    page_rules = template.get("sector_pages")
    if not page_rules:
        raise ValueError("Template is missing required 'sector_pages' rules.")
    chart_config = template.get("chart_generation", {})
    comparison_source = str(chart_config.get("comparison_source_system", "ESTO"))
    base_year = int(chart_config.get("base_year", 2023))
    excluded_flow_code_prefixes = template.get("excluded_flow_code_prefixes", [])
    excluded_flow_labels = template.get("excluded_flow_labels", [])
    df = _keep_one_measure_for_energy_balance_charts(df)
    df = drop_esto_post_base_year_rows(df, comparison_source, base_year)
    df = drop_excluded_flow_rows(df, excluded_flow_code_prefixes, excluded_flow_labels)
    if scope_df is not None:
        scope_df = _keep_one_measure_for_energy_balance_charts(scope_df)
        scope_df = drop_esto_post_base_year_rows(scope_df, comparison_source, base_year)
        scope_df = drop_excluded_flow_rows(
            scope_df,
            excluded_flow_code_prefixes,
            excluded_flow_labels,
        )
    routing_special_cases = template.get("routing_special_cases", [])
    assigned_df = assign_pages(df, page_rules, routing_special_cases)
    assigned_df = assign_bespoke_overview_rows(
        assigned_df,
        template.get("total_demand_page", {}),
    )
    page_summary_df = build_page_assignment_summary(assigned_df)
    page_summary_df.to_csv(layout["supporting"] / "page_assignment_summary.csv", index=False)

    secondary_config = template.get("secondary_pages", {})
    secondary_pages_by_key: dict[str, dict] = {}
    if secondary_config.get("enabled", False):
        for secondary_page in secondary_config.get("pages", []):
            if not secondary_page.get("enabled", True):
                continue
            secondary_key = safe_slug(secondary_page.get("page_key", "secondary"))
            if secondary_key:
                secondary_pages_by_key[secondary_key] = secondary_page

    # First pass: build page inventory (needed for navigation chips on every page).
    page_meta = assigned_df[["_page_key", "_page_label"]].drop_duplicates().sort_values("_page_key")
    page_inventory: list[dict] = []
    # Add the synthetic total demand page first so it appears in nav on all other pages.
    if template.get("total_demand_page", {}).get("enabled", False):
        overview_label = str(
            template.get("total_demand_page", {}).get("page_label", "Energy balance overview")
        )
        page_inventory.append({"page_key": "total_demand", "page_label": overview_label, "file": page_file_name("total_demand")})
    hidden_page_keys = {
        str(key) for key in template.get("leap_demand_sector_coverage", {}).get("_hidden_page_keys", [])
    }
    coverage_config = template.get("leap_demand_sector_coverage", {})
    hidden_page_keys.update(
        page_keys_without_required_source(
            assigned_df,
            coverage_config.get("require_primary_source_page_keys", []),
            chart_config.get("primary_area_source_system", "LEAP"),
        )
    )
    for _, meta in page_meta.iterrows():
        page_key = safe_slug(meta["_page_key"])
        if page_key == "total_demand":
            continue
        if page_key in hidden_page_keys:
            continue
        page_label = str(meta["_page_label"])
        if not assigned_df[assigned_df["_page_key"] == meta["_page_key"]].empty:
            page_inventory.append({"page_key": page_key, "page_label": page_label, "file": page_file_name(page_key)})

    for secondary_key, secondary_page in secondary_pages_by_key.items():
        secondary_mask = _configured_scope_page_mask(assigned_df, secondary_page)
        if secondary_mask.any() and secondary_key not in {page["page_key"] for page in page_inventory}:
            page_inventory.append({
                "page_key": secondary_key,
                "page_label": str(secondary_page.get("page_label", secondary_key)),
                "file": f"{secondary_key}.html",
            })

    scope_config = template.get("scope_specific_pages", {})
    if scope_config.get("enabled", False) and scope_df is not None and not scope_df.empty:
        scope_inventory_df = assign_pages(scope_df, page_rules, routing_special_cases)
        for scope_page in scope_config.get("pages", []):
            if not scope_page.get("enabled", True):
                continue
            scope_page_key = safe_slug(scope_page.get("page_key", "scope_specific"))
            scope_page_label = str(scope_page.get("page_label", scope_page_key))
            scope_mask = _configured_scope_page_mask(scope_inventory_df, scope_page)
            if scope_mask.any():
                page_inventory.append({
                    "page_key": scope_page_key,
                    "page_label": scope_page_label,
                    "file": page_file_name(scope_page_key),
                })

    # The Emissions page is derived from the demand pages above, so it must be
    # in the inventory before any page renders its navigation chips.
    if emissions_page_enabled(template, assigned_df):
        emissions_config = template.get("emissions_page", {})
        emissions_page_key = safe_slug(emissions_config.get("page_key", "emissions"))
        page_inventory.append({
            "page_key": emissions_page_key,
            "page_label": str(emissions_config.get("page_label", "Emissions")),
            "file": page_file_name(emissions_page_key),
        })

    for page in additional_pages or []:
        page_key = safe_slug(page.get("page_key", ""))
        if page_key and page_key not in {item["page_key"] for item in page_inventory}:
            page_inventory.append({
                "page_key": page_key,
                "page_label": str(page.get("page_label", page_key)),
                "file": str(page.get("file", page_file_name(page_key))),
            })

    manifest_rows: list[dict[str, object]] = []
    page_rows: list[dict[str, object]] = []

    # Second pass: generate charts and pages.
    chart_config = template.get("chart_generation", {})
    primary_source = str(chart_config.get("primary_area_source_system", "LEAP"))
    primary_scenario = str(chart_config.get("primary_area_scenario", "Target"))
    comparison_source = str(chart_config.get("comparison_source_system", "ESTO"))
    base_year = int(chart_config.get("base_year", 2023))
    ninth_source = str(chart_config.get("ninth_source_system", "NINTH"))
    suppression_threshold = effective_chart_suppression_threshold(template, assigned_df)

    for page_info in page_inventory:
        page_key = page_info["page_key"]
        page_label = page_info["page_label"]
        page_rule = next(
            (
                rule
                for rule in template.get("sector_pages", [])
                if safe_slug(rule.get("page_key", "")) == page_key
            ),
            {},
        )
        page_scope_overview_label = str(
            page_rule.get("page_scope_overview_label", "")
        ).strip()
        # Bespoke pages own their complete bundle and manifest. They must not
        # first pass through the generic builder and then overwrite its files.
        if page_key == "total_demand":
            continue
        secondary_page = secondary_pages_by_key.get(page_key)
        if secondary_page:
            page_df = assigned_df[
                _configured_scope_page_mask(assigned_df, secondary_page)
            ].copy()
            page_df["_page_key"] = page_key
            page_df["_page_label"] = page_label
            page_df["_section_key"] = page_key
            page_df["_section_label"] = page_label
        else:
            page_df = assigned_df[assigned_df["_page_key"].apply(safe_slug) == page_key].copy()
        if page_df.empty:
            continue

        other_transformation_config = template.get("other_transformation_page", {})
        other_transformation_page_key = safe_slug(
            other_transformation_config.get("page_key", "other_transformation")
        )
        if page_key == other_transformation_page_key:
            comparison_context_df = scope_df if scope_df is not None else assigned_df
            page_df = prepare_other_transformation_page_rows(
                page_df,
                comparison_context_df,
                other_transformation_config,
            )
            if page_df.empty:
                continue

        charts: dict[str, go.Figure] = {}
        chart_rows: list[dict] = []

        supply_config = template.get("supply_page", {})
        supply_page_key = safe_slug(supply_config.get("page_key", "supply"))
        if page_key == supply_page_key:
            excluded_flow_codes = {
                str(value).strip()
                for value in supply_config.get("exclude_flow_codes", [])
                if str(value).strip()
            }
            if uses_combined_international_transport_placeholder(template):
                # The placeholder has one value at the 04-05 boundary. Keep that
                # comparable parent and suppress its 04/05 children until LEAP
                # supplies the separate Air and Shipping source branches.
                excluded_flow_codes.discard("04-05")
                excluded_flow_codes.update({"04", "05"})
            if excluded_flow_codes and "common_flow_code" in page_df.columns:
                page_df = page_df[
                    ~page_df["common_flow_code"].astype(str).isin(excluded_flow_codes)
                ].copy()
            balancing_page_df = page_df
            balancing_scope = str(
                supply_config.get("base_year_bar_comparison_scope", "")
            ).strip()
            active_scope = str(template.get("_active_comparison_scope", "")).strip()
            if (
                balancing_scope
                and balancing_scope != active_scope
                and scope_df is not None
                and "comparison_scope" in scope_df.columns
            ):
                balancing_scope_df = scope_df[
                    scope_df["comparison_scope"].astype(str).eq(balancing_scope)
                ].copy()
                if not balancing_scope_df.empty:
                    balancing_assigned_df = assign_pages(
                        balancing_scope_df,
                        page_rules,
                        routing_special_cases,
                    )
                    balancing_assigned_df = assign_bespoke_overview_rows(
                        balancing_assigned_df,
                        template.get("total_demand_page", {}),
                    )
                    balancing_page_df = balancing_assigned_df[
                        balancing_assigned_df["_page_key"].apply(safe_slug)
                        == supply_page_key
                    ].copy()
            bar_charts, bar_chart_rows, bar_manifest_rows, page_df = (
                _build_supply_base_year_bar_charts(
                    page_df=balancing_page_df,
                    page_key=page_key,
                    page_label=page_label,
                    flow_codes=list(supply_config.get("base_year_bar_flow_codes", [])),
                    base_year=base_year,
                    suppression_threshold=suppression_threshold,
                    primary_source=primary_source,
                    primary_scenario=primary_scenario,
                    comparison_source=comparison_source,
                    ninth_source=ninth_source,
                    series_labels=series_labels,
                    comparison_scope=balancing_scope or active_scope,
                    comparison_scope_label=str(
                        supply_config.get("base_year_bar_scope_label", "")
                    ).strip(),
                    ordinary_page_df=page_df,
                    source_value_multipliers_by_flow=dict(
                        supply_config.get("base_year_bar_source_value_multipliers", {})
                    ),
                )
            )
            charts.update(bar_charts)
            chart_rows.extend(bar_chart_rows)
            manifest_rows.extend(bar_manifest_rows)

        area_specs = (
            []
            if page_key == other_transformation_page_key
            and other_transformation_config.get("hide_generic_overview", False)
            else pick_area_specs(page_df, template)
        )
        page_flow_labels = {
            str(value).strip()
            for value in page_df["common_flow_label"].dropna().unique()
            if str(value).strip()
        }
        for area_spec in area_specs:
            source_aggregate_label = str(area_spec["aggregate_flow_label"])
            source_root_code = str(area_spec.get("aggregate_flow_prefix") or "").strip()
            if not source_root_code:
                source_root_code = code_candidate_text(source_aggregate_label)
            if area_spec_is_placeholder_only_demand_child(page_key, area_spec, template):
                continue
            is_real_page_flow = source_aggregate_label in page_flow_labels
            subtree_is_page_complete = _flow_subtree_is_page_complete(
                assigned_df,
                page_key,
                source_root_code,
            )
            is_complete_page_root = is_real_page_flow and subtree_is_page_complete
            display_aggregate_label = area_chart_display_label(
                source_aggregate_label,
                page_scope_overview_label,
                subtree_is_page_complete,
            )
            display_area_spec = {
                **area_spec,
                "aggregate_flow_label": display_aggregate_label,
            }
            chart_key = f"chart__area__{safe_slug(area_spec['aggregate_flow_prefix'])}__{safe_slug(source_aggregate_label)}"
            area_df = area_spec_rows(page_df, area_spec)
            if not area_chart_allowed_for_demand_coverage(
                page_key,
                area_df,
                template,
            ):
                continue
            metrics = compute_ranking_metrics(area_df, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            suppressed = metrics["total_abs_value"] < suppression_threshold
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": "Overview",
                "chart_type": "stacked_area",
                "chart_key": chart_key,
                "common_flow_label": source_aggregate_label,
                "common_product_label": "All products",
                "row_count": int(len(area_df)),
                "source_flow_labels": "; ".join(area_spec["source_flow_labels"]),
                "sign_note": sign_note_for_chart(area_df),
                "suppressed": suppressed,
                **metrics,
            })
            if suppressed:
                continue
            figure = build_area_chart(page_df, display_area_spec, series_labels, template)
            if not figure.data:
                manifest_rows[-1]["suppressed"] = True
                continue
            charts[chart_key] = figure
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": display_aggregate_label,
                "product_label": display_aggregate_label,
                "section_label": "Overview",
                "navigation_root_label": (
                    source_aggregate_label
                    if is_complete_page_root
                    else ""
                ),
                "datasets": chart_dataset_tokens_from_figure(figure),
                "stacked_area_note": stacked_area_note_from_figure(figure),
                **metrics,
            })

        if aggregate_only_demand_page_active(page_key, template):
            # A page-level placeholder supplies one broad total, not a valid
            # sector/product decomposition. Keep its top-level overview card
            # above, but do not manufacture detail cards from ESTO rows that
            # the active LEAP placeholder does not represent.
            detail_page_df = page_df.iloc[0:0].copy()
        else:
            detail_page_df = drop_placeholder_only_demand_detail_rows(
                page_key,
                page_df,
                template,
            )
        flow_nodes = get_existing_flow_nodes(detail_page_df)
        all_canonical = set(flow_nodes["canonical_code"].astype(str))
        parent_flow_labels: set[str] = set()
        for _, node in flow_nodes.iterrows():
            code = str(node["canonical_code"])
            if code and any(c.startswith(code + ".") for c in all_canonical if c != code):
                parent_flow_labels.add(str(node["common_flow_label"]))

        # Section aggregate charts: two per section (by product, by flow), summing all non-parent flows.
        section_charts, section_chart_rows, section_manifest_rows = _build_section_aggregate_charts(
            detail_page_df, page_key, page_label, parent_flow_labels, template, series_labels,
        )
        charts.update(section_charts)
        chart_rows.extend(section_chart_rows)
        manifest_rows.extend(section_manifest_rows)

        # Subsection aggregate charts: two per flow-group subsection (by product, by sub-flow).
        flow_group_charts, flow_group_chart_rows, flow_group_manifest_rows = _build_flow_group_aggregate_charts(
            detail_page_df, page_key, page_label, parent_flow_labels, template, series_labels,
        )
        charts.update(flow_group_charts)
        chart_rows.extend(flow_group_chart_rows)
        manifest_rows.extend(flow_group_manifest_rows)

        pairs = detail_page_df[["common_flow_label", "common_product_label"]].drop_duplicates().sort_values(["common_flow_label", "common_product_label"])
        for _, pair in pairs.iterrows():
            flow_label = pair["common_flow_label"]
            product_label = pair["common_product_label"]
            if flow_label in parent_flow_labels:
                continue
            pair_rows = detail_page_df[
                (detail_page_df["common_flow_label"] == flow_label)
                & (detail_page_df["common_product_label"] == product_label)
            ]
            section_label = str(pair_rows["_section_label"].mode().iloc[0]) if not pair_rows.empty else page_label
            chart_key = f"chart__line__{safe_slug(flow_label)}__{safe_slug(product_label)}"
            metrics = compute_ranking_metrics(pair_rows, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            suppressed = metrics["total_abs_value"] < suppression_threshold
            product_display = str(product_label)
            hist_diff_by_scenario, proj_diff_by_scenario = compute_diff_series_by_scenario(
                pair_rows, primary_source, comparison_source, ninth_source, base_year
            )
            hist_diff = hist_diff_by_scenario[primary_scenario]
            proj_diff = proj_diff_by_scenario[primary_scenario]
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": section_label,
                "chart_type": "line",
                "chart_key": chart_key,
                "common_flow_label": flow_label,
                "common_product_label": product_label,
                "row_count": int(len(pair_rows)),
                "source_flow_labels": flow_label,
                "sign_note": sign_note_for_chart(pair_rows),
                "suppressed": suppressed,
                "diff_hist_json": hist_diff.to_json() if not hist_diff.empty else "",
                "diff_proj_json": proj_diff.to_json() if not proj_diff.empty else "",
                **metrics,
            })
            if suppressed:
                continue
            chart_figure = build_product_chart(
                pair_rows, flow_label, product_label, series_labels,
                primary_source=primary_source, primary_scenario=primary_scenario,
                comparison_source=comparison_source, base_year=base_year,
            )
            if not chart_figure.data:
                manifest_rows[-1]["suppressed"] = True
                continue
            charts[chart_key] = chart_figure
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "line",
                "title": f"{flow_label} - {product_label}",
                "product_label": product_display,
                "section_label": section_label,
                "flow_group_label": str(flow_label),
                "common_row_id": (
                    str(pair_rows["common_row_id"].mode().iloc[0])
                    if "common_row_id" in pair_rows.columns
                    and not pair_rows["common_row_id"].dropna().empty
                    else ""
                ),
                "datasets": chart_dataset_tokens_from_figure(chart_figure),
                "stacked_area_note": stacked_area_note_from_figure(chart_figure),
                **metrics,
            })

        if not charts:
            continue
        bundle_name = f"{page_key}__charts.json"
        write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
        page_file = page_file_name(page_key)
        write_dashboard_page(
            {"page_key": page_key, "page_label": page_label},
            chart_rows=chart_rows,
            bundle_js_name=bundle_name.replace(".json", ".js"),
            output_path=layout["dashboards"] / page_file,
            all_pages=page_inventory,
            economy_label=economy_label,
            dashboard_switcher=dashboard_switcher,
            current_dashboard=current_dashboard,
            page_note=(
                str(secondary_page.get("page_note", ""))
                if secondary_page
                else page_placeholder_note(page_key, template)
            ),
            dashboard_updated_label=dashboard_updated_label,
            guide_context=guide_page_context(
                page_key,
                chart_rows,
                template,
                source_category_map,
            ),
            **category_basis_ui_kwargs(template),
        )
        page_rows.append({
            "file": page_file,
            "label": page_label,
            "area_chart_count": sum(r.get("chart_type") == "stacked_area" for r in chart_rows),
            "line_chart_count": sum(r.get("chart_type") == "line" for r in chart_rows),
        })

    td_manifest_rows, td_page_row = build_total_demand_page(
        assigned_df, template, series_labels, layout, page_inventory,
        primary_source=primary_source, primary_scenario=primary_scenario,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        dashboard_updated_label=dashboard_updated_label,
        unmet_requirements_df=unmet_requirements_df,
    )
    manifest_rows.extend(td_manifest_rows)
    if td_page_row:
        page_rows.append(td_page_row)

    for legacy_page_key in _PUBLIC_PAGE_FILES:
        write_legacy_page_redirect(layout["dashboards"], legacy_page_key)

    emissions_manifest_rows: list[dict] = []
    emissions_page_row: dict | None = None
    if emissions_page_enabled(template, assigned_df):
        emissions_manifest_rows, emissions_page_row = build_emissions_page(
            assigned_df, template, series_labels, layout, page_inventory,
            primary_source=primary_source, primary_scenario=primary_scenario,
            economy_label=economy_label,
            dashboard_switcher=dashboard_switcher,
            current_dashboard=current_dashboard,
            dashboard_updated_label=dashboard_updated_label,
        )
    manifest_rows.extend(emissions_manifest_rows)
    if emissions_page_row:
        page_rows.append(emissions_page_row)

    scope_manifest_rows, scope_page_rows = build_scope_specific_pages(
        scope_df if scope_df is not None else pd.DataFrame(),
        template,
        series_labels,
        layout,
        page_inventory,
        primary_source,
        primary_scenario,
        comparison_source,
        ninth_source,
        base_year,
        suppression_threshold,
        economy_label,
        dashboard_switcher,
        current_dashboard,
        dashboard_updated_label,
    )
    manifest_rows.extend(scope_manifest_rows)
    page_rows.extend(scope_page_rows)

    # Diagnostics pages have no chart bundle, so they are not added in the
    # chart-rendering loop above. Keep them visible from the overview index.
    existing_page_files = {str(row["file"]) for row in page_rows}
    for page in additional_pages or []:
        page_file = str(page.get("file", ""))
        if page_file and page_file not in existing_page_files:
            page_rows.append({
                "file": page_file,
                "label": str(page.get("page_label", page_file)),
                "area_chart_count": 0,
                "line_chart_count": 0,
            })

    write_index(
        page_rows,
        layout["dashboards"] / "index.html",
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        dashboard_updated_label=dashboard_updated_label,
        **category_basis_ui_kwargs(template),
    )
    manifest_df = finalize_chart_manifest(pd.DataFrame(manifest_rows))
    active_scope = str(template.get("_active_comparison_scope", "")).strip()
    if active_scope and "comparison_scope" not in manifest_df.columns:
        manifest_df.insert(0, "comparison_scope", active_scope)
    manifest_df.to_csv(layout["supporting"] / "chart_manifest.csv", index=False)
    return manifest_df

#%%
