# Special rules and design decisions

This is the decision log for `leap_dashboard`. Record rules whose correct behaviour cannot be derived from comparison data, canonical configuration, or the established hierarchy. Keep implementation details in code documentation. Update an existing entry and its history rather than creating a duplicate.

Cross-repository decisions use a `CROSS-###` ID and have one authoritative entry in the repository that owns the implementation. Other affected repositories should link to that entry instead of copying it.

## DASH-001: Use a flow frontier to prevent parent-child double charting

**Status:** Confirmed
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** `test/common_esto_dashboard_agent_pack_transfer_rules/src/common_esto_dashboard_renderer.py`; `frontier_flow_labels`; chart manifest; line and area chart generation

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

**Status:** Provisional
**Owner:** leap_dashboard
**Type:** Presentation
**Affected areas:** `test/common_esto_dashboard_agent_pack_transfer_rules/config/common_esto_dashboard_template.json`; `suppression_threshold`; renderer chart metrics; chart manifest

### Situation

Very small series can make navigation noisy, but hiding them can conceal mapping gaps, unit errors, or legitimate small energy flows. The source data does not define a universally meaningful display threshold.

### Options

- Display every chart.
- Drop charts below a threshold, reducing noise but losing auditability.
- Suppress them from display while retaining a manifest entry and metrics.

### Current rule

Use the third option. The prototype threshold is `1.0` PJ based on total absolute value across all years. Suppressed entries remain in the chart manifest with `suppressed: true`. The 1 PJ value is provisional and configuration-owned.

### Decision needed

Should the production threshold remain 1 PJ, vary by chart scope or unit, or default to no suppression? The choice should be made from representative all-economy output, not the USA sample alone.

### Validation

Produce a threshold sensitivity table showing chart counts and total absolute energy hidden at 0, 0.1, 1, and 5 PJ by economy and page. Confirm every hidden chart remains in the manifest and that suppression never changes comparison totals or coverage diagnostics.

### History

- 2026-06-27: Recorded the implemented prototype behaviour; retained the numeric threshold as provisional pending all-economy review.

## End-to-end run report

Append a dated subsection after each end-to-end run. Report:

- newly discovered decisions;
- unresolved decisions blocking correct output;
- provisional assumptions used to continue;
- rules that should move into configuration;
- rules that should become automated validation;
- the next decisions requiring human guidance.

Also report coverage, dropped rows, source-versus-output totals, hierarchy consistency, mapping cardinality inherited from upstream data, and semantic correctness of grouping and presentation. A successful render is not evidence that the published comparison is correct.
