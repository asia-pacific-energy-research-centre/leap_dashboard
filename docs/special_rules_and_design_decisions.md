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
