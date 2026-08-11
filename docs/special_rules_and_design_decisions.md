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

Use the third option. When children are present, exclude their parent from peer line-chart generation and replace a within-page parent with an aggregate-by-product area summary. Build that summary from a source-specific, non-overlapping frontier: use the parent for a dataset that publishes the parent, and the available children for a dataset that publishes only children. Top-level roots remain page-overview concerns because their descendants can be routed across several pages; do not create a parent summary when its descendants cross different semantic page sections. Flow hierarchy, not product hierarchy, determines the frontier.

### Validation

For every rendered group, verify that no selected line-chart flow is an ancestor of another selected flow. Compare chart-manifest flow keys with source hierarchy coverage and confirm area totals equal the intended child frontier without double counting.

### History

- 2026-06-27: Recorded the implemented frontier rule from the active dashboard plan and renderer.
- 2026-08-10: Made the parent summary a general subsection rule, including Gas processing and Coal transformation on Other transformation, while retaining source-specific frontiers and section-boundary safeguards.

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
continues to show the reviewed supply and TFC aggregates and also shows `Total
transformation sector (excluding transfers)`. TFEC remains temporarily disabled
under DASH-010 until non-energy use can be separated from aggregated
Other-sector LEAP demand.

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

Use declared top-level flow `12 Total final consumption` for the TFC comparison
line whenever that row exists for a source. Use visible demand detail only as a
fallback when the requested aggregate is absent.

Flow `13 Total final energy consumption` is temporarily unavailable for the
production presentation. LEAP currently carries non-energy use inside an
aggregated Other-sector demand category, so the dashboard cannot extract and
subtract that amount reliably to present TFEC. Retain flow 13 upstream and in
diagnostic evidence, but do not show a production TFEC comparison or silently
substitute an incomplete detail sum. Record it as explicitly disabled with this
dependency; enable it after the non-energy boundary is separately available
and validated.

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
- 2026-08-08: Clarified the current operational boundary. Flow 13 is
  intentionally disabled because non-energy use cannot yet be separated from
  aggregated Other-sector LEAP demand; the dashboard must not present an
  incomplete TFEC fallback while that dependency remains.

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

When a visible page uses one of these placeholders, show a page-top note naming
the placeholder branch and the affected page sector. The guide's page-content
table must use the published source-to-Common mappings to show which native
ESTO, LEAP, and 9th flow/product categories feed each visible Common category;
do not reconstruct that provenance from display-label similarity.

Do not apply this exception to Bunkers. International bunkers are outside the
four domestic demand placeholders and remain hidden when their LEAP branch is
aggregate-only.

Route the combined `Other sector including non-energy (all demand aggregate)`
row to Other demand through its exact, temporary routing special case.
Continue routing an exact code-17 row to Non-energy. Hide the standalone page
only while it has no usable standalone LEAP mapping; it must appear
automatically when source-specific code-17 data becomes available. This is
presentation routing only; the dashboard does not split or recalculate the
upstream aggregate.

### Validation

Regression tests require aggregate-only demand pages to remain visible, the
unmapped Non-energy page to remain hidden, the combined placeholder to route to
Other demand, and an exact code-17 row to retain its Non-energy assignment and
become visible once it contains LEAP data.

### History

- 2026-08-03: Confirmed while reviewing China, where Industry and Buildings
  had valid LEAP placeholder rows but were hidden, and the combined Other-sector
  placeholder was assigned to the hidden Non-energy page.
- 2026-08-03: Narrowed the exception after visual review showed that a global
  aggregate-page override also exposed Bunkers without a usable LEAP projection.
- 2026-08-09: Replaced rule-order routing with boundary-safe, most-specific
  page roots; isolated the combined placeholder as an exact special case; and
  made Non-energy visibility depend on usable LEAP coverage rather than a
  permanent skip list.
- 2026-08-10: Added visible page-top placeholder notices and mapping-backed
  page-content provenance tables to the routed chart-page guides.
- 2026-08-11: Extended the same placeholder presentation to Power when the
  upstream source-branch fallback audit records an interim power branch as
  retained. Merely having an interim mapping is not enough to trigger the
  warning; the audit must show that interim values are actually in use during
  the dashboard period.
