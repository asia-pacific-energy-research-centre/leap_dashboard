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

**Finding / action (2026-08-31):** Marine and aviation are not cross-mapped in
Ninth. The raw Ninth rows are correctly negative. The ESTO-Extended
mapping-chain artifact instead carries small positive LEAP-like rows for both
flows, even though original ESTO has negative bunker observations. The
comparison fact is preserved for auditability, while the Supply presentation
now applies the Common balance semantic to exact child flows 04 and 05:
international bunkers are always shown as negative domestic-supply
withdrawals. A regression test proves positive source magnitudes become
negative while already-negative values and unrelated supply flows retain
their meaning. Upstream ESTO-Extended exact-row provenance still needs repair.

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

## AUS-CONSIST-007 — Page and placeholder exceptions to paired-card spacing

**Observed**

- Energy balance overview and Emissions contain intentionally complementary
  charts whose titles are not literal `by product` / `by flow` pairs, so the
  generic singleton spacer separates charts that belong together.
- Supply contains important balance summaries that normally have no meaningful
  by-flow companion.
- A placeholder-only Industry boundary emits a one-series by-flow chart even
  though the LEAP placeholder publishes no activity detail.

**Required rule**

- Do not reserve missing-companion cells on Energy balance overview, Emissions
  or Supply.
- Do not generate generic by-flow companions for placeholder-only demand
  boundaries. Explicitly designed placeholder views such as Other demand may
  remain because they communicate observed history versus the published LEAP
  aggregate.

**Finding / action (2026-08-31):** The shared card renderer already supported
this policy, but bespoke Energy-balance and Emissions builders discarded their
full page configuration before writing HTML. Full page configuration now
reaches the shared writer. Supply also opts out, and an active aggregate-only
demand page automatically opts out so two meaningful placeholder product
cards may share a row without fake companions.

## AUS-CONSIST-008 — Other-demand Ninth flow frontier collapses after 2022

The Other-demand product and flow views must use the same authoritative
16.03-16.05 total for every source/year. Ninth child areas must not disappear
merely because a LEAP placeholder becomes active. Diagnose source-specific
frontier selection and retain an explicit Unallocated remainder when the
published children do not add to the parent.

**Finding / action (2026-08-31):** AUS Ninth publishes a combined
`16.03-16.04 Agriculture and fishing` row rather than separate `16.03` and
`16.04` rows. The placeholder-generated child list superseded the explicit
Other-demand list and retained only tiny `16.05`. The page-specific
`16.03-16.05` product/flow frontier now replaces any generic or placeholder
version and explicitly accepts the combined child before considering separate
children.

## AUS-CONSIST-009 — Portable rendering omits the Power interim audit

The placeholder candidate was rendered without passing
`leap_source_branch_fallback_audit.csv`, so Electricity and CHP interim owners
were not marked as placeholders and fuel-specific CHP detail leaked into the
navigation. Portable rendering should discover the sibling audit beside the
comparison artifact when no explicit path is supplied. Heat is shown as a
placeholder only when the audit actually reports a retained Heat interim
branch; absence or zero data must not invent one.

**Finding / action (2026-08-31):** Portable rendering now discovers the sibling
audit beside the comparison parquet. The AUS placeholder candidate reports
and navigates only the retained Electricity and CHP interim owners; the former
fuel-specific CHP navigation leak is gone. No Heat placeholder is shown
because the supplied audit has no retained Heat interim row.

## AUS-CONSIST-010 — Overview coverage for Other transformation and Refining

- Other transformation's multi-flow summaries need both by-product and
  by-flow views. A by-flow view remains inappropriate where the Common ESTO
  boundary has only one published flow; such cases keep the by-product view.
- Refining must have a prominent Overview aggregate even though it is one
  Common flow. The current comparison fact combines refining and refinery own
  use into `09.07 ... (including own use)`; a truthful split between those
  components requires upstream contributor-level facts and must not be
reconstructed from the combined row.

**Finding / action (2026-08-31):** `Other transformation (including own use)`
and `Other energy-sector own use` now receive paired product/flow cards because
they each have multiple non-zero Common child flows. Transfers and
Transmission/distribution losses retain product-only cards because the current
fact has only one Common flow for each. Refining is promoted to a full-width
Overview product aggregate. A refinery-versus-own-use flow split remains
unavailable because both contributors are already collapsed into one Common
row upstream.

## AUS-CONSIST-011 — Detailed and placeholder bunker behavior diverges

The combined placeholder bunker chart is internally comparable, while the
detailed Supply chart exposes the upstream ESTO-Extended sign/source mismatch
recorded in AUS-CONSIST-006. Dashboard logic must keep combined and separate
navigation honest, but must not use the placeholder aggregate to conceal the
bad detailed source rows.

**Finding / action (2026-08-31):** Supply now has an explicit combined 04-05
Overview product card plus a marine/aviation by-flow companion whenever both
children are non-zero. Detailed candidates retain separate 04 and 05 sections;
placeholder candidates retain their authoritative combined owner. Exact child
charts use the signed-withdrawal presentation rule recorded in
AUS-CONSIST-006.
