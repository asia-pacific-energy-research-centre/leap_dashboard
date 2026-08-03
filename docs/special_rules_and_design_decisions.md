# Special rules and design decisions

This is the decision log for `leap_dashboard`. Record rules whose correct behaviour cannot be derived from comparison data, canonical configuration, or the established hierarchy. Keep implementation details in code documentation. Update an existing entry and its history rather than creating a duplicate.

Cross-repository decisions use a `CROSS-###` ID and have one authoritative entry in the repository that owns the implementation. Other affected repositories should link to that entry instead of copying it.

## DASH-001: Use a flow frontier to prevent parent-child double charting

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** `codebase/common_esto_dashboard_renderer.py`; `frontier_flow_labels`; chart manifest; line and area chart generation

### Situation

Common ESTO data can contain a parent flow and its child flows simultaneously. Both are technically valid rows, but rendering all of them as peer line charts repeats aggregate and component values and can imply additional energy.

### Options

- Render every row, preserving raw coverage but exposing overlapping totals as peers.
- Render only parents, losing available detail.
- Render parent flows as area overviews and use a non-overlapping child frontier for line charts.

### Current rule

Use the third option. When children are present, exclude their parent from peer line-chart generation. The parent may remain as an area overview. Flow hierarchy, not product hierarchy, determines the frontier.

### Validation

For every rendered group, verify that no selected line-chart flow is an ancestor of another selected flow. Compare chart-manifest flow keys with source hierarchy coverage and confirm area totals equal the intended child frontier without double counting.

### History

- 2026-06-27: Recorded the implemented frontier rule from the active dashboard plan and renderer.

## DASH-002: Suppress small charts without dropping their audit record

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** `config/common_esto_dashboard/common_esto_dashboard_template.json`; `suppression_threshold`; renderer chart metrics; chart manifest

### Situation

Very small series can make navigation noisy, but hiding them can conceal mapping gaps, unit errors, or legitimate small energy flows. The source data does not define a universally meaningful display threshold.

### Options

- Display every chart.
- Drop charts below a threshold, reducing noise but losing auditability.
- Suppress them from display while retaining a manifest entry and metrics.

### Current rule

Use the third option. The default threshold is `1.0` PJ based on total absolute
value across all years. Suppressed entries remain in the chart manifest with
`suppressed: true`. The threshold remains configuration-owned, but changing it
requires a new all-economy sensitivity review rather than a single-economy
visual preference.

### Validation

The 2026-06-28 sensitivity review covered 21 economies and 10,173 manifest
chart rows. Thresholds of 0, 0.1, 1, and 5 PJ suppressed 0, 455, 954, and 1,563
rows, respectively. At 1 PJ, 9.38% of chart rows were hidden from pages while
remaining in the manifests; the economy-level share ranged from 1.9% to 19.8%.
The corresponding cumulative chart magnitude was 232.128 PJ, compared with
11.105 PJ at 0.1 and 1,876.958 PJ at 5. Suppression does not change comparison
totals or coverage diagnostics.

The cumulative magnitude is a presentation sensitivity measure summed over
chart records, not a unique physical-energy total across the hierarchy.

### History

- 2026-06-27: Recorded the implemented prototype behaviour; retained the numeric threshold as provisional pending all-economy review.
- 2026-06-28: Confirmed the 1 PJ default from the existing 21-economy outputs;
  rejected a higher threshold as a substitute for navigation and grouping on
  genuinely dense pages.

## DASH-003: Make the Common ESTO implementation the sole production dashboard

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Architecture
**Affected areas:** repository layout, production entry point, documentation, and legacy comparison boundary

### Situation

Commit `1984a6bdf592cabb49e9f5d4db0d09be1ffc8004` introduced the Common ESTO
dashboard twice: an agent-transfer test pack under
`test/common_esto_dashboard_agent_pack_transfer_rules/` and an initial copy
under `codebase/common_esto_dashboard/`. The test pack stopped changing after
introduction. The `codebase/` copy subsequently gained fixtures and smoke tests,
fixture refresh tooling, diagnostic-page controls, publication checks,
dashboard switching, all-economy rendering, page-noise analysis, page-status
documentation, and the disabled Sankey routing QA scaffold.

### Current rule

