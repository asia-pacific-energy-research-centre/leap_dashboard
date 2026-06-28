# Common ESTO Comparison Dashboard: Current State and Backlog

Last reconciled: 2026-06-28.

## Purpose

This document is the authoritative planning summary for the production Common
ESTO dashboard. It separates what exists now from the confirmed backlog,
deliberately deferred work, and the historical build record.

Detailed operating instructions are in `docs/common_esto_dashboard_guide.md`.
Page counts and review findings are in
`docs/common_esto_dashboard_page_status.md`. Rules that require an explicit
human decision are recorded in `docs/special_rules_and_design_decisions.md`.

## 1. Current implemented state

### Production boundary

The official implementation lives in this repository:

```text
codebase/common_esto_dashboard_workflow.py
codebase/common_esto_dashboard_data.py
codebase/common_esto_dashboard_renderer.py
codebase/common_esto_dashboard_output_layout.py
config/common_esto_dashboard/
tests/
scripts/
```

The frozen historical implementation is in
`C:\Users\Work\github\leap_dashboard_legacy`. New production work must not be
added there or under a new `test/` implementation tree.

The dashboard is downstream of `leap_mappings`. It consumes the final Common
ESTO comparison data and optional common-row membership metadata. It does not
read raw ESTO or 9th Outlook data, rebuild mappings, or use the retired
`relationship_id -> graph_id` links.

The core design rule is:

```text
The dataset defines chart membership.
Configuration defines interpretation and presentation.
```

### Input and classification

The production workflow currently supports:

- long-form Common ESTO comparison data;
- wide-form data with year columns;
- combined source/scenario labels, split into `source_system` and `scenario`;
- signed energy-balance values and configurable sign semantics;
- generated flow and product labels containing component-code lists and
  ranges;
- configurable, priority-ordered page and section assignment;
- a fallback page so unassigned rows are visible rather than silently lost;
- optional enrichment from `common_esto_rows.csv` for component-level audit
  detail.

Generated category membership is determined upstream. The dashboard parses
component codes and respects `comparison_scope`; it does not split or merge
Common ESTO categories for presentation convenience.

### Pages and chart families

The default dashboard generates these production-facing pages:

```text
Total demand
Supply
Bunkers
Power
Other transformation
Refining
Industry
Transport
Buildings
Other demand
Non-energy use
```

The current upstream `20_USA` output contains 850 chart-manifest rows. Industry
has 219 rows and Supply has 211. The complete page breakdown and page-noise
review are maintained in `docs/common_esto_dashboard_page_status.md`.

Implemented chart behaviour includes:

- stacked-area overview charts based on the flow hierarchy;
- a flow-frontier check that prevents parent and child flows from appearing as
  peer line charts;
- individual line charts for the non-overlapping flow/product frontier;
- summary aggregate charts between page overviews and detailed charts;
- a Total demand page with the configured supply comparison line;
- optional difference traces on line charts, pre-computed as LEAP minus ESTO
  for years at or before the base year and LEAP minus 9th Outlook after the
  base year;
- suppression of low-magnitude charts from display while retaining their
  manifest records;
- sticky navigation, section jump links, responsive chart grids, and lazy
  loading of Plotly bundles;
- client-side sorting by total magnitude, absolute difference, and percentage
  difference;
- an economy/dashboard switcher.

Difference traces, scope-specific page generation, and publishing support are
implemented. They are no longer future features. Scope-specific pages and
publishing are intentionally gated as described below.

### Suppression rule

DASH-002 is confirmed at a threshold of 1 PJ, measured as total absolute chart
value across all years. The all-economy sensitivity review covered 21
economies and 10,173 manifest chart rows:

| Threshold | Chart rows suppressed | Share | Cumulative suppressed chart magnitude |
|---:|---:|---:|---:|
| 0 PJ | 0 | 0.00% | 0 PJ |
| 0.1 PJ | 455 | 4.47% | 11.105 PJ |
| 1 PJ | 954 | 9.38% | 232.128 PJ |
| 5 PJ | 1,563 | 15.36% | 1,876.958 PJ |

At 1 PJ, the suppressed share ranges from 1.9% to 19.8% by economy. Raising
the threshold to 5 PJ removes substantially more legitimate small-series
detail without solving the separate problem of dense high-value pages. The 1
PJ threshold therefore remains configuration-owned but is now the confirmed
default. Every suppressed chart remains in `chart_manifest.csv` with
`suppressed = true`; suppression does not alter source data, comparison totals,
or coverage diagnostics.

