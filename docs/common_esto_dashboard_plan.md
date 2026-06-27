# Common ESTO Comparison Dashboard: Process and Design Plan

## Purpose

This document explains the planned dashboard process for comparing APERC energy-balance outputs across ESTO, LEAP, and the 9th Outlook. It describes how the dashboard is created, what data it expects, how charts are generated automatically, how generated common ESTO categories are handled, and why the system is being designed this way.

The main design goal is to move away from a hand-authored dashboard where every graph is listed in a large JSON file. Instead, the dashboard should be generated from the structure of the final merged comparison dataset. The JSON file should remain useful, but only as a small configuration layer for rules that cannot be reliably inferred from the data alone, such as page grouping, sign interpretation, and preferred display settings.

## Contents

### Overview

- [Summary of the intended workflow](#summary-of-the-intended-workflow)
- [Why this approach is needed](#why-this-approach-is-needed)
- [Current prototype status](#current-prototype-status)

### Design principles

- [Main design principle](#main-design-principle)
- [Upstream mapping and common ESTO structure](#upstream-mapping-and-common-esto-structure)
- [Graph partitioning and common denominator logic](#graph-partitioning-and-common-denominator-logic)
- [Generated common category naming](#generated-common-category-naming)
- [Why not use AI dynamically for chart structure?](#why-not-use-ai-dynamically-for-chart-structure)

### Data and inputs

- [Dashboard input files](#dashboard-input-files)
- [Input data expected by the dashboard](#input-data-expected-by-the-dashboard)
- [Dataset filtering](#dataset-filtering)
- [Sign semantics](#sign-semantics)

### Chart generation

- [Page and section assignment](#page-and-section-assignment)
- [Chart generation logic](#chart-generation-logic)
- [Main chart families](#main-chart-families)
- [Sorting and prioritisation](#sorting-and-prioritisation)

### Dashboard structure

- [Dashboard page and chart structure](#dashboard-page-and-chart-structure)
- [Page structure](#page-structure)

### QA and audit outputs

- [Chart manifest](#chart-manifest)
- [QA outputs](#qa-outputs)
- [Sankey extension plan](#sankey-extension-plan)

### Configuration and running

- [Repository structure](#repository-structure)
- [Configuration files](#configuration-files)
- [Running the dashboard](#running-the-dashboard)
- [Recommended development workflow](#recommended-development-workflow)

### Reference

- [Design decisions](#design-decisions)
- [Production build plan](#production-build-plan)
- [Acceptance criteria for the dashboard plan](#acceptance-criteria-for-the-dashboard-plan)
- [Final concept](#final-concept)
- [Relationship to Plotly controls](#relationship-to-plotly-controls)
- [Relationship to the JSON configuration](#relationship-to-the-json-configuration)
- [Why this design is preferred](#why-this-design-is-preferred)

---

## Summary of the intended workflow

The dashboard workflow is intended to work as follows:

```text
Simple mapping sheets
  -> generated energy-balance relationships
  -> graph/partition common ESTO structure
  -> common ESTO comparison dataset
  -> automatic dashboard pages and charts
  -> supporting QA files
```

The dashboard itself should use the final common ESTO comparison dataset, not the original mapping workbook and not old `relationship_id -> graph_id` links. The common dataset should already contain the safest comparison rows available for each comparison scope.

In practical terms, the dashboard should be able to read data similar to:

```text
economy, scenario, product, flow, 1990, 1991, ..., 2060
```

The dashboard then decides what pages and charts to create by inspecting the common flow and product structure in the dataset.

## Why this approach is needed

The frozen dashboard in `C:\Users\Work\github\leap_dashboard_legacy` relied heavily on a large JSON template that defined the dashboard hierarchy and many of the specific graphs. That worked when the mapping structure was relatively stable, but it becomes difficult to maintain when LEAP, ESTO, and 9th Outlook have different levels of detail and when they change over time. The legacy approach also required researchers to maintain a large set of `relationship_id -> graph_id` links with many-to-many relationships. This was error-prone and hard to audit.

The new mapping process in leap_mappings creates common comparison categories automatically. These categories can change when the relationship between source datasets changes. For example, if LEAP has detail for several ESTO products but the 9th Outlook has them as one aggregate, then the dashboard should compare all datasets at that aggregate level. This is not a presentation choice; it is required to avoid unfair or misleading comparisons.

Because the common categories are generated mechanically, the dashboard cannot depend on old fixed graph names. It needs to understand generated labels such as:

```text
07.12-07.17,07.99 Petroleum products
09.01.01,09.02.01 Electricity plants
16.01-16.02 Buildings
16.03-16.04 Agriculture and fishing
```

The dashboard should therefore classify rows using their component codes and common labels, not by assuming a small fixed set of manually named graph IDs.

## Current production status

The production dashboard implements this direction. It can:

- read long-form common ESTO comparison data;
- read wide-form comparison data with year columns;
- split combined scenario labels into `source_system` and `scenario` where possible (for example, a wide-form input column named `LEAP Target` is split into `source_system = LEAP` and `scenario = Target`);
- preserve signed energy-balance values;
- attach sign interpretation metadata by flow/sector;
- assign rows to dashboard pages using configurable rules;
- parse generated code expressions containing commas and ranges;
- generate stacked-area charts for higher-level flow groups;
- generate line charts for individual flow/product series;
- write supporting QA-style files such as chart manifests, page assignment summaries, and sign summaries that allow dashboard decisions to be audited and worked back to the original dataset from.

The dashboard is generated from Common ESTO rows rather than graph IDs and is designed to work with whatever valid Common ESTO structure the upstream mapping pipeline produces.

### What is and isn't built

The production modules in `codebase/` implement the following:

**Implemented in production:**

- Long-form and wide-form input loading and normalisation
- Sign semantics metadata attachment by flow code
- Page assignment with priority rules and code-expression parsing
- Stacked-area overview charts (primary LEAP scenario stacked by product, comparison dataset totals as lines)
- Individual line charts for every common flow/product pair
- Chart manifest CSV
- Page assignment summary CSV
- Sign semantics summary CSV
- Sticky header with collapse toggle
- Section jump navigation chips
- Lazy-loaded Plotly chart bundles (IntersectionObserver-based)
- Client-side chart sorting by size, absolute difference, and percentage difference
- Dashboard index page

**Original follow-on plan (now largely implemented):**

- Parent/child frontier check: implemented; parent flow rows are excluded from line chart generation when children are present
- Summary aggregate charts (the third chart family — sits between overview and detail level)
- Total demand page with a supply line that includes bunkers: implemented
- Difference traces on line charts: LEAP minus ESTO for historical years, LEAP minus 9th for projection years, pre-computed and stored in the manifest
- Series suppression with retained manifest audit rows: implemented
- Economy/dashboard switcher in the header: implemented
- Scope-specific diagnostic pages: implemented and disabled by default pending review
- Optional copy of serving outputs to `docs/` for GitHub Pages publishing: implemented behind `PUBLISH_TO_DOCS`
- Sankey diagrams (deferred — not part of initial production build)
- Full ranking metrics in the manifest (prototype writes `total_abs_value`, `abs_diff`, `pct_diff` only; the full field list is in [Suggested ranking metrics](#suggested-ranking-metrics))
- Correct comparison year pairing: LEAP vs ESTO for years ≤ base year, LEAP vs 9th Outlook for years > base year (see [Sorting and prioritisation](#sorting-and-prioritisation))

## Main design principle

The most important design principle is:

```text
The dataset defines chart membership.
The JSON defines interpretation and presentation rules.
```

This means the dashboard should not ask the JSON file, "which exact graphs should exist?" Instead, it should ask the dataset, "which flow/product combinations exist for this economy, comparison scope, and set of source systems? What is the structural hierarchy of those flows and products?" The dashboard should then generate charts for every valid flow/product pair in the dataset.

The JSON should still be used for things the dataset alone cannot reliably tell us, such as:

- which balance flows (beginning from the highest level) belong on which dashboard page;
- what positive and negative signs mean for each flow type (beginning from the highest level);
- which source/scenario should be used as the primary series for stacked-area charts;
- how deep the hierarchy should be before extra aggregate charts are created;
- how to label or override display names in special cases.

This gives a more maintainable system than either extreme. A fully hand-authored dashboard is too rigid and time consuming to maintain. A fully rule-free dashboard would be too ambiguous.

## Upstream mapping and common ESTO structure

The dashboard is downstream of the mapping process. It should not solve the mapping problem itself. Instead, upstream scripts should create the common ESTO structure. The full mapping system design — how LEAP branches, ESTO flows, and 9th Outlook sectors correspond, how rollups and graph partitioning work, and how the pipeline stages produce the common ESTO structure — is documented in `leap_mappings/docs/mappings_system.md`. This section summarises what the dashboard needs to understand about that upstream process.

The intended upstream process is:

1. Researchers maintain simple mapping sheets, such as LEAP to ESTO and 9th Outlook to ESTO.
2. Code in leap_mappings compiles these simple mappings into `energy_balance_relationships`.
3. Code uses the relationships to infer the safest common ESTO comparison structure for each comparison scope.
4. ESTO-shaped source data is converted into the common ESTO structure.
5. The dashboard consumes the final common ESTO comparison data.

```text
flowchart TD
    A[Simple mapping sheets<br/>Human-maintained inputs]
    A1[LEAP to ESTO]
    A2[9th Outlook to ESTO]
    A3[Other mapping sheets as needed]

    B[Compile mappings<br/>leap_mappings]
    C[energy_balance_relationships]
    D[Infer common ESTO structure<br/>Safest comparison rows by scope]
    E[Apply common structure<br/>to ESTO-shaped source data]
    F[common_esto_comparison_data]
    G[Dashboard<br/>pages, charts, QA files]

    A --> A1
    A --> A2
    A --> A3
    A1 --> B
    A2 --> B
    A3 --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
```

The mapping code should preserve simple human-facing inputs. Researchers should not be asked to manually maintain generated relationship tables, graph IDs, or generated common-row membership. The code should generate those complex tables and QA files.

## Graph partitioning and common denominator logic

The full graph partitioning logic is documented in `leap_mappings/docs/mappings_system.md`. This section covers what the dashboard needs to understand about the generated outputs.

The mapping pipeline uses graph partitioning to find the most detailed safe comparison structure when source aggregates overlap across LEAP, ESTO, and 9th Outlook. The comparison scope determines which source constraints apply — `leap_vs_esto` can remain more detailed than `leap_vs_esto_vs_ninth` where the 9th Outlook is coarser.

The core rule the dashboard must implement:

```text
If any included source represents several ESTO components as one aggregate, those components must stay together for any comparison scope that includes that source.
```

This prevents the dashboard from pretending a coarse source dataset has detail it does not contain. For example, if the 9th Outlook maps all petroleum product sub-codes as one aggregate, the pipeline generates a combined category `07.12-07.17,07.99 Petroleum products` so that LEAP, ESTO, and 9th can all be fairly compared at that level.

From the dashboard's perspective the key consequences are:

- Generated category names must be parsed by their component codes, not matched as free text.
- The dashboard must not assume a fixed set of manually named graph IDs.
- The comparison scope affects how detailed the available categories are — the dashboard should respect the scope in the input data rather than trying to split or merge categories itself.

## Generated common category naming

The naming convention is defined in full in `leap_mappings/docs/mappings_system.md`. This section covers what the dashboard needs to know to classify and display generated labels correctly.

Generated labels follow the pattern `{compressed component codes} {common parent name}`, for example:

```text
07.12-07.17,07.99 Petroleum products
09.01.01,09.02.01 Electricity plants
16.01-16.02 Buildings
16.03-16.04 Agriculture and fishing
```

The dashboard must:

- **Parse component codes from generated labels**, not match rows by free-text name. Code identity is the source of truth for page assignment.
- **Not depend on vague labels** such as `Other petroleum products` for logic — those are display overrides only.
- **Use the stable machine-safe identifier** (`common_row_id`, formed by lowercasing and underscoring the label, prefixed with `common_` or `rollup_`) for joining and traceability, not the display label.
- **Support label overrides** that change display text only, without changing category membership or the underlying ID.

The component membership table (which ESTO rows belong to each generated category) is the actual category definition. The label is only a human-readable summary of that membership.

> todo UPTO HERE — review remaining content below for accuracy

## Dashboard input files

The dashboard consumes data that has already been processed by the upstream mapping pipeline in `leap_mappings`. It does not read raw ESTO or 9th Outlook source files directly.

There are two main input files:

- **`common_esto_comparison_data.csv`** — The primary dashboard input. Contains the common ESTO comparison dataset in long or wide form. This is the output of the `leap_mappings` pipeline and is the only file strictly required to run the dashboard. See [Input data expected by the dashboard](#input-data-expected-by-the-dashboard) for the full column specification.

- **`common_esto_rows.csv`** (optional) — Component membership metadata generated by the `leap_mappings` pipeline. Each row describes which ESTO flow/product pairs make up a common category. The dashboard uses this file to enrich page-assignment QA outputs and the chart manifest with details about what went into each generated category. If this file is absent, the dashboard runs normally but the QA outputs contain less detail.

The sample files in `tests/fixtures/common_esto_dashboard/` were produced by `leap_mappings` for the USA economy and can be used to test the production dashboard without running the full upstream pipeline.

## Input data expected by the dashboard

The preferred long-form dashboard input is:

```text
comparison_scope
source_system
economy
scenario
year
common_flow_code        — used for page assignment and sign semantics
common_flow_name        — derived from the label; used for keyword page matching
common_flow_label       — primary grouping and display column
common_product_code     — required by the loader; not currently used in chart logic
common_product_name     — required by the loader; not currently used in chart logic
common_product_label    — primary grouping and display column
value
```

This is the cleanest form because it already contains the common ESTO structure.

A real row from the sample data looks like:

```text
comparison_scope  : esto_only
source_system     : ESTO
economy           : 20_USA
scenario          : historical
year              : 1990
common_flow_code  : 01
common_flow_name  : Production
common_flow_label : 01 Production
common_product_code : 01.01
common_product_name : Coking coal
common_product_label: 01.01 Coking coal
value             : 2819.5
```

The prototype also supports a wide-form input:

```text
economy
scenario
product
flow
1990
1991
...
2060
```

A real row from the wide-form sample (truncated to a few years) looks like:

```text
economy  : 20_USA
scenario : ESTO historical
product  : 01.01 Coking coal
flow     : 01 Production
1990     : 2819.5
1991     : 2686.3
...
2023     : 1592.9
```

The wide-form loader melts the year columns into long form and splits labels such as `LEAP Target` into:

```text
source_system = LEAP
scenario = Target
```

Where the wide file does not include `comparison_scope`, the workflow assigns a default comparison scope from the dashboard config.

New scenarios are added by updating `config/common_esto_dashboard/series_config.json`. For example, adding a `LEAP EED` entry there means the dashboard will include it automatically on every line chart where matching data exists in the input file. No other code changes are needed — the chart generator picks up all configured visible series from the dataset.

## Dataset filtering

After loading, the workflow filters the dataset by:

- comparison scope;
- economy;
- year range;
- visible source/scenario series.

Visible series are configured separately so the same input dataset can support several dashboard views. For example, the dashboard can show:

```text
ESTO Historical
LEAP Reference
LEAP Target
LEAP EED
NINTH Reference
NINTH Target
```

The full list is configurable via `config/common_esto_dashboard/series_config.json`. Additional LEAP scenarios can be added there without any code changes. A smaller subset can also be configured if a particular dashboard view should be less crowded.

## Sign semantics

The dashboard preserves the signed balance values. It does not flip signs by default.

Instead, it attaches sign metadata based on the flow or sector. This is important because the same positive or negative sign can mean different things in different parts of the energy balance.

It will avoid mixing signs and instead graph data of different signs in different charts, but it will not change the original sign of the data. The dashboard should explain what the signs mean in hover text and chart notes. When calculating aggregates that combine positive and negative values, the dashboard should preserve the meaning of the signs and not simply sum absolute values. For example, Total primary energy supply should be the sum of signed values across production, imports, exports, stock changes, and losses — not the sum of their absolute values — so that the balance equation is preserved.

Current sign meanings are:

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

The sign metadata is used for:

- chart hover text;
- chart title notes;
- sign QA summaries;
- future Sankey direction rules.

This design avoids hiding the original balance convention while still helping dashboard users understand what the signed values mean.

## Page and section assignment

The dashboard assigns rows to pages using a small set of configurable rules. The rules should be code-aware, not just text-aware.

A generated label can contain several codes or ranges, such as:

```text
08,08.01-08.04,08.99 Transfers
```

That one is for the Transfers page in the dashboard.

The page-assignment logic must parse those codes and classify the row based on the component code identity. The current rule is:

```text
Code identity wins over wording.
```

For example:

```text
Any generated/common row containing an 08 component is either
-> Other transformation page
-> or Transfers section
depending on whether a transfers section is wanted or if it is just put into Other transformation. This is also a config choice.   
```

This is true even if the display label includes words like `Refinery and blending`. The component code `08` means the row belongs with Transfers for dashboard organisation.

Example page rules:

```text
01, 02, 03, 06, 07, 11 -> Supply
04, 05 -> Bunkers
18, 19, 10.01.01, 9.01, 9.02 -> Power
08 -> Other transformation / Transfers
09.07, 10.01.11 -> Refining
09, 10.01, 10.02 -> Other transformation fallback
14 -> Industry
15 -> Transport
16.01, 16.02 -> Buildings
16.03, 16.04, 16.05 -> Other demand
17 -> Non-energy use
```

These rules should be ordered by priority. More specific rules should run before broad fallback rules. The dashboard should write a `page_assignment_summary.csv` file so the user can check where each common/generated flow row was placed.

## Chart generation logic

The dashboard generates charts from the common flow and product structure in the filtered dataset.

There are two main chart types:

1. aggregate stacked-area charts;
2. individual line charts.

### Aggregate stacked-area charts

Area charts are used to show the composition of high-level flow groups. They are useful for seeing which products make up a sector or balance flow.

The current intended rule is:

```text
If a page has flow hierarchy chains deeper than 2 levels:
  create area charts for the first 2 hierarchy levels.
Otherwise:
  create area charts for the first 1 hierarchy level.
The user can reserve the ability to show charts for the 3rd level of a 4+ level hierarchy. But its likely it will not provide useful info, so by default it is not enabled.
```

For example, a deep transformation hierarchy may produce area charts for both:

```text
09 Transformation
09.01 Main activity producer electricity plants
```

A simpler page may only produce area charts for:

```text
15 Transport
```

The source/scenario used for the stacked-area composition should be configurable. The current prototype uses a primary source/scenario, such as `LEAP Target`, for area-chart composition. The reason is that stacking all source/scenario combinations in one area chart would be visually confusing.

### Individual line charts

For every unique flow/product pair, the dashboard generates a line chart.

The line chart compares all visible source/scenario series. For example, a single chart might show:

```text
ESTO Historical
LEAP Reference
LEAP Target
NINTH Reference
NINTH Target
```

This is the main replacement for manually authored graph IDs. If the dataset contains a flow/product pair, and the row is within the selected economy/scope/series filters, the dashboard can create the line chart automatically.

## Chart manifest

Every dashboard run should create a chart manifest. This file is important because the dashboard is generated automatically. The manifest explains what was generated.

Expected fields include:

```text
page_key
page_label
chart_id
chart_type
chart_title
common_flow_label
common_product_label
row_count
source_systems
scenarios
sign_note
```

The manifest is the main audit output for chart generation. It replaces the old practice of manually reading a large graph JSON file to understand what the dashboard contains.

## QA outputs

The dashboard workflow should create supporting files that make the automatic decisions auditable.

Current or planned QA outputs include:

```text
chart_manifest.csv
page_assignment_summary.csv
sign_semantics_summary.csv
```

Upstream common-structure QA should include:

```text
qa_common_esto_structure_summary.csv
qa_common_esto_components_missing_from_structure.csv
qa_common_esto_duplicate_components.csv
qa_common_esto_source_aggregates_split.csv
qa_common_esto_rollup_explanations.csv
qa_common_esto_unresolved_partial_coverage.csv
qa_common_esto_total_check.csv
```

The dashboard should not silently hide problems. If a row cannot be assigned to a page, it should be placed on an `Unassigned` page and flagged. If signs do not match the expected convention, the sign summary should report this. If a generated common category has unclear naming, the common-structure QA should flag it before dashboarding.

## Sankey extension plan

A Sankey diagram can be built from the common ESTO comparison dataset, but it should be described carefully.

The dataset has enough information for a useful balance-structure Sankey because it contains:

```text
economy
source_system
scenario
year
flow
product
value
sign semantics
```

The Sankey should be treated as an energy-balance structure diagram, not as a fully physical process-flow diagram. Energy balances can show how much coal went into transformation and how much electricity came out, but they do not always prove the exact physical routing from one input fuel to one output fuel unless the transformation data is detailed enough.

A first Sankey version should use deterministic rules:

```text
Production, imports, stock draw, transfers in
  -> available supply by product

Available supply by product
  -> transformation input / direct final use / exports / bunkers / stock build / losses

Transformation input
  -> transformation output

Transformation output
  -> final demand / exports / losses
```

The Sankey should use absolute values for link widths but preserve signed value and sign interpretation in hover text.

AI can help define and test the routing rules, but the dashboard should not rely on AI to invent links at runtime. The final Sankey should be generated by deterministic code and checked with balance QA.

## Why not use AI dynamically for chart structure?

AI is useful for designing rules, checking confusing cases, and generating documentation. It should not be used as the live chart-generation engine.

The dashboard should be deterministic because:

- results need to be reproducible;
- QA files need to explain every generated chart;
- researchers need to debug mapping issues from stable outputs;
- the same input should produce the same dashboard every time;
- automated deployment should not depend on model judgement at runtime.

AI can help write and refine the rules, but the rules should then be implemented as code and configuration.

## Repository structure

The production repository uses this structure:

```text
AGENTS.md
README.md
codebase/
  common_esto_dashboard_workflow.py
  common_esto_dashboard_data.py
  common_esto_dashboard_renderer.py
  common_esto_dashboard_output_layout.py
config/common_esto_dashboard/
  common_esto_dashboard_template.json
  series_config.json
tests/fixtures/common_esto_dashboard/
  common_esto_comparison_data_sample.csv
  common_esto_rows.csv
outputs/
  common_esto_dashboard/<economy>/
    dashboards/
    chart_bundles/
    supporting_files/
```

The main scripts are:

```text
codebase/common_esto_dashboard_workflow.py
```

Workflow entry point. Loads configuration, reads input data, filters rows, applies sign semantics, calls the renderer, and writes supporting files.

```text
codebase/common_esto_dashboard_data.py
```

Loads long or wide data, normalises it into common long format, splits combined scenario labels, filters by scope/economy/year, applies visible-series filters, and attaches sign metadata.

```text
codebase/common_esto_dashboard_renderer.py
```

Assigns rows to pages, parses generated code expressions, chooses area-chart groups, builds Plotly charts, writes chart bundles, writes pages, writes the dashboard index, and produces chart/page manifests.

```text
codebase/common_esto_dashboard_output_layout.py
```

Builds standard output paths for each economy.

## Configuration files

The dashboard currently uses two main config files.

### `config/common_esto_dashboard/common_esto_dashboard_template.json`

This file should define:

- dashboard title;
- default comparison scope;
- dashboard mode;
- automatic chart-generation settings;
- sector/page rules;
- sign semantics.

It should not list every chart manually.

### `config/common_esto_dashboard/series_config.json`

This file should define which source/scenario series are visible and how they are displayed. For example:

```text
ESTO Historical
LEAP Reference
LEAP Target
NINTH Reference
NINTH Target
```

This separation is useful because page/chart logic and series display logic change at different times.

## Running the dashboard

A typical local run is:

```powershell
cd C:\Users\Work\github\leap_dashboard
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

Optional environment variables can override default inputs:

```bash
COMMON_ESTO_INPUT_DATA_PATH=/path/to/common_esto_comparison_data.csv
COMMON_ESTO_ECONOMY=20_USA
COMMON_ESTO_COMPARISON_SCOPE=leap_vs_esto_vs_ninth
```

The expected output is:

```text
outputs/<economy>/dashboards/index.html
outputs/<economy>/chart_bundles/*.json
outputs/<economy>/chart_bundles/*.js
outputs/<economy>/supporting_files/chart_manifest.csv
outputs/<economy>/supporting_files/page_assignment_summary.csv
outputs/<economy>/supporting_files/sign_semantics_summary.csv
```

## Recommended development workflow

>todo check this is all relevant and up to date including a lot of the stuff above sincw the last todo comment

The recommended workflow for improving the dashboard is:

1. Start with a real `common_esto_comparison_data` extract for one economy.
2. Run the dashboard.
3. Review `page_assignment_summary.csv` first.
4. Fix page rules where generated rows land on the wrong page.
5. Review `sign_semantics_summary.csv`.
6. Fix sign rules if expected sign conventions are wrong.
7. Review `chart_manifest.csv`.
8. Suppress or group charts that are too noisy.
9. Open the dashboard and check whether the generated page structure is useful.
10. Only then adjust visual layout or chart styling.

This order matters because layout improvements are less useful if the generated row/page/chart logic is wrong.

## Design decisions

The following decisions have been made for the production build. One open question remains.

### Resolved

**1. Area chart hierarchy: flow, not product.**
Area charts follow flow hierarchy — they show product composition within a flow group (e.g. `09 Transformation` stacked by product). Product hierarchy charts across flows are not meaningful in a balance structure and are not generated. The prototype already implements this correctly.

**2. Parent and child rows: do not double-chart.**
When a parent flow (e.g. `09 Transformation`) and a child flow (e.g. `09.01 Electricity plants`) both exist in the dataset, the parent appears only as an area overview chart. Child rows get line charts. The production renderer implements this frontier check so parent rows are excluded from line chart generation when their children are present.

**3. Suppressing tiny or empty series: threshold with audit trail.**
Charts where the total absolute value across all years falls below a configurable threshold (e.g. < 1 PJ) are suppressed from display, but are still written to the chart manifest with `suppressed: true`. They are never silently dropped. This ensures data-quality problems remain visible in QA outputs even when charts are hidden.

**4. Showing differences directly: extra traces, not separate charts.**
Difference views (LEAP minus ESTO for historical years, LEAP minus 9th for projection years) are added as optional extra traces on existing line charts, not as a separate chart type. Differences are pre-computed and stored in the chart manifest so no recalculation is needed in the browser. This is a planned feature, not yet implemented.

**5. Sankey: deferred.**
Sankey diagrams are deferred and are not part of the initial production build. The routing rules need to be designed separately and should not block the main dashboard build.

**6. Sections within pages: yes, config-driven.**
Page rules support explicit sections within pages (e.g. `Other transformation > Transfers`). This is already partially implemented — the `08` transfer rule assigns rows a `section_key` separate from `page_key`. This pattern should be applied consistently to all pages via configuration. No code changes are required, only config.

### Repository placement

**7. Production location.**
Resolved on 2026-06-27: the production modules live directly in `codebase/`.
The duplicate test pack was removed. Historical comparisons use
`C:\Users\Work\github\leap_dashboard_legacy`.

## Historical production build plan

This section records the sequence used to build the current production dashboard. Retain it as design history; use the current-status section and decision log for implementation status.

### Phase 1 — Core correctness

These are fixes to known bugs or gaps in the prototype. Nothing new should be built until these are in place, because they affect the correctness of every chart.

**1.1 Frontier check for parent/child rows.**
When a parent flow and one or more of its children both appear in the dataset, the parent row must be excluded from line chart generation. Currently the prototype generates a line chart for every flow/product pair, which double-counts parent rows. The fix is to detect, before chart generation, whether any child rows exist for a given flow code, and if so, skip the parent for line charts (it still gets an area chart).

**1.2 Correct comparison year pairing in sorting metrics.**
The sorting metrics `abs_diff` and `pct_diff` must use the correct comparison pair per year: LEAP vs ESTO for years at or below the base year, and LEAP vs 9th Outlook for years above the base year. Missing LEAP data for a year must not be treated as zero — that year must be excluded from difference calculations. This affects how charts are ranked when sorting by difference or percentage difference.

### Phase 2 — Missing pages and chart families

These add pages and chart types that are in the design but not yet in the prototype.

**2.1 Total demand page with supply line.**
Add a total demand page that aggregates demand across end-use sectors. Include a total supply line that adds international bunkers to the supply total, so aggregate supply and aggregate demand are directly comparable on the same chart. This page is a top-level summary and does not replace sector-level pages.

**2.2 Summary aggregate charts.**
Add the third chart family that sits between the per-page overview area charts and the individual flow/product line charts. Summary charts show aggregates across a page (e.g. total electricity, total oil demand) and help users navigate before drilling into detail charts.

### Phase 3 — Difference traces and suppression

These improve chart quality and data-quality visibility.

**3.1 Difference traces on line charts.**
Add optional difference traces to existing line charts: LEAP minus ESTO for historical years, LEAP minus 9th Outlook for projection years. Differences are pre-computed during chart generation and stored in the chart manifest. No browser-side recalculation is needed. These traces are off by default and toggled via the Plotly legend.

**3.2 Series suppression with audit trail.**
Charts where the total absolute value across all years falls below a configurable threshold are suppressed from display but written to the manifest with `suppressed: true`. The threshold value should be a config parameter (e.g. 1 PJ). Suppressed rows are never silently dropped.

### Phase 4 — Publishing

**4.1 Automatic docs/ copy after each run.**
After each workflow run, copy the required dashboard files from `outputs/<economy>/` to `docs/<economy>/`. Only the files needed to serve the dashboard are copied:

```text
outputs/<economy>/dashboards/*.html    -> docs/<economy>/dashboards/
outputs/<economy>/chart_bundles/*.js   -> docs/<economy>/chart_bundles/
outputs/<economy>/chart_bundles/*.json -> docs/<economy>/chart_bundles/
```

Supporting files (CSV, page-assignment summaries, sign summaries, chart manifests) stay in `outputs/` only. The user then commits and pushes `docs/` to publish.

### Phase 5 — Deferred

These are not part of the initial production build and should not block earlier phases.

- **Sankey diagrams:** routing rules need separate design work.
- **Economy/dashboard switcher:** add a header control to switch between economy dashboards without navigating away.
- **Scope-specific charts:** charts tailored to `leap_vs_ninth` or sector detail available only in LEAP (e.g. transport subsectors, datacentres).

## Acceptance criteria for the dashboard plan

A mature version of the new dashboard should satisfy these criteria:

1. It reads the final common ESTO comparison dataset directly.
2. It does not require `relationship_id -> graph_id` links.
3. It does not require a JSON file listing every graph.
4. It supports generated common categories with code expressions and ranges.
5. It assigns generated rows to pages based on component code identity and priority rules.
6. It preserves signed balance values.
7. It explains sign meanings by flow/sector.
8. It generates aggregate area charts automatically.
9. It generates individual line charts automatically.
10. It compares configured source/scenario series on each line chart.
11. It writes chart, page-assignment, and sign QA outputs.
12. It has an unassigned/fallback page so rows are not silently lost.
13. It can later support Sankey diagrams through deterministic balance-routing rules.
14. It remains close to the original energy-balance style while reducing manual dashboard maintenance.

## Final concept

The new dashboard should be understood as a reporting layer over the common ESTO comparison structure.

The common ESTO process decides what can be fairly compared. The dashboard then visualises those common rows in a consistent, auditable way.

The intended final relationship is:

```text
Mapping code decides category membership.
Dashboard code decides how to display those categories.
Config files explain ambiguous presentation rules.
QA files make every automatic decision checkable.
```

That separation is what should make the system easier to maintain as the LEAP mapping process evolves.

## Dashboard page and chart structure

The dashboard should keep the existing page-based design. It should not become a general-purpose BI tool with many controls. Most interactions that users need, such as changing the visible years, zooming into a period, hiding a line, or inspecting a value, can already be handled inside Plotly charts. Adding too many dashboard-level controls would make the dashboard harder to understand and harder to maintain.

The dashboard should instead remain organised around a fixed set of pages and sections that follow the energy-balance structure. Each page should show a clear set of related charts. Users should be able to skim the page, jump between subsections, and inspect individual charts as needed.

The main new interactive feature should be chart sorting. Within a page or section, users should be able to sort charts by:

```text
- size over the selected/full year range;
- absolute difference between datasets over the year range;
- percentage difference between datasets over the year range.
```

This sorting is more useful than a large control panel because the main problem is not changing the chart type. The main problem is finding which charts matter most among many automatically generated charts.

Two rules must be respected when computing sorting and difference metrics. First, missing LEAP data must not be treated as zero — if LEAP has no value for a given year, that year should be excluded from the difference calculation rather than being counted as a full divergence from the comparison dataset. Second, the comparison pairing should follow the balance convention: LEAP should be compared against ESTO historical data for years at or before the base year, and against 9th Outlook data for years beyond the base year. Mixing these pairings across periods would inflate or mask differences depending on which dataset covers which period.

### Overall page layout

Each dashboard page should follow the same broad structure:

```text
1. Sticky page header
2. Economy/dashboard switch
3. Main page navigation chips
4. Section jump navigation
5. Optional visible note
6. Page-level overview charts
7. Section-level chart groups
8. Detailed chart cards
9. Lazy-loaded Plotly chart bundles
```

The purpose of this structure is to keep the dashboard close to the existing dashboard style while allowing the chart list to be generated automatically from the common ESTO comparison dataset.

### Sticky header and navigation

Each page should have a sticky header. The header should show:

```text
- the page title;
- the selected economy;
- the economy/dashboard selector;
- navigation chips for the major dashboard pages;
- section jump links for the current page;
- a collapse button for reducing header height.
```

The major dashboard pages should remain close to the existing structure:

```text
- About
- Buildings
- Bunkers
- Industry
- Transport
- Other demand / Others
- Power
- Refining
- Other transformation
- Transfers, if not in Other transformation
- Supply
- Total demand
```

This gives the user a stable mental model. Even if the underlying chart list is generated from the dataset, the user still sees familiar page names and energy-system groupings.

### Section jump navigation

Each page should include section jump links near the top. These should be generated from the section hierarchy on that page.

For a simple page such as Buildings, the section structure might be:

```text
Buildings
  Commercial and public services
  Datacentres
  Residential
```

For a deeper page such as Industry, the section structure might be:

```text
Industry
  Construction
  Manufacturing
    Chemical (incl. petrochemical)
    Food, beverages and tobacco
    Iron and steel
    Machinery
    Non-ferrous metals
    Non-metallic mineral products
    Non-specified industry
    Pulp, paper and printing
    Textiles and leather
    Transportation equipment
    Wood and wood products
  Mining and quarrying
```

The section navigation should show first-level and second-level sections differently, so users can see the page hierarchy without reading the whole page. This is especially useful for large pages such as Industry, Transformation, and Supply.

### Page notes

A page may include a short visible note below the header. This should be used sparingly for important modelling or dashboard context.

Examples:

```text
The Buildings model is currently being rebuilt. ETA June 2026.
```

```text
The Industry model is currently being rebuilt. Non-energy use is expected around the same time, but is not included in this page yet.
```

These notes should not replace documentation. They should only explain why a page may look incomplete, provisional, or unusual.

### Chart cards

Charts should be displayed in cards. Each chart card should include:

```text
- chart title;
- chart subtitle showing the page/section path;
- optional sign note or comparison note;
- queued/loading state;
- Plotly chart area.
```

For example:

```text
Electricity
Buildings > Residential
```

or:

```text
Total
Industry > Manufacturing > Iron and steel
```

This card structure makes it possible to show many charts on one page without losing context. It also makes the dashboard easy to skim.

### Lazy loading

Charts should be lazy-loaded where possible. Large pages may contain many charts, and loading every Plotly figure at once can make the dashboard slow. The page should therefore queue charts and render them as the user scrolls near them.

This keeps the dense-page style available in the frozen legacy repository while making the page practical for larger automatically generated chart sets.

## Main chart families

The dashboard should contain three main chart families.

### 1. Page and section overview charts

Overview charts are the highest-level charts on a page or inside a major section. Their purpose is to show the broad structure of the result before the user inspects individual fuel or sector charts.

The preferred format is:

```text
LEAP data shown as stacked areas
comparison dataset totals shown as lines
```

For example, a transport overview chart might show LEAP transport energy by product as stacked areas, with ESTO and 9th Outlook totals shown as lines.

This chart type is useful because it shows both:

```text
- the composition of the modelled result;
- whether the model total is close to the comparison datasets.
```

These charts should usually be generated at the highest useful level of the common ESTO structure. If the page has a deep hierarchy, the dashboard may generate overview charts for the top two levels. If the page has a shallow hierarchy, it may only generate one overview level.

Examples:

```text
Buildings
  Overview by main buildings subsector

Industry
  Overview by construction, manufacturing, mining
  Manufacturing overview by subsector

Other transformation
  Overview by transformation group
  Transfers shown as a separate section under Other transformation
```

The overview charts should remain relatively few. They are for orientation, not exhaustive detail.

### 2. Detailed fuel/sector comparison charts

Detailed comparison charts are the core transparency layer of the dashboard. They should be generated for each valid common flow/product pair at the finest common detail available in the mapped data.

These charts should normally be line charts. Each chart should show the available dataset/scenario series, such as:

```text
- ESTO historical;
- LEAP reference;
- LEAP target;
- 9th Outlook reference;
- 9th Outlook target.
```

The purpose of these charts is to let users inspect differences at the level where the comparison is actually valid. They should not be removed just because they are small or uninteresting. Their existence is part of the audit trail: users can see that the dashboard has not hidden detailed differences.

However, they should be made easier to browse. This is where sorting is useful.

### 3. Summary aggregate charts

Summary aggregate charts sit between the overview charts and the detailed charts. They are useful where the detailed chart list is too long or where several detailed rows naturally belong together.

These charts should be generated from the same common ESTO structure. They should not require manually maintained graph IDs.

Examples:

```text
- total by fuel within a sector;
- total by sector within a fuel group;
- manufacturing total by subsector;
- buildings total by residential/commercial/datacentres;
- transformation input/output totals;
- supply total by production/imports/exports/stock changes;
- generated common aggregate rows created by graph partitioning.
```

The role of these charts is to summarise related detailed charts without hiding the detailed charts. In other words:

```text
Overview charts show the page story.
Summary charts show where to look.
Detailed charts show the actual mapped series.
```

## Sorting and prioritisation

The main dashboard-level interaction should be sorting.

Within each page or section, the user should be able to sort chart cards by:

```text
- default energy-balance order;
- largest total size;
- largest absolute difference;
- largest percentage difference.
```

The default order should follow the energy-balance hierarchy. This keeps the dashboard readable as a structured report.

The size-based order should rank charts by the total magnitude of the selected series over the full year range, for example:

```text
sum(abs(value)) across all years
```

The difference-based order should rank charts by the difference between a selected model series and a comparison series over the full year range, for example:

```text
sum(abs(LEAP Target - 9th Target)) across all overlapping years
```

or:

```text
sum(abs(LEAP Target - ESTO Historical)) across historical overlap years
```

The percentage-difference order should rank charts by relative difference, while handling small denominators carefully. For example:

```text
sum(abs(LEAP - comparison)) / sum(abs(comparison))
```

Rows with very small comparison totals should either be excluded from percentage ranking or flagged, because percentage differences can become misleading when the base is close to zero.

This sorting feature should not change the data. It should only change the order in which chart cards are displayed.

### Suggested ranking metrics

The chart manifest should store ranking metrics for every generated chart.

Suggested fields:

```text
chart_id
page_key
section_path
chart_type
common_flow_label
common_product_label
default_order
total_abs_value
model_abs_value
comparison_abs_value
absolute_difference_sum
percentage_difference
max_annual_absolute_difference
max_annual_percentage_difference
non_zero_year_count
unexpected_sign_count
ranking_warning
```

These metrics allow the dashboard to sort charts without recalculating everything in the browser. They also make the dashboard more auditable because users can see why a chart was ranked as important.

## Page structure

The dashboard should use fixed pages, but the contents of those pages should be generated from the dataset.

### Demand pages

Demand pages should be organised by sector and subsector. They should mostly contain positive final energy use charts.

Expected pages include:

```text
- Buildings
- Industry
- Transport
- Other demand / Others
- Total demand
```

Each demand page should usually contain:

```text
1. a page note if the model is provisional;
2. section jump links;
3. one or more overview charts;
4. summary charts for important subsectors;
5. detailed fuel charts for each sector/subsector.
```

For Buildings, the page sections should resemble:

```text
Buildings
  Commercial and public services
  Datacentres
  Residential
```

For Industry, the page sections should resemble:

```text
Industry
  Construction
  Manufacturing
    Iron and steel
    Chemical (incl. petrochemical)
    Non-ferrous metals
    Non-metallic mineral products
    Transportation equipment
    Machinery
    Food, beverages and tobacco
    Pulp, paper and printing
    Wood and wood products
    Textiles and leather
    Non-specified industry
  Mining and quarrying
```

For Transport, the page sections should follow the transport structure available in the common ESTO data. This may include road, rail, domestic aviation, domestic navigation, pipelines, non-specified transport, and other transport categories depending on the mapped detail.

For some sectors, LEAP and the 9th Outlook have more detail than ESTO — for example, transport subsectors and datacentres. Where this is the case, a scope-specific comparison (e.g. `leap_vs_ninth` only) may be worth adding alongside the full three-way comparison. This is not yet implemented but should be considered when the transport and buildings pages are reviewed. The process itself is relatively simple — the main challenge will be ensuring the scope-filtered charts are formatted consistently alongside the full three-way charts.

### Transformation pages

Transformation pages should be organised by transformation process rather than by final demand sector.

Expected pages include:

```text
- Power
- Refining
- Other transformation
```

Power should contain electricity and heat output charts, power-sector input charts, own-use/loss charts where available, and relevant aggregate summaries.

Refining should contain oil refinery inputs, refinery outputs, and refinery-related own-use/losses.

Other transformation should contain the remaining transformation categories. Transfers should be kept within Other transformation unless otherwise stated via the config. Any category with an `08` flow/component code should be treated as Transfers, even if the generated label contains words such as refinery or blending. This is because the code identity is the source of truth and `08` represents Transfers in the energy balance.

Transformation pages should pay particular attention to sign semantics:

```text
positive = transformation output
negative = transformation input
```

This sign rule should be visible in chart notes or hover text where useful.

### Supply page

The Supply page should show the parts of the balance that explain how energy enters or leaves domestic supply.

Expected sections include:

```text
- Production
- Imports
- Exports
- Stock changes
```

The Supply page should preserve signed energy-balance values and explain their meaning:

```text
Production:
  positive = domestic production added to supply

Imports:
  positive = imports added to supply

Exports:
  negative = exports removed from domestic supply

Stock changes:
  positive = stock draw, added to supply
  negative = stock build, removed from supply
```

The Supply page should include overview charts by product and detailed line charts for individual products.

Bunkers are kept on a separate page and are not included in supply totals on this page. This means TPES figures shown here exclude international aviation and marine bunkers. Charts and hover text on the Supply page should note this where relevant.

### Bunkers page

The Bunkers page should contain international aviation and international marine bunkers.

Bunkers should use the sign convention:

```text
negative = fuel supplied to international aviation/marine, removed from domestic supply
```

This page should remain separate from domestic transport because bunker fuels are not domestic final energy demand in the same sense as road, rail, domestic navigation, or domestic aviation.

### Total demand page

The Total demand page summarises demand across the end-use sectors. It provides a top-level check of LEAP totals against ESTO and 9th Outlook and does not replace the individual sector pages.

The page contains two area charts:

- **By sector** — LEAP Target demand stacked by sector (Industry, Transport, Buildings, Other demand, Non-energy use), with ESTO and NINTH comparison total lines. Includes a TFC/TFEC Plotly dropdown that hides the Non-energy use sector trace and switches comparison lines accordingly.
- **By fuel** — LEAP Target demand stacked by `common_product_label` across all demand flows, with ESTO and NINTH comparison total lines. Always shows TFC (all demand sectors).

Both charts include a **supply total line** defined as:

```text
supply_total = sum of signed values for codes 01, 02, 03
               (Production + Imports − Exports)
```

Bunkers (codes 04, 05) and stock changes (code 06) are **excluded** from the supply line because they are not recorded in LEAP projection scenarios. Including them would create a break between historical and projection years rather than a valid comparison across the full time series. The gap between the supply line and the demand total in the projection period therefore reflects modelling assumptions about net transformation, own use, and losses rather than a balance error.

#### TFC vs TFEC

- **TFC (Total Final Consumption)** — includes Non-energy use (code 17).
- **TFEC (Total Final Energy Consumption)** — excludes Non-energy use (code 17).

The toggle is implemented as a Plotly `updatemenus` dropdown on the sector chart. Comparison lines are pre-computed for both modes and stored in the figure; no browser-side recalculation is needed.

#### Implementation note

The total demand page is a config-driven bespoke page. It aggregates across sector pages rather than operating on a single assigned page's rows. The parameters (demand page keys, supply codes, excluded sector keys, sector colours) are all driven by the `total_demand_page` section in `config/common_esto_dashboard/common_esto_dashboard_template.json`. See the section [Adding bespoke pages and charts](#adding-bespoke-pages-and-charts) below for the pattern used.

## Adding bespoke pages and charts

Some pages cannot be derived automatically from the page-assignment tree because they aggregate across multiple sector pages or require custom layout logic. The Total demand page is the canonical example. These are implemented as **config-driven bespoke pages**: a Python function reads structured parameters from the template JSON and builds the page from scratch, with no reliance on the auto-generated per-flow loop.

### The pattern

1. **Add a named section to the template.** Give it a clear key (e.g. `total_demand_page`). Record every parameter the function needs: page keys to aggregate, series colors, codes to include or exclude, and any toggle groups. Adding an `"enabled": true/false` flag lets the page be switched off without editing Python.

2. **Write a focused bespoke function in `common_esto_dashboard_renderer.py`.** The function signature should take `assigned_df`, `template`, `series_config`, and `layout` — the same objects the main loop receives — so it has access to the full filtered data and can look up parameters from the config section. The function writes chart bundle files directly via the shared helpers (`_write_bundle`, etc.) and returns a list of manifest row dicts.

3. **Call the bespoke function from `render_dashboard()`.** Register the page key in `page_inventory` before the main loop (so the nav chip appears and the page shows up in the index), then call the function after the main loop and append its manifest rows.

### Guiding an AI agent to create a new bespoke page

Because all parameters live in the JSON template and the Python pattern is consistent, a language model agent can reliably create new bespoke pages from a short brief. Give the agent:

- **What the page should show** — which flows or sectors to aggregate, which source systems to compare, any toggles needed.
- **Where the data comes from** — which `page_key` values in `assigned_df` to filter on, or which flow codes to match directly.
- **The config section key** — the name to use in `common_esto_dashboard_template.json`.
- **A reference implementation** — point the agent to `build_total_demand_page()` as the pattern to follow.

The agent can then: (a) add the config section to the template, (b) write the bespoke function mirroring the pattern, (c) register the page key in `render_dashboard()`. Because the change is isolated to those three locations, the rest of the pipeline is unaffected and the workflow can be re-run immediately to verify output.

### Checklist for a new bespoke page

```text
[ ] Add config section to common_esto_dashboard_template.json with "enabled" flag
[ ] Write build_<page_name>_page() in common_esto_dashboard_renderer.py
[ ] Register page key in page_inventory before the main loop in render_dashboard()
[ ] Call the function after the main loop; extend manifest_rows with its output
[ ] Run the workflow and check the nav chip, chart count, and manifest entries
```

## Relationship to Plotly controls

The dashboard should rely on Plotly for chart-level interaction. Users can already use Plotly to:

```text
- zoom into a year range;
- pan across time;
- show or hide traces using the legend;
- hover to inspect exact values;
- export chart images;
- reset axes.
```

Because these controls already exist inside each chart, the dashboard does not need separate global controls for year range, trace visibility, or chart type. Adding those controls would add complexity without much benefit.

The main dashboard-level control that Plotly does not solve is prioritisation across many charts. That is why sorting by size, difference, and percentage difference should be the main additional interaction.

## Relationship to the JSON configuration

The JSON configuration should not list every chart manually. However, it can still define the stable dashboard structure.

The JSON should be used for:

```text
- page names and order;
- page assignment rules;
- section naming rules;
- sign semantics;
- default chart family settings;
- sorting metric definitions;
- optional display label overrides;
- page notes.
```

The JSON should not be used for:

```text
- manually assigning every flow/product pair to a graph;
- maintaining graph IDs as the main dashboard logic;
- defining every detailed chart one by one.
```

The dataset and common ESTO structure should determine what charts exist. The JSON should determine how those charts are organised and presented.

A useful division of responsibilities is:

```text
common ESTO comparison data = what data exists
chart generator = which charts are generated
JSON config = where charts appear and how pages are labelled
chart manifest = what was actually produced
```

## Why this design is preferred

This design keeps the useful presentation strengths of the frozen legacy repository while improving maintainability.

It keeps:

```text
- fixed pages;
- clear energy-balance structure;
- visible chart cards;
- section jump navigation;
- Plotly chart interaction;
- detailed charts for transparency.
```

It improves:

```text
- automatic chart generation from mapped data;
- support for generated common ESTO categories;
- prioritisation of important charts;
- auditing through the chart manifest;
- reduced dependence on manually maintained graph IDs.
```

The dashboard therefore remains a structured report rather than a generic control-heavy app. The only major new interaction is sorting, because sorting directly solves the main problem created by automatic chart generation: there may be many charts, and users need a quick way to find the largest and most important differences.

## Publishing to GitHub Pages

The dashboard is hosted via GitHub Pages served from the `docs/` folder of the repository. The `outputs/` folder where the dashboard script writes its files is gitignored and is never committed.

To activate GitHub Pages for this repository, go to [https://github.com/asia-pacific-energy-research-centre/leap_dashboard/settings/pages](https://github.com/asia-pacific-energy-research-centre/leap_dashboard/settings/pages), select the branch and set the folder to `/docs`, then press Save.

### Planned: automatic publish copy after each run

A planned feature is a post-run copy step that automatically copies the required dashboard files from `outputs/<economy>/` into `docs/<economy>/` after each workflow run. Only the files needed to serve the dashboard are copied — specifically:

```text
outputs/<economy>/dashboards/*.html   -> docs/<economy>/dashboards/
outputs/<economy>/chart_bundles/*.js  -> docs/<economy>/chart_bundles/
outputs/<economy>/chart_bundles/*.json -> docs/<economy>/chart_bundles/
```

Supporting files (CSV, page-assignment summaries, sign summaries, chart manifests) are not copied to `docs/` — they remain in `outputs/` only. This keeps the committed `docs/` folder small and focused on what GitHub Pages needs to serve.

Once the copy step runs, publishing is just a `git add docs/ && git commit && git push`.
