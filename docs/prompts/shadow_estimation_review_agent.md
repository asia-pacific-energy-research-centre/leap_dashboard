# Agentic estimation-method chart review

**Status:** Active design and review instruction pack

**Purpose:** Give an agent a repeatable, read-only way to test whether a LEAP
result looks like the result implied by the current documented estimation
methods, then show material and safe differences using the production Common
ESTO dashboard figures. An explicitly requested audit may also render a safe
passing boundary: a close match is evidence that the method/boundary path is
working, not an error.

This is deliberately not a workflow for creating or storing a universal
"expected LEAP results" dataset. Estimation methods, exports, mapping runs,
and LEAP configurations change. The agent should construct narrowly scoped
test expectations for a stated question, retain provenance, and discard the
working calculation after writing its review evidence.

## Required reading

Read in this order before acting:

1. `leap_dashboard/AGENTS.md` and `docs/work_queue.md`.
2. `leap_mappings/docs/mappings_system.md` and
   `leap_dashboard/docs/common_esto_mapping_consumer.md`.
3. The relevant estimation-method document and the workflow that produced the
   selected seed/result/export in `leap_initialisation`.
4. `leap_initialisation/docs/baseline_seed_balance_diagnostics.md` when the
   question compares seed-derived intent to a post-import LEAP balance.
5. `codebase/common_esto_dashboard_renderer.py`, especially the existing
   chart builder for the requested chart family.

The visual reference
`C:\Users\Work\.codex\visualizations\2026\08\20\01a01cc6-7099-7342-a3b4-4aa05b55e2bd\transformation_net_fuel_balance.html`
shows the intended investigation: reconstruct signed transformation fuel
components from estimation inputs and compare their net total with observed
output. It is not production code. Do not copy its hand-written Plotly traces
or hard-coded values into the dashboard.

## Non-negotiable boundaries

- `leap_mappings` owns mapping, hierarchy, rollup, component membership, and
  source-to-Common ESTO conversion. The agent must call or consume those
  artifacts; it must not recreate their semantics.
- `leap_initialisation` owns estimation methods and LEAP-boundary adjustments.
  The agent must cite the method file and its input artifacts for every
  calculated expectation.
- `leap_dashboard` owns chart construction and presentation only. Render
  figures through its existing builders (for example `build_product_chart`,
  `build_area_chart`, and the normal bundle/page writers). A direct
  `Figure.to_html` export is not a mergeable review output: it does not prove
  the dashboard's bundle, lazy-loader, filtering, or chart-card contract.
  Never use standalone handwritten Plotly markup.
- All work is read-only unless a user separately authorizes code, mapping, or
  model changes. Never update a seed, import workbook, LEAP area, mapping
  workbook, or production dashboard output while investigating.
- Never allocate a source total to create a comparable expected row. If a
  comparison requires an unreviewed split, report `unsafe_comparison_grain`
  and do not draw a mismatch chart.

## Agent procedure

### 1. Define a narrow question

State the economy, scenario, LEAP export/run, years, flow/product boundary,
and the relevant estimation method. Prefer one process/fuel boundary first;
for example, `09.07 Oil refineries (including own use)` by one product or
`09.08.01 Coke ovens (including own use)` by fuel.

Do not begin from an entire dashboard or an all-economy difference scan.

### 1a. Separate the code-variable expectation from downstream comparators

First locate the active estimation workflow's own emitted variables or process
records. For a transformation process this can mean pre-seed capacity, output
share, efficiency, and auxiliary-use variables; derive the expected output
from those variables before workbook/seed assembly. The balance diagnostic is
still required for the observed LEAP stack and a canonical 9th comparator, but
it is not a substitute for the code-variable expectation.

Record whether the selected evidence is current for the export. An older
diagnostic can demonstrate an investigation pattern but cannot establish the
state of a newer LEAP area.

### 2. Establish the comparison boundary

Resolve the expected and observed series onto the same declared Common ESTO
boundary and establish whether it is an input, output, net, or inclusive
transformation boundary. Inspect and record:

- sign convention;
- own-use/loss treatment;
- placeholder or replacement-sector status;
- Common ESTO comparison scope and mapping run ID;
- source-to-common cardinality; and
- hierarchy frontier selected by the dashboard.