The later production-hardened implementation is authoritative. Its four modules
live directly under `codebase/`, with
`codebase/common_esto_dashboard_workflow.py` as the sole production entry point.
Configuration remains under `config/common_esto_dashboard/`, and tests and
fixtures remain under `tests/`. New implementation work must not be placed in
`test/`.

The frozen legacy repository is
`C:\Users\Work\github\leap_dashboard_legacy`, on branch `legacy-reference`.
Its code boundary is commit `8747ca2bfeece881a34026517589ad9319f66bc4`,
the parent of the introduction commit. No later commit independently modified
legacy-owned files; changes to legacy files inside the mixed introduction
commit were not retained because they alter the frozen visual/reference
boundary rather than constituting isolated later fixes.

### History

- 2026-06-27: Confirmed the introduction boundary from path-addition history,
  separated the frozen legacy repository, promoted the later implementation,
  flattened it into `codebase/`, and removed both duplicate and legacy code from
  the official repository.

## DASH-004: Prefer readable responsive charts over maximum card density

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** overview grid, chart grid, area-chart legends, responsive navigation

### Situation

Four overview cards at desktop width left too little room for Common ESTO
product legends and sign subtitles. Visual comparison showed those elements
overlapping the plot on Industry, Supply, and Buildings pages. On a 500-pixel
viewport, the non-wrapping page navigation also extended beyond the viewport.

### Current rule

Use two columns for overview charts, three columns for ordinary chart grids,
and one column below 600 pixels. Place dense overview legends below the plot
with enough bottom margin to keep titles and data unobstructed. Allow the
mobile page navigation to wrap. Keep every legend series available, using the
Plotly legend scrollbar when the complete product list is longer than the
available card height.

### Validation

Render representative dense and sparse pages at 1440 x 1000 and 500 x 900.
Check that titles, sign notes, axes, and legends do not overlap the plotted
data; navigation must remain reachable without widening the page. The smoke
test also checks the overview legend position and reserved bottom margin.

### History

- 2026-06-27: Confirmed after side-by-side review of legacy and Common ESTO
  Industry, Supply, and Buildings pages; implemented in commit `398d5bc`.

## DASH-005: Energy balance overview uses declared aggregate identities

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Comparison
**Affected areas:** Energy balance overview; Common ESTO metadata loading; total transformation chart

### Current rule

The former Total demand page is presented as the Energy balance overview. It
continues to show the reviewed supply, TFC, and TFEC aggregates and also shows
`Total transformation sector (excluding transfers)`.

Transformation selection is not inferred from display labels. Rows must carry
source-aggregate membership for `Total transformation - no transfers`. LEAP
uses generated rows with `requires_rollup = True`; ESTO and Ninth use exact
parents with `is_exact_row = True`. Parent and generated representations are
comparison alternatives and are never added together for one source series.

### Validation

Confirm the overview manifest contains
`chart__line__total_transformation_no_transfers`, includes all available source
systems, and contains no duplicate `(source, scenario, year, common_row_id)`
rows after applying the source-role rule. Multiple exact component rows may
share one displayed product rollup and are summed within the chart.

### History

- 2026-06-29: Added the configured no-transfers transformation comparison to
  the aggregate overview and renamed its navigation label.

## DASH-006: Rollup modes appear inside the hierarchy tree

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** Mapping diagnostics; All sector rollup structure

### Current rule

Show `EXPANDING` relationships in the sector hierarchy view by default. Provide
one checkbox that adds `NON_EXPANDING` and `DETACHED` targets and display
relationships when the reviewer needs them. Do not restore the former
rollup-mode selector. Place the mode label inside the rollup target box and use
a dotted edge for display membership that is not an ordinary hierarchy edge.

Do not render a second, separate rollup-composition graph below the hierarchy.
Detailed rule membership and reconciliation evidence remain available in the
page tables. This display rule does not change the canonical hierarchy
contract or turn rollup inputs into ordinary structural children.

### Validation

The Power-sector view must show Electricity plants, CHP plants, and Heat plants
under the labelled `EXPANDING` target. The unchecked view must omit
`NON_EXPANDING` and `DETACHED` display relationships; checking the special
rollup control must add them. The page must have no rollup-mode selector and no
separate `REGISTERED ROLLUP COMPOSITION` graph heading.

### History

- 2026-07-29: Confirmed during live review of the 20_USA mapping diagnostics
  prototype.
- 2026-07-29: Refined so NON_EXPANDING and DETACHED display relationships are
  opt-in through one checkbox.