The cumulative magnitude above is a presentation sensitivity measure summed
over chart records. It is not a unique physical-energy total because chart
families can represent related levels of the hierarchy.

### Scope-specific diagnostic pages

Scope-specific LEAP-vs-9th page generation is implemented through
`scope_specific_pages` in the dashboard template. Two diagnostic page
definitions currently exist:

- `transport_leap_vs_ninth`;
- `datacentres_leap_vs_ninth`.

They remain disabled by default. The available USA diagnostic render produced
30 transport charts, many of them sparse alternate-scope slices, and two
datacentre charts from one electricity row. That evidence is insufficient to
make either page part of normal navigation. Focused review runs may enable the
pages; publication-readiness checks require them to be absent from default
output.

### Manifest and QA outputs

Each economy output includes:

```text
dashboards/*.html
chart_bundles/*.js
chart_bundles/*.json
supporting_files/chart_manifest.csv
supporting_files/page_assignment_summary.csv
supporting_files/sign_semantics_summary.csv
```

The manifest currently provides the ranking metrics:

```text
total_abs_value
abs_diff
pct_diff
```

It also records page/section placement, chart identity and type, source rows,
sign notes, suppression state, and pre-computed historical and projection
difference traces. It does not yet provide the complete ranking field set in
the near-term backlog.

Supporting scripts provide:

- fixture refresh;
- all-economy rendering;
- page-noise analysis;
- publication-readiness checks;
- disabled Sankey routing QA.

### Publishing policy

Publishing support is implemented by `publish_to_docs()`. It copies only the
serving assets from `outputs/<economy>/` into `docs/<economy>/`; supporting CSV
files remain under `outputs/`.

Publishing remains an explicit manual action:

1. Leave `PUBLISH_TO_DOCS = False` for normal renders and fixture refreshes.
2. Run publication-readiness checks and review the intended economies.
3. Set `PUBLISH_TO_DOCS = True` only for the deliberate publication run.
4. Inspect the copied `docs/` assets before committing them.
5. Set the toggle back to `False` after publication.

Automatic copy after every render is not the policy. Ordinary validation runs
must not create publishable working-tree changes or accidentally replace the
currently served dashboard.

## 2. Confirmed near-term backlog

### 2.1 Improve navigation on dense pages

The all-economy page-noise report contains 23 flagged economy/page pairs:

- 8 have a high chart count;
- 15 have a high suppressed share;
- 3 have many sparse one-row charts;
- some pages have more than one reason.

These flags do not all require the same response. A high suppressed share is a
QA prompt to inspect small-series coverage; it is not evidence that the 1 PJ
threshold should increase. Sparse-row flags require a content review. High
chart counts require a navigation and grouping response.

Industry is the recurring density problem across economies. Supply is also
dense for Canada and the USA. The next presentation change should therefore
add aggregate-first navigation and stronger configuration-driven sections to
Industry and Supply, then re-run the page-noise report. Detailed charts must
remain available and all rows must remain in the manifest. The change must not
be implemented by dropping coverage or increasing the suppression threshold.

### 2.2 Complete diagnostic-page review

Before either LEAP-vs-9th page is enabled by default:

1. render it for representative large, medium, and small economies;
2. check row coverage and source/scenario completeness;
3. identify sparse or repeated slices;
4. confirm the page answers a modeller question not already answered by the
   default three-way pages;
5. update page-status documentation with economy-specific evidence;
6. pass publication-readiness checks with the intended default page list.

Until those checks are complete, both pages remain diagnostic and disabled by
default.

### 2.3 Complete ranking metrics

Current sorting works with `total_abs_value`, `abs_diff`, and `pct_diff`, but
the audit record is incomplete. Add the following manifest fields without
changing the correct historical/projection comparison pairing:

```text
default_order
model_abs_value
comparison_abs_value
max_annual_absolute_difference
max_annual_percentage_difference
non_zero_year_count
unexpected_sign_count
ranking_warning
```

Small comparison denominators must be flagged rather than allowed to create
misleading percentage rankings. Manifest metrics should remain pre-computed so
the browser only changes display order.

### 2.4 Keep page-status evidence current

After a reproducible upstream refresh, regenerate the all-economy dashboards,
page-noise outputs, and publication checks together. Update
`common_esto_dashboard_page_status.md` when chart counts or review decisions
change. Do not treat a successful render alone as evidence that comparison
semantics are correct.

