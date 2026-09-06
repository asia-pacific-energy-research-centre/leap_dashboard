# Other-demand native child frontier

Status: implemented; production regeneration pending.

## Problem

The Other-demand flow overview preferred the derived `16.03-16.04`
Agriculture-and-fishing rollup even when native ESTO published its separate
`16.03 Agriculture` and `16.04 Fishing` children. This hid valid source detail.

## Permanent rule

- Prefer native `16.03`, `16.04`, and `16.05` rows when their sum reconciles to
  the authoritative `16.03-16.05` parent for the same source, year, and fuel.
- Retain `16.03-16.04` for a source that publishes only that compound.
- Retain the parent whenever the available children do not reconcile. Never
  manufacture a balancing child.

For the 2026 AUS issue, `16.04 Fishing` is genuinely zero. The historical
stack therefore contains nonzero `16.03 Agriculture` and `16.05 Non-specified
others`, without relabelling Agriculture as the compound rollup.