- 2026-08-11: Passed that run-specific fallback audit through the portable and
  HF dashboard-from-export path so hosted renders apply the same warning rule
  as maintainer renders.

## DASH-013: Gas-works own use is shown only in the shared transformation boundary

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / comparison-boundary filtering
**Affected areas:** Other transformation overview and detail charts

### Current rule

Do not plot `10.01.02 Gas works plants` as a standalone own-use comparison.
LEAP does not expose that quantity separately in its balance results; it is
already part of `09.06.01 Gas works plants (including own use)`, which is the
valid shared comparison boundary. Keep the other code-10 own-use and loss rows
available.

Synthetic overview prefixes must use their configured ESTO hierarchy names:
`10 Losses and own use` and `10.01 Own use`. They must not inherit the name of
the first available descendant.

### Validation

Regression tests require the standalone `10.01.02` row to be filtered while
retaining the boundary-adjusted transformation row and unrelated own-use rows.
They also require the code-10 overview cards to use the hierarchy labels.

### History

- 2026-08-03: Confirmed after the China Other transformation overview labeled
  both synthetic prefixes as Gas works plants and exposed the unextractable
  own-use detail as a separate comparison.

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

## DASH-018: Refinery own use appears only in the inclusive comparison boundary

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / comparison-boundary filtering
**Affected areas:** Refining overview and detail charts

### Current rule

Do not display `10.01.11 Oil refineries` as a standalone dashboard comparison.
LEAP does not publish refinery own use separately; its value is part of the
refinery process. The mapping system already folds ESTO and Ninth `10.01.11`
into `09.07 Oil refineries (including own use)`, which is paired with LEAP's
`09.07 Oil refineries` as the shared boundary.

Retain that inclusive refinery comparison and suppress the redundant code-10
component. This is the same presentation principle used for gas-works own use;
the mapping and its `NON_EXPANDING` rollup remain owned upstream.

### Validation

Regression tests require the inclusive `09.07` row to survive dashboard flow
exclusions while standalone `10.01.11` is removed. A production USA Refining
page must not contain a `10 Losses and own use` overview card or a standalone
`10.01.11 Oil refineries` detail group.

### History

- 2026-08-03: Confirmed after the Refining page showed an ESTO/Ninth-only own-use
  card beside the valid inclusive refinery comparison, with no LEAP series.

## DASH-019: Aggregate frontiers remain fixed across a time series

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Aggregation / zero-row handling
**Affected areas:** Aggregate charts containing generated or NON_EXPANDING rows

### Current rule

Choose a common-row frontier once for each comparison scope, source, economy,
and scenario series. Do not choose it independently for each year. If a
generated or NON_EXPANDING row is observed anywhere in that series, keep its
frontier authoritative in years where the row is absent because its components
cancel to exact zero; treat that absence as zero instead of restoring an
overlapping detail row.

Sources that never publish the aggregate row still retain their additive detail
frontier. This preserves source-specific comparison boundaries without allowing
long-form zero suppression to change the boundary from one year to the next.

### Validation

Regression coverage requires a refinery inclusive row observed with a
floating-point residual in one year to suppress its ordinary refinery-gas
detail in both that year and a later exact-zero year. The production USA Ninth
Target refinery total must be about `-3,605.34 PJ` in 2027, not the erroneous
`-2,981.39 PJ` fallback value.

### History

- 2026-08-03: Confirmed after exact cancellation between Ninth refinery-gas
  output and own use caused the Refining aggregate to alternate by roughly
  `624 PJ` depending on whether a zero row survived long-form serialization.

## DASH-020: Aggregate-placeholder demand overviews require LEAP coverage

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Demand-page overview eligibility
**Affected areas:** Buildings, Industry, Transport, and Other demand overviews

### Current rule

The four demand pages allowed to remain visible while LEAP uses an
`All demand aggregated` placeholder may only display overview area cards whose
selected frontier contains the configured primary LEAP source. Do not present
an ESTO/Ninth-only child card as a three-dataset overview comparison.

