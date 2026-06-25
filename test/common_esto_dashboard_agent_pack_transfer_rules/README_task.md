# Common ESTO dashboard agent pack

This pack now supports an automated dashboard workflow that can consume either:

1. long-form common ESTO comparison data with `comparison_scope`, `source_system`, `economy`, `scenario`, `year`, common flow/product labels, and `value`; or
2. wide-form comparison data with `economy`, combined `scenario`, `flow`, `product`, and year columns such as `1990` ... `2060`.

The uploaded `common_esto_comparison_wide.csv` format is handled by `src/common_esto_dashboard_data.py`, which converts it to the long common ESTO format internally.

## Current dashboard approach

The dashboard no longer needs a JSON file listing every graph. Instead, `config/common_esto_dashboard_template.json` only defines:

- the dashboard mode;
- automatic chart-generation settings;
- broad sector/page recogniser rules.

Charts are generated from the common ESTO flow/product structure:

- aggregate stacked-area charts are generated for the highest available flow levels;
- if a page has deeper hierarchy chains, the first two hierarchy levels are charted;
- otherwise, only the highest available level is charted;
- individual line charts are generated for every flow/product pair;
- all charts include dataset comparisons across configured source/scenario series.

The workflow also applies sector-based sign semantics from
`config/common_esto_dashboard_template.json`. These rules do not flip signs by
default. They preserve the signed balance values, then attach metadata explaining
what positive and negative values mean for each flow/sector.

Current sign meanings:

```text
01 Production:
  positive = domestic production added to supply

02 Imports:
  positive = imports added to supply

03 Exports:
  negative = exports removed from domestic supply

04/05 Bunkers:
  negative = fuel supplied to international aviation/marine, removed from domestic supply

06 Stock changes:
  positive = stock draw, added to supply
  negative = stock build, removed from supply

08 Transfers:
  positive = fuel transferred into this product/category
  negative = fuel transferred out of this product/category

09 Transformation:
  positive = transformation output
  negative = transformation input

10 Own use / losses:
  negative = energy used or lost within the energy sector

14/15/16/17 Demand:
  positive = final energy use by end-use sectors

18/19 Electricity and heat output:
  positive = electricity or heat produced
```

This preserves the spirit of the original hand-written dashboard JSON while avoiding manual graph maintenance.

## Main files

```text
src/common_esto_dashboard_workflow.py      # workflow entry point
src/common_esto_dashboard_data.py          # long/wide input loading and filtering
src/common_esto_dashboard_renderer.py      # automatic page/chart generation
config/common_esto_dashboard_template.json # page recognisers + chart-generation rules
config/series_config.json                  # visible dataset/scenario series
inputs/common_esto_comparison_wide.csv     # example wide input
```

## Running

```bash
cd common_esto_dashboard_agent_pack
python src/common_esto_dashboard_workflow.py
```

Optional environment variables:

```bash
COMMON_ESTO_INPUT_DATA_PATH=/path/to/input.csv
COMMON_ESTO_ECONOMY=20_USA
COMMON_ESTO_COMPARISON_SCOPE=leap_vs_esto_vs_ninth
```

## Outputs

```text
outputs/<economy>/dashboards/index.html
outputs/<economy>/chart_bundles/*.json
outputs/<economy>/chart_bundles/*.js
outputs/<economy>/supporting_files/chart_manifest.csv
outputs/<economy>/supporting_files/sign_semantics_summary.csv
```

## Current caveats

The sector recogniser is heuristic. It is intentionally simple and should be refined as common ESTO flow labels stabilise. The important point is that graph membership is now inferred from common flow/product labels rather than maintained as explicit graph IDs.

## Page recogniser rules for generated common categories

The dashboard page rules must handle generated common ESTO categories, not only exact historical ESTO labels. Graph partitioning can create common categories such as:

```text
07.12-07.17,07.99 Petroleum products
09.01.01,09.02.01 Electricity plants
08,08.01-08.04,08.99 Refinery and blending transfers
```

For that reason, page assignment is now based on parsed code expressions and label keywords. The recogniser does not only check whether a string starts with one prefix. It parses comma-separated codes and compressed ranges, then checks whether any component/range sits under a configured prefix.

The JSON page rules support these fields:

```text
page_key
page_label
priority
flow_code_prefixes
flow_keywords
exclude_flow_code_prefixes
exclude_flow_keywords
flow_regexes
exclude_flow_regexes
rule_note
```

The old `flow_code_prefixes` and `flow_keywords` names still work, but the renderer also accepts the clearer `include_flow_code_prefixes` and `include_flow_keywords` names.

Rules are applied by `priority`, then by list order. This means more specific pages should have lower priority numbers and appear before broad fallback pages. For example:

```text
Power priority 30 catches 18, 19, 10.01.01, and labels containing electricity plants / CHP plants / heat plants.
Refining priority 40 catches 09.07, 10.01.11, Oil refineries, and Refinery and blending transfers.
Other transformation priority 50 catches broader 08, 09, 10.01, 10.02 rows that were not already assigned to Power or Refining.
```

