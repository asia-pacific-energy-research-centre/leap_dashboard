# Common ESTO mapping — consumer guide

How this dashboard consumes the Common ESTO structure mappings, and why the
consumption is deliberately boring.

`leap_mappings` owns the mappings and states the contract in
`leap_mappings/docs/using_common_esto_mappings.md`. **Read that first** — it
explains the guarantee. This document is the worked example: what a consumer
actually has to do, and the things a consumer must not do.

This dashboard is intended to be the reference implementation of that contract.
When the two disagree, the mappings repository is right and this one is the bug.

## The guarantee, in one line

A common row is a `(common_flow_label, common_product_label)` pair that every
dataset in the scope can express **without being split**, because the structure
is built at the lowest common denominator of its participating datasets.

## What that means for consuming code

**Mapping a source onto common rows is a merge and an aggregation.** No
allocation, no shares, no estimation, no judgement.

The 9th's `01_x_thermal_coal` covers three ESTO fuels, so putting the 9th on
*ESTO's* axis means splitting one number three ways using ESTO's own observed
proportions. Putting it on *common rows* does not, because all three ESTO fuels
live in the single common row `01.02-01.04 Coal`. The split and the
re-aggregation cancel. Measured across scope `esto_leap_ninth`: 0 of 1,920 9th
source pairs and 0 of 1,108 LEAP pairs fan out at the common level.

So the consumer contract is:

1. Take source values in the dataset's native vocabulary.
2. Merge onto the mapping for `(source_system, comparison_scope)`.
3. Aggregate by `common_row_id`, economy, scenario, year.

If consuming code is doing anything more interesting than that, it has probably
strayed into mapping logic and belongs upstream.

## Rules for this repository

- **Never allocate, split, or apportion a source value.** If a value seems to
  need splitting to fit the comparison, the structure is wrong upstream; do not
  compensate here.
- **Never add a downstream fallback for fan-out.** `leap_mappings` asserts the
  no-split invariant and publishes the check
  (`results/common_esto/qa_common_esto_source_aggregates_split.csv`, expected
  empty). A fallback here would convert a loud upstream failure into a quiet
  approximation, and silently wrong totals are the failure this whole system
  exists to prevent.
- **Always carry the comparison scope.** A mapping is only valid within its own
  scope. The 9th maps cleanly in `esto_leap_ninth` and *not* in `esto_leap`,
  where it is not a participant — 151 of its pairs fan out there. That is the
  rule working, not a defect.
- **Do not re-derive mapping semantics.** `leap_dashboard/AGENTS.md` forbids
  reproducing mapping logic here. Note that it forbids a second *implementation*
  — it does not forbid this repository from performing the conversion by calling
  the upstream one.

## Aggregation: get parenthood from the contract, not from label text

Common rows form a hierarchy. A sector page holds `14 Industry sector` next to
`14.03 Manufacturing` next to `14.03.01 Iron and steel`. Charting those
individually is correct. **Summing them is not** — the same fuel is counted
several times. Any total must be built from one non-overlapping frontier.

Not hypothetical: the first Emissions implementation summed every demand row and
reported 4,838 Mt CO2e for 20USA 2022 against a correct 3,443 Mt.

**Parenthood is already published and must not be re-derived here.** The
mappings-owned hierarchy/subtotal contract declares the common axis directly:
`results/hierarchy_subtotal_contract/current/axis_nodes.csv`, rows with
`dataset_id = common_esto`, carrying `is_leaf`, `is_structural_parent`,
`parent_node_id`, `depth` and `child_count`. It covers 104 flow and 75 product
nodes, and correctly marks `14 Industry sector`, `14.03 Manufacturing`,
`16 Other sector` and `09 Total transformation sector` as structural parents.

This repository already has a strict consumer for it:
`codebase/hierarchy_subtotal_contract_loader.py`. Use it. Deriving parenthood by
parsing code expressions out of display labels is a second implementation of
mapping semantics and is exactly what `AGENTS.md` prohibits.

### What genuinely remains a dashboard concern

Two things the declared hierarchy does not answer, both of which stay here:

1. **Which rows a given source actually reported.** Leaf-ness is structural, not
   per-source. One source may report only `14 Industry sector` while another
   reports its children; excluding every non-leaf would silently drop the first
   source's data. The frontier must therefore be resolved per source system and
   scenario against the rows actually present.
2. **Generated rollups that sit outside the declared tree.** Measured on scope
   `esto_leap_ninth`, 97 of 98 common flow labels and 52 of 54 product labels are
   in the contract. The exceptions are
   `16.03-16.05,17 Other sector including non-energy (all demand aggregate)`,
   `02.01-02.08 Coal products` and `06.03-06.04 Crude oil and NGL` — generated
   aggregates that cut across the tree rather than sitting in it. The first is
   the dangerous one: it overlaps `16 Other sector` on `16.03-16.05` **and**
   `17 Non-energy use`, so no set of declared parents identifies the overlap.

See `codebase/common_esto_dashboard_emissions.select_non_overlapping_rows` and
`DASH-021` in `docs/special_rules_and_design_decisions.md`. That code currently
derives *all* of the above from code expressions; migrating its parenthood half
onto the contract is tracked in
the archived implementation plan at
`docs/archive/dashboard_emissions_program_20260806/measure_aware_dashboard_and_mapping_inversion_plan.md`.

## Current state versus target state

Worth being exact, because the target shape is not yet what the code does.

**Today.** This dashboard reads the pre-converted, manifested
`leap_mappings/results/common_esto/common_esto_comparison_data.parquet` via
`codebase/common_esto_dashboard_data.load_common_esto_data`. The conversion has
already happened upstream, so the guarantee above is inherited rather than
exercised here.

The one place this repository applies a mapping itself today is the emissions
factor join in `codebase/common_esto_dashboard_emissions.py` — factors resolved
onto `common_product_label`, then a merge and a multiply. That is the shape the
rest is heading towards, though its factor *resolution* is mapping work that is
scheduled to move upstream.

The upstream repository now also publishes
`results/common_esto/source_to_common_esto_map.csv` for LEAP and 9th native
categories, alongside `esto_to_common_esto_map.csv` for ESTO components. The
dashboard uses these files as read-only provenance for its guide tables; it
does not use them to reimplement the upstream value conversion.

**Target.** This dashboard converts the original datasets at render time by
calling an importable function published by `leap_mappings`, using a per-scope
`(source_system, native flow, native product) -> common_row_id` table. One merge
per dataset, cached and invalidated on input change.

The point of the target is not performance. It is that anyone holding their own
version of a dataset gets identical common rows from identical mappings, with
only the values differing.

See the archived
`docs/archive/dashboard_emissions_program_20260806/measure_aware_dashboard_and_mapping_inversion_plan.md`
(Phase C). The plan is retained as design history; any remaining inversion work
must be re-scoped in `docs/work_queue.md` from the current parquet consumer
rather than re-running that completed programme.
