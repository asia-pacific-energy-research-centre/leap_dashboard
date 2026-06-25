# Sankey Balance Routing Design

## Status

Sankey generation is deliberately scaffolded but disabled. The dashboard already
has enough data to draw lines and area charts from common flow/product rows, but
a Sankey needs an additional routing layer that defines source and target nodes.
Without that layer, transformation inputs, outputs, losses, transfers, and final
demand can be double-counted or connected in misleading ways.

## Readiness Review

Last reviewed: 2026-06-25.

Sankey implementation is not ready to start. The repository has the disabled
`sankey_diagrams` config scaffold, but no routing table, no route QA output, and
no double-counting reconciliation checks. Keep `sankey_diagrams.enabled = false`
until those inputs exist.

Current blockers:

- No `routing_table_path` is configured.
- No file defines `route_id`, `source_node`, `target_node`, and signed flow rules.
- No QA output identifies included, excluded, or multiply-routed rows.
- No reconciliation check proves Sankey totals match the source comparison data.
- No page-specific diagram definitions exist for the candidate pages.

The next safe step is to create a reviewed routing-table draft and QA checker,
not to add Plotly Sankey rendering.

## Design Rule

The Sankey builder should consume the common ESTO comparison data plus a separate
balance-routing table. It should not infer full energy-system routing from labels,
relationship IDs, graph IDs, or the old ESTO-axis dashboard mapping pipeline.

## Required Routing Fields

Each routing row should contain:

- `route_id`: stable identifier for the routing rule.
- `comparison_scope`: scope the route applies to.
- `source_node`: Sankey source node label or node key.
- `target_node`: Sankey target node label or node key.
- `flow_code_prefixes`: common flow code prefixes included by the rule.
- `product_code_prefixes`: optional product filters.
- `value_sign`: whether to use positive values, negative values, or both.
- `include_in_total`: boolean guard for totals and QA.
- `priority`: deterministic order when route filters overlap.

## Initial Diagram Candidates

Start with narrow diagrams where routing semantics are clear:

- Supply to domestic availability: production, imports, exports, and stock changes.
- Power transformation: fuel inputs to electricity and heat outputs plus losses.
- Refining: crude/feedstock inputs to petroleum product outputs.
- Other transformation: one process group at a time, not all processes together.
- Total demand: final demand by sector and fuel after transformation routing is validated.

## Acceptance Criteria

A Sankey page should not be enabled until:

- every included common flow/product row maps to zero or one route;
- excluded rows are written to a Sankey QA file with reasons;
- signed values are handled consistently with the dashboard sign semantics;
- parent/child flow rows are filtered with the same frontier logic used by line charts;
- totals reconcile to the source comparison data within a configured tolerance.

## Config Hook

The dashboard template contains a disabled `sankey_diagrams` section. Future work
should extend that section with a `routing_table_path`, page-specific diagram
definitions, and a `tolerance_pj` setting before enabling generation.
