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
    names = {"ESTO": "ESTO", "LEAP": "LEAP", "NINTH": "9th edition"}
    source = str(source_system).strip().upper()
    return names.get(source, source or "unknown dataset")


def stacked_area_dataset_note(sources: set[str], subject: str) -> str:
    """Describe the dataset(s) contributing the stacked traces."""
    if not sources:
        return "Stacked areas: no detailed dataset available."
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

    The area charts should use one category frontier on both sides of the
    base-year boundary.  Choose the most detailed available projection source,
    then restrict ESTO historical rows to categories that are actually active
    in that source after the base year.  This prevents an ESTO-only category
    from appearing as a misleading zero band beside the LEAP stack.
    """
    candidates = [primary_source, "NINTH", "LEAP", "ESTO"]
    source_column = df["source_system"].astype(str).str.casefold()
    scenario_column = df["scenario"].astype(str).str.casefold()
    selected_source = ""
    projected = df.iloc[0:0].copy()
    for source_name in candidates:
        source_rows = df[
            source_column.eq(source_name.casefold())
            & scenario_column.eq(scenario_name.casefold())
            & df["year"].gt(base_year)
        ]
        if source_rows.empty or source_rows[detail_col].nunique(dropna=True) < detail_minimum:
            continue
        selected_source = source_name
        projected = source_rows
        break
    if not selected_source:
        return df.iloc[0:0].copy(), ""

    active_groups = (
        projected.groupby(group_col, dropna=False)[value_col]
        .sum()
        .loc[lambda values: values.abs() > 1e-12]
        .index
    )
    projected = projected[projected[group_col].isin(active_groups)]
    historical = df[
        source_column.eq(comparison_source.casefold())
        & df["year"].le(base_year)
        & df[group_col].isin(active_groups)
    ]
    return pd.concat([historical, projected], ignore_index=True), selected_source


def area_chart_allowed_for_demand_coverage(
    page_key: str,
    area_df: pd.DataFrame,
    template: dict,
) -> bool:
    """Keep aggregate-placeholder demand overviews on a LEAP-backed frontier."""
    coverage_config = template.get("leap_demand_sector_coverage", {})
    placeholder_page_keys = {
        str(key)
        for key in coverage_config.get("show_aggregate_only_page_keys", [])
    }
    if str(page_key) not in placeholder_page_keys:
        return True

    primary_source = str(
        template.get("chart_generation", {}).get(
            "primary_area_source_system",
            "LEAP",
        )
    ).casefold()
    if "source_system" not in area_df.columns:
        return False
    return area_df["source_system"].astype(str).str.casefold().eq(primary_source).any()


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

    category_rows = work[["common_flow_label", "_flow_code", "_flow_name", "_is_boundary_adjusted"]].drop_duplicates()
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
    kept_categories = category_rows[category_rows["common_flow_label"].isin(replacements)]
    for _, category in kept_categories.iterrows():
        code = str(category["_flow_code"])
        if code and any(
            other != code and code_matches_prefix(code, other)
            for other in kept_categories["_flow_code"].astype(str)
        ):
            keep.loc[keep & (work["_flow_code"] == code)] = False

    result = work.loc[keep].copy()
    result["common_flow_label"] = result["common_flow_label"].map(replacements).fillna(result["common_flow_label"])
    return result.drop(columns=["_flow_code", "_flow_name", "_is_boundary_adjusted"])


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
            label = area_chart_flow_labels.get(prefix, node_label_for_prefix(nodes, prefix))
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
        return {"product": {}, "flow": {}, "plotting": {}}
    payload = load_json(CODE_COLORS_PATH)
    return {
        "product": dict(payload.get("product", {})),
        "flow": dict(payload.get("flow", {})),
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

    Colours are keyed by code rather than display name because a common label
    takes its name from the first component of its partition: a rollup change
    or a label override rewrites the name while the code span stays put. The
    lookup uses the first code of the expression (07.12-07.17 -> 07.12) and
    walks up the hierarchy, so an unseen sub-code inherits its family colour.
    """
    colors = load_code_colors().get(axis, {})
    code = canonical_code(code_or_label)
    while code:
        if code in colors:
            return colors[code]
        if "." not in code:
            break
        code = code.rsplit(".", 1)[0]
    text = str(code_or_label or "").strip()
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
        color = _TOTAL_SERIES_COLORS[source]
        trace.line.color = color
        trace.line.width = max(float(trace.line.width or 0), 2.25)
        if getattr(trace, "marker", None) is not None:
            trace.marker.color = color


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

    # Keep the historical comparison stack on the same category frontier as
    # the active LEAP projection stack.  ESTO can contain categories that are
    # absent or zero throughout the projection; showing those as empty bands
    # makes the legend look like a data series exists when it does not.
    projected_groups = (
        chart_df[
            (chart_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
            & (chart_df["scenario"].astype(str).str.casefold().isin({"reference", "target"}))
            & (chart_df["year"] > base_year)
        ]
        .groupby(group_col, dropna=False)["value"]
        .sum()
    )
    active_groups = projected_groups.loc[projected_groups.abs() > 1e-12].index
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
        group_df = (
            area_df.groupby([group_col, "year"], as_index=False)["value"].sum().sort_values([group_col, "year"])
        )
        for group_label, group in group_df.groupby(group_col, dropna=False):
            if not _has_nonzero_values(group["value"]):
                continue
            # Plotly stacks traces cumulatively in the order they're added,
            # regardless of sign - a positive (output) product added after
            # several negative (input) products would render below zero,
            # offset by the prior negative running total. Splitting into a
            # positive and a negative stackgroup gives each its own
            # from-zero baseline so outputs stack up and inputs stack down.
            group_sign = "neg" if group["value"].sum() < 0 else "pos"
            fig.add_trace(
                go.Scatter(
                    x=group["year"],
                    y=group["value"],
                    mode="lines",
                    stackgroup=f"scenario_{tag}_{group_sign}",
                    name=str(group_label),
                    visible=True if is_default else False,
                    hovertemplate="%{x}<br>Signed value: %{y:,.2f}" + chart_unit + "<extra>" + escape(str(group_label)) + "</extra>",
                )
            )
            trace_meta.append(trace_meta_entry(primary_source, scenario_name, True))

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
            "stacked_area_note": (
                f"Stacked areas: {dataset_display_name(comparison_source)} historical through "
                f"{base_year}; {dataset_display_name(primary_source)} projection after {base_year}."
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
    suppression_threshold = float(chart_config.get("suppression_threshold", 1.0))

    flow_section = non_parent_df.groupby("common_flow_label")["_section_label"].agg(lambda s: s.mode().iloc[0])
    section_flows: dict[str, list[str]] = {}
    for flow_label, section_label in flow_section.items():
        section_flows.setdefault(str(section_label), []).append(str(flow_label))

    ordered_sections: list[str] = []
    for flow_label in non_parent_df["common_flow_label"]:
        section_label = str(flow_section.get(flow_label, page_label))
        if section_label not in ordered_sections:
            ordered_sections.append(section_label)

    for section_label in ordered_sections:
        flow_labels = sorted(set(section_flows.get(section_label, [])))
        if not flow_labels:
            continue
        area_spec = {
            "aggregate_flow_prefix": "",
            "aggregate_flow_label": section_label,
            "source_flow_labels": flow_labels,
        }
        area_df = page_df[page_df["common_flow_label"].isin(flow_labels)]
        for group_col, group_noun, title_prefix, manifest_flow, manifest_product in (
            ("common_product_label", "product", "Aggregate by product", section_label, "All products"),
            ("common_flow_label", "flow", "Aggregate by flow", "All flows", section_label),
        ):
            chart_key = f"chart__area__section__{safe_slug(page_key)}__{safe_slug(section_label)}__{group_noun}"
            metrics = compute_ranking_metrics(area_df, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            suppressed = metrics["total_abs_value"] < suppression_threshold
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": section_label,
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
                "section_label": section_label,
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
    suppression_threshold = float(chart_config.get("suppression_threshold", 1.0))

    page_df = page_df.copy()
    if "component_flow_name" in page_df.columns:
        subflow_label = page_df["component_flow_name"].astype(str).str.strip()
        subflow_label = subflow_label.where(subflow_label != "", page_df["common_flow_label"])
    else:
        subflow_label = page_df["common_flow_label"]
    page_df["_subflow_label"] = subflow_label

    flow_section = non_parent_df.groupby("common_flow_label")["_section_label"].agg(lambda s: s.mode().iloc[0])

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
    proj_years = model.index[model.index > base_year].intersection(proj_comp.index)
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
    hist_diff_by_scenario: dict[str, pd.Series] | None = None,
    proj_diff_by_scenario: dict[str, pd.Series] | None = None,
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
    comparison_source: str = "ESTO",
    base_year: int | None = None,
) -> go.Figure:
    """Build a line chart for one common flow/product row.

    ``hist_diff_by_scenario``/``proj_diff_by_scenario`` map scenario name
    ("Reference"/"Target") to a diff series, so both scenarios' diff lines can
    be built and left for the client-side REF/TGT toggle to show/hide.
    """
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
            group = group[group["year"] >= base_year]
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
    for scenario_name, diff_series in (hist_diff_by_scenario or {}).items():
        if diff_series is None or diff_series.empty:
            continue
        diff_label = f"{primary_source} {scenario_name} minus comparison (hist)"
        fig.add_trace(
            go.Scatter(
                x=diff_series.index.tolist(),
                y=diff_series.values.tolist(),
                mode="lines",
                name=diff_label,
                visible="legendonly",
                line={"dash": "dot", "color": "#6b7280"},
                hovertemplate="%{x}<br>Diff: %{y:,.2f}" + chart_unit + "<extra>" + escape(diff_label) + "</extra>",
            )
        )
        trace_meta.append(trace_meta_entry(primary_source, scenario_name, "legendonly"))
    for scenario_name, diff_series in (proj_diff_by_scenario or {}).items():
        if diff_series is None or diff_series.empty:
            continue
        diff_label = f"{primary_source} {scenario_name} minus 9th (proj)"
        fig.add_trace(
            go.Scatter(
                x=diff_series.index.tolist(),
                y=diff_series.values.tolist(),
                mode="lines",
                name=diff_label,
                visible="legendonly",
                line={"dash": "dot", "color": "#f59e0b"},
                hovertemplate="%{x}<br>Diff: %{y:,.2f}" + chart_unit + "<extra>" + escape(diff_label) + "</extra>",
            )
        )
        trace_meta.append(trace_meta_entry(primary_source, scenario_name, "legendonly"))
    fig.update_layout(
        title=title_with_sign_note(f"{flow_label} - {product_label}", chart_df),
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        # Legend below the plot, not above: long product legends collide
        # with the title otherwise (see build_area_chart).
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={"trace_meta": trace_meta},
    )
    apply_chart_chrome(fig, base_year)
    return fig


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
  display:flex;align-items:center;gap:8px;justify-content:flex-end;
  flex:1 1 100%;flex-wrap:wrap;margin-left:0;min-width:0;
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
  padding: 6px 10px;
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
.header-nav-separator { color:#6b7280;font-weight:700;line-height:1.25;padding:6px 2px; }
.header-toggle {
  width: 30px; height: 30px;
  border: 1px solid #c5ccd3;
  border-radius: 999px;
  background: #fff;
  color: #0b3d5c;
  cursor: pointer;
}
.header-toggle-row { display:flex;justify-content:flex-end;margin-top:8px; }
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
.jump-chip {
  position:relative;display:inline-flex;align-items:center;gap:6px;
  padding:4px 9px;border:1px solid #c5ccd3;border-radius:999px;
  background:#fff;color:#0b3d5c;text-decoration:none;font-size:12px;line-height:1.25;
  box-shadow:0 1px 1px rgba(15,23,42,0.04);
}
.jump-chip::before { content:"";display:block;width:8px;height:8px;border-radius:999px;flex:0 0 auto;background:#94a3b8; }
.jump-chip[data-level="1"] { background:#fff4e6;border-color:#f2a65a;color:#7a3b00; }
.jump-chip[data-level="1"]::before { background:#f97316; }
.jump-chip[data-level="2"] { background:#f5edff;border-color:#c69af0;color:#4c1d70; }
.jump-chip[data-level="2"]::before { background:#9333ea; }
.visible-note { margin:8px 0 10px 0;padding:8px 12px;background:#fffbe6;border-left:3px solid #f0a500;border-radius:4px;font-size:13px;color:#5a3e00;line-height:1.5; }
.sort-bar {
  display:flex;flex-wrap:wrap;align-items:center;gap:6px;
  margin:10px 0 8px 0;font-size:12px;color:#4b5563;
}
.sort-bar-label { font-weight:600;white-space:nowrap; }
.sort-btn {
  padding:4px 10px;border:1px solid #c5ccd3;border-radius:999px;
  background:#fff;color:#0b3d5c;font-size:12px;cursor:pointer;
}
.sort-btn.active { border-color:#1f6feb;background:#e8f0fe;font-weight:700; }
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

  var renderPlot = function(plot) {
    if (plot.dataset.rendered === 'true' || plot.dataset.rendering === 'true') return;
    plot.dataset.rendering = 'true';
    setState(plot, 'Loading chart…', false);
    try {
      var bundle = bundleData;
      var chart = bundle && bundle.charts && bundle.charts[plot.dataset.chartKey];
      if (!chart) throw new Error('Missing chart: ' + plot.dataset.chartKey);
      window.Plotly.newPlot(plot, chart.data || [], chart.layout || {}, {responsive: true});
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

_SORT_JS = """
(function() {
  document.querySelectorAll('.sort-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var sortKey = btn.dataset.sort;
      var bar = btn.closest('.sort-bar');
      var grid = btn.closest('.section-sort-group').querySelector('[data-sortable-grid]');
      if (!grid) return;
      var cards = Array.from(grid.querySelectorAll(':scope > .chart-card'));
      if (sortKey === 'default') {
        cards.sort(function(a, b) { return parseInt(a.dataset.defaultOrder||0) - parseInt(b.dataset.defaultOrder||0); });
      } else {
        cards.sort(function(a, b) { return parseFloat(b.dataset[sortKey]||0) - parseFloat(a.dataset[sortKey]||0); });
      }
      cards.forEach(function(c) { grid.appendChild(c); });
      bar.querySelectorAll('.sort-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
    });
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
) -> dict[str, float]:
    """Compute sort ranking metrics for one flow/product chart.

    Uses ESTO as the comparison for years <= base_year and NINTH for years > base_year.
    Years where LEAP has no data are excluded from diff calculations rather than
    being treated as zero.
    """
    if pair_df.empty:
        return {"total_abs_value": 0.0, "abs_diff": 0.0, "pct_diff": 0.0}
    total_abs = float(pair_df["value"].abs().sum())
    by_year = pair_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    model = by_year[
        (by_year["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (by_year["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
    ].set_index("year")["value"]
    if model.empty:
        return {"total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0}

    hist_comparison = by_year[
        by_year["source_system"].astype(str).str.casefold() == comparison_source.casefold()
    ].groupby("year")["value"].mean()
    proj_comparison = by_year[
        by_year["source_system"].astype(str).str.casefold() == ninth_source.casefold()
    ].groupby("year")["value"].mean()

    hist_years = model.index[model.index <= base_year].intersection(hist_comparison.index)
    proj_years = model.index[model.index > base_year].intersection(proj_comparison.index)

    all_diff_years = hist_years.union(proj_years)
    if all_diff_years.empty:
        return {"total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0}

    diffs: list[pd.Series] = []
    comp_totals: list[float] = []
    if not hist_years.empty:
        diffs.append((model.loc[hist_years] - hist_comparison.loc[hist_years]).abs())
        comp_totals.append(float(hist_comparison.loc[hist_years].abs().sum()))
    if not proj_years.empty:
        diffs.append((model.loc[proj_years] - proj_comparison.loc[proj_years]).abs())
        comp_totals.append(float(proj_comparison.loc[proj_years].abs().sum()))

    abs_diff = float(pd.concat(diffs).sum()) if diffs else 0.0
    comp_total = sum(comp_totals)
    pct_diff = abs_diff / comp_total if comp_total > 1e-9 else 0.0
    return {"total_abs_value": total_abs, "abs_diff": abs_diff, "pct_diff": pct_diff}


def _section_anchor(page_label: str, section_label: str, subsection_label: str | None = None) -> str:
    """Generate a stable HTML anchor id for a page section or subsection."""
    anchor = "sec-" + safe_slug(page_label) + "__" + safe_slug(section_label)
    if subsection_label:
        anchor = anchor + "__" + safe_slug(subsection_label)
    return anchor


def _nav_chips_html(all_pages: list[dict], current_file: str) -> str:
    """Build page-navigation chip HTML."""
    overview = ["total_demand"]
    demand = ["buildings", "bunkers", "industry", "transport", "others", "non_energy"]
    transform = ["power", "refining", "other_transformation"]
    supply = ["supply"]
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
        '<label class="dashboard-switcher">'
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
        '<label class="category-basis-switcher">'
        '<span>Common categories</span>'
        f'<select data-navigation-select data-category-basis-switcher aria-label="Choose datasets defining the common categories">{"".join(options)}</select>'
        '</label>'
    )


_DATASET_DISPLAY_LABELS = {"NINTH": "Ninth"}

SHOW_DATASET_FILTER = True


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


def _jump_nav_html(page_label: str, section_tree: list[tuple[str, list[str]]]) -> str:
    """Build the section jump-navigation block.

    ``section_tree`` is an ordered list of (section_label, subsection_labels) pairs.
    The top-level section chips render on row 1; each section that has more than one
    subsection gets its own indented row directly beneath row 1, in section order, so a
    page with several subdivided sections ends up with rows 2, 3, 4... one per parent.
    """
    if not section_tree:
        return ""
    top_chips = "".join(
        f'<a href="#{_section_anchor(page_label, sl)}" class="jump-chip" data-level="1">{escape(sl)}</a>'
        for sl, _ in section_tree
    )
    rows = [f'<div class="jump-nav-row" data-level="1">{top_chips}</div>']
    for sl, subsection_labels in section_tree:
        if len(subsection_labels) < 2:
            continue
        sub_chips = "".join(
            f'<a href="#{_section_anchor(page_label, sl, sub)}" class="jump-chip" data-level="2">{escape(sub)}</a>'
            for sub in subsection_labels
        )
        rows.append(f'<div class="jump-nav-row" data-level="2">{sub_chips}</div>')
    return (
        f'<div class="jump-nav"><span class="jump-nav-label">Sections:</span>'
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
    grid_class = "dashboard-grid overview-grid" if len(area_rows) > 1 else "dashboard-grid expand-1"
    cards = []
    for i, row in enumerate(area_rows):
        caption = escape(str(row.get("title", "")))
        key = escape(row["chart_key"])
        cards.append(
            f'<figure class="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}" data-datasets="{escape(str(row.get("datasets", "")))}">'
            f'<figcaption class="chart-caption">{caption}</figcaption>'
            f'<div class="meta-subline">{escape(page_label)}</div>'
            f'<div class="area-data-note">{escape(str(row.get("stacked_area_note", "")))}</div>'
            f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
            f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{caption}"></div>'
            f'</figure>'
        )
    return (
        f'<section data-dataset-filter-section>'
        f'<h2 class="section-heading">Overview</h2>'
        f'<section class="section-sort-group">'
        f'<div class="sort-bar"><span class="sort-bar-label">Sort:</span>'
        f'<button class="sort-btn active" data-sort="default">Default</button>'
        f'<button class="sort-btn" data-sort="totalAbs">Largest total</button>'
        f'<button class="sort-btn" data-sort="absDiff">Largest difference</button>'
        f'<button class="sort-btn" data-sort="pctDiff">Largest % diff</button>'
        f'</div>'
        f'<div class="{grid_class}" data-sortable-grid="overview">{"".join(cards)}</div>'
        f'</section>'
        f'</section>'
    )


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
            f'<figure class="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}" data-datasets="{escape(str(row.get("datasets", "")))}">'
            f'<figcaption class="chart-caption">{product_name}</figcaption>'
            f'<div class="meta-subline">{escape(subline)}</div>'
            f'{area_note}'
            f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
            f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{product_name}"></div>'
            f'</figure>'
        )
    return "".join(cards)


def _sort_bar_html() -> str:
    return (
        '<div class="sort-bar"><span class="sort-bar-label">Sort:</span>'
        '<button class="sort-btn active" data-sort="default">Default</button>'
        '<button class="sort-btn" data-sort="totalAbs">Largest total</button>'
        '<button class="sort-btn" data-sort="absDiff">Largest difference</button>'
        '<button class="sort-btn" data-sort="pctDiff">Largest % diff</button>'
        '</div>'
    )


def line_section_tree(line_rows: list[dict]) -> list[tuple[str, list[str]]]:
    """Return ordered (section_label, subsection_labels) pairs for the jump nav.

    A section only gets subsections when it contains more than one distinct
    ``flow_group_label`` — sections that are already a single flow (e.g. Refining)
    stay flat rather than gaining a pointless one-item subsection row.
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
    return [(sl, subs if len(subs) > 1 else []) for sl, subs in tree]


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
    for section_label in seen:
        section_rows = [r for r in line_rows if str(r.get("section_label") or "Other") == section_label]
        anchor = _section_anchor(page_label, section_label)

        flow_groups: list[str] = []
        for row in section_rows:
            group = str(row.get("flow_group_label") or "").strip()
            if group and group not in flow_groups:
                flow_groups.append(group)

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
) -> None:
    """Write a polished HTML dashboard page with sticky header, lazy loading, and sorting."""
    page_label = str(page_config.get("page_label", "Dashboard"))
    page_file = output_path.name
    area_rows = [r for r in chart_rows if r.get("chart_type") == "stacked_area" and str(r.get("section_label")) == "Overview"]
    line_rows = [r for r in chart_rows if not (r.get("chart_type") == "stacked_area" and str(r.get("section_label")) == "Overview")]
    section_tree = line_section_tree(line_rows)

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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(page_label)}</title>
  <style>{_PAGE_CSS}</style>
</head>
<body>
  <div class="page-shell">
    <header class="page-header" id="page-header">
      <div class="header-collapsible">
      <div class="header-main-row">
        <div style="min-width:220px;flex:1 1 320px;">
          <h1 style="margin:0;font-size:24px;line-height:1.15;">{escape(page_label)}</h1>
          {f'<div class="dashboard-context">{economy_ctx}</div>' if economy_ctx else ""}
        </div>
        <div class="header-side-controls">
          {_SCENARIO_TOGGLE_HTML}
          {switcher_html}
          {category_basis_html}
          {dataset_filter_html}
          <div class="header-inline-controls">{nav_chips}</div>
        </div>
      </div>
      {jump_nav}
      </div>
      <div class="header-toggle-row">
        <button id="header-toggle" class="header-toggle" type="button" aria-expanded="true" aria-label="Collapse header">&#9652;</button>
      </div>
    </header>
    <main class="page-body">
      {note_html}
      {overview_html}
      {sections_html}
    </main>
  </div>
  <script>{_HEADER_TOGGLE_JS}</script>
  <script>{_DASHBOARD_SWITCHER_JS}</script>
  <script>{_SCENARIO_TOGGLE_JS}</script>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <script src="../chart_bundles/{escape(bundle_js_name)}"></script>
  <script>{_LAZY_LOAD_JS}</script>
  <script>{_SORT_JS}</script>
  <script>{_DATASET_FILTER_JS}</script>
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
  </style>
</head>
<body>
  <div class="shell">
    <div class="top-row">
      <div>
        <h1>Common ESTO Dashboard{economy_heading}</h1>
        {updated_html}
      </div>
      {switcher_html}
      {category_basis_html}
    </div>
    <p style="color:#4b5563;">Charts are generated automatically from common ESTO flow/product rows.</p>
    <ul>{cards}</ul>
    <div style="margin-top:32px;border-top:1px solid #d8dee4;padding-top:24px;">
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
      <p style="margin:0;color:#4b5563;font-size:13px;">Each rendered economy is a self-contained set of static files: this page,
      the other pages linked above, a <code>chart_bundles/</code> folder holding
      each page's chart data, and a <code>supporting_files/</code> folder holding
      the CSVs behind the charts. Pages load their charts from
      <code>chart_bundles/</code> by a relative path, so <strong>copying a single
      <code>.html</code> file on its own will open the page but its charts will not
      draw</strong> — copy the whole economy folder (or the whole
      <code>dashboards/</code> + <code>chart_bundles/</code> pair) together
      whenever sharing a rendered dashboard.</p>
    </div>
    <div style="margin-top:32px;border-top:1px solid #d8dee4;padding-top:24px;">
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
  <script>{_DASHBOARD_SWITCHER_JS}</script>
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


def _build_td_sector_chart(
    demand_df: pd.DataFrame,
    supply_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    sector_colors: dict[str, str],
    base_year: int | None = None,
) -> go.Figure:
    """Build the sector stack against the currently valid TFC total.

    TFC (Total Final Consumption) includes all demand sectors (codes 14-17).
    TFEC remains deliberately unavailable until non-energy use can be separated
    from aggregated Other-sector LEAP demand, so this chart must not calculate
    a visible-detail substitute for flow 13.

    supply_total = sum of signed values for codes 01, 02, 03
    (Production + Imports - Exports). Bunkers (04, 05) and stock changes (06)
    are excluded because they are not recorded in LEAP projection scenarios,
    making the supply line a valid comparison across the full time series.
    """
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
            group_col="_page_key",
            detail_col="_page_key",
        )
        # Keep the sector stack on the same non-overlapping parent/child
        # frontier as the authoritative TFC/TFEC totals.  Without this,
        # historical ESTO rows such as Buildings plus its Commercial and
        # Residential children are summed together, while the projected LEAP
        # side may contain only the parent row.
        return _non_overlapping_common_row_frontier(rows)

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
        projected_source_rows = _non_overlapping_common_row_frontier(projected_source_rows)
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
            group_sign = "neg" if sector_data["value"].sum() < 0 else "pos"
            trace_kw: dict = dict(
                x=sector_data["year"],
                y=sector_data["value"],
                mode="lines",
                stackgroup=f"demand_{scenario_toggle_tag(stack_source_name, scenario_name)}_{group_sign}",
                name=page_label,
                visible=True if is_default else False,
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(page_label) + "</extra>",
            )
            if color:
                trace_kw["line"] = {"color": color}
            fig.add_trace(go.Scatter(**trace_kw))
            trace_meta.append(trace_meta_entry(stack_source_name, scenario_name, True))

    # Explicit flow 12 is the reliable total. The displayed detail can contain
    # several valid hierarchy views and must not be added together.
    tfc_total_df = _select_total_rows_by_source(
        demand_df,
        overview_flow_df,
        flow_code="12",
    )

    # TFC demand totals, incl. primary LEAP scenarios: the sector stack above
    # is split into pos/neg stackgroups when sectors have mixed signs, so it
    # no longer shows a single net total line on its own.
    tfc_totals = tfc_total_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in tfc_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " (TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    # Supply total lines — always visible regardless of TFC/TFEC mode
    if not supply_df.empty:
        for (src, scen), grp in supply_df.groupby(["source_system", "scenario"]):
            if not _has_nonzero_values(grp["value"]):
                continue
            lbl = series_label_from_values(src, scen, series_labels) + " supply (01–03)"
            grp_sorted = grp.sort_values("year")
            fig.add_trace(go.Scatter(
                x=grp_sorted["year"], y=grp_sorted["value"],
                mode="lines", name=lbl, line={"dash": "dot"},
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
            ))
            trace_meta.append(trace_meta_entry(src, scen, True, "both"))

    fig.update_layout(
        title="Supply vs Demand by sector (TFC)",
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 100, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": stacked_area_dataset_note(stacked_sources, "demand"),
        },
    )
    apply_chart_chrome(fig, base_year)
    return fig


def _build_td_fuel_chart(
    demand_df: pd.DataFrame,
    supply_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    base_year: int | None = None,
) -> go.Figure:
    """Stacked-area chart by fuel across all demand sectors (TFC), with supply line."""
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
        return _non_overlapping_common_row_frontier(rows)

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
        scenario_df = _non_overlapping_common_row_frontier(scenario_df)
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
            group_sign = "neg" if grp["value"].sum() < 0 else "pos"
            fig.add_trace(go.Scatter(
                x=grp["year"], y=grp["value"],
                mode="lines", stackgroup=f"demand_{scenario_toggle_tag(stack_source_name, scenario_name)}_{group_sign}", name=lbl,
                visible=True if is_default else False,
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
            ))
            trace_meta.append(trace_meta_entry(stack_source_name, scenario_name, True))

    # Use the same authoritative aggregate policy as the sector chart.
    tfc_total_df = _select_total_rows_by_source(
        demand_df,
        overview_flow_df,
        flow_code="12",
    )

    # Demand total lines, incl. primary LEAP scenarios (see note in
    # _build_td_sector_chart on why the stacked fuel breakdown alone doesn't
    # show a single net total when fuels have mixed signs).
    comp_totals = tfc_total_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in comp_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " total (TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    # Supply total lines
    if not supply_df.empty:
        supply_totals = supply_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
        for (src, scen), grp in supply_totals.groupby(["source_system", "scenario"]):
            if not _has_nonzero_values(grp["value"]):
                continue
            lbl = series_label_from_values(src, scen, series_labels) + " supply (01–03)"
            fig.add_trace(go.Scatter(
                x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
                mode="lines", name=lbl, line={"dash": "dot"},
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
            ))
            trace_meta.append(trace_meta_entry(src, scen, True))

    fig.update_layout(
        title="Supply vs Demand by fuel (TFC)",
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": stacked_area_dataset_note(stacked_sources, "fuel"),
        },
    )
    apply_chart_chrome(fig, base_year, code_axis="product")
    return fig


def _build_supply_stack_chart(
    supply_detail_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    overview_flow_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    group_col: str,
    chart_title: str,
    base_year: int | None = None,
) -> go.Figure:
    """Stacked-area chart of supply (TPES) split by `group_col`, with a demand total line.

    Mirrors _build_td_fuel_chart with roles reversed: supply is the stacked series
    and demand is the comparison total line. `group_col` is "common_flow_label" for
    a by-component (Production/Imports/Exports, ...) breakdown or
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
        group_by_year = scenario_df.groupby([group_col, "year"], as_index=False)["value"].sum()
        for group_value in group_totals:
            grp = group_by_year[group_by_year[group_col] == group_value].sort_values("year")
            if grp.empty:
                continue
            if not _has_nonzero_values(grp["value"]):
                continue
            lbl = str(group_value)
            group_sign = "neg" if grp["value"].sum() < 0 else "pos"
            fig.add_trace(go.Scatter(
                x=grp["year"], y=grp["value"],
                mode="lines", stackgroup=f"supply_{scenario_toggle_tag(stack_source_name, scenario_name)}_{group_sign}", name=lbl,
                visible=True if is_default else False,
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
            ))
            trace_meta.append(trace_meta_entry(stack_source_name, scenario_name, True))

    # Supply total lines, incl. primary LEAP scenarios (see note in
    # _build_td_sector_chart on why the stacked breakdown alone doesn't show
    # a single net total when components have mixed signs).
    comp_totals = supply_detail_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in comp_totals.groupby(["source_system", "scenario"]):
        if not _has_nonzero_values(grp["value"]):
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " supply total"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(src, scen, True))

    # Demand total lines. Explicit flow 12 also carries LEAP demand when an
    # economy is still modelled through the All demand aggregated placeholder.
    demand_total_df = _select_total_rows_by_source(
        demand_df,
        overview_flow_df,
        flow_code="12",
    )
    if not demand_total_df.empty:
        demand_totals = demand_total_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
        for (src, scen), grp in demand_totals.groupby(["source_system", "scenario"]):
            if not _has_nonzero_values(grp["value"]):
                continue
            lbl = series_label_from_values(src, scen, series_labels) + " demand (TFC)"
            fig.add_trace(go.Scatter(
                x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
                mode="lines", name=lbl, line={"dash": "dot"},
                hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(lbl) + "</extra>",
            ))
            trace_meta.append(trace_meta_entry(src, scen, True))

    fig.update_layout(
        title=chart_title,
        xaxis_title="Year",
        yaxis_title=f"Signed energy ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={
            "trace_meta": trace_meta,
            "stacked_area_note": stacked_area_dataset_note(stacked_sources, "supply"),
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


def _build_transformation_total_chart(
    transformation_df: pd.DataFrame,
    series_labels: dict[str, str],
    base_year: int | None = None,
) -> go.Figure:
    """Build the signed no-transfers transformation total comparison."""
    chart_unit = _chart_unit(transformation_df)
    fig = go.Figure()
    trace_meta: list[dict] = []
    totals = transformation_df.groupby(
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
            hovertemplate="%{x}<br>%{y:,.2f}" + chart_unit + "<extra>" + escape(label) + "</extra>",
        ))
        trace_meta.append(trace_meta_entry(source_system, scenario, True))
    fig.update_layout(
        title="Total transformation sector (excluding transfers)",
        xaxis_title="Year",
        yaxis_title=f"Signed energy balance ({chart_unit})",
        margin={"l": 64, "r": 28, "t": 84, "b": 160},
        legend={"orientation": "h", "yanchor": "top", "y": -0.20, "xanchor": "left", "x": 0},
        meta={"trace_meta": trace_meta},
    )
    apply_chart_chrome(fig, base_year)
    return fig


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
) -> tuple[list[dict], dict | None]:
    """Build the total demand summary page (config-driven bespoke page).

    Generates aggregate balance-check comparison charts:
    - Supply vs Demand by sector: demand stacked by demand page group, TFC/TFEC
      dropdown, with a supply total line overlaid
    - Supply vs Demand by fuel: demand stacked by common_product_label, with a
      supply total line overlaid
    - Demand vs Supply by component: supply (total_demand_page.supply_codes)
      stacked by common_flow_label (Production/Imports/Exports/...), with a
      demand total line overlaid. Adding codes to supply_codes (e.g. bunkers
      04/05) automatically adds new stacked series here.
    - Demand vs Supply by fuel: supply stacked by common_product_label, with a
      demand total line overlaid
    - Total transformation excluding transfers, when configured rollup metadata exists

    The first two charts include a supply total line defined as:
        supply_total = sum of signed values for codes 01, 02, 03
        (Production + Imports - Exports)

    Bunkers (04, 05) and stock changes (06) are excluded from the supply line
    because they are not modelled in LEAP projection scenarios, ensuring the
    supply line is a valid comparison across both historical and projection years.

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
        "demand_page_keys", ["industry", "transport", "buildings", "others", "non_energy"]
    )]
    supply_codes = [str(c) for c in config.get("supply_codes", ["01", "02", "03"])]
    sector_colors: dict[str, str] = config.get("sector_colors", {
        "industry": "#3b82f6",
        "transport": "#f97316",
        "buildings": "#10b981",
        "others": "#8b5cf6",
        "non_energy": "#94a3b8",
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
    supply_df = (
        supply_detail_df
        .groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    )

    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    demand_total_abs = float(demand_df["value"].abs().sum())
    chart_specs: list[dict] = [
        {
            "chart_key": "chart__area__total_demand__sector",
            "title": "Supply vs Demand by sector",
            "build": lambda: _build_td_sector_chart(demand_df, supply_df, overview_flow_df, series_labels, primary_source, primary_scenario, sector_colors, base_year=base_year),
            "total_abs": demand_total_abs,
            "row_count": len(demand_df),
            "source_flow_labels": "; ".join(demand_page_keys),
        },
        {
            "chart_key": "chart__area__total_demand__fuel",
            "title": "Supply vs Demand by fuel",
            "build": lambda: _build_td_fuel_chart(demand_df, supply_df, overview_flow_df, series_labels, primary_source, primary_scenario, base_year=base_year),
            "total_abs": demand_total_abs,
            "row_count": len(demand_df),
            "source_flow_labels": "; ".join(demand_page_keys),
        },
    ]
    if not supply_detail_df.empty:
        supply_total_abs = float(supply_detail_df["value"].abs().sum())
        chart_specs.append({
            "chart_key": "chart__area__total_demand__supply_component",
            "title": "Demand vs Supply by component",
            "build": lambda: _build_supply_stack_chart(
                supply_detail_df, demand_df, overview_flow_df, series_labels, primary_source, primary_scenario,
                group_col="common_flow_label", chart_title="Demand vs Supply by component", base_year=base_year,
            ),
            "total_abs": supply_total_abs,
            "row_count": len(supply_detail_df),
            "source_flow_labels": "; ".join(supply_codes),
        })
        chart_specs.append({
            "chart_key": "chart__area__total_demand__supply_fuel",
            "title": "Demand vs Supply by fuel",
            "build": lambda: _build_supply_stack_chart(
                supply_detail_df, demand_df, overview_flow_df, series_labels, primary_source, primary_scenario,
                group_col="common_product_label", chart_title="Demand vs Supply by fuel", base_year=base_year,
            ),
            "total_abs": supply_total_abs,
            "row_count": len(supply_detail_df),
            "source_flow_labels": "; ".join(supply_codes),
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
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
            "datasets": chart_dataset_tokens_from_figure(fig),
            "stacked_area_note": stacked_area_note_from_figure(fig),
        })
        manifest_rows.append({
            "page_key": "total_demand", "page_label": page_label,
            "section_label": "Overview", "chart_type": "stacked_area",
            "chart_key": chart_key, "common_flow_label": title,
            "common_product_label": "All", "row_count": int(spec["row_count"]),
            "source_flow_labels": spec["source_flow_labels"],
            "sign_note": "", "suppressed": False,
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
            "diff_hist_json": "", "diff_proj_json": "",
        })

    transformation_config = config.get("transformation_total", {})
    if transformation_config.get("enabled", False):
        transformation_df = select_transformation_total_rows(assigned_df, transformation_config)
        if not transformation_df.empty:
            chart_key = "chart__line__total_transformation_no_transfers"
            title = "Total transformation sector (excluding transfers)"
            transformation_figure = _build_transformation_total_chart(
                transformation_df, series_labels, base_year=base_year
            )
            charts[chart_key] = transformation_figure
            total_abs = float(transformation_df["value"].abs().sum())
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "line",
                "title": title,
                "product_label": title,
                "section_label": "Overview",
                "total_abs_value": total_abs,
                "abs_diff": 0.0,
                "pct_diff": 0.0,
                "datasets": chart_dataset_tokens_from_figure(transformation_figure),
            })
            manifest_rows.append({
                "page_key": "total_demand",
                "page_label": page_label,
                "section_label": "Overview",
                "chart_type": "line",
                "chart_key": chart_key,
                "common_flow_label": title,
                "common_product_label": "All products",
                "row_count": int(len(transformation_df)),
                "source_flow_labels": str(transformation_config.get("source_aggregate_label", "")),
                "sign_note": "Signed total: transformation inputs are negative and outputs are positive.",
                "suppressed": False,
                "total_abs_value": total_abs,
                "abs_diff": 0.0,
                "pct_diff": 0.0,
                "diff_hist_json": "",
                "diff_proj_json": "",
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

    bundle_name = "total_demand__charts.json"
    write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
    write_dashboard_page(
        {"page_key": "total_demand", "page_label": page_label},
        chart_rows=chart_rows,
        bundle_js_name=bundle_name.replace(".json", ".js"),
        output_path=layout["dashboards"] / "total_demand.html",
        all_pages=all_pages,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
        dashboard_updated_label=dashboard_updated_label,
        **category_basis_ui_kwargs(template),
    )
    page_row = {
        "file": "total_demand.html", "label": page_label,
        "area_chart_count": sum(row["chart_type"] == "stacked_area" for row in chart_rows),
        "summary_chart_count": 0,
        "line_chart_count": sum(row["chart_type"] == "line" for row in chart_rows),
    }
    return manifest_rows, page_row


def _configured_scope_page_mask(df: pd.DataFrame, scope_page: dict) -> pd.Series:
    """Return rows matching a scope-specific page config."""
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
            hist_diff_by_scenario=hist_diff_by_scenario,
            proj_diff_by_scenario=proj_diff_by_scenario,
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
        page_file = f"{page_key}.html"
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


def drop_excluded_flow_rows(df: pd.DataFrame, excluded_flow_code_prefixes: list[object]) -> pd.DataFrame:
    """Drop rows whose common flow code matches a configured exclusion prefix.

    Applies only to ``measure == "energy"`` rows: the exclusion list encodes
    energy-balance identity rules (supply/TFC/TFEC), which do not mean
    anything for a non-energy series. A frame without a ``measure`` column is
    treated as all-energy, matching behaviour before that column existed.
    """
    if df.empty or not excluded_flow_code_prefixes:
        return df
    is_energy = (
        df["measure"].astype(str).eq("energy")
        if "measure" in df.columns
        else pd.Series(True, index=df.index)
    )
    excluded_mask = is_energy & df["common_flow_code"].apply(
        lambda value: code_expression_matches_any_prefix(value, excluded_flow_code_prefixes)
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
    df = _keep_one_measure_for_energy_balance_charts(df)
    df = drop_esto_post_base_year_rows(df, comparison_source, base_year)
    df = drop_excluded_flow_rows(df, excluded_flow_code_prefixes)
    if scope_df is not None:
        scope_df = _keep_one_measure_for_energy_balance_charts(scope_df)
        scope_df = drop_esto_post_base_year_rows(scope_df, comparison_source, base_year)
        scope_df = drop_excluded_flow_rows(scope_df, excluded_flow_code_prefixes)
    routing_special_cases = template.get("routing_special_cases", [])
    assigned_df = assign_pages(df, page_rules, routing_special_cases)
    assigned_df = assign_bespoke_overview_rows(
        assigned_df,
        template.get("total_demand_page", {}),
    )
    page_summary_df = build_page_assignment_summary(assigned_df)
    page_summary_df.to_csv(layout["supporting"] / "page_assignment_summary.csv", index=False)

    # First pass: build page inventory (needed for navigation chips on every page).
    page_meta = assigned_df[["_page_key", "_page_label"]].drop_duplicates().sort_values("_page_key")
    page_inventory: list[dict] = []
    # Add the synthetic total demand page first so it appears in nav on all other pages.
    if template.get("total_demand_page", {}).get("enabled", False):
        overview_label = str(
            template.get("total_demand_page", {}).get("page_label", "Energy balance overview")
        )
        page_inventory.append({"page_key": "total_demand", "page_label": overview_label, "file": "total_demand.html"})
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
            page_inventory.append({"page_key": page_key, "page_label": page_label, "file": f"{page_key}.html"})

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
                    "file": f"{scope_page_key}.html",
                })

    # The Emissions page is derived from the demand pages above, so it must be
    # in the inventory before any page renders its navigation chips.
    if emissions_page_enabled(template, assigned_df):
        emissions_config = template.get("emissions_page", {})
        emissions_page_key = safe_slug(emissions_config.get("page_key", "emissions"))
        page_inventory.append({
            "page_key": emissions_page_key,
            "page_label": str(emissions_config.get("page_label", "Emissions")),
            "file": f"{emissions_page_key}.html",
        })

    for page in additional_pages or []:
        page_key = safe_slug(page.get("page_key", ""))
        if page_key and page_key not in {item["page_key"] for item in page_inventory}:
            page_inventory.append({
                "page_key": page_key,
                "page_label": str(page.get("page_label", page_key)),
                "file": str(page.get("file", f"{page_key}.html")),
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
    suppression_threshold = float(chart_config.get("suppression_threshold", 1.0))

    for page_info in page_inventory:
        page_key = page_info["page_key"]
        page_label = page_info["page_label"]
        # Bespoke pages own their complete bundle and manifest. They must not
        # first pass through the generic builder and then overwrite its files.
        if page_key == "total_demand":
            continue
        page_df = assigned_df[assigned_df["_page_key"].apply(safe_slug) == page_key].copy()
        if page_df.empty:
            continue

        charts: dict[str, go.Figure] = {}
        chart_rows: list[dict] = []

        for area_spec in pick_area_specs(page_df, template):
            chart_key = f"chart__area__{safe_slug(area_spec['aggregate_flow_prefix'])}__{safe_slug(area_spec['aggregate_flow_label'])}"
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
                "common_flow_label": area_spec["aggregate_flow_label"],
                "common_product_label": "All products",
                "row_count": int(len(area_df)),
                "source_flow_labels": "; ".join(area_spec["source_flow_labels"]),
                "sign_note": sign_note_for_chart(area_df),
                "suppressed": suppressed,
                **metrics,
            })
            if suppressed:
                continue
            figure = build_area_chart(page_df, area_spec, series_labels, template)
            if not figure.data:
                manifest_rows[-1]["suppressed"] = True
                continue
            charts[chart_key] = figure
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": str(area_spec["aggregate_flow_label"]),
                "product_label": str(area_spec["aggregate_flow_label"]),
                "section_label": "Overview",
                "datasets": chart_dataset_tokens_from_figure(figure),
                "stacked_area_note": stacked_area_note_from_figure(figure),
                **metrics,
            })

        flow_nodes = get_existing_flow_nodes(page_df)
        all_canonical = set(flow_nodes["canonical_code"].astype(str))
        parent_flow_labels: set[str] = set()
        for _, node in flow_nodes.iterrows():
            code = str(node["canonical_code"])
            if code and any(c.startswith(code + ".") for c in all_canonical if c != code):
                parent_flow_labels.add(str(node["common_flow_label"]))

        # Section aggregate charts: two per section (by product, by flow), summing all non-parent flows.
        section_charts, section_chart_rows, section_manifest_rows = _build_section_aggregate_charts(
            page_df, page_key, page_label, parent_flow_labels, template, series_labels,
        )
        charts.update(section_charts)
        chart_rows.extend(section_chart_rows)
        manifest_rows.extend(section_manifest_rows)

        # Subsection aggregate charts: two per flow-group subsection (by product, by sub-flow).
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
                hist_diff_by_scenario=hist_diff_by_scenario, proj_diff_by_scenario=proj_diff_by_scenario,
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
                "datasets": chart_dataset_tokens_from_figure(chart_figure),
                **metrics,
            })

        if not charts:
            continue
        bundle_name = f"{page_key}__charts.json"
        write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
        page_file = f"{page_key}.html"
        write_dashboard_page(
            {"page_key": page_key, "page_label": page_label},
            chart_rows=chart_rows,
            bundle_js_name=bundle_name.replace(".json", ".js"),
            output_path=layout["dashboards"] / page_file,
            all_pages=page_inventory,
            economy_label=economy_label,
            dashboard_switcher=dashboard_switcher,
            current_dashboard=current_dashboard,
            dashboard_updated_label=dashboard_updated_label,
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
    )
    manifest_rows.extend(td_manifest_rows)
    if td_page_row:
        page_rows.append(td_page_row)

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
    manifest_df = pd.DataFrame(manifest_rows)
    active_scope = str(template.get("_active_comparison_scope", "")).strip()
    if active_scope and "comparison_scope" not in manifest_df.columns:
        manifest_df.insert(0, "comparison_scope", active_scope)
    manifest_df.to_csv(layout["supporting"] / "chart_manifest.csv", index=False)
    return manifest_df

#%%
