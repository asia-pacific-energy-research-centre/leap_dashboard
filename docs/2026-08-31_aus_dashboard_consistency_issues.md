# Australia dashboard consistency review — 2026-08-31

**Status:** Renderer corrections implemented and locally verified; two upstream
source-data corrections remain outside the dashboard renderer

**Reviewed artifacts**

- Placeholder dashboard: `leap_review_tools/outputs/local_deployment_tests/2026-08-31_AUS_aggregate_allocation_candidate/01_AUS_placeholder_dashboard_archive/01AUS/dashboards/`
- Detailed-road dashboard: `leap_review_tools/outputs/local_deployment_tests/2026-08-31_AUS_aggregate_allocation_candidate/01_AUS_detailed_road_dashboard_archive/01AUS/dashboards/`

This ledger preserves the reported symptoms before further renderer changes.
Statements under **Observed** are user-visible facts. Statements under
**Investigate** are questions or hypotheses and must not be treated as causes
until the source rows and chart bundle have been reconciled.

## AUS-CONSIST-001 — Power-generation by-flow category is misleading

**Affected chart:** `09.01-09.02 Power generation — by flow`, both artifacts.

**Observed**

- The chart shows `09.01.01,09.02.01 Electricity plants` and the compound label
  `09.01.02,09.02.02,09.01.02.01,09.02.02.01 Total transformation - no transfers`.
- The latter label is not a useful plant-flow description and appears to hide
  the intended electricity/CHP/heat plant breakdown.

**Investigate**

- Whether a Common ESTO compound comparison boundary is being exposed as a
  display flow instead of being used only for source reconciliation.
- Whether parent-first frontier selection is suppressing the intended
  `09.01.01/09.02.01` and `09.01.02/09.02.02` children.
- Whether the placeholder and detailed cases require different component-local
  frontiers without changing the authoritative power total.

**Acceptance criteria**

- The by-flow stack uses intelligible plant categories at one non-overlapping
  hierarchy level.
- Compound reconciliation rows remain internal unless no truthful named child
  breakdown exists; any residual is labelled `Unallocated`, not as a false
  technology.
- The by-flow stack and authoritative total reconcile for ESTO, LEAP and Ninth.

**Finding / action (2026-08-31):** The compound row is the mapped CHP connected
component, but its internal reconciliation label leaked into presentation.
Power Overview now supplies explicit public labels for Electricity plants, CHP
plants and Heat plants. A regression test protects those labels.

## AUS-CONSIST-002 — Other-demand detail cards show only one side of 2022

**Affected charts:** `16.03-16.04 Agriculture and fishing — by product` and
`16.03-16.05 Other sector (all demand aggregate) — by product`, detailed artifact.

**Observed**

- The cards do not present continuous ESTO history plus LEAP/Ninth projection.
- Instead, one side of the base-year boundary appears at a time, making the
  comparison look incomplete.

**Investigate**

- Whether the broad placeholder row and detailed child rows are being assigned
  to separate chart owners.
- Whether source-specific frontier selection removes ESTO from one card and
  LEAP/Ninth from the other.
- Whether the broad combined placeholder should remain only in Overview while
  genuine detailed children own their own cards.

**Acceptance criteria**

- Each retained card has one declared comparison boundary and continuous
  source ownership across the base year.
- A placeholder aggregate is never presented as if it were a detailed child.
- No ESTO, LEAP or Ninth value is duplicated between the aggregate and child
  cards.

**Finding / action (2026-08-31):** ESTO owns the broad historical comparison
row while LEAP/Ninth own a different projected rollup, so the renderer was
publishing two source-specific facts as incomplete detail owners. Exact
`16.03-16.04` and `16.03-16.05` comparison rollups are now owned only by the
continuous Overview; genuine children such as `16.03` and `16.05` remain.

## AUS-CONSIST-003 — Transport flow charts jump at the base year

**Affected charts:** `15 Transport sector — by flow`, `15.02 Road — by flow`,
and `15.01,15.03-15.06 Transport non-road`, detailed artifact.

**Observed**

- By-flow charts show a material jump between ESTO history and LEAP at 2022/23.
- The corresponding Road by-product chart does not show the same mismatch.
- The detailed input exposes named non-road flows (`15.01`, `15.03`–`15.06`),
  but the non-road Overview currently shows only a by-product aggregate.

**Investigate**

- Whether by-flow stacks add parent and child rows, use different source
  frontiers by period, or compare domestic Transport with a broader LEAP total.
- Whether dummy non-road detail is genuine nonzero LEAP detail and therefore
  qualifies for a paired by-flow Overview under the two-child rule.
- Whether the by-product and by-flow charts use different owner rows or total
  boundaries.

**Acceptance criteria**

- By-product and by-flow views of the same boundary have identical annual
  signed totals for each source/scenario.
- Parent and child flow rows are never added together.
- Non-road receives a by-flow chart when at least two immediate child flows are
  nonzero; otherwise the absence is explicit and tested.