## DASH-007: Hierarchy validation uses one explained diagnostic panel

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** Mapping diagnostics; hierarchy validation

### Current rule

Present final-output hierarchy failures, source/mapping anchor failures,
failure reasons, materiality, and reviewed exceptions in one hierarchy
validation panel. Explain that a hierarchy failure means the tested parent
does not equal its expected accounting frontier within tolerance, or that the
frontier is incomplete; it does not by itself prove that a mapping is missing.

Keep the two validation layers visibly distinct:

- Final output hierarchy compares a Common ESTO parent with its declared
  output children.
- Source/mapping anchor compares a raw source parent with the de-duplicated
  mapped frontier used to represent it.

Rank failed checks by absolute mismatch and show the reason alongside the
values. Keep every numerical failure in that total. An exact, user-confirmed
source issue is review metadata attached to a failed row: it does not turn the
row into a pass, prove the mapping is correct, or prove that the source issue
caused the mapped-anchor failure. Show confirmed and unconfirmed failures
separately when the current artifact provides the explicit review fields.

Apply the selected dashboard economy to the failure table, review table,
exception candidates, and summary cards. If an older artifact lacks the
explicit confirmation fields, state that clearly instead of treating its
legacy boolean flag as confirmation. Do not show a separate table of rows
already visible in the current hierarchy graph.

### Validation

The page must show one hierarchy-validation panel with the two check layers
explained, one materiality-ranked failure table containing failure reasons,
and the reviewed exceptions below it. It must not retain the former separate
Stage 3 failures, anchor mismatches, failure reasons, or current-graph rows
sections.

### History

- 2026-07-29: Confirmed during live review of the 20_USA mapping diagnostics
  prototype.
- 2026-07-29: Clarified that source-issue confirmation is a review
  classification, never a numerical pass, and added strict economy scoping and
  legacy-artifact handling.

## DASH-008: Paired hierarchy trees use compact values

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** Mapping diagnostics; original-versus-mapped hierarchy trees

### Current rule

Use one shared magnitude scale within each original-versus-mapped hierarchy
case and display no more than two decimal places after scaling. Apply the same
formatter to parents, children, mapped components, totals, and residuals for
every source dataset. Continue all validation calculations with the original
unrounded values.

### Validation

The shared context formatter must scale the whole case consistently and emit
at most two decimal places. The rendered note must continue to state that
calculations use unrounded values.

### History

- 2026-07-29: Confirmed during live review of the mapping diagnostics
  prototype.

## DASH-009: A displayed time-series category has one point per year

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Aggregation / presentation validation
**Affected areas:** Common ESTO flow-product detail charts; chart-bundle QA

### Current rule

A detail-card label can represent several distinct Common ESTO component rows.
Before plotting, sum those component values by source system, scenario, and
year so the displayed category has exactly one signed value per year. Do not
connect the component rows sequentially: repeated years create misleading
vertical spikes.

Keep the upstream `common_row_id` contract distinct from this presentation
aggregation. Multiple component IDs under one displayed category are valid;
duplicate source/scenario/year rows for the same component remain an upstream
data-contract issue.

Every emitted line or stacked-line trace must also pass a blocking uniqueness
check on its x values. A chart bundle is not written when a trace still
contains a repeated year.

### Validation

Regression tests cover multi-component displayed categories and deliberate
duplicate-year traces. The 2026-07-30 20USA production render emitted 2,784
line traces across 311 bundled charts with zero repeated-year traces.

### History

- 2026-07-30: Added after repeated component rows produced vertical spikes in
  Power detail charts.

## DASH-010: Energy-balance demand lines use declared TFC/TFEC totals

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Aggregation / presentation validation
**Affected areas:** Energy balance overview; all four demand/supply charts

### Current rule

Use the declared top-level flow `12 Total final consumption` and flow `13 Total
final energy consumption` for TFC and TFEC comparison lines whenever those rows
exist for a source. Use visible demand detail only as a fallback when the
requested aggregate is absent.

Do not calculate a total by adding every displayed demand row. Common ESTO can
legitimately retain parent, child, exact, and generated rollup views together;
adding those views double counts the same demand. The two supply-detail charts
also use flow 12 for their demand comparator, which makes LEAP demand available
for economies still represented by `All demand aggregated`.

### Validation

Regression tests require declared aggregates to override overlapping visible
detail, retain the detail fallback, and add a LEAP TFC comparator to the supply
charts when only the aggregate demand row is available.

