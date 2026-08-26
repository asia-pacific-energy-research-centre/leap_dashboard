# Implement PRC power own-use projections and power-page loss ownership

## Objective

Fix the missing projected fuels shown on the PRC Target **Power** dashboard for
`10.01.01 Electricity, CHP and heat plants`, then make the Power page own the
electricity and heat portion of transmission and distribution losses.

This is a cross-repository change. The dashboard presentation work belongs in
`C:\Users\Work\github\leap_dashboard`; the LEAP seed/model projection work
belongs in `C:\Users\Work\github\leap_initialisation`. Do not modify generated
dashboard HTML, chart JSON, archives, or mapping output directly.

## Confirmed evidence

The archive to use as the reproduction case is:

```text
C:\Users\Work\Downloads\05_PRC_Target_dashboard_archive_260826_123917\dashboard\05PRC\dashboards\power.html
```

For Common flow `10.01.01 Electricity, CHP and heat plants`:

- The dashboard has detail cards for the non-electricity fuels. They are not
  being suppressed by the browser or renderer.
- In the archive's `mapping_chain/leap_results_converted_to_esto.csv`, coal,
  coal products, crude oil, petroleum products, natural gas, and other biomass
  have a non-zero 2022 value but are zero in every projection year 2023–2060.
- Electricity is the only product with non-zero values for all 38 projection
  years. Heat also becomes zero after 2022.
- The dashboard chart manifest correctly reports those fuels as sparse model
  series. Therefore the root defect is upstream LEAP input/projection coverage,
  not dashboard chart generation.

For `10.02 Transmission and distribution losses`:

- `17 Electricity` and `18 Heat` have meaningful rows for ESTO, LEAP, and
  Ninth in PRC and are currently routed to **Other transformation**.
- Other `10.02` fuels must stay on **Other transformation**.
- The present dashboard special-routing matcher supports flow conditions only;
  it cannot safely move only products 17 and 18 without a small product-aware
  extension.

## Required work

1. Read repository instructions first, including:

   - `leap_initialisation/AGENTS.md` and its referenced balance/export notes;
   - `leap_dashboard/AGENTS.md`;
   - `leap_mappings/docs/mappings_system.md`,
     `leap_dashboard/docs/common_esto_mapping_consumer.md`, and the linked
     Common ESTO consumer contract before changing any dashboard mapping
     assumptions.

2. Reproduce the PRC finding from the archive and trace the non-electricity and
   heat values backwards through `leap_results_converted_to_esto.csv`, raw LEAP
   results, and the `Other loss and own use/Electricity CHP and heat plants`
   input/projection path. Identify precisely why only electricity receives a
   projection.

3. Implement the upstream correction in `leap_initialisation` so the branch's
   projected fuel mix is derived from an existing, defensible source rule. Do
   not simply carry 2022 values forward, fabricate fuel shares, or duplicate
   Common ESTO mapping logic. Preserve signs, scenario isolation, mass/balance
   checks, and the distinction between historical calibration and projection.
   If the available source/model rules cannot support a defensible projection,
   stop before inventing one and document the needed modelling decision with
   evidence.

4. In `leap_dashboard`, rename the Power aggregate titled
   `10 Losses and own use` to **Power-related losses and own use**. Scope this
   as a presentation label for Power if a global rename could affect another
   page. Update relevant guide copy, documentation, and focused test
   expectations.

5. Add a product-aware, explicit dashboard routing special case that sends only
   Common flow `10.02` products `17 Electricity` and `18 Heat` to the Power
   page. Keep every other `10.02` product in Other transformation. Give the
   Power section an accurate label such as `Transmission and distribution
   losses`; do not combine it numerically with `10.01.01` own use.

6. Update the Power and Other transformation guide content so page ownership,
   boundaries, signs, and the residual non-electric/heat `10.02` losses are
   clear. Record the presentation decision in
   `docs/special_rules_and_design_decisions.md`.

## Tests and acceptance criteria

- Add focused unit/regression tests for product-aware special routing:
  `10.02` + `17`/`18` routes to Power in every comparison scope, while at least
  one non-electric `10.02` fuel remains on Other transformation.
- Preserve mapping ownership: no source data is duplicated across pages and no
  Common category is allocated/disaggregated by the dashboard.
- Add a regression test for the Power-specific aggregate label and update tests
  that currently assert `10 Losses and own use`.
- Run the focused dashboard tests, render the tracked USA fixture, and run the
  normal page-noise, routing-QA, and publication-readiness checks required by
  `leap_dashboard/AGENTS.md`.
- Run proportionate initialisation validation for the altered source path,
  including a narrow PRC seed/results check where Windows LEAP COM is available.
  Do not interrupt any long-running reconciliation workflow.
- Re-render the PRC Target dashboard using a newly produced results export.
  Verify 2023, 2030, and 2060 for `10.01.01` product series against their
  declared upstream source, and verify the Power/Other-transformation page
  assignments and chart manifests for `10.02` electricity, heat, and a retained
  non-electric fuel.
- Commit small, repository-scoped changes separately. Do not commit pre-existing
  edits. Report exact commands run, outputs inspected, and any remaining
  modelling decision or external LEAP dependency.

## Definition of done

The revised PRC Power page contains projected `10.01.01` fuel series wherever
the approved upstream source supports them (and clearly identifies any truly
unavailable series); calls its own-use/loss overview **Power-related losses and
own use**; and presents `10.02` electricity and heat on Power while leaving the
other `10.02` fuels on Other transformation. All changes are source-driven,
tested, rendered, and committed without hand-editing generated outputs.