Keep those child categories in their detail groups. When detailed LEAP rows
become available upstream, their overview cards become eligible automatically.
Non-demand pages are unaffected by this rule.

### Validation

Regression coverage requires a Buildings overview selection containing only
ESTO and Ninth Residential rows to be rejected, the same selection with LEAP
to be accepted, and an equivalent non-demand selection to remain accepted.
The production USA overview manifest must retain only the broad `16 Buildings`,
`14 Industry sector`, `15 Transport sector`, and `16 Other sector` demand cards,
while retaining Residential and Industry child detail groups.

### History

- 2026-08-03: Confirmed after hierarchy depth caused Residential, Mining,
  Construction, and Manufacturing to appear as ESTO/Ninth-only overview cards,
  while shallower Transport and Other-demand hierarchies happened not to expose
  equivalent child cards.

## DASH-021: Emissions are derived from a declared factor set and a detail frontier

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Derived-quantity presentation
**Affected areas:** Emissions page; `codebase/common_esto_dashboard_emissions.py`;
`config/common_esto_dashboard/emissions_factor_sets.json`

### Current rule

The Emissions page is derived, not sourced. Every chart is
`final energy demand x emissions factor`, applied to the same demand rows the
sector pages plot, so LEAP, ESTO, and the 9th edition are compared on one
consistent basis.

Four rules make that derivation reproducible:

1. **The factor axis is declared, not assumed.** A factor set names the axis its
   factors are keyed on (`ninth_fuel`, `esto_product`, or `esto_product_flow`).
   The loader resolves that axis onto `common_product_label` - and
   `common_flow_label` when the set is keyed on product/flow pairs - using the
   leap_mappings contract (`ninth_fuel_to_esto`) and the generated
   `esto_to_common_esto_map.csv`. A new factor source with different mapping
   requirements is a config entry, not a code change.
2. **Subfuels collapse onto their parent fuel.** In a fuels/subfuels factor
   file, any subfuel other than the placeholder replaces its parent fuel. A
   parent row carrying the placeholder stands in for that fuel's
   `<fuel>_unallocated` code only when no explicit unallocated subfuel row
   already supplies it; otherwise it is a fuel-level aggregate over rows already
   present and is dropped so its members are not counted twice. Aggregates with
   no mappable code at all (`19_total`, `20_total_renewables`) are dropped and
   reported.
3. **A blank factor means no emissions, not missing data.** Blanks resolve to
   zero, so electricity, heat, hydrogen, and the renewable carriers contribute
   nothing at the point of final use rather than dropping out of a total.
4. **Only one non-overlapping frontier is summed.** Sector pages carry a whole
   flow hierarchy plus generated rollups that span several pages
   (`16.03-16.05,17 Other sector including non-energy`). A row that covers
   another row of the same source and scenario on both axes is dropped, keeping
   the detail. Detail is preferred over aggregate because the aggregates overlap
   each other - `16 Other sector` and `16.03-16.05,17` share `16.03-16.05` - so
   no set of aggregates is guaranteed to partition demand.

Scope is deliberately final energy demand only. Combustion in transformation
and the power sector is excluded, which is why electricity carries a zero
factor here rather than an implied grid intensity. Adding transformation page
keys to `emissions_page.demand_page_keys` would double count against the fuels
those inputs produce.

Conflicts are resolved by declared strategy and reported, never silently
averaged. Several 9th fuels mapping to one ESTO product resolve by
`prefer_specific_then_mean`, which drops residual `_unallocated` contributors
when a specific one exists; ESTO components disagreeing under one common fuel
resolve by `component_conflict_resolution`. Both land in
`supporting_files/emissions_factor_conflicts.csv`.

### Validation

`supporting_files/` must contain `emissions_factor_resolution.csv` (one factor
per common fuel with its contributing 9th fuels and ESTO components),
`emissions_factor_conflicts.csv`, `emissions_dropped_factor_rows.csv`,
`emissions_axis_values_without_factor.csv` (expected empty), and
`emissions_frontier_coverage_check.csv`.