For transformation processes, input, output, and auxiliary fuel must remain
separate during reconstruction. A net total is useful for review only after
those component checks have passed; never use cancellation to conceal a bad
component.

### 2a. Prove the process reconstruction before calling it an expectation

Before plotting an expected net line, make a one-year reconciliation table
for the selected process and the exact selected run. It must contain, on the
same signed inclusive boundary:

```text
stage, gross output, feedstock input, auxiliary/own use, net total,
artifact path, artifact hash/run ID
```

The stages are: the source/9th boundary where applicable, the active
workflow's emitted process variables, and the observed LEAP result. For oil
refining, `09.07 Oil refineries` plus `10.01.11 Oil refineries` is the
inclusive source boundary; the latter is represented in LEAP as Auxiliary
Fuel Use, not as a second net-total line.

When the active method derives its process variables from the mapped 9th
projection, the mapped inclusive 9th total is the first preservation target:
the process-variable reconstruction must agree with it within the stated
tolerance. A gap is an upstream `source_to_process_reconstruction_mismatch`,
not an assumed LEAP-calculation difference. For oil refining, this specifically
tests that mapped `09.07 Oil refineries` plus `10.01.11 Oil refineries` is
preserved through capacity, output shares, feedstock efficiency, and auxiliary
fuel use. Only after that passes may the agent compare the same reconstructed
net with LEAP. If either reconciliation fails, withhold the expected-net line
and render component evidence only.

### 2b. Classify the process accounting before selecting a formula

Do not transfer a formula from one transformation module to another merely
because both have capacity, efficiency, output-share, or auxiliary-use
variables. Before calculating an expected net, inspect the active workflow,
the selected export, and the Common ESTO mappings, then record a small
classification table for each process or aggregate card:

```text
process/card, mapped source boundary, capacity basis, output ownership,
own-use owner, auxiliary denominator, expected-net formula, evidence paths
```

The classification must establish whether capacity is gross process output,
deliverable output, or absent/endogenous; whether an auxiliary fuel is supplied
from the same process output, another transformation module, or a demand/loss
proxy; and whether the auxiliary-use variable is a fraction, percentage, or
direct per-unit ratio. Use the formula supported by those facts only. For
example, a gross-capacity process can use output minus feedstock minus its
process-owned auxiliary use, while a deliverable-capacity process may require
a gross-up. A parent card which combines children with different ownership or
unresolved subtotal allocation has no safe single expected-net line: retain
the normal dashboard stack and write `unclassified_process_accounting` in the
evidence instead.

An interim or capacity-constrained module may instead be **endogenously
dispatched**: `Exogenous Capacity` is an upper bound, not an instruction to
produce that amount. Evidence can include zero Historical Production and no
nonzero output trade target. For that class, do not call the difference between
capacity and realised LEAP output an error, and do not label capacity as
`Expected output`. Check that realised activity is within capacity and derive
one expected total from the emitted conversion settings at that activity (for
example, realised output minus realised output divided by the emitted
efficiency, with the emitted feedstock shares). In the chart, call this simply
`Expected total (code settings)`; its evidence must state that activity is
LEAP-realised, so it is a settings-response check rather than an independent
dispatch forecast. Do not draw a capacity-envelope line by default: add one
only when the review question is specifically about utilisation or a binding
capacity constraint. Retain the 9th source trajectory as a separate comparator,
not as a failed LEAP dispatch target.

This classification is required separately for every economy, scenario, run,
and process boundary. Named rules in the case ledger below are examples, not
defaults for other transformation cases.

When own use is owned by a separate demand/loss proxy, retrieve its emitted
activity and intensity (or equivalent calculated amount) from that same run
and add its signed consumption to the inclusive process net. Do not omit it
merely because it is not an `Auxiliary Fuel Use` row in the transformation
workbook. The agent may withhold the line only when the proxy output or its
source route cannot be traced for the selected run.

### 2c. Direct demand-energy class

An `All demand aggregated` component can be a direct demand-energy class rather
than a transformation or dispatch calculation. For that class, calculate the
expected total from the emitted code variables at the fuel-leaf grain:

```text
expected total = sum(Activity Level × Final Energy Intensity)
                 for every emitted aggregate-demand branch in the selected
                 dashboard boundary and scenario
```

