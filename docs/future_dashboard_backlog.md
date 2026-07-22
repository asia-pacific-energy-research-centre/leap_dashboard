# Future Common ESTO Dashboard Backlog

This document records dashboard feature work intentionally deferred from the
2026-07-22 repository cleanup. It is separate from
`zip_extraction_plan.md`, which records completed repository hygiene and
validation checkpoints.

## Priority order

### 1. Improve aggregate-first navigation for dense pages

Focus on the Industry and Supply pages, which currently contain many charts
and are flagged by page-noise analysis in several economies.

Work items:

- Review aggregate-first sections for Industry and Supply.
- Make section ordering and navigation more prominent.
- Preserve access to detailed charts and manifest rows.
- Validate the change against USA, China, Australia, Korea, Russia, Chinese
  Taipei, and Canada, where density flags are currently concentrated.

Acceptance criteria:

- Dense pages remain complete but are easier to scan from aggregate to detail.
- Page-noise analysis shows an intentional reduction in navigation-risk flags.
- Publication-readiness and focused tests pass.

### 2. Review diagnostic comparison-scope pages

Diagnostic LEAP-vs-9th pages remain disabled by default. Review whether their
rows and labels are sufficiently complete for representative economies before
considering publication.

Work items:

- Inspect diagnostic page inputs for representative economies.
- Confirm the intended historical and projection semantics.
- Identify sparse, duplicated, or misleading charts.
- Document required configuration or upstream-data changes.
- Keep pages disabled unless the evidence supports enabling them.

Acceptance criteria:

- A representative-economy review is documented.
- Diagnostic pages have clear enable/disable decisions and rationale.
- No diagnostic page is enabled by default without passing readiness checks.

### 3. Extend chart-manifest ranking and warning metrics

The chart manifest already contains core comparison metrics. Extend it only
where the additional values improve review or publication decisions.

Potential additions:

- explicit missing-year indicators;
- historical/projection coverage counts;
- source/scenario availability summaries;
- zero-only or empty-series warnings;
- clearer suppression reasons.

Acceptance criteria:

- New metrics are defined in the dashboard design documentation.
- Metrics are generated consistently for every rendered economy.
- Tests cover missing, sparse, suppressed, and normal chart cases.

### 4. Keep page-status evidence reproducible

Synchronize `docs/common_esto_dashboard_page_status.md` with reproducible
renders and page-noise reports.

Work items:

- Record the render input boundary and review date.
- Refresh page counts from the current intended dataset.
- Distinguish production-facing pages from diagnostic pages.
- Preserve historical counts only as explicitly labelled evidence.

Acceptance criteria:

- Page-status tables can be regenerated or checked from tracked scripts.
- Every stated chart count has a corresponding render or manifest source.
- The document does not describe obsolete fixture structure as current.

## Deferred feature work

These items remain out of scope until their upstream semantics and design
requirements are deliberately reopened:

- Sankey diagrams and routing beyond the current validation scaffold.
- New bespoke comparison-scope pages.
- Automatic publication after ordinary workflow runs.
- Dashboard-owned mapping logic; mapping remains owned by `leap_mappings`.

## Before starting a backlog item

1. Read `docs/common_esto_dashboard_plan.md` and
   `docs/special_rules_and_design_decisions.md`.
2. Read the current `leap_mappings` mapping-system documentation when the
   work touches comparison scopes, hierarchy, components, or rollups.
3. Define a focused test or validation artifact before changing production
   code.
4. Render affected representative economies before and after the change.
5. Run publication-readiness and page-noise checks before committing.