The coverage check compares every dropped aggregate against the detail retained
inside it; a gap above `emissions_page.frontier_coverage_tolerance_pj` means the
detail is incomplete and that source's emissions are understated, and the page
says so in its note. Base-year totals for LEAP, ESTO, and the 9th edition must
agree where all three report the same demand: for 20USA at 2022 all three read
3,443 Mt CO2e.

### History

- 2026-08-06: Added the Emissions page. The first implementation summed every
  demand row and reported 4,838 Mt CO2e for 20USA 2022 against 3,443 for LEAP;
  the gap was parent and child flows counted together, which is what rule 4
  above now prevents.

## DASH-022: Single-boundary overview cards inherit their real comparison label

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** Generated overview area charts; Refining

### Current rule

After the renderer computes each source system's non-overlapping frontier for a
generated overview card, it checks whether every selected label represents the
same canonical flow code and logical name. If so, the card inherits a real
common-flow label from that boundary instead of fabricating a label from the
broader hierarchy prefix. A boundary-adjusted `(including own use)` label is
preferred when both adjusted and unadjusted forms exist.

Explicit `area_chart_flow_labels` configuration remains authoritative. Cards
whose frontier contains different codes or logical names do not inherit a child
label and continue through the existing aggregate-prefix label path. Therefore
this rule fixes the Refining overview without globally renaming all `09`
transformation cards.

The rule changes presentation only. Source-specific frontier membership,
values, mapping output, and comparison scopes are unchanged.

### Validation

Regression coverage requires a `09.07 Oil refineries` / `09.07 Oil refineries
(including own use)` frontier to render under the adjusted real label, while a
frontier containing both oil refining and coal transformation must not inherit
either child label.

### History

- 2026-08-09: Added after the Refining overview was titled `09 Oil refineries`,
  even though no such common mapping row existed and its complete frontier was
  the single `09.07` comparison boundary.

## DASH-023: Signed composition is preserved before category aggregation

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation and aggregation order
**Affected areas:** Signed stacked-area charts; transformation section summaries

### Current rule

Every signed stacked-area chart separates positive and negative observations
before aggregating the category displayed in its legend. Products or flows can
therefore contribute to both the output and input stacks in one year without
their gross activity cancelling into a small net area. Dataset total lines
remain signed net totals and are unchanged.

The rule applies to both product-grouped and flow-grouped area charts. It is
harmless for one-sided demand and supply compositions and necessary for
transformation sections, where positive outputs and negative inputs routinely
share a category.

A section-level `Aggregate by flow` chart is suppressed when its selected,
non-overlapping frontier contains only one effective flow. In that case the
companion product chart already shows the same positive and negative envelope,
so the flow card adds no decomposition. Multi-flow sections retain both charts.

### Validation

Regression coverage requires both product and flow aggregation to retain gross
positive and negative values when their net is smaller. A one-flow Refining
section must render its product aggregate and suppress only its redundant flow
aggregate; multi-flow sections remain eligible for flow charts.

### History

- 2026-08-09: Added after the USA Refining flow aggregate displayed only the
  roughly `-3,400 PJ` net balance while its product companion showed about
  `+33,000 PJ` of outputs and `-36,000 PJ` of inputs.

## DASH-024: Refining publishes the inclusive boundary and ordinary charts omit difference diagnostics

**Status:** Implemented.

The public **Refining** page is based on the comparison boundary
`09.07 Oil refineries (including own use)`. The non-inclusive
`09.07 Oil refineries` row is excluded from dashboard page construction, so it
cannot appear as a second apparently valid section or overview card. The page
name remains the concise presentation label **Refining**; the chip and chart
labels expose the actual inclusive comparison boundary.

The optional `LEAP ... minus comparison` and `LEAP ... minus 9th` traces are no
longer added to ordinary chart legends. The renderer still computes and stores
the historical and projection difference series used by manifest diagnostics,
sorting and audit workflows; only the optional visual traces were removed.

## DASH-025: Other transformation shows inclusive process detail and separate residual operations

**Status:** Implemented.

The **Other transformation** page no longer presents the broad `09 Total
transformation sector`, the combined `10 Losses and own use`, or a section-wide
Other-transformation aggregate. Those totals were unclear and could cross into
the separately owned Power and Refining pages.