**Finding / action (2026-08-31):** The LEAP frontier contained both the stale
compound non-road rollup and published `15.01`, `15.03`-`15.06` children. The
Transport selector kept the rollup and later re-added the children. Published
children now replace that rollup and qualify for a paired non-road by-flow
chart. In the detailed AUS render, the 2022 LEAP non-road handoff changed from
216.68 PJ to 185.31 PJ and now matches ESTO; total Transport by-product and
by-flow both equal 1,239.15 PJ for LEAP and ESTO. The Ninth 2022 total remains
1,270.52 PJ because its own published non-road rows total 216.68 PJ; that is a
source comparison difference, not a remaining parent/child duplication.

## AUS-CONSIST-004 — Aggregate card ordering breaks product/flow pairs

**Affected page:** Industry and non-energy, detailed artifact.

**Observed**

- `17 Non-energy use` is placed beside `14.03 Manufacturing — by product`, while
  `14.03 Manufacturing — by flow` wraps onto the next row.

**Required presentation rule**

- Aggregate cards follow navigation order.
- A category's by-product and by-flow cards stay adjacent as a pair.
- A configured single-card aggregate such as Non-energy reserves the empty
  partner column rather than allowing the next category to occupy it.

**Acceptance criteria**

- Card rows are laid out by aggregate owner, not by a flat chart list.
- Paired cards remain side by side at desktop width.
- Single-card owners render with a deliberate blank sibling cell and do not
  disturb navigation order.

**Finding / action (2026-08-31):** Overview HTML now groups cards by aggregate
owner before laying out the two-column grid. A single owner receives a desktop
spacer, which disappears in the one-column responsive layout.

## AUS-CONSIST-005 — Buildings base-year step is too large

**Affected charts:** `16 Buildings` by product and by flow, with likely impact
on Energy balance overview totals.

**Observed**

- ESTO history is roughly 560 PJ in 2022 while LEAP/Ninth begin near 780 PJ.
- Both Buildings views show the same step, so this is a boundary/data issue,
  not merely a product legend issue.

**Investigate**

- Whether new `16.01.01 Datacentres`, `16.01.99 Commercial and public services
  unallocated`, or another child is added to a parent that already contains it.
- Whether Buildings uses a different domestic-TFC boundary from ESTO.
- Whether the LEAP export itself contains a genuine calibration mismatch.

**Acceptance criteria**

- Reconcile every 2022 Buildings child to its parent for each source before any
  display fix.
- If double counting or boundary mismatch exists, correct the shared frontier.
- If the source model genuinely differs, retain the difference and show a
  precise diagnostic note; do not force artificial equality.
- Energy balance overview must use the same corrected Buildings owner rows.

**Finding (2026-08-31):** The top-level chart is not double-counting a displayed
stack. The mapped inputs themselves disagree at the 2022 handoff: ESTO is
570.795 PJ and LEAP/Ninth are about 781.607 PJ after the dashboard's normal
measure and subtotal filters. This must be reconciled in the upstream
Buildings calibration/mapping input. The renderer deliberately continues to
show the gap rather than scale one source to another.

## AUS-CONSIST-006 — International bunker mapping/sign mismatch

**Affected charts:** `04 International marine bunkers` and
`05 International aviation bunkers`, Supply page.

**Observed**

- ESTO and LEAP marine-bunker values are small and positive in the displayed
  stack, while the 9th line is large and negative.
- The chart sign note says bunker fuel is removed from domestic supply and
  should therefore be negative.

**Investigate**

- Whether 9th marine and aviation source flows are reversed or cross-mapped.
- Whether ESTO/LEAP signs are being normalised differently from Ninth.
- Whether raw sources publish magnitudes with different conventions and need
  one shared semantic sign transformation after mapping.

**Acceptance criteria**

- Marine maps only to flow 04 and aviation only to flow 05.
- All three datasets use the same dashboard sign convention after mapping.
- Raw source identity, mapped flow and sign transformation are covered by a
  regression test for both bunker types.

**Finding (2026-08-31):** Marine and aviation are not cross-mapped in Ninth.
The raw Ninth rows are correctly negative. The ESTO-Extended mapping-chain
artifact instead carries small positive LEAP-like rows for both flows, even
though original ESTO has negative bunker observations. The correction belongs
in ESTO-Extended exact-row/source selection and sign preservation upstream;
the dashboard must not negate selected sources ad hoc.

## Cross-cutting consistency gates

Before another dashboard candidate is accepted:

1. For every paired by-product/by-flow aggregate, assert equal annual totals by
   source, scenario and year.
2. For every parent boundary, assert the selected non-overlapping child
   frontier plus visible `Unallocated` residual equals the authoritative parent.
3. Assert each row has one aggregate owner and one detail owner at most.
4. Assert historical comparison and projection ownership is continuous at the
   base year unless a source is genuinely missing, in which case the card must
   say so.
5. Assert chart order follows navigation-owner order and product/flow pairs are
   emitted as layout groups rather than a flat sequence.
6. Run source-level reconciliation tables before visual QA; screenshots alone
   are not sufficient evidence of a fix.
