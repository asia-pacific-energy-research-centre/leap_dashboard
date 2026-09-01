# Power page hierarchy update — 2026-09-01

Status: implemented and verified.

The Power page now treats these active boundaries as first-level navigation
owners:

- `09.01-09.02 Power`
- `09.01.01,09.02.01 Electricity plants`
- `09.01.02,09.02.02 CHP plants`
- `09.01.03,09.02.03 Heat plants`
- `10.02 Transmission and distribution losses`

Every active boundary receives a by-product aggregate. A by-flow aggregate is
added when at least two immediate child processes are nonzero. Process-level
flows remain subordinate navigation pills. The former “Power generation” title
is now “Power”.

Focused dashboard tests pass, including product-only leaf behavior and forced
first-level navigation ownership.