Use the emitted workbook's viewing/value table or its parsed expressions; do
not reconstruct the value from a later baseline seed rollup. Then compare that
total with the normal dashboard card that claims to represent the same boundary.
When a Common ESTO card is explicitly inclusive, first include every emitted
code branch it owns (for example, `Other sector` plus `Non Energy Use`) before
classifying a mismatch. If the fully matched boundary still differs, retain the
line and classify the difference as `dashboard_to_code_boundary_mismatch` until
the mappings establish which extra or missing branches belong in the card. Do
not change the expected formula just to make a broader Common ESTO card agree.

### 3. Reconstruct a temporary expectation

Run the method described in the source workflow using only the declared seed,
source, and configuration inputs. Create an in-memory/narrow temporary table
with at least:

```text
economy, scenario, year, comparison_scope,
common_flow_code, common_product_code,
expected_value, observed_leap_value,
difference, absolute_difference, percent_difference,
comparison_status, method_path, method_version_or_hash,
seed_or_source_hash, leap_export_hash, mapping_run_id,
boundary_rule, comparison_grain
```

Expected values must be labelled `candidate_estimation_expectation` until the
method and boundary have been reviewed. They are never a new dashboard source
system and are never added to the permanent Common ESTO fact table.

### 4. Decide whether a visual comparison is safe and material

Withhold the chart if any of these apply:

- missing expected or observed values;
- unresolved mapping/cardinality/fan-out;
- mixed placeholder and replacement branches without a passing group-boundary
  reconciliation;
- unclassified sign or own-use treatment; or
- no material difference under the explicitly stated absolute and percentage
  tolerances.

Write a compact evidence row for every withheld result. A withheld result is
useful diagnostic evidence, not a silent omission. An explicit user request
for a full-boundary audit may render a safe non-material match, but the page
and manifest must label it `audit_pass` rather than presenting it as an alert.

### 4a. Use the full available horizon

For a selected export, first inspect its available year sheets and regenerate
or select a diagnostic over every requested projection year. Do not project a
single-year discrepancy forward. Plot every year for which both LEAP and the
declared source comparator are available at a reviewed comparison grain.

Record years withheld from the expectation line, including the reason (for
example `ESTO unavailable`, `source unavailable`, or
`unsafe_comparison_grain`). A LEAP-only fuel may still appear in the actual
fuel-mix stack, but it must not create an expected-output point.

### 5. Render through the dashboard code

For material, safe results, pass temporary review rows alongside the actual
LEAP rows into the same production chart builder that owns the ordinary chart:

- preserve the existing figure layout, axes, legend placement, sign notes,
  base-year marker, `trace_meta`, responsive bundle mechanism, and chart-card
  HTML;
- use one composite stacked-area chart for a transformation boundary whenever
  a fuel mix is useful: LEAP Target fuel areas, the builder's LEAP Target net
  total, and one restrained dashed expected-output line;
- derive the expected-line label from its actual provenance. When the active
  workflow emits capacity/output-share variables, label their result
  `Expected output (transformation settings)` and retain the 9th Target line
  separately; use `Expected output (9th Outlook)` only when 9th is genuinely
  the direct method input and no code-variable expectation exists;
- include an ESTO historical line only when the maintained comparison supplies
  an ESTO value at the same boundary. Never add a zero or reconstructed ESTO
  point merely to complete the visual;
- use the normal `build_area_chart` path for the composite figure, then the
  normal bundle/page writers. Preserve its LEAP stack and total-line behaviour
  rather than hand-assembling Plotly traces;
- render to an isolated review output root; do not add it to ordinary pages or
  published docs;
- use the ordinary chart manifest shape plus the provenance columns above.

The result should be able to move into a future diagnostic page without a
visual rewrite. A reviewer should recognise it immediately as a dashboard
chart, not an external analysis graphic.

### 5a. Review-output contract

Each isolated review root must contain:

```text
diagnostics/                  # maintained comparison inputs selected for this review
chart_bundles/<review>__charts.js
dashboards/<review>.html      # exactly one composite chart card per selected boundary
supporting_files/shadow_chart_manifest.json
```

The manifest must state the selected export, year coverage, comparator source,
withheld years, comparison grain, flow/product boundary, mapping evidence,
chart key, and review outcome (`material_difference`, `audit_pass`, or
`withheld`). This is review evidence, not a durable dashboard fact dataset.