This order matters because a generated category can contain several codes. For example, `08,08.01-08.04,08.99 Refinery and blending transfers` has an `08` code, but it is assigned to Refining because the more specific Refining keyword rule is applied before the broader Other transformation rule.

The workflow writes:

```text
outputs/<economy>/supporting_files/page_assignment_summary.csv
```

This file should be checked whenever page rules change. It explains which generated/common flow rows were placed on each page and which rule note applied.

## Naming conventions for generated aggregate categories

Generated aggregate categories should be transparent, stable, and mechanically traceable. A user should be able to look at a generated category name and understand which original categories were combined.

Generated category names should describe their component codes first, and their common meaning second.

For example:

```text
07.12-07.17,07.99 Petroleum products
```

means:

```text
This category contains ESTO product codes 07.12 through 07.17, plus 07.99.
```

Do not create vague labels such as:

```text
Other petroleum products
```

unless there is a label override. The mechanical code-based label should remain available for traceability.

### Generated code

When several categories are joined, the generated code should be created from the component codes.

Rules:

1. Sort component codes in their natural code order.
2. Compress consecutive ranges with a hyphen.
3. Separate non-consecutive components with commas.
4. Preserve the relevant code prefix where possible.
5. If the group exactly matches a real parent category, use the real parent category instead of a generated code.

Examples:

```text
07.12 + 07.13 + 07.14 + 07.15 + 07.16 + 07.17
→ 07.12-07.17
```

```text
07.12 + 07.13 + 07.14 + 07.15 + 07.16 + 07.17 + 07.99
→ 07.12-07.17,07.99
```

```text
09.01.01 + 09.02.01
→ 09.01.01,09.02.01
```

If a broader real parent category exists and is the intended comparison row, prefer the parent:

```text
08.01 + 08.02 + 08.03 + 08.04 + 08.99
→ 08 Transfers
```

rather than:

```text
08.01-08.04,08.99 Transfers
```

because `08 Transfers` is a real ESTO parent row.

### Generated name

The generated name should use the nearest useful common parent or shared description.

Examples:

```text
07.12-07.17,07.99 Petroleum products
09.01.01,09.02.01 Electricity plants
09.01.02,09.02.02 CHP plants
09.01.03,09.02.03 Heat plants
```

If the code cannot confidently infer a common name, it should still generate a stable code-based label and flag the name for review.

### Generated label

The display label should combine the generated code and generated name:

```text
generated_label = generated_code + " " + generated_name
```

Examples:

```text
07.12-07.17,07.99 Petroleum products
09.01.01,09.02.01 Electricity plants
09.01.02,09.02.02 CHP plants
```

### Generated ID

The system should also create a machine-safe identifier.

The ID should be deterministic and based on the generated label.

Rules:

1. Lowercase the label.
2. Replace spaces, punctuation, slashes, commas, and hyphens with underscores.
3. Collapse repeated underscores.
4. Remove leading or trailing underscores.
5. Prefix with `rollup_` or `common_` depending on the output type.

Examples:

```text
07.12-07.17,07.99 Petroleum products
→ common_07_12_07_17_07_99_petroleum_products
```

```text
09.01.01,09.02.01 Electricity plants
→ common_09_01_01_09_02_01_electricity_plants
```

```text
08 Transfers
→ rollup_08_transfers
```

### Component membership remains the source of truth

The generated label is only a label. The actual category definition is the list of component rows.

For each generated category, the system should preserve a component table such as:

```text
generated_category_id
component_flow_or_sector
component_product_or_fuel
component_name
source_system
comparison_scope
```

This makes the generated category auditable.

### Label overrides

Human-readable label overrides are allowed, but they should not change membership.

For example, a generated label might be:

```text
07.12-07.17,07.99 Petroleum products
```

A label override could display this as:

```text
Other petroleum products
```

but the original generated label and component list should still be preserved.

Label overrides should therefore affect display only:

```text
preferred_rollup_label
```

They should not alter:

```text
rollup_group_id
generated_category_id
component membership
```

### Why this naming convention matters

This naming system is used so that generated comparison categories are:

- stable across runs;
- easy to audit;
- mechanically traceable back to original ESTO or source-system categories;
- close to the original energy-balance style;
- clear enough for dashboard users and mapping maintainers.

The aim is to avoid hidden manual categories. If the system creates a new aggregate category, the category name should show what was combined.

### Transfer page assignment rule

Transfer rows are classified by their balance code, not by refinery-related wording in the generated label. Any generated/common flow containing an `08` transfer component is assigned to the Transfers section under the Other transformation page. For example, `08,08.01-08.04,08.99 Refinery and blending transfers` remains an 08 Transfers row for dashboard organisation, even though the generated name mentions refinery and blending.

