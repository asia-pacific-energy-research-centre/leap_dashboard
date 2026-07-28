# Future Common ESTO Dashboard Backlog

> **Archived 2026-07-28.** This file is no longer maintained. Its live items
> were merged into [`../work_queue.md`](../work_queue.md); it is preserved here
> to retain the original prioritization and checklist.
>
> Its four prioritized items and its deferred-feature list are now in
> [`../work_queue.md`](../work_queue.md), which is the single controlling backlog for
> this repository:
>
> | Former item | Now |
> |---|---|
> | 1. Improve aggregate-first navigation for dense pages | `DASHQ-013` |
> | 2. Review diagnostic comparison-scope pages | `DASHQ-018` |
> | 3. Extend chart-manifest ranking and warning metrics | `DASHQ-019` |
> | 4. Keep page-status evidence reproducible | `DASHQ-012` |
> | Deferred feature work (Sankey, bespoke scope pages, automatic publication, dashboard-owned mapping logic) | "Deferred by decision — not queue items" |
>
> This file duplicated §2 and §3 of
> [`../common_esto_dashboard_plan.md`](../common_esto_dashboard_plan.md). Maintaining
> three parallel backlogs is what the 2026-07-28 documentation audit flagged;
> the queue now carries the acceptance criteria and the constraints that were
> unique to each source.

## Before starting a backlog item

This checklist is still current and still applies.

1. Read [`../common_esto_dashboard_plan.md`](../common_esto_dashboard_plan.md) §1 for
   the current implemented state, and
   [`../special_rules_and_design_decisions.md`](../special_rules_and_design_decisions.md)
   for decisions that cannot be re-derived from the data.
2. Read the current `leap_mappings` mapping-system documentation when the work
   touches comparison scopes, hierarchy, components, or rollups.
3. Define a focused test or validation artifact before changing production code.
4. Render affected representative economies before and after the change.
5. Run publication-readiness and page-noise checks before committing.