### 6. Report, do not repair

For every material difference, state the exact boundary, component evidence,
direction and size of the gap, provenance, and plausible owner:

- estimation method/input;
- LEAP model configuration or calculation;
- export/result extraction;
- mapping/boundary definition; or
- unresolved evidence.

Do not infer a fix or modify source data. Stop for human review before any
change to a mapping, estimation method, seed, or LEAP area.

## Versioned LEAP total lines

This capability must remain compatible with `DASHQ-058`, but does not depend
on it. If a reviewer supplies multiple LEAP exports, treat each as a separate
observed result series—not as an expected value. Keep its export hash, run
label, mapping run, scope, scenario, and selected boundary. A series from a
different mapping run or boundary is not comparable until a reviewed
normalisation path exists.

## Initial acceptance example

Reproduce the review question in the visual reference for Australia coal
transformation, but generate the chart with the dashboard renderer:

1. Reconstruct coke-oven or blast-furnace signed inputs, output, and auxiliary
   use from the documented baseline-seed method.
2. Verify the inclusive own-use boundary before forming a net total.
3. Compare it with the selected LEAP export at the same Common ESTO boundary.
4. Render a chart only if the tolerance is exceeded and the comparison is
   safe.
5. Produce a manifest/evidence table that lets a human trace every plotted
   point to its method and source artifacts.

Completion of an investigation is an evidence-backed review result, not a
new permanent data pipeline. Move this prompt into `docs/archive/` only after
the capability is implemented, tested, committed, and superseded by an
operational guide.

## Case ledger: Australia refining, first live test

**Question:** Does the `01_AUS` Target balance export reproduce the expected
refinery product outputs at the inclusive refinery boundary?

**Current evidence:**

- Balance export: `data/leap balances exports/01_AUS/AUS TGT 1808 daniel.xlsx`.
- Maintained diagnostic: `outputs/diagnostics/ah72_investigation_20260818/`
  `leap_balance_source_differences.csv` in `leap_initialisation`.
- Safe boundary: `09.07 Oil refineries (including own use)`, not bare
  `09.07 Oil refineries`; the former is the reviewed refinery transformation
  plus own-use comparison boundary.
- First usable projected comparison: 2023 Target. Its refinery output rows
  use `canonical_allocated_ninth_to_esto_pair`, so the selected 9th projection
  has a documented comparison route rather than an ad hoc dashboard split.

The maintained 2023 diagnostic shows a common direction across refinery
outputs: for example motor gasoline is `-8.969 PJ` (`-4.812%`) and gas/diesel
oil is `-7.863 PJ` (`-4.812%`) versus the projected expectation. Crude-oil and
refinery-feedstock inputs are much closer (about `-0.062%`). This is a
material, reviewable pattern; it is not yet proof of an estimation or LEAP
defect. The agent must next trace the Target oil-refining process record,
capacity/output-share expressions, and the selected export's provenance before
assigning an owner.

Natural gas and electricity rows are not chart-safe in this case because the
selected diagnostic has no source comparator for them. They must remain
withheld rather than drawn as zero-valued expected series.

### Recorded refinery lessons (case-specific example)

The first implementation made three errors. These are retained as refinery
guardrails rather than treated as one-off prototype details. They apply only
after the classification above proves the same refinery accounting boundary;
they are not a universal transformation formula:

1. **Do not begin by blaming LEAP.** When process variables are derived from
   the mapped 9th projection, first reconcile the code-variable net against
   the inclusive 9th total. Only the remaining code-to-LEAP difference is a
   LEAP/import/export review question.
2. **Do not treat refinery Exogenous Capacity as gross output.** The
   capacity-like Target override intentionally seeds *deliverable* output for
   `Oil Refining`: same-module output fuel used as auxiliary energy is already
   netted from that capacity. LEAP grosses the process internally to supply
   that auxiliary demand. A shadow reconstruction must recover gross output
   as `deliverable_output / (1 - same_module_auxiliary_ratio)`, calculate
   feedstock from that gross output and efficiency, and subtract only
   *external* auxiliary energy from deliverable output. Subtracting all
   auxiliary use from deliverable capacity double-counts same-module own use.
3. **Do not draw a separate own-use total beside this net.** For this boundary
   it is an accounting component of the same signed net, not a comparable
   second outcome. Retain component values in the evidence table and hover
   provenance instead.