Instead, transformation processes are shown as individual charts and their
titles explicitly state `(including own use)`, because LEAP necessarily carries
auxiliary-fuel own use inside its transformation inputs. When upstream Common
ESTO output supplies both plain and inclusive forms, the inclusive boundary is
preferred and the plain duplicate is suppressed.

The same page retains three separate operational sections where data exist:

- **Other energy-sector own use** contains explicit own-use rows not absorbed
  into an upstream inclusive transformation boundary;
- **Transmission and distribution losses** contains `10.02`; and
- **Transfers** contains `08` and is absent when an economy has no transfer
  rows.

The page Overview follows the same boundary-driven rule as Refining, without
reintroducing a broad `09` or combined `10` total. It shows separate summaries
for transformation processes, residual own use, transmission/distribution
losses and transfers. A summary groups by flow when several logical flows are
present; when only one flow exists it groups by product instead, because a
single-item flow legend would be redundant.

Absorbed own-use membership is read from upstream Common ESTO component
metadata and the non-expanding-rollup contributor QA emitted alongside it.
The dashboard does not maintain a second list of mapping relationships.
Power-related pump-storage own use is routed to Power.

On 2026-08-11, the page guide was expanded to explain how inclusive own use,
residual own use, transfers, and transmission and distribution losses are
represented in LEAP and aggregated for cross-dataset review.

## DASH-026: Historical composition stacks reconcile to their total lines

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation and numeric reconciliation
**Affected areas:** `codebase/common_esto_dashboard_renderer.py`; stacked-area charts

### Current rule

The category frontier for a comparison stacked-area chart is the union of
categories with nonzero historical comparison data and categories with nonzero
projected stack-source data. Historical-only categories remain visible through
the base year and then end naturally; projected-only categories begin when
their source data begins. Categories that are zero in both windows are omitted.

This ensures the historical stacked envelope equals its historical total line.
Restricting history to categories also present in LEAP projections is invalid
because it silently removes legitimate historical fuels. Russia Industry is
the regression case: historical `07.10 Refinery gas (not liquefied)` contributes
192.155 PJ in 2010 and 384.833 PJ in 2017, while `16.01 Biogas` contributes
0.0615 PJ in 2022; all are included in the ESTO total line and must therefore
also appear in its stack.

### History

- 2026-08-10: Replaced projection-only category filtering with the nonzero
  historical/projected union across generic and bespoke composition charts.

## DASH-027: LEAP flow-tree diagnostics remain provisional until exports are verified

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Diagnostic interpretation warning
**Affected areas:** `codebase/common_esto_dashboard_mapping_diagnostics.py`; LEAP flow-tree comparison

### Current rule

The LEAP flow-tree original-versus-mapped section displays a prominent warning
that apparent hierarchy or mapping problems can originate in incomplete,
flattened, inconsistent, or otherwise messy LEAP balance exports. Reviewers
must verify the relevant LEAP exports before treating this section as reliable
mapping evidence. The equivalent NINTH section does not inherit this warning.

### History

- 2026-08-10: Added after live review found flat LEAP export structures and
  inconsistent raw-versus-normalized signs producing misleading issue cards.

## DASH-028: Source exceptions are reviewed outside the dashboard

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Diagnostic workflow boundary
**Affected areas:** `codebase/common_esto_dashboard_mapping_diagnostics.py`

### Current rule

The mapping diagnostics page does not prepare or download candidate source
exceptions. Source exceptions require evidence-led review in the upstream
mapping workflow and its maintained exception workbook; the dashboard remains
a read-only diagnostic consumer. Numerical, attribution, and review evidence is
displayed directly beneath the failed source-tree check that it explains.

### History

- 2026-08-10: Removed the `Prepare reviewed source exception` panel and its
  browser-side candidate-generation controls.
- 2026-08-10: Removed the standalone hierarchy-validation and related-economy
  tables in favour of a collapsed evidence drill-down on each failed check.

## DASH-029: Rollup structure filters use structural membership, not selected-period values

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Diagnostic interaction and structural filtering
**Affected areas:** `codebase/common_esto_dashboard_mapping_diagnostics.py`; all-sector rollup graph

