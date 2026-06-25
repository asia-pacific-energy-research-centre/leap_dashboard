#%%
"""Render a static dashboard from common ESTO comparison data."""

#%%
import json
import re
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder


CODE_MATCH_COLUMNS = [
    "common_flow_code",
    "common_flow_label",
    "component_flow_code",
    "component_esto_flow",
    "component_flow_name",
]

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


def series_label(row: pd.Series, series_labels: dict[str, str]) -> str:
    """Return a display label for a source/scenario series."""
    return series_label_from_values(row["source_system"], row["scenario"], series_labels)


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


def assign_pages(df: pd.DataFrame, page_rules: list[dict]) -> pd.DataFrame:
    """Assign each row to the first matching sector page and record the rule used."""
    out = df.copy()
    out["_page_key"] = "unassigned"
    out["_page_label"] = "Unassigned"
    out["_section_key"] = "unassigned"
    out["_section_label"] = "Unassigned"
    out["_page_rule_priority"] = ""
    out["_page_rule_note"] = "No sector/page recogniser matched this generated flow label or component code."
    remaining = pd.Series(True, index=out.index)
    for rule in sorted_page_rules(page_rules):
        mask = rule_mask(out, rule) & remaining
        page_key = str(rule.get("page_key", "page"))
        page_label = str(rule.get("page_label", rule.get("page_key", "Page")))
        out.loc[mask, "_page_key"] = page_key
        out.loc[mask, "_page_label"] = page_label
        out.loc[mask, "_section_key"] = str(rule.get("section_key", page_key))
        out.loc[mask, "_section_label"] = str(rule.get("section_label", page_label))
        out.loc[mask, "_page_rule_priority"] = str(rule.get("priority", ""))
        out.loc[mask, "_page_rule_note"] = str(rule.get("rule_note", ""))
        remaining = remaining & ~mask
    return out