For the audited `01_AUS` Target 2023 workbook
`SEED_AUS_CONSOLIDATED_20260820`, the corrected reconstruction is
`-52.742 PJ`; the dashboard's 9th Target total is `-52.725 PJ` (difference
`-0.017 PJ`, approximately `0.03%`). This passes the source-to-process
reconstruction check. The dashboard LEAP Target net is `-52.154 PJ`; its
roughly `0.57 PJ` gap from the now-validated expected/9th net is the separate
next investigation, not evidence against the reconstruction formula.

Required evidence for another refinery run is therefore: selected 9th source
and mapping run, process-variable workbook/run ID, identification of
same-module versus external auxiliary fuel labels, the three accounting
components (deliverable output, recovered gross feedstock, external auxiliary
use), and the selected LEAP result export. Do not carry any of these numeric
values to another economy, vintage, or scenario.

## Case ledger: Australia full-horizon refinery and hydrogen reviews

The first live review was extended to all 38 available Target projection years
(`2023`–`2060`) from `AUS TGT 1808 daniel.xlsx`. The isolated refinery review
uses one composite dashboard chart: all mapped LEAP Target refinery fuels as
stacked areas, the LEAP Target total, `Expected output (transformation
settings)` derived from the pre-seed Exogenous Capacity × Output Share
variables, a separate 9th Target output line, and an ESTO historical-output
line. Natural gas and electricity remain actual stack categories only because
the selected output expectation is gas/diesel.

The refinery *net* expectation uses the more specific deliverable-capacity
gross-up rule above; it must not be reconstructed with the output-only
capacity-times-share formula.

The same contract was tested on `09.13 Hydrogen transformation` →
`16.12 Hydrogen`. Its mapped LEAP stack contains ammonia, e-fuel, and hydrogen
and its expected/observed output matches closely across the full horizon. It
is an `audit_pass` design example, not a mismatch alert. The selected
projection diagnostic supplied 9th Outlook values, but no maintained ESTO
hydrogen comparator; therefore no ESTO line is drawn.

## Case ledger: Australia electricity interim, capacity-dispatch check

`Electricity interim` is not an output-target process. In the audited Target
workbook it has zero Historical Production and zero output trade targets, while
its 2023 Exogenous Capacity is `950.707 PJ`; that value is a capacity ceiling.
LEAP realises `913.059 PJ` of electricity (`96.0%` utilisation), and the
emitted 2023 efficiency (`45.539%`) gives a conditional expected net of
`913.059 - 913.059 / 0.45539 = -1091.935 PJ`, matching the dashboard LEAP
Target net (`-1091.935 PJ`, rounding only). The 9th source net is
`-1116.741 PJ`: it remains a source-trajectory comparator, but its difference
from realised LEAP dispatch is not by itself an interim-model defect.

For this class, the shadow chart shows the normal LEAP fuel stack and total,
the 9th total, and one purple `Expected total (code settings)` line. It is
calculated using realised LEAP activity and the emitted conversion settings,
which is recorded in the evidence as a settings-response check. A separate
capacity-envelope line is omitted because it does not improve the output
comparison; it may be added only for a review explicitly about utilisation or
binding capacity. The visual label stays plain, while the evidence preserves
the methodological distinction.

## Case ledger: Australia All demand aggregated, direct demand-energy review

The audited Target workbook
`SEED_AUS_CONSOLIDATED_20260820_R2/aggregated_demand_01_AUS_Target_Reference_CurrentAccounts_by_sector.xlsx`
has one Activity Level and one Final Energy Intensity setting per aggregate
sector/fuel leaf. Its expected sector total is the sum of those products, not
a value reconstructed from a Common ESTO rollup. Across `2023`–`2060`, the
Industry card matches its LEAP Target stack within floating-point rounding and
Transport non-road matches within `0.000008 PJ`. The Other-sector card is an
inclusive boundary: it must sum both emitted `Other sector` and `Non Energy
Use` branches. With both included, it also matches the LEAP stack within
`0.000130 PJ`. These are direct code-to-LEAP passes. The initial single-branch
comparison is retained as a workflow guardrail: a label containing
`including non-energy` must cause the agent to inspect the component mapping
before reporting a code-to-LEAP difference.