### Current rule

The default all-sector graph is limited by timeless original-ESTO structural
membership. It must not require an ESTO value for the scenario and year chosen
for another dataset, because ESTO historical periods do not overlap NINTH or
LEAP projection selections. A separate checkbox includes ESTO Extended-only
rows. Dataset values are always displayed one selected dataset at a time; the
former `Compare ESTO vs Extended` graph mode is not part of this general
structure explorer.

### History

- 2026-08-10: Fixed NINTH projection selections being filtered to an empty graph
  by an impossible ESTO scenario/year lookup; replaced the basis dropdown with
  `Include ESTO Extended-only rows`.

## DASH-030: Show balancing-only supply flows as base-year bars

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** Supply page; Stock changes (`06`); Statistical discrepancy (`11`)

### Current rule

Stock changes and Statistical discrepancy do not form ordinary comparable
projection series. Source these rows from the upstream `esto_leap` Common ESTO
scope, exclude them from normal area and line generation, and show one grouped
bar chart per flow using the configured base year. Fuels are on the x-axis and
ESTO and LEAP are the comparison series. Label this two-source boundary on the
chart. The 9th Outlook does not report these rows, so its absence is unavailable
data rather than zero. Do not source or map the rows directly in the dashboard.

### History

- 2026-08-12: Activated the upstream `esto_leap` balancing-flow boundary and
  labelled the base-year bars as ESTO and LEAP only.

- 2026-08-10: Added conditional base-year bar rendering. The current upstream
  comparison fact contains no flow-06 or flow-11 rows, so activation remains
  blocked on a consistent upstream mapping generation.

## DASH-031: Keep marine and aviation bunkers separate on Supply

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Presentation / source-coverage warning
**Affected areas:** Supply; international marine bunkers (`04`); international aviation bunkers (`05`)

### Current rule

Show flow `04` and flow `05` separately on Supply and omit their combined
`04-05 International transport (bunkers)` parent from that page. Continue to
use the combined row as the non-overlapping bunker boundary in the Energy
balance overview supply total.

When the upstream coverage record says International transport is still part
of `All demand aggregated`, show a yellow placeholder warning. The current USA
LEAP input supplies only `All demand aggregated/International transport`; its
separate mapped Air and Shipping branches are absent. Do not allocate that
combined value between marine and aviation. The separate Supply charts must
therefore show LEAP as unavailable until detailed source data are supplied.

### History

- 2026-08-11: Confirmed from the upstream raw LEAP fact, converted ESTO fact,
  published source map, and Common ESTO comparison fact. The detailed mappings
  exist, but only the combined source placeholder has values for USA.

## DASH-032: Exception-set matches leave the default paired-tree issue queue

**Status:** Confirmed and implemented
**Owner:** leap_dashboard
**Type:** Diagnostic presentation
**Affected areas:** Mapping diagnostics; paired original-versus-mapped flow trees

### Current rule

Treat `known_data_quality_exception = true` as the authoritative signal that an
anchor context matched the active upstream exception set. Omit every such
context from the default NINTH, LEAP, and ESTO paired-tree issue queues without
requiring a particular review status or final classification.

Keep the evidence inspectable in a collapsed **Exception cases by
classification** panel. Its selector groups cases by `exception_issue_class`
and renders the same original-versus-mapped card, related economy rows, review
fields, and source-review candidates as the default issue queue. Missing class
labels are grouped as `unclassified_exception`.

Show a brief meaning beneath each classification heading. The dashboard may
explain the review semantics, but it must retain and display the upstream class
code rather than inventing a replacement taxonomy. In particular,
`source_non_additivity` means the raw parent/children already disagree;
`intentional_detail_exclusion` means detail is outside the shared comparison
boundary; and `provisional_apec_anchor_review` is temporary pending a final
root-cause classification.

### History

- 2026-08-11: Replaced the two-class final-exception allowlist. Provisional and
  unclassified exception-set matches now leave the default queue but remain
  available in the classification browser.
- 2026-08-11: Added short classification descriptions beside the retained
  upstream class codes.

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