### History

- 2026-08-02: Confirmed after China 9th Target TFEC was plotted at 235,190 PJ
  in 2039 while the declared flow 13 value was 86,774 PJ.

## DASH-011: Section aggregates use one non-expanding component frontier

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Aggregation / presentation validation
**Affected areas:** Section-level aggregate-by-flow and aggregate-by-product charts

### Current rule

When an observed `NON_EXPANDING` subtotal and its additive component rows are
both present, plot the subtotal once and remove the covered components for that
source, economy, scenario, year, and common opposite-axis category. Use the
mapping-owned `component_flow_code` or `component_product_code` expression to
identify covered exact codes and inclusive ranges. Keep the alternative detail
frontier when that source observation does not publish the subtotal.

This handles compound subtotals such as `15.01,15.03-15.06 Transport non-road`
without hard-coding transport labels or reconstructing mapping relationships.

### Validation

The regression test covers a compound transport rollup, two covered children,
and unaffected `15.02 Road`. The 2026-08-03 China production render leaves only
Transport non-road and Road in the Transport section aggregate-by-flow stack;
all-economy publication readiness passed and page-noise analysis found zero
flags.

### History

- 2026-08-03: Added after the China Transport stack displayed the non-road
  subtotal together with Domestic air transport, Rail, Domestic navigation,
  Pipeline transport, and Non-specified transport.

## DASH-012: Aggregate demand placeholders remain visible by sector

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Demand-page routing / transitional presentation
**Affected areas:** Industry, Transport, Buildings, Other demand, and Non-energy page routing

### Current rule

Keep standalone Industry, Transport, Buildings, and Other demand pages visible
when their LEAP projection is still supplied by an `All demand aggregated`
placeholder. These are transitional sector rows and should remain reviewable
until detailed LEAP demand branches replace them upstream.

Route the combined `Other sector including non-energy (all demand aggregate)`
row to Other demand. Continue routing an exact code-17 row to Non-energy and
keep that standalone page hidden while it has no usable standalone LEAP
mapping. This is presentation routing only; the dashboard does not split or
recalculate the upstream aggregate.

### Validation

Regression tests require aggregate-only demand pages to remain visible, the
unmapped Non-energy page to remain hidden, the combined placeholder to route to
Other demand, and an exact code-17 row to retain its Non-energy assignment.

### History

- 2026-08-03: Confirmed while reviewing China, where Industry and Buildings
  had valid LEAP placeholder rows but were hidden, and the combined Other-sector
  placeholder was assigned to the hidden Non-energy page.

## DASH-014: Aggregate charts choose one observed common-row frontier

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / aggregate-chart selection
**Affected areas:** Stacked aggregate-by-flow and aggregate-by-product charts

### Current rule

Common ESTO may retain a generated compound flow category and its contained
flows as separate valid views. Within one aggregate dashboard chart, do not add
those overlapping flow views together. For each source, economy, scenario,
year, and product category, prefer an observed compound common flow over common
flows contained by its ranges or component list. If the compound row is absent
for an observation, retain the available detail.

Apply this detached-compound rule only after page routing and only on the flow
axis. A broad transformation flow must not erase Power or Refining rows before
their higher-priority page rules claim them. Compound product labels are normal
disjoint dashboard categories and do not imply that contained product codes
are additive alternatives. Explicit metadata-backed NON_EXPANDING product
rollups continue to use their established frontier rule.

This extends the existing NON_EXPANDING-rollup frontier rule to detached or
aggregate-backed common rows that do not carry `is_non_expanding_rollup=True`.
It changes dashboard aggregation only; the upstream rows and detailed line
charts remain available.

### Validation

Regression tests require `16.03-16.05,17 Other sector including non-energy
(all demand aggregate)` to suppress its observed `16.03-16.04` and `16.05`
components in an aggregate chart, while another source without the broad row
continues to use those components. A production USA render must show only the
combined flow in `Aggregate by flow: Other demand`.

### History

- 2026-08-03: Confirmed from the USA Other demand chart. The generated
  all-demand category is structurally compound but is not flagged as a
  NON_EXPANDING rollup, so the earlier subtotal-only selector retained it and
  its components together.
- 2026-08-03: Restricted the rule after the global, two-axis implementation
  removed Power and Refining detail before routing and changed the USA 2060
  Transfers total from 2,134 PJ to 8,601 PJ by dropping a negative product.