## 3. Explicitly deferred work

### Sankey diagrams

Sankey rendering remains deliberately deferred. The repository contains a
disabled configuration scaffold, a draft routing table, routing QA, and the
design note `docs/common_esto_sankey_balance_routing_design.md`; it does not
contain an enabled production Sankey.

Implementation must wait until:

- deterministic source-to-target routes are agreed;
- signed input, output, loss, and stock-change treatment is explicit;
- overlap and double-counting checks pass;
- reconciliation checks define acceptable node imbalances;
- route coverage is reviewed across representative economies.

The dashboard must not infer physical links dynamically or use AI to invent
runtime routes. Link widths may use absolute values only if signed values and
their interpretation remain available in hover text and QA outputs.

### Automatic publishing after ordinary runs

The copy mechanism exists, but automatically invoking it after every render is
deferred indefinitely in favour of the manual publication gate. Reconsider
only if publication moves to a CI job with an explicit approval step, a clean
source revision, artifact review, and rollback.

### Additional bespoke scope pages

New transport, buildings, or other source-specific pages are deferred until
the two existing diagnostic pages establish a useful and repeatable review
pattern. A bespoke page must use existing Common ESTO membership and
configuration rules; it must not introduce dashboard-owned mapping logic.

## 4. Historical build record

This section preserves the rationale and build sequence without presenting
completed work as backlog.

### Original problem

The legacy dashboard depended on a large hand-authored graph hierarchy and
`relationship_id -> graph_id` maintenance. That model became fragile as LEAP,
ESTO, and 9th Outlook exposed different levels of detail. The Common ESTO
mapping pipeline instead generates the safest comparison categories for each
comparison scope. The dashboard was redesigned as a reporting layer over that
output.

The upstream process is:

```text
Human-maintained mapping sheets
  -> compiled energy-balance relationships
  -> comparison-scope graph partitioning
  -> Common ESTO rows and component membership
  -> converted comparison data
  -> dashboard pages, charts, and QA files
```

If any source in a comparison scope represents several ESTO components as one
aggregate, those components remain together in that scope. The dashboard uses
the generated category and its component codes; it does not recreate the
partition or assume a fixed graph name.

### Completed production phases

1. **Core correctness:** implemented the parent/child frontier and correct
   year pairing for difference metrics.
2. **Page and chart coverage:** added Total demand, summary aggregate charts,
   an index, section navigation, and responsive/lazy-loaded chart bundles.
3. **Difference and suppression:** added pre-computed difference traces and
   audited suppression; the all-economy review later confirmed 1 PJ as the
   default threshold.
4. **Publishing support:** added serving-asset copy support and readiness
   checks. The final policy kept invocation manual rather than automatic.
5. **Repository migration:** made the flattened `codebase/` implementation the
   sole production dashboard and moved the frozen reference implementation to
   `leap_dashboard_legacy`.
6. **Operational QA:** added fixture refresh, all-economy render, page-noise,
   diagnostic-page, publication, and Sankey-routing support scripts.

### Completed design decisions

- Flow hierarchy, not product hierarchy, defines overview and frontier chart
  behaviour.
- Parent flows may appear as area overviews but not as peer line charts when
  child flows are present.
- Difference traces belong on existing line charts and remain optional in the
  legend; they are not a separate chart family.
- Low-magnitude charts are hidden from display but never dropped from audit
  output.
- Fixed page names and configuration-driven sections provide structure while
  row membership remains data-driven.
- GitHub Pages serving assets are copied only during an intentional publication
  run.
- Sankey diagrams do not block production dashboard work.

### Migration and review evidence

On 2026-06-27 the duplicate implementation and embedded legacy code were
removed from the official repository. Visual review established responsive
two-column overview charts, three-column detail grids, legends below dense
overview plots, and wrapping mobile navigation.

The earlier tracked USA fixture produced 860 manifest rows. A later upstream
run produced 850 rows from 19,103 visible input rows, including 219 Industry
and 211 Supply charts. The current page-status document uses the latter output
and retains the earlier fixture count only as historical evidence.

On 2026-06-28, existing all-economy outputs were used to review suppression and
page noise. The review confirmed DASH-002 at 1 PJ, retained diagnostic pages as
disabled, selected aggregate-first navigation for genuinely dense pages, and
confirmed manual publication as the production policy.