def build_page_assignment_summary(assigned_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise how generated/common rows were assigned to dashboard pages."""
    if assigned_df.empty:
        return pd.DataFrame()
    group_columns = [
        "_page_key",
        "_page_label",
        "_section_key",
        "_section_label",
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


def frontier_flow_labels(nodes: pd.DataFrame, parent_prefix: str, target_level: int) -> list[str]:
    """Return flow labels that form a non-double-counting frontier under a prefix."""
    subtree = nodes[nodes["canonical_code"].astype(str).apply(lambda value: value == parent_prefix or value.startswith(parent_prefix + "."))].copy()
    if subtree.empty:
        return []

    exact_at_target = subtree[subtree["canonical_code"].apply(lambda value: len(str(value).split(".")) == target_level)].copy()
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


def pick_area_specs(page_df: pd.DataFrame, template: dict) -> list[dict[str, object]]:
    """Choose aggregate area charts from the flow hierarchy."""
    nodes = get_existing_flow_nodes(page_df)
    if nodes.empty:
        return []
    chart_config = template.get("chart_generation", {})
    deep_min_depth = int(chart_config.get("deep_chain_min_depth", 3))
    max_depth = int(nodes["depth"].max())
    level_count = 2 if max_depth >= deep_min_depth else 1
    level_count = int(chart_config.get("top_levels_for_deep_chains", level_count)) if max_depth >= deep_min_depth else int(chart_config.get("top_levels_for_other_chains", level_count))
    max_area_charts = int(chart_config.get("max_area_charts_per_page", 30))

    specs: list[dict[str, object]] = []
    used_group_keys: set[tuple[int, str]] = set()
    for level in range(1, level_count + 1):
        prefixes = sorted({code_prefix(code, level) for code in nodes["canonical_code"] if code_prefix(code, level)})
        for prefix in prefixes:
            group_key = (level, prefix)
            if group_key in used_group_keys:
                continue
            labels = frontier_flow_labels(nodes, prefix, level + 1 if level == 1 else level)
            if not labels:
                continue
            label = node_label_for_prefix(nodes, prefix)
            specs.append(
                {
                    "area_level": level,
                    "aggregate_flow_prefix": prefix,
                    "aggregate_flow_label": label,
                    "source_flow_labels": labels,
                }
            )
            used_group_keys.add(group_key)
            if len(specs) >= max_area_charts:
                return specs
    return specs


def area_source_priority(df: pd.DataFrame, template: dict) -> tuple[str, str] | None:
    """Pick the source/scenario to use as stacked-area bars."""
    chart_config = template.get("chart_generation", {})
    preferred = (
        str(chart_config.get("primary_area_source_system", "LEAP")),
        str(chart_config.get("primary_area_scenario", "Target")),
    )
    available = {
        (str(source), str(scenario))
        for source, scenario in df[["source_system", "scenario"]].drop_duplicates().itertuples(index=False, name=None)
    }
    for candidate in [preferred, ("LEAP", "Reference"), ("NINTH", "Target"), ("NINTH", "Reference"), ("ESTO", "historical")]:
        for source, scenario in available:
            if source.casefold() == candidate[0].casefold() and scenario.casefold() == candidate[1].casefold():
                return source, scenario
    return next(iter(sorted(available))) if available else None


def build_area_chart(
    df: pd.DataFrame,
    area_spec: dict[str, object],
    series_labels: dict[str, str],
    template: dict,
) -> go.Figure:
    """Build a stacked product area chart with dataset-comparison total lines."""
    source_flow_labels = [str(value) for value in area_spec["source_flow_labels"]]
    chart_df = df[df["common_flow_label"].isin(source_flow_labels)].copy()
    primary = area_source_priority(chart_df, template)
    fig = go.Figure()
    if primary is not None:
        primary_source, primary_scenario = primary
        primary_df = chart_df[
            (chart_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
            & (chart_df["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
        ].copy()
        product_df = (
            primary_df.groupby(["common_product_label", "year"], as_index=False)["value"].sum().sort_values(["common_product_label", "year"])
        )
        for product_label, group in product_df.groupby("common_product_label", dropna=False):
            fig.add_trace(
                go.Scatter(
                    x=group["year"],
                    y=group["value"],
                    mode="lines",
                    stackgroup="one",
                    name=str(product_label),
                    hovertemplate="%{x}<br>Signed value: %{y:,.2f} PJ<extra>" + escape(str(product_label)) + "</extra>",
                )
            )
    total_df = (
        chart_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum().sort_values(["source_system", "scenario", "year"])
    )
    for (source_system, scenario), group in total_df.groupby(["source_system", "scenario"], dropna=False):
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
    fig.update_layout(
        title=title_with_sign_note(f"Aggregate by product: {area_spec['aggregate_flow_label']}", chart_df),
        xaxis_title="Year",
        yaxis_title="Signed energy (PJ)",
        margin={"l": 64, "r": 28, "t": 56, "b": 72},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    return fig


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


def build_product_chart(
    chart_df: pd.DataFrame,
    flow_label: str,
    product_label: str,
    series_labels: dict[str, str],
    *,
    hist_diff: pd.Series | None = None,
    proj_diff: pd.Series | None = None,
    primary_source: str = "LEAP",
    primary_scenario: str = "Target",
) -> go.Figure:
    """Build a line chart for one common flow/product row."""
    fig = go.Figure()
    for (_source_system, _scenario), group in chart_df.groupby(["source_system", "scenario"], dropna=False):
        group = group.sort_values("year")
        label = series_label(group.iloc[0], series_labels)
        customdata = None
        hovertemplate = "%{x}<br>Signed value: %{y:,.2f} PJ<extra>" + escape(label) + "</extra>"
        if {"sign_status", "sign_interpretation"}.issubset(set(group.columns)):
            customdata = group[["sign_status", "sign_interpretation"]].astype(str).values
            hovertemplate = (
                "%{x}<br>Signed value: %{y:,.2f} PJ"
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
    if hist_diff is not None and not hist_diff.empty:
        diff_label = f"{primary_source} {primary_scenario} minus comparison (hist)"
        fig.add_trace(
            go.Scatter(
                x=hist_diff.index.tolist(),
                y=hist_diff.values.tolist(),
                mode="lines",
                name=diff_label,
                visible="legendonly",
                line={"dash": "dot", "color": "#6b7280"},
                hovertemplate="%{x}<br>Diff: %{y:,.2f} PJ<extra>" + escape(diff_label) + "</extra>",
            )
        )
    if proj_diff is not None and not proj_diff.empty:
        diff_label = f"{primary_source} {primary_scenario} minus 9th (proj)"
        fig.add_trace(
            go.Scatter(
                x=proj_diff.index.tolist(),
                y=proj_diff.values.tolist(),
                mode="lines",
                name=diff_label,
                visible="legendonly",
                line={"dash": "dot", "color": "#f59e0b"},
                hovertemplate="%{x}<br>Diff: %{y:,.2f} PJ<extra>" + escape(diff_label) + "</extra>",
            )
        )
    fig.update_layout(
        title=title_with_sign_note(f"{flow_label} - {product_label}", chart_df),
        xaxis_title="Year",
        yaxis_title="Signed energy (PJ)",
        margin={"l": 64, "r": 28, "t": 56, "b": 72},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
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
  flex:0 0 auto;flex-wrap:nowrap;margin-left:auto;
}
.dashboard-context { margin-top:6px;color:#4b5563;font-size:13px;line-height:1.35; }
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
.dashboard-grid {
  display:grid;
  grid-template-columns:repeat(4, minmax(0, 1fr));
  gap:12px;
  align-items:start;
}
.dashboard-grid.expand-1 { grid-template-columns:minmax(0, 1fr); }
.dashboard-grid.expand-2 { grid-template-columns:repeat(2, minmax(0, 1fr)); }
.dashboard-grid.expand-3 { grid-template-columns:repeat(3, minmax(0, 1fr)); }
.chart-card { margin:0;padding:10px;border:1px solid #d0d7de;border-radius:8px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,0.05); }
.chart-caption { font-weight:600;margin-bottom:4px; }
.meta-subline { margin-top:-4px;margin-bottom:8px;color:#4b5563;font-size:12px; }
.chart-load-state { min-height:22px;margin:4px 0 6px 0;color:#64748b;font-size:12px; }
.chart-load-state[data-loaded="true"] { display:none; }
.lazy-chart-plot {
  width:100%;height:clamp(380px, 62vh, 1100px);
  border:1px solid #d0d7de;border-radius:6px;background:#fff;display:block;box-sizing:border-box;
}
.lazy-chart-plot.is-unloaded { background:#f8fafc; }
.section-heading { margin:18px 0 8px 0;font-size:var(--section-title-size);color:#23384d; }
@media (max-width: 900px) { .dashboard-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .dashboard-grid { grid-template-columns:minmax(0, 1fr); } .lazy-chart-plot { height:420px; } }
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
  document.querySelectorAll('[data-dashboard-switcher]').forEach(function(select) {
    select.addEventListener('change', function() {
      var href = select.value;
      if (href) window.location.href = href;
    });
  });
})();
"""


def write_chart_bundle(charts: dict[str, go.Figure], output_path: Path) -> None:
    """Write a page-level Plotly chart bundle as JSON and JS."""
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


def _section_anchor(page_label: str, section_label: str) -> str:
    """Generate a stable HTML anchor id for a page section."""
    return "sec-" + safe_slug(page_label) + "__" + safe_slug(section_label)


def _nav_chips_html(all_pages: list[dict], current_file: str) -> str:
    """Build page-navigation chip HTML."""
    demand = ["total_demand", "buildings", "bunkers", "industry", "transport", "others", "non_energy"]
    transform = ["power", "refining", "other_transformation"]
    supply = ["supply"]
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

    parts: list[str] = []
    for key in demand:
        h = chip(key)
        if h:
            parts.append(h)
    sep = '<span class="header-nav-separator" aria-hidden="true">|</span>'
    transform_chips = [chip(k) for k in transform if chip(k)]
    if transform_chips:
        parts.append(sep)
        parts.extend(transform_chips)
    supply_chips = [chip(k) for k in supply if chip(k)]
    if supply_chips:
        parts.append(sep)
        parts.extend(supply_chips)
    remaining_keys = {p["page_key"] for p in all_pages} - set(demand + transform + supply)
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


def _dashboard_switcher_html(dashboards: list[dict[str, str]], current_dashboard: str, current_file: str) -> str:
    """Build a static cross-dashboard switcher for matching page filenames."""
    if len(dashboards) <= 1:
        return ""

    options: list[str] = []
    for item in dashboards:
        dashboard_key = item["dashboard_key"]
        label = item["label"]
        href = current_file if dashboard_key == current_dashboard else f"../../{escape(dashboard_key)}/dashboards/{escape(current_file)}"
        selected = " selected" if dashboard_key == current_dashboard else ""
        options.append(f'<option value="{href}"{selected}>{escape(label)}</option>')

    return (
        '<label class="dashboard-switcher">'
        '<span>Dashboard</span>'
        f'<select data-dashboard-switcher aria-label="Switch dashboard">{"".join(options)}</select>'
        '</label>'
    )


def _jump_nav_html(page_label: str, section_labels: list[str]) -> str:
    """Build the section jump-navigation block."""
    if not section_labels:
        return ""
    chips = "".join(
        f'<a href="#{_section_anchor(page_label, sl)}" class="jump-chip" data-level="1">{escape(sl)}</a>'
        for sl in section_labels
    )
    return (
        f'<div class="jump-nav"><span class="jump-nav-label">Sections:</span>'
        f'<div class="jump-nav-groups"><div class="jump-nav-row" data-level="1">{chips}</div></div></div>'
    )


def _area_charts_html(area_rows: list[dict], page_label: str) -> str:
    """Build HTML for the page-level overview (area) charts."""
    if not area_rows:
        return ""
    grid_class = "dashboard-grid" if len(area_rows) > 1 else "dashboard-grid expand-1"
    cards = []
    for i, row in enumerate(area_rows):
        caption = escape(str(row.get("title", "")))
        key = escape(row["chart_key"])
        cards.append(
            f'<figure class="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}">'
            f'<figcaption class="chart-caption">{caption}</figcaption>'
            f'<div class="meta-subline">{escape(page_label)}</div>'
            f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
            f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{caption}"></div>'
            f'</figure>'
        )
    return (
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
    )


def _line_sections_html(line_rows: list[dict], page_label: str) -> str:
    """Build section-grouped HTML for line charts."""
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
        n = len(section_rows)
        if n == 1:
            grid_class = "dashboard-grid expand-1"
        elif n == 2:
            grid_class = "dashboard-grid expand-2"
        elif n == 3:
            grid_class = "dashboard-grid expand-3"
        else:
            grid_class = "dashboard-grid"
        cards = []
        for i, row in enumerate(section_rows):
            product_name = escape(str(row.get("product_label", row.get("title", ""))))
            key = escape(row["chart_key"])
            subline = escape(f"{page_label} > {section_label}")
            cards.append(
                f'<figure class="chart-card" data-default-order="{i}" data-total-abs="{row.get("total_abs_value",0):.4f}" data-abs-diff="{row.get("abs_diff",0):.4f}" data-pct-diff="{row.get("pct_diff",0):.6f}">'
                f'<figcaption class="chart-caption">{product_name}</figcaption>'
                f'<div class="meta-subline">{subline}</div>'
                f'<div class="chart-load-state" data-loaded="false">Chart queued</div>'
                f'<div data-chart-key="{key}" class="lazy-chart-plot is-unloaded" role="img" aria-label="{product_name}"></div>'
                f'</figure>'
            )
        chunks.append(
            f'<section id="{anchor}" style="scroll-margin-top:150px;">'
            f'<h2 class="section-heading">{escape(section_label)}</h2>'
            f'<section class="section-sort-group">'
            f'<div class="sort-bar"><span class="sort-bar-label">Sort:</span>'
            f'<button class="sort-btn active" data-sort="default">Default</button>'
            f'<button class="sort-btn" data-sort="totalAbs">Largest total</button>'
            f'<button class="sort-btn" data-sort="absDiff">Largest difference</button>'
            f'<button class="sort-btn" data-sort="pctDiff">Largest % diff</button>'
            f'</div>'
            f'<div class="{grid_class}" data-sortable-grid="{escape(anchor)}">{"".join(cards)}</div>'
            f'</section>'
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
) -> None:
    """Write a polished HTML dashboard page with sticky header, lazy loading, and sorting."""
    page_label = str(page_config.get("page_label", "Dashboard"))
    page_file = output_path.name
    area_rows = [r for r in chart_rows if r.get("chart_type") == "stacked_area"]
    line_rows = [r for r in chart_rows if r.get("chart_type") == "line"]
    section_labels = []
    for r in line_rows:
        sl = str(r.get("section_label") or "Other")
        if sl not in section_labels:
            section_labels.append(sl)

    nav_chips = _nav_chips_html(all_pages or [], page_file)
    switcher_html = _dashboard_switcher_html(dashboard_switcher or [], current_dashboard, page_file)
    jump_nav = _jump_nav_html(page_label, section_labels)
    note_html = f'<div class="visible-note">{escape(page_note)}</div>' if page_note else ""
    overview_html = _area_charts_html(area_rows, page_label)
    sections_html = _line_sections_html(line_rows, page_label)
    economy_ctx = f"Economy: <strong>{escape(economy_label)}</strong>" if economy_label else ""

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
          {switcher_html}
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
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <script src="../chart_bundles/{escape(bundle_js_name)}"></script>
  <script>{_LAZY_LOAD_JS}</script>
  <script>{_SORT_JS}</script>
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
    switcher_html = _dashboard_switcher_html(dashboard_switcher or [], current_dashboard, "index.html")
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
    ul {{ list-style: none; padding: 0; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="top-row">
      <h1>Common ESTO Dashboard{economy_heading}</h1>
      {switcher_html}
    </div>
    <p style="color:#4b5563;">Charts are generated automatically from common ESTO flow/product rows.</p>
    <ul>{cards}</ul>
  </div>
  <script>{_DASHBOARD_SWITCHER_JS}</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def _build_td_sector_chart(
    demand_df: pd.DataFrame,
    supply_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
    tfec_exclude_keys: list[str],
    sector_colors: dict[str, str],
) -> go.Figure:
    """Stacked-area chart by demand sector with a TFC/TFEC Plotly dropdown.

    TFC (Total Final Consumption) includes all demand sectors (codes 14-17).
    TFEC (Total Final Energy Consumption) excludes sectors listed in
    tfec_exclude_keys (typically non_energy / code 17).

    supply_total = sum of signed values for codes 01, 02, 03
    (Production + Imports - Exports). Bunkers (04, 05) and stock changes (06)
    are excluded because they are not recorded in LEAP projection scenarios,
    making the supply line a valid comparison across the full time series.
    """
    fig = go.Figure()
    trace_modes: list[str] = []  # "tfc", "tfec", or "both"

    primary_mask = (
        (demand_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (demand_df["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
    )
    primary_df = demand_df[primary_mask]

    # Sector order: largest TFC total first
    sector_order = (
        primary_df.groupby(["_page_key", "_page_label"])["value"]
        .sum().abs().sort_values(ascending=False).reset_index()
    )

    for _, sector_row in sector_order.iterrows():
        page_key = str(sector_row["_page_key"])
        page_label = str(sector_row["_page_label"])
        sector_data = (
            primary_df[primary_df["_page_key"] == page_key]
            .groupby("year", as_index=False)["value"].sum()
            .sort_values("year")
        )
        is_tfec_excluded = page_key in tfec_exclude_keys
        color = sector_colors.get(page_key)
        trace_kw: dict = dict(
            x=sector_data["year"],
            y=sector_data["value"],
            mode="lines",
            stackgroup="demand",
            name=page_label,
            hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(page_label) + "</extra>",
        )
        if color:
            trace_kw["line"] = {"color": color}
        fig.add_trace(go.Scatter(**trace_kw))
        trace_modes.append("tfc" if is_tfec_excluded else "both")

    # TFC comparison demand totals (non-LEAP visible series)
    tfc_totals = demand_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in tfc_totals.groupby(["source_system", "scenario"]):
        if str(src).casefold() == primary_source.casefold():
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " (TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
        ))
        trace_modes.append("tfc")

    # TFEC comparison demand totals
    tfec_demand = demand_df[~demand_df["_page_key"].isin(tfec_exclude_keys)]
    tfec_totals = tfec_demand.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in tfec_totals.groupby(["source_system", "scenario"]):
        if str(src).casefold() == primary_source.casefold():
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " (TFEC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            visible=False,
            hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
        ))
        trace_modes.append("tfec")

    # Supply total lines — always visible regardless of TFC/TFEC mode
    if not supply_df.empty:
        for (src, scen), grp in supply_df.groupby(["source_system", "scenario"]):
            lbl = series_label_from_values(src, scen, series_labels) + " supply (01–03)"
            grp_sorted = grp.sort_values("year")
            fig.add_trace(go.Scatter(
                x=grp_sorted["year"], y=grp_sorted["value"],
                mode="lines", name=lbl, line={"dash": "dot"},
                hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
            ))
            trace_modes.append("both")

    tfc_vis = [m in ("tfc", "both") for m in trace_modes]
    tfec_vis = [m in ("tfec", "both") for m in trace_modes]
    fig.update_layout(
        title="Total demand by sector (TFC)",
        xaxis_title="Year",
        yaxis_title="Signed energy (PJ)",
        margin={"l": 64, "r": 28, "t": 100, "b": 72},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        updatemenus=[{
            "buttons": [
                {"label": "TFC (incl. Non-energy use)", "method": "update",
                 "args": [{"visible": tfc_vis}, {"title": "Total demand by sector (TFC)"}]},
                {"label": "TFEC (excl. Non-energy use)", "method": "update",
                 "args": [{"visible": tfec_vis}, {"title": "Total demand by sector (TFEC)"}]},
            ],
            "direction": "down", "showactive": True,
            "x": 0.0, "xanchor": "left", "y": 1.22, "yanchor": "top",
        }],
    )
    return fig


def _build_td_fuel_chart(
    demand_df: pd.DataFrame,
    supply_df: pd.DataFrame,
    series_labels: dict[str, str],
    primary_source: str,
    primary_scenario: str,
) -> go.Figure:
    """Stacked-area chart by fuel across all demand sectors (TFC), with supply line."""
    fig = go.Figure()
    primary_df = demand_df[
        (demand_df["source_system"].astype(str).str.casefold() == primary_source.casefold())
        & (demand_df["scenario"].astype(str).str.casefold() == primary_scenario.casefold())
    ]

    # Stack by product — largest total first
    product_totals = (
        primary_df.groupby("common_product_label")["value"].sum().abs()
        .sort_values(ascending=False).index.tolist()
    )
    product_by_year = primary_df.groupby(["common_product_label", "year"], as_index=False)["value"].sum()
    for product in product_totals:
        grp = product_by_year[product_by_year["common_product_label"] == product].sort_values("year")
        lbl = str(product)
        fig.add_trace(go.Scatter(
            x=grp["year"], y=grp["value"],
            mode="lines", stackgroup="demand", name=lbl,
            hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
        ))

    # Comparison demand total lines
    comp_totals = demand_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    for (src, scen), grp in comp_totals.groupby(["source_system", "scenario"]):
        if str(src).casefold() == primary_source.casefold():
            continue
        lbl = series_label_from_values(src, scen, series_labels) + " total (TFC)"
        fig.add_trace(go.Scatter(
            x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
            mode="lines+markers", name=lbl, line={"dash": "dash"},
            hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
        ))

    # Supply total lines
    if not supply_df.empty:
        supply_totals = supply_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
        for (src, scen), grp in supply_totals.groupby(["source_system", "scenario"]):
            lbl = series_label_from_values(src, scen, series_labels) + " supply (01–03)"
            fig.add_trace(go.Scatter(
                x=grp.sort_values("year")["year"], y=grp.sort_values("year")["value"],
                mode="lines", name=lbl, line={"dash": "dot"},
                hovertemplate="%{x}<br>%{y:,.2f} PJ<extra>" + escape(lbl) + "</extra>",
            ))

    fig.update_layout(
        title="Total demand by fuel (TFC)",
        xaxis_title="Year",
        yaxis_title="Signed energy (PJ)",
        margin={"l": 64, "r": 28, "t": 56, "b": 72},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
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
) -> tuple[list[dict], dict | None]:
    """Build the total demand summary page (config-driven bespoke page).

    Generates two area charts:
    - By sector: stacked by demand page group with TFC/TFEC dropdown
    - By fuel: stacked by common_product_label across all demand (TFC)

    Both charts include a supply total line defined as:
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

    demand_page_keys = [str(k) for k in config.get(
        "demand_page_keys", ["industry", "transport", "buildings", "others", "non_energy"]
    )]
    supply_codes = [str(c) for c in config.get("supply_codes", ["01", "02", "03"])]
    tfec_exclude_keys = [str(k) for k in config.get("tfec_exclude_page_keys", ["non_energy"])]
    sector_colors: dict[str, str] = config.get("sector_colors", {
        "industry": "#3b82f6",
        "transport": "#f97316",
        "buildings": "#10b981",
        "others": "#8b5cf6",
        "non_energy": "#94a3b8",
    })

    demand_df = assigned_df[assigned_df["_page_key"].isin(demand_page_keys)].copy()
    if demand_df.empty:
        return [], None

    supply_df = (
        assigned_df[
            assigned_df["common_flow_code"].apply(
                lambda c: code_expression_matches_any_prefix(c, supply_codes)
            )
        ]
        .groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
    )

    charts: dict[str, go.Figure] = {}
    chart_rows: list[dict] = []
    manifest_rows: list[dict] = []

    for kind, build_fn in [
        ("sector", lambda: _build_td_sector_chart(demand_df, supply_df, series_labels, primary_source, primary_scenario, tfec_exclude_keys, sector_colors)),
        ("fuel",   lambda: _build_td_fuel_chart(demand_df, supply_df, series_labels, primary_source, primary_scenario)),
    ]:
        chart_key = f"chart__area__total_demand__{kind}"
        fig = build_fn()
        charts[chart_key] = fig
        title = f"Total demand by {kind}"
        total_abs = float(demand_df["value"].abs().sum())
        chart_rows.append({
            "chart_key": chart_key, "chart_type": "stacked_area",
            "title": title, "product_label": title, "section_label": "Overview",
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
        })
        manifest_rows.append({
            "page_key": "total_demand", "page_label": "Total demand",
            "section_label": "Overview", "chart_type": "stacked_area",
            "chart_key": chart_key, "common_flow_label": title,
            "common_product_label": "All", "row_count": int(len(demand_df)),
            "source_flow_labels": "; ".join(demand_page_keys),
            "sign_note": "", "suppressed": False,
            "total_abs_value": total_abs, "abs_diff": 0.0, "pct_diff": 0.0,
            "diff_hist_json": "", "diff_proj_json": "",
        })

    bundle_name = "total_demand__charts.json"
    write_chart_bundle(charts, layout["chart_bundles"] / bundle_name)
    write_dashboard_page(
        {"page_key": "total_demand", "page_label": "Total demand"},
        chart_rows=chart_rows,
        bundle_js_name=bundle_name.replace(".json", ".js"),
        output_path=layout["dashboards"] / "total_demand.html",
        all_pages=all_pages,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
    )
    page_row = {
        "file": "total_demand.html", "label": "Total demand",
        "area_chart_count": len(charts), "summary_chart_count": 0, "line_chart_count": 0,
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
) -> tuple[dict[str, go.Figure], list[dict], list[dict]]:
    """Build product-summary and detail line chart records for a page dataframe."""
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

    summary_products = sorted(
        page_df.loc[~page_df["common_flow_label"].isin(parent_flow_labels), "common_product_label"]
        .dropna().unique()
    )
    for product_label in summary_products:
        prod_df = page_df[
            (~page_df["common_flow_label"].isin(parent_flow_labels))
            & (page_df["common_product_label"] == product_label)
        ]
        if prod_df.empty:
            continue
        agg_rows = prod_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
        chart_key = f"chart__summary__{safe_slug(page_key)}__{safe_slug(product_label)}"
        metrics = compute_ranking_metrics(
            agg_rows,
            primary_source,
            primary_scenario,
            comparison_source,
            base_year=base_year,
            ninth_source=ninth_source,
        )
        suppressed = metrics["total_abs_value"] < suppression_threshold
        product_display = flow_name_without_code(product_label)
        hist_diff, proj_diff = compute_diff_series(
            agg_rows,
            primary_source,
            primary_scenario,
            comparison_source,
            ninth_source,
            base_year,
        )
        manifest_rows.append({
            "page_key": page_key,
            "page_label": page_label,
            "section_label": "By product",
            "chart_type": "product_summary",
            "chart_key": chart_key,
            "common_flow_label": "(all flows)",
            "common_product_label": product_label,
            "row_count": int(len(prod_df)),
            "source_flow_labels": "",
            "sign_note": sign_note_for_chart(prod_df),
            "suppressed": suppressed,
            "diff_hist_json": hist_diff.to_json() if not hist_diff.empty else "",
            "diff_proj_json": proj_diff.to_json() if not proj_diff.empty else "",
            **metrics,
        })
        if suppressed:
            continue
        charts[chart_key] = build_product_chart(
            agg_rows,
            "All flows",
            product_label,
            series_labels,
            hist_diff=hist_diff,
            proj_diff=proj_diff,
            primary_source=primary_source,
            primary_scenario=primary_scenario,
        )
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "line",
            "title": f"All flows - {product_label}",
            "product_label": product_display,
            "section_label": "By product",
            **metrics,
        })

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
        product_display = flow_name_without_code(product_label)
        hist_diff, proj_diff = compute_diff_series(
            pair_rows,
            primary_source,
            primary_scenario,
            comparison_source,
            ninth_source,
            base_year,
        )
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
        charts[chart_key] = build_product_chart(
            pair_rows,
            flow_label,
            product_label,
            series_labels,
            hist_diff=hist_diff,
            proj_diff=proj_diff,
            primary_source=primary_source,
            primary_scenario=primary_scenario,
        )
        chart_rows.append({
            "chart_key": chart_key,
            "chart_type": "line",
            "title": f"{flow_label} - {product_label}",
            "product_label": product_display,
            "section_label": section_label,
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
) -> tuple[list[dict], list[dict]]:
    """Build optional pages for alternate comparison scopes such as LEAP vs 9th."""
    config = template.get("scope_specific_pages", {})
    if not config.get("enabled", False) or scope_df.empty:
        return [], []

    assigned_scope_df = assign_pages(scope_df, template.get("sector_pages", []))
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
        )
        page_rows.append({
            "file": page_file,
            "label": page_label,
            "area_chart_count": 0,
            "line_chart_count": sum(r.get("chart_type") == "line" and r.get("section_label") != "By product" for r in chart_rows),
            "summary_chart_count": sum(r.get("section_label") == "By product" for r in chart_rows),
        })
    return manifest_rows, page_rows


def render_dashboard(
    df: pd.DataFrame,
    template: dict,
    series_config: dict,
    layout: dict[str, Path],
    scope_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Render page bundles, dashboard pages, and a chart manifest."""
    series_labels = series_config.get("series_labels", {})
    economy_label = series_config.get("economy_label", "")
    current_dashboard = layout["root"].name
    dashboard_switcher = _normalise_dashboard_switcher(series_config, current_dashboard)
    page_rules = template.get("sector_pages")
    if not page_rules:
        raise ValueError("Template is missing required 'sector_pages' rules.")
    assigned_df = assign_pages(df, page_rules)
    page_summary_df = build_page_assignment_summary(assigned_df)
    page_summary_df.to_csv(layout["supporting"] / "page_assignment_summary.csv", index=False)

    # First pass: build page inventory (needed for navigation chips on every page).
    page_meta = assigned_df[["_page_key", "_page_label"]].drop_duplicates().sort_values("_page_key")
    page_inventory: list[dict] = []
    # Add the synthetic total demand page first so it appears in nav on all other pages.
    if template.get("total_demand_page", {}).get("enabled", False):
        page_inventory.append({"page_key": "total_demand", "page_label": "Total demand", "file": "total_demand.html"})
    for _, meta in page_meta.iterrows():
        page_key = safe_slug(meta["_page_key"])
        page_label = str(meta["_page_label"])
        if not assigned_df[assigned_df["_page_key"] == meta["_page_key"]].empty:
            page_inventory.append({"page_key": page_key, "page_label": page_label, "file": f"{page_key}.html"})

    scope_config = template.get("scope_specific_pages", {})
    if scope_config.get("enabled", False) and scope_df is not None and not scope_df.empty:
        scope_inventory_df = assign_pages(scope_df, page_rules)
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
        page_df = assigned_df[assigned_df["_page_key"].apply(safe_slug) == page_key].copy()
        if page_df.empty:
            continue

        charts: dict[str, go.Figure] = {}
        chart_rows: list[dict] = []

        for area_spec in pick_area_specs(page_df, template):
            chart_key = f"chart__area__{safe_slug(area_spec['aggregate_flow_prefix'])}__{safe_slug(area_spec['aggregate_flow_label'])}"
            area_df = page_df[page_df["common_flow_label"].isin(area_spec["source_flow_labels"])]
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
            charts[chart_key] = build_area_chart(page_df, area_spec, series_labels, template)
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "stacked_area",
                "title": str(area_spec["aggregate_flow_label"]),
                "product_label": str(area_spec["aggregate_flow_label"]),
                "section_label": "Overview",
                **metrics,
            })

        flow_nodes = get_existing_flow_nodes(page_df)
        all_canonical = set(flow_nodes["canonical_code"].astype(str))
        parent_flow_labels: set[str] = set()
        for _, node in flow_nodes.iterrows():
            code = str(node["canonical_code"])
            if code and any(c.startswith(code + ".") for c in all_canonical if c != code):
                parent_flow_labels.add(str(node["common_flow_label"]))

        # Product summary charts: one chart per product, summing all non-parent flows.
        summary_products = sorted(
            page_df.loc[~page_df["common_flow_label"].isin(parent_flow_labels), "common_product_label"]
            .dropna().unique()
        )
        for product_label in summary_products:
            prod_df = page_df[
                (~page_df["common_flow_label"].isin(parent_flow_labels))
                & (page_df["common_product_label"] == product_label)
            ]
            if prod_df.empty:
                continue
            agg_rows = prod_df.groupby(["source_system", "scenario", "year"], as_index=False)["value"].sum()
            chart_key = f"chart__summary__{safe_slug(page_key)}__{safe_slug(product_label)}"
            metrics = compute_ranking_metrics(agg_rows, primary_source, primary_scenario, comparison_source, base_year=base_year, ninth_source=ninth_source)
            suppressed = metrics["total_abs_value"] < suppression_threshold
            product_display = flow_name_without_code(product_label)
            hist_diff, proj_diff = compute_diff_series(agg_rows, primary_source, primary_scenario, comparison_source, ninth_source, base_year)
            manifest_rows.append({
                "page_key": page_key,
                "page_label": page_label,
                "section_label": "By product",
                "chart_type": "product_summary",
                "chart_key": chart_key,
                "common_flow_label": "(all flows)",
                "common_product_label": product_label,
                "row_count": int(len(prod_df)),
                "source_flow_labels": "",
                "sign_note": sign_note_for_chart(prod_df),
                "suppressed": suppressed,
                "diff_hist_json": hist_diff.to_json() if not hist_diff.empty else "",
                "diff_proj_json": proj_diff.to_json() if not proj_diff.empty else "",
                **metrics,
            })
            if suppressed:
                continue
            charts[chart_key] = build_product_chart(
                agg_rows, "All flows", product_label, series_labels,
                hist_diff=hist_diff, proj_diff=proj_diff,
                primary_source=primary_source, primary_scenario=primary_scenario,
            )
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "line",
                "title": f"All flows — {product_label}",
                "product_label": product_display,
                "section_label": "By product",
                **metrics,
            })

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
            product_display = flow_name_without_code(product_label)
            hist_diff, proj_diff = compute_diff_series(pair_rows, primary_source, primary_scenario, comparison_source, ninth_source, base_year)
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
            charts[chart_key] = build_product_chart(pair_rows, flow_label, product_label, series_labels, hist_diff=hist_diff, proj_diff=proj_diff, primary_source=primary_source, primary_scenario=primary_scenario)
            chart_rows.append({
                "chart_key": chart_key,
                "chart_type": "line",
                "title": f"{flow_label} - {product_label}",
                "product_label": product_display,
                "section_label": section_label,
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
        )
        page_rows.append({
            "file": page_file,
            "label": page_label,
            "area_chart_count": sum(r.get("chart_type") == "stacked_area" for r in chart_rows),
            "line_chart_count": sum(r.get("chart_type") == "line" and r.get("section_label") != "By product" for r in chart_rows),
            "summary_chart_count": sum(r.get("section_label") == "By product" for r in chart_rows),
        })

    td_manifest_rows, td_page_row = build_total_demand_page(
        assigned_df, template, series_labels, layout, page_inventory,
        primary_source=primary_source, primary_scenario=primary_scenario,
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
    )
    manifest_rows.extend(td_manifest_rows)
    if td_page_row:
        page_rows.append(td_page_row)

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
    )
    manifest_rows.extend(scope_manifest_rows)
    page_rows.extend(scope_page_rows)

    write_index(
        page_rows,
        layout["dashboards"] / "index.html",
        economy_label=economy_label,
        dashboard_switcher=dashboard_switcher,
        current_dashboard=current_dashboard,
    )
    manifest_df = pd.DataFrame(manifest_rows)
    manifest_df.to_csv(layout["supporting"] / "chart_manifest.csv", index=False)
    return manifest_df

#%%