## DASH-015: Compound-range overview cards include every range endpoint

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / hierarchy-card generation
**Affected areas:** Overview stacked-area cards

### Current rule

When overview discovery encounters a compound common flow such as
`16.01-16.02 Buildings`, close that generated subtree over every common
category contained by the compound expression. Do not treat only the first
range endpoint as the card's scope.

Source-specific frontiers remain authoritative. For Buildings, LEAP can use the
combined Buildings row while Ninth uses Commercial and Residential. If this
closed frontier duplicates an already generated parent card, keep only the
first card; retain genuinely distinct detail cards such as Residential.

### Validation

Regression tests require the incomplete `16.01`-derived Buildings card to be
deduplicated. The production USA Buildings overview must contain `16 Buildings`
and `16.02 Residential`, with the all-Buildings frontier including Ninth
Commercial and Ninth Residential.

### History

- 2026-08-03: Confirmed from the USA Buildings overview. The dashboard
  canonicalized `16.01-16.02` to `16.01`, titled that partial subtree with the
  compound label, and consequently omitted Ninth Residential from the card.
  The upstream Ninth Residential mapping itself was present and correct.

## DASH-016: Mixed-depth compound flows remain valid overview frontiers

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / hierarchy-card generation
**Affected areas:** Other transformation overview stacked-area cards

### Current rule

Determine a compound flow's overview level from every expression endpoint, not
only its first canonical code. A row such as `09,09.03 Total transformation -
no transfers` reaches level two through `09.03` and is therefore a valid
level-two frontier for the code-09 overview. Its own row must not disappear and
leave only deeper gas-processing descendants in the card.

### Validation

Regression tests require the mixed-depth row to be the source-specific code-09
frontier. The production USA overview must contain all five dataset totals and
the complete transformation product stack.

### History

- 2026-08-03: Confirmed after the Other transformation overview rendered only
  gas works even though 5,133 rows for the broad transformation category were
  present in the page assignment summary.

## DASH-017: Comparison lines expose available base-year calibration gaps

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / time-series boundary
**Affected areas:** Aggregate totals and flow-product line charts

### Current rule

Show LEAP and Ninth comparison-line values at the configured base year whenever
those values exist. Hide their earlier backcast years. Continue using ESTO for
the stacked historical area through the base year and LEAP for the stacked
projection only after it, so the fill boundary remains unchanged.

This intentionally allows ESTO, LEAP, and Ninth to display different values at
the same base-year x coordinate. That visible gap is calibration evidence and
must not be concealed by starting projection lines one year later.

### Validation

Regression tests require aggregate total lines and individual flow-product
lines to include LEAP and Ninth at the base year while excluding their earlier
years. A point available only before the base year remains non-renderable.

### History

- 2026-08-03: Confirmed because the difference between ESTO and model datasets
  at the handoff year is important diagnostic information.

## End-to-end run report

Append a dated subsection after each end-to-end run. Report:

- newly discovered decisions;
- unresolved decisions blocking correct output;
- provisional assumptions used to continue;
- rules that should move into configuration;
- rules that should become automated validation;
- the next decisions requiring human guidance.

Also report coverage, dropped rows, source-versus-output totals, hierarchy consistency, mapping cardinality inherited from upstream data, and semantic correctness of grouping and presentation. A successful render is not evidence that the published comparison is correct.

### 2026-06-27 migration and visual-review run

- No new mapping or grouping semantics were introduced.
- DASH-004 was discovered and confirmed through rendered-page comparison.
- At the time of this run, the 1 PJ suppression threshold had not been
  confirmed from the USA fixture; the 21-economy review on 2026-06-28 resolved
  DASH-002.
- The 20_USA fixture rendered 860 charts from 18,366 filtered rows; focused
  tests and publication readiness passed.
- The upstream one-economy batch path separately rendered 850 charts from
  19,103 visible rows. Its `leap_mappings` worktree was dirty, so this run
  validates execution and presentation but is not a reproducible data baseline.
- Existing all-economy page-noise output still flags 23 pages. USA Industry
  (228 charts) and Supply (212 charts) require future aggregate-first or
  section-navigation review; this should be configuration-driven and must not
  remove manifest coverage.
- Legacy regeneration is blocked by current external mapping cardinality, so
  tracked legacy pages are the comparison baseline.
