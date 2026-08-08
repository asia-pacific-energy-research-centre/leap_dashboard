# Plan: mapping inversion, measure-aware dashboard, and derived factor sets

**Status:** Not started. Written 2026-08-06, revised after owner review, to be
enacted later.
**Repos touched:** `leap_mappings`, `leap_dashboard`, `leap_initialisation`
(manifest), `leap_review_tools` / `leap_review_web_app` (deploy only).

## Goal

Three connected changes, in the owner's words:

- **Inversion.** `leap_dashboard` should use the *mapping tables* from
  `leap_mappings` to convert the original datasets into the common structure,
  rather than consuming a pre-built common-structure fact table. This guarantees
  that someone with different numbers for any dataset still gets the same
  fundamental mapping, and it builds the habit of mapping datasets as they are
  needed instead of depending on one central converted dataset.
- **Measure-awareness.** The dashboard currently assumes exactly one measure
  (energy, PJ). It needs to carry a measure and unit per series.
- **Factor sets.** ESTO and LEAP emissions factor sets, derived for now by
  propagating the 9th-edition factors through the existing
  `outlook_mappings_single_axis.xlsx` mappings.

Phases below are lettered (A/B/C) deliberately: an earlier draft numbered them
to match the list above and then recommended a different order, which was
confusing. **Phase C is the inversion.**

## Where everything is written down

**For the 2026-08-06 overnight session, the operational runbook is
`docs/prompts/overnight_work_program_20260806.md`** — work items, order, gates
and the report template. This file is the design reference it points back to.

This file is the plan for all phases. Two companion documents are **reference
contracts, not plans** — they describe how the mappings are meant to be used and
are updated as phases land:

- `leap_mappings/docs/using_common_esto_mappings.md` — the publisher-side
  contract, with a current-vs-planned status table and one open question for
  maintainers (are spanning rollups deliberately outside the declared tree?).
- `leap_dashboard/docs/common_esto_mapping_consumer.md` — the consumer-side
  worked example.

Already-implemented behaviour is recorded separately in
`leap_dashboard/docs/special_rules_and_design_decisions.md` (`DASH-021`), not
here.

## Recommended order: 0 → A → B → C

- **0. Ship the existing Emissions page to the web app** — no architecture work;
  delivers the original request on its own.
- **A. Measure-aware dashboard** — one repo, no new upstream artifacts.
- **B. Derived factor sets + emissions as a measure** — depends on A to display.
- **C. Mapping inversion** — spans two repos and creates a new published
  artifact, so it carries the most coordination risk even though its code is
  small (one merge, no allocation).

The inversion last, because if it lands first the new conversion path is built
single-measure and has to be reworked immediately. This is a recommendation, not
a constraint; if the inversion is the priority, do it first and accept the
rework.

## On the "don't reproduce mapping logic" rule

`leap_dashboard/AGENTS.md` line 48 says:

> Do not reproduce mapping logic in dashboard code.

An earlier draft of this plan described that as forbidding the dashboard from
converting datasets. That was an overstatement. The rule says *reproduce* — do
not write a **second implementation** of the mapping semantics. It does not say
the dashboard may not *run* the conversion.

The owner's position (2026-08-06): changing mapping semantics is fine as long as
the **mapping tables come from `leap_mappings`**; the code that applies them is
simple enough that the semantics live in the tables, not the code. Applying a
mapping means merging source rows onto an existing mapping output — such as
9th → common ESTO — exactly as the emissions factors are merged on today.

**This is correct.** An earlier draft of this plan argued otherwise by comparing
whole-file line counts, which measured the wrong thing. Corrected measurement,
2026-08-06 — separate *building* a mapping from *applying* one:

| Operation | Where | Size | Runs |
|---|---|---|---|
| **Build** the common structure (decide which components form which common rows) | `build_common_esto_structure.py` | 1,883 lines | Rarely; output is `common_esto_rows.csv`, already a shipped asset |
| **Apply** it to source values | `apply_common_structure` in `apply_common_esto_structure.py` | **137 lines** | Every conversion |
| Per-economy wrapper around the apply | `apply_common_structure_by_source_economy` | 147 lines | Every conversion |
| Convert a native dataset into ESTO shape | `convert_leap_results_to_esto.py` | 316 lines | Every conversion |

`apply_common_structure`'s own docstring is *"Join ESTO-shaped source rows to
common rows and aggregate values."* It is a merge on
`(comparison_scope, component_esto_flow, component_esto_product)` followed by an
aggregation. The remaining ~2,150 lines of that 2,436-line file are
orchestration, relevance and coverage QA, diagnostics, total checks and output
writing — **none of which the dashboard needs to reproduce.**

So the conversion the dashboard actually needs is **two merges**: native → ESTO
shape, then ESTO shape → common rows. The complexity lives in *building* the
structure, which stays upstream and is already consumed as data.

**The owner's suggestion is the right answer and it is cheap:** hold that merge
in `leap_mappings` as an importable function, so there is one canonical
implementation and it doubles as the guide for how the merge is meant to be
done. The dashboard calls it with whatever numbers it has. This is Phase C, and
it is a much smaller phase than the earlier draft implied.

The residual drift risk is small but real, and is what the importable function
protects: the join keys, the aggregation, the `comparison_scope` filtering and
the sign handling all have to match exactly, and a second copy that quietly
disagreed would surface as wrong comparisons rather than as an error.

Note that the same AGENTS.md paragraph also says `leap_mappings` "produces the
Common ESTO comparison data consumed here". That clause describes the current
arrangement, which Phase C changes. **Update that paragraph as part of Phase C**
rather than treating it as law.

## Design principle: dataset fidelity beats factor uniformity

Owner decision, 2026-08-06, and it governs Phase B.

It may look odd to convert 9th data with 9th factors rather than putting every
dataset on one common factor set. A common set is attractive, but **the more
important property is that 9th emissions reproduce published 9th emissions.**
So each dataset uses its own native factors wherever they exist. The 9th keeps
its own factors permanently; they are also the easiest to apply.

The consequence, stated plainly so nobody rediscovers it as a bug: a difference
between two sources then mixes energy differences with factor differences. That
is accepted. The common-axis factor table (B1) remains available as a diagnostic
view when someone specifically wants to hold factors constant and isolate the
energy difference — both views are supported, and they answer different
questions.

## Current state (verified 2026-08-06)

Facts established while investigating, so this plan can be picked up cold:

- **`leap_mappings` is already measure-agnostic where it matters.**
  `apply_common_esto_structure.py` contains no unit or measure handling at all;
  it carries values and sums them, and its rollups are label-to-label.
- **The dataset registry already models the concept.**
  `leap_mappings/config/datasets/dataset_registry.csv` has `native_unit`,
  `value_adapter`, and `canonical_target_dataset_id` per dataset. All six rows
  currently say `PJ`.
- **But PJ is pinned.** `codebase/mapping_tools/value_adapter_registry.py:221`
  raises unless `native_unit == "PJ"`. A deliberate lock, not an obstacle.
- **`leap_dashboard` is not measure-aware.** ~24 hardcoded `"PJ"` literals in
  axis titles and hovertemplates; sign semantics (`production_supply`,
  `exports_removed_from_supply`, …) and the overview identities
  (`supply = 01 + 02 - 03`, TFC/TFEC) are energy-balance concepts; the
  three-way comparison is hardwired to `LEAP`/`ESTO`/`NINTH` `source_system`
  values with no measure dimension to pair within.
- **The fact grain would cope.** Emissions datasets entering as new
  `source_system` values would not collide with anything.
- **Only one emissions factor file exists** across all three repos: the
  9th-edition one at
  `leap_dashboard/config/9th_edition_co2_emissions_factors_by_fuel_energy_weighted_20250403_122429.csv`.
  There is no ESTO factor set and no LEAP factor set. This is why Phase B
  derives them rather than sourcing them.
- **The inversion has a working precedent.** The Gradio Space already bundles a
  mapping-chain worker (`parse_leap_balance_export`,
  `convert_leap_results_to_esto`, `apply_common_esto_structure`,
  `portable_mapping_chain` — see the module-closure comment in
  `leap_initialisation/config/portable_release_manifest.toml`) and runs it on an
  uploaded LEAP export, joining the result onto shipped ESTO and 9th tables.
  Phase C generalises that existing pattern to all three datasets; it is not a
  new invention.

### Already done (on branch `claude/dashboard-emissions-page-5c4fbd`)

An Emissions page exists and works, deriving emissions on the common axis from
the 9th factors. See `DASH-021` in `docs/special_rules_and_design_decisions.md`.
It is the thing being generalised, and its numbers are the migration baseline:
**20USA 2022 = 3,443 Mt CO2e, agreeing across LEAP, ESTO and 9th.**

Known debt in it, resolved by Phase B: it performs mapping work (9th-fuel to
ESTO join, subfuel collapse, `_unallocated` aliasing, conflict resolution)
inside dashboard code. That *is* a second implementation of mapping semantics,
so it is exactly what the AGENTS.md rule is aimed at, and it moves upstream.

## The safety property for every phase

**Each phase must be value-preserving and independently verifiable.** No phase
may change a number. Concretely:

- Energy: dashboard output after a change must reproduce the current
  `common_esto_comparison_data.csv`-derived charts exactly.
- Emissions: 20USA 2022 must stay 3,443 Mt CO2e across all three sources.
- Every phase gets a regression test asserting the above before it is merged.

If a phase changes a number, that is a finding to explain, not a result to
accept.

The executable form of this property is specified in **Before/after equivalence
tests** below. Note the precondition documented there: renders are
content-deterministic but **not** byte-deterministic, so all comparison must
normalise ordering first. Comparing bytes or hashes reports false regressions on
unchanged code.

---

## Phase 0: ship the existing Emissions page to the web app

**Independent of A/B/C.** The Emissions page already works and is validated; it
simply never reaches the Gradio Space, because the Space runs off a frozen
`runtime/` snapshot whose file list does not include it. `emissions_page_enabled`
finds its inputs missing and hides the page *and* its nav chip — correct
graceful degradation, but it means the page is invisible there.

This is the owner's original request, and it needs none of the architecture work
below. Do it first.

### Four files must reach the runtime

`[repositories.leap_dashboard]` in
`leap_initialisation/config/portable_release_manifest.toml` currently names 4
modules, and `[[config_assets]]` names 3 config files. Add:

| File | Repo | Why |
|---|---|---|
| `codebase/common_esto_dashboard_emissions.py` | `leap_dashboard` | the page itself |
| `config/common_esto_dashboard/emissions_factor_sets.json` | `leap_dashboard` | factor set config |
| `config/9th_edition_co2_emissions_factors_by_fuel_energy_weighted_20250403_122429.csv` | `leap_dashboard` | the factors |
| `config/outlook_mappings_single_axis.xlsx` | `leap_mappings` | the 9th-fuel → ESTO contract |

### One dependency can be removed for free

The page currently reads
`leap_mappings/results/common_esto/esto_to_common_esto_map.csv`, which is **not**
in the runtime. `common_esto_rows.csv` **is** (declared as
`mapping_chain_common_esto_rows`), and the two give **set-identical**
product→common pairs — verified 2026-08-06, zero differences either way.

Switching the lookup removes one manifest entry. Do this before touching the
manifest.

### Do not substitute the master workbook

`outlook_mappings_master.xlsx` is already in the runtime and looks like a free
swap for `single_axis`. It is not. Its `ninth fuel to esto product` sheet is a
superset carrying `15_solid_biomass -> 15 Solid biomass` and
`16_others -> 16 Others`, which would put those codes into the registry, defeat
the rule that drops fuel-level aggregate rows, and reintroduce double counting.
It is also missing `05_oil_shale_and_oil_sands`. Use `single_axis` — it is the
human-maintained source of truth per its own README.

### Also worth doing while here

`common_esto_dashboard_emissions.py` resolves its config paths from
`REPO_ROOT = __file__.parents[1]`. That works in the Gradio runtime layout
(`runtime/leap_dashboard/{codebase,config}/`) but **not** in the portable
executable staging, which uses `strip_prefix = "codebase"` and flattens it.
The portable module's stated design is "every input an explicit argument,
nothing from the working directory" — add an explicit factor-config path
argument so both layouts work.

### Steps

1. Switch the common-axis lookup to `common_esto_rows.csv`; confirm the factor
   table and 20USA 2022 = 3,443 Mt CO2e are unchanged.
2. Add the explicit factor-config path argument.
3. Merge the branch (the manifest pins commits and sha256 hashes, so nothing can
   be added until the work is on master).
4. Add the three remaining files to `portable_release_manifest.toml` with hashes.
5. `leap_review_tools/scripts/refresh_runtime.py`, copy `runtime/` into
   `leap_review_web_app`, deploy.
6. Confirm the page and its nav chip appear in the Space.

---

## Phase A: measure-aware dashboard

**Repo:** `leap_dashboard`. Independent of the other phases.

1. **Add a measure dimension to the dashboard's internal frame.** A `measure`
   and `unit` column alongside `value`, defaulting to `energy` / `PJ` so
   existing inputs are unchanged. Source it from the dataset registry's
   `native_unit` where available rather than inventing a second registry.
2. **Replace the hardcoded `"PJ"` literals** with the unit carried by the
   series being charted. Grep target: `PJ` in
   `codebase/common_esto_dashboard_renderer.py`.
3. **Gate the energy-balance machinery by measure.** Sign semantics, the
   supply/TFC/TFEC identities on the Energy balance overview, and the
   `excluded_flow_code_prefixes` rules must apply only to `measure == energy`.
   A non-energy series must never be fed through `supply = 01 + 02 - 03`.
4. **Pair comparisons within a measure.** `comparison_source_system` /
   `ninth_source_system` resolution must match on `(source_system, measure)`,
   so an emissions series is never diffed against an energy series.
5. **Refactor the Emissions page onto this seam.** It stops being a bespoke page
   that computes its own unit and becomes the first consumer of a general
   mechanism.
6. **Move frontier parenthood onto the hierarchy/subtotal contract.**
   `common_esto_dashboard_emissions.select_non_overlapping_rows` currently
   derives parent/child by parsing code expressions out of display labels. That
   is a second implementation of mapping semantics, and it is unnecessary: the
   contract already declares the common axis in
   `leap_mappings/results/hierarchy_subtotal_contract/current/axis_nodes.csv`
   (`dataset_id = common_esto`, 104 flow + 75 product nodes, with `is_leaf`,
   `is_structural_parent`, `parent_node_id`, `depth`, `child_count`), and this
   repository already has a strict consumer in
   `codebase/hierarchy_subtotal_contract_loader.py`.

   Two parts stay in the dashboard because the declared hierarchy cannot answer
   them: **per-source presence** (leaf-ness is structural, so a source reporting
   only `14 Industry sector` must not be dropped), and **generated rollups
   outside the tree** — measured on `esto_leap_ninth`, 97 of 98 flow labels and
   52 of 54 product labels are in the contract, the exceptions being
   `16.03-16.05,17 Other sector including non-energy (all demand aggregate)`,
   `02.01-02.08 Coal products` and `06.03-06.04 Crude oil and NGL`. The first
   overlaps `16 Other sector` **and** `17 Non-energy use`, so no set of declared
   parents identifies that overlap.

   **Raise the three gaps with `leap_mappings` before building around them.**
   If spanning rollups are deliberately outside the declared tree, that belongs
   in `using_common_esto_mappings.md` as a documented consumer obligation. If it
   is an oversight, fix it upstream and the dashboard-side residue shrinks to
   per-source presence alone.

   **Ordering note — Phase A must not depend on Phase C.** Phase A consumes
   `axis_nodes.csv` directly via the existing
   `hierarchy_subtotal_contract_loader.py`, which exists today. Shipping the
   flags *on the mapping outputs* is a convenience improvement that belongs with
   Phase C, because the any-dataset map it denormalises onto does not exist until
   then. Do not block Phase A on it.

   **Preferred upstream fix (owner proposal, 2026-08-06), scheduled with Phase C:
   ship the flags on the mapping outputs**, so a consumer gets them in the same
   merge instead of joining a separate contract build — a consumer that skips
   that join double-counts silently. Add to
   `leap_mappings/results/common_esto/common_esto_row_metadata.csv` (the
   authority: one row per `(comparison_scope, common_row_id)`, 6,105 rows) and
   denormalise onto the any-dataset map Phase C creates, plus the existing
   ESTO-only `leap_mappings/results/common_esto/esto_to_common_esto_map.csv`:
   `is_subtotal`, `common_flow_is_subtotal`, `common_product_is_subtotal`, and
   `common_flow_hierarchy_status` / `common_product_hierarchy_status` valued
   `leaf` / `parent` / `outside_declared_tree`.

   Projected from `axis_nodes.csv` so the contract remains the single authority.
   The status column must be explicit rather than null: on `esto_leap_ninth`, of
   1,500 common rows, 167 have a structural-parent flow axis, 0 a
   structural-parent product axis, and **112 sit outside the declared tree**. A
   null there reads as "not a parent" and therefore "safe to sum", which is the
   exact double-count being prevented.

   With this landed, the dashboard's frontier code reduces to per-source
   presence plus handling `outside_declared_tree` rows — no code parsing at all.

**Validation:** full render of 20USA and 02BD unchanged for energy; Emissions
page unchanged; `tests/test_emissions_page.py` still green; publication-readiness
and page-noise scripts clean.

---

## Phase B: derived factor sets and emissions as a measure

**Repo:** `leap_mappings` (owns the mapping, so owns the derivation).

### Two distinct outputs — do not conflate them

**B1. Emissions factors on the common ESTO axis.** This is the 54-row table the
current Emissions page already computes internally
(`emissions_factor_resolution.csv`: one factor per `common_product_label`, with
the contributing 9th fuels and ESTO components named). Promote it to a
**first-class published output** of `leap_mappings`, next to
`esto_to_common_esto_map.csv`.

This is the owner's "conversion factors mapped through the common mappings", and
it is worth publishing on its own merits: anyone wanting emissions factors
aligned to the common structure gets one small CSV instead of re-deriving the
chain. It is a legitimate primary deliverable, not a quarantined one.

**B2. Factor sets in each dataset's native vocabulary.** ESTO-product-keyed and
LEAP-fuel-keyed factor sets, propagated outward:

- **ESTO factors:** via `ninth_fuel_to_esto` (9th fuel → ESTO product).
- **LEAP factors:** via `leap_fuel_to_ninth` (LEAP fuel → 9th fuel) **while 9th
  is the derivation source**; via `leap_fuel_to_esto` once real ESTO factors
  exist — see the derivation chain below.

### Every published factor artifact carries `derived_from`

Owner decision, 2026-08-06: **B1 as well as B2.** Both outputs get a
`derived_from` provenance column, valued `ninth` today. Nothing published states
a factor without saying where it came from, so no artifact can later be mistaken
for authoritative just because it was copied out of context.

Treat `derived_from` as data, not a filename convention — the value changes as
the chain below moves, and downstream readers should be able to branch on it.

### The derivation chain is configurable, because it will move

Owner expectation, 2026-08-06: **real ESTO factors are expected; real LEAP
factors are not, and LEAP factors will likely be made to match the ESTO ones.**

So the chain is not fixed, and the ESTO scaffold must be built to become the
*source* for LEAP rather than a peer of it:

| Stage | ESTO factors | LEAP factors | `derived_from` |
|---|---|---|---|
| Today | derived via `ninth_fuel_to_esto` | derived via `leap_fuel_to_ninth` | `ninth` |
| Once real ESTO factors land | authoritative | derived via `leap_fuel_to_esto` | `esto` |

**Do not hardcode "LEAP derives from 9th."** Make the derivation source a config
parameter so the second row is a config change, not a rewrite.

This is directly supported by mappings that already exist: `leap_fuel_to_esto`
is in `outlook_mappings_single_axis.xlsx` and is a clean **1:1 — 70 LEAP fuels,
70 rows, zero one-to-many** (verified 2026-08-06). So the ESTO → LEAP step needs
no conflict resolution at all, unlike the 9th → LEAP step it replaces.

The 9th keeps its own factors permanently at every stage — see the fidelity
principle above.

### Cardinality is already checked and benign

Verified 2026-08-06:

- 71 distinct LEAP fuels, 70 distinct ESTO products.
- Only **3 LEAP fuels** map to more than one 9th fuel: `Other biomass`,
  `Other sources`, `Solar nonspecified`.
- Only **4 ESTO products** receive more than one 9th fuel:
  `12.99 Solar nonspecified`, `15.05 Other biomass`, `16.09 Other sources`,
  `17 Electricity`.
- Of those, only `16.09 Other sources` has genuinely differing factors
  (`16_09_other_sources` blank/zero vs `16_others_unallocated` 0.143).

These are exactly the cases the existing `prefer_specific_then_mean` rule
already handles and tests. Reuse that rule; do not invent a second one.

### Steps

1. Move the 9th factor CSV and `emissions_factor_sets.json` into
   `leap_mappings/config/`. Emissions factors become an owned input of the
   mapping system.
2. Move the resolution logic out of
   `leap_dashboard/codebase/common_esto_dashboard_emissions.py` into
   `leap_mappings`, next to `build_common_esto_structure.py`. This clears the
   duplicate-implementation debt noted above.
3. Publish B1 and B2 as described.
4. Relax the `native_unit == "PJ"` assertion at
   `value_adapter_registry.py:221` and register emissions datasets in
   `dataset_registry.csv` with `native_unit = Mt CO2e`.

### How long each derived set lives (owner input, 2026-08-06)

- **Real ESTO factors are expected.** The derived ESTO set is a **scaffold** —
  build it to be replaced, keep the swap to a config change, and do not let
  anything downstream depend on its specific values. It must also be built to
  become LEAP's derivation source, per the chain above.
- **Real LEAP factors are unlikely**, and LEAP is expected to be aligned to ESTO
  rather than sourced independently. So the derived LEAP set is probably the
  **permanent** answer. Document it as such rather than as temporary, and make
  sure its provenance columns explain how each LEAP fuel got its factor — that
  explanation is the only thing a reader will have.

### Why derived factors still make the migration safer

While everything derives from the 9th, all three datasets carry the same
underlying carbon intensities in their own vocabularies, so the derived route
**must reproduce the current numbers exactly** — 20USA 2022 must still be
3,443 Mt CO2e. That makes Phase B verifiable rather than a leap of faith, and
proves the architecture end to end before real ESTO factors arrive.

Once real ESTO factors land that equality intentionally breaks, and the
regression baseline must be re-cut at that point rather than defended. Expect
it, and record the before/after so the change is attributable to the new factors
and nothing else.

---

## Phase C: mapping inversion

**Repos:** `leap_mappings` (publishes), `leap_dashboard` (consumes). Largest and
riskiest phase.

### The design decision that makes this safe

`leap_mappings` publishes its conversion as an **importable library**; the
dashboard calls it, passing whatever dataset numbers it has:

```
converted = leap_mappings.convert_to_common(dataset_values, mapping_tables)
```

One implementation, owned upstream. Only the timing of conversion moves to
render time. That is what delivers the owner's goal — different numbers,
identical mapping — without a second implementation to drift.

The Space's existing mapping-chain worker is the working proof of this shape.
Prefer promoting that worker into a supported library over writing a new one.

### Caching (owner decision, 2026-08-06)

**Design cache-first from the start.** Converted output is cached inside
`leap_dashboard` and reused until an input actually changes — a new ESTO
vintage, a 9th data revision, a mapping edit. Those happen rarely, so the steady
state is a cache hit and per-render conversion cost is not on the critical path.

- Cache key: `(dataset id, dataset version/hash, mapping tables version/hash,
  common structure version)`. Any component changing invalidates.
- Store the key alongside the cached frame so a stale cache is detectable rather
  than silently served.
- Provide an explicit force-refresh toggle, matching the existing
  `COMMON_ESTO_UPDATE_DATA` convention.
- The cache is a build artifact: it lives under `outputs/`, is never committed,
  and a cold run must reproduce it exactly.

**Initialise the cache before the app starts** (owner decision, 2026-08-06).
Converted values are computed ahead of time and shipped warm, so no user ever
pays the cold-start cost. This fits the existing deployment model exactly: the
Space already runs off a prepared snapshot built by
`leap_review_tools/scripts/refresh_runtime.py`, so cache warming becomes a step
in that script and the warm cache becomes one more runtime data asset. Same for
the portable release. A cold cache stays supported as the fallback, not as the
normal path.

### Collapse the two merges into one native → common map — yes, do this

Owner's proposal, 2026-08-06, and it is **correct**. It should be the design.

The reasoning: the common row is built at the granularity where the sources in
that scope agree — the lowest common denominator. The 9th's coarser vocabulary
is one of the constraints that granularity is built to respect. So mapping the
9th straight to common rows should have no fan-out at all, and the intermediate
trip through ESTO's finer vocabulary is a split immediately followed by a
re-aggregation that undoes it.

Measured, and it holds exactly:

| Source | Scope | Source pairs | Fan out at **ESTO** level | Fan out at **common** level |
|---|---|---|---|---|
| 9th | `esto_leap_ninth` | 1,920 | 248 | **0** |
| 9th | `esto_extended_leap_ninth` | 1,920 | 248 | **0** |
| LEAP | `esto_leap_ninth` | 1,108 | 0 | **0** |
| LEAP | `esto_leap` | 1,083 | 0 | **0** |
| 9th | `esto_leap` | 1,637 | 248 | 151 |

`01_x_thermal_coal` splits across `01.02 Other bituminous coal`,
`01.03 Sub-bituminous coal` and `01.04 Anthracite` — and all three land in the
single common row `01.02-01.04 Coal`. The split cancels.

Value preservation checked on real data (20_USA, 2030, reference, 1,743 common
rows): **maximum absolute difference 0.0** between the ESTO-split-then-
re-aggregated values and the direct totals. The allocation shares sum to 1.0
within each common row, so nothing is gained or lost by going direct.

### This is guaranteed by construction, not observed by luck

The zero above is not a property of the current data that might change. It is
the mapping system's central design rule. From `mappings_system.md`:

> **Do not split a source aggregate unless there is an explicit allocation
> method.**
>
> ...In both cases, the finer data are rolled up to a comparison level that the
> coarser source can support. The system should not pretend to know a split that
> the source data do not provide.

The common structure *is* the lowest common denominator for the datasets used in
a scope. A participating source cannot fan out at the common level, because the
structure is built so it cannot. `leap_mappings` already asserts this and
publishes the check: `results/common_esto/qa_common_esto_source_aggregates_split.csv`
is **empty**.

Two consequences, and they are the point of the design:

- **The dashboard needs no allocation logic at all**, and must not carry any.
  Allocation exists solely to reach ESTO's finer vocabulary in the two-step path.
  Going direct, there is nothing to allocate.
- **Fan-out at the common level is a mapping-system bug, not a case to handle.**
  If it ever appears, the fix is upstream in the structure build, and the
  existing QA output above is what surfaces it. Do not add a dashboard-side
  fallback, and do not retain the allocation path "just in case" — that would
  convert a loud upstream failure into a quiet downstream approximation.

The `esto_leap` row in the table is not a counterexample. There the structure is
the lowest common denominator for **ESTO and LEAP**, which are its participants;
the 9th is not one, so its vocabulary is not represented and it is not converted
in that scope. That is the rule working. It does mean the direct map is
generated **per comparison scope, for participating sources only**.

**What this buys, beyond one fewer merge:**

- **No allocation at all.** The data-dependent `target_dataset_share` allocation
  (891 of 2,623 9th relationships have shares varying by economy/scenario/year)
  exists only to reach ESTO's finer vocabulary. Going direct never needs it.
- **Datasets become genuinely independent.** An earlier draft of this plan
  concluded that converting the 9th required ESTO to be present, because the 9th
  allocation shares are drawn from ESTO's observed proportions. **That is true
  of the two-step path and false of the direct path.** The direct map removes the
  dependency, so the phase's headline goal — different numbers for any dataset,
  same fundamental mapping — holds cleanly for every dataset rather than only
  for LEAP. This is a stronger reason to adopt the proposal than the merge saving.
- **Smaller cache keys.** No ESTO version needed in the 9th's cache key.
- **Small static artifacts.** Built structurally: 1,969 source pairs for the
  9th, 2,988 for LEAP (the lineage-observed counts of 1,920 and 1,108 are what
  the data happens to exercise — see the structural note below).

### There is no any-dataset → common map today — this phase creates it

Worth stating explicitly, because it is easy to assume otherwise.
`leap_mappings/results/common_esto/esto_to_common_esto_map.csv` maps **ESTO
components only**. For LEAP and the 9th there is no equivalent: a consumer must
read the pre-converted fact table, or compose
`results/mapping_relationships/{leap,ninth}_source_to_esto_component_lineage.csv.gz`
with the ESTO map itself.

**Build `leap_mappings/results/common_esto/source_to_common_esto_map.csv`:**

```text
comparison_scope, source_system, source_flow, source_product,
common_row_id, common_flow_label, common_product_label,
is_subtotal, common_flow_is_subtotal, common_product_is_subtotal,
common_flow_hierarchy_status, common_product_hierarchy_status
```

Roughly 2,000–3,000 source pairs per dataset per scope, so small enough to ship
as a runtime data asset. `esto_to_common_esto_map.csv` becomes its ESTO slice.

**Build it from the structural relationship table, not from the lineage files.**
The `*_source_to_esto_component_lineage.csv.gz` files are outputs of a
conversion run over actual values, so a map derived from them would only contain
pairs some economy happened to report. The structural source is
`results/mapping_relationships/energy_balance_relationships.csv`
(18,020 rows: `source_system, source_flow, source_product → target_flow,
target_product`) composed with `esto_to_common_esto_map.csv`.

Verified 2026-08-06 that this changes nothing about the guarantee — built
structurally, fan-out at the common level is still **zero**:

| Source | Structural source pairs | Lineage-observed pairs | Fan out at common |
|---|---|---|---|
| LEAP | 2,988 | 1,108 | **0** |
| 9th | 1,969 | 1,920 | **0** |

The structural table carries substantially more LEAP pairs than any data run
exercises, and even those do not fan out. The lowest-common-denominator property
is therefore structural rather than merely observed, which is what makes
publishing a static map safe.

**Known unknown to resolve before publishing:** of 6,335 structural LEAP links,
**3,347 have no common row** in `esto_leap_ninth` — ESTO targets that are not
part of that common structure. Explain these before shipping the map. If any
correspond to LEAP source pairs that carry real values, they would silently map
to nothing, which is the failure mode this whole design exists to avoid. (The
9th has zero such links.)

This one file is what makes the single-merge contract real for every dataset
rather than only ESTO, carries the aggregation flags with the mapping, and
doubles as the readable "which native row becomes which common row" reference.

**Verify once at migration, then retire the two-step path.** Diff direct against
two-step row for row while switching over (Phase C step 5) to prove the change
moved no numbers. That is a migration check, not a standing guard: the invariant
it would guard is owned and already asserted upstream, so once the switch is
proven the allocation path is dead code for participating sources and should go.

### Steps

**C0. Gate: explain the 3,347 unmapped structural LEAP links before anything
else.** Stop and report if they include LEAP source pairs that carry real
values; that would mean the direct map silently drops data and the approach
needs rethinking. This is cheap to check and is the only finding that could
invalidate the phase, so it runs first and blocks the rest.

1. **Generate `source_to_common_esto_map.csv`** in `leap_mappings` from
   `energy_balance_relationships.csv` composed with
   `esto_to_common_esto_map.csv`, per scope, participating sources only. Assert
   zero fan-out at the common level while generating; fail loudly if not.
2. **Publish an importable apply function** in `leap_mappings` — one merge plus
   an aggregation, taking native source values and the map above. `leap_mappings`
   keeps the single implementation. Leave orchestration, relevance/coverage QA,
   diagnostics, total checks and output writing where they are.
3. Give the API a declared, versioned input contract, because the dashboard now
   depends on its signature.
4. Build the cache layer described above.
5. Switch `leap_dashboard` to call it, replacing
   `load_common_esto_data(common_esto_comparison_data.csv)`. Keep the old path
   behind a flag so the two can be diffed.
6. **Diff the two paths on real data** for every economy: the converted-at-
   render-time frame must equal the prebuilt fact table row for row. This is the
   phase's whole safety argument — do not skip it or sample it.
7. Retire the prebuilt-table path, and the two-step allocation path with it, once
   the diff is clean across all economies.
8. Update the AGENTS.md "Upstream data boundary" paragraph to describe the new
   arrangement.

**Note on `convert_leap_results_to_esto`.** With the direct map in place, the
conversion path does **not** need the native → ESTO step at all: that step exists
only to reach ESTO's vocabulary, which the direct map bypasses. It stays in
`leap_mappings` for the pipeline's own use and for generating the map, but it is
not part of the dashboard's API surface. An earlier draft listed extracting it as
step 1; that was left over from the two-merge design.

### Remaining risks

- **Scope creep into `leap_mappings`' pipeline stages.** Only the two merges
  move. Structure *building*, Stage 1/2 mapping maintenance, QA outputs and
  diagnostics all stay upstream. If the extracted API starts growing QA
  outputs, that is the signal it has taken too much.
- **The dashboard gains a hard dependency on `leap_mappings` code**, not just
  its data. Small in code terms, but it is what makes portable/web packaging
  heavier — see below.
- **Join-semantics drift** if anyone later re-implements the merge instead of
  calling the API. The keys, aggregation, `comparison_scope` filtering and sign
  handling must match exactly, and a disagreement surfaces as wrong numbers
  rather than an error. The step-5 diff is the detector; keep it as a test.
- **Cost is a large join, not a large computation.** Cache warming (above)
  makes this a non-issue in the normal path; measure before optimising further.

---

## Web app / packaging consequences

The Gradio Space runs off a frozen `runtime/` snapshot whose file list is
declared in `leap_initialisation/config/portable_release_manifest.toml`
(`[repositories.leap_dashboard]` currently names 4 modules; `[[config_assets]]`
names 3 config files).

- **Phase 0** adds three files (see that phase for the list, and for the one
  dependency that can be removed first).
- **Phase A** adds nothing to the manifest.
- **Phase B** adds the published factor tables as small data assets. Because
  resolution moves upstream, the shipped artifact is one small CSV rather than a
  factor file plus mapping workbooks. Note that
  `outlook_mappings_single_axis.xlsx` is **not** currently in the runtime and
  `outlook_mappings_master.xlsx` is **not** a valid substitute — master's
  `ninth fuel to esto product` sheet is a superset carrying
  `15_solid_biomass -> 15 Solid biomass` and `16_others -> 16 Others`, which
  would break the rule that drops fuel-level aggregate rows and reintroduce
  double counting. Resolving upstream avoids needing either workbook at runtime.
- **Phase C** is the heavy one: the conversion library and the per-dataset
  source tables all have to reach the runtime, plus possibly a warm cache.

Sequencing constraint for all of it: the manifest pins commits and sha256
hashes, so nothing reaches the Space until the work is merged. Order is merge →
update manifest → `leap_review_tools/scripts/refresh_runtime.py` → copy
`runtime/` into `leap_review_web_app` → deploy.

## Before/after equivalence tests

The safety property — no phase changes a number — is only worth anything if it
is executable. This section specifies how.

### Critical precondition: renders are content-deterministic, not byte-deterministic

Measured 2026-08-06 by rendering 20USA twice from unchanged code and inputs:
**15 of 19 output files differed byte-for-byte**, including `chart_manifest.csv`,
every chart bundle, and `emissions_by_sector_and_fuel.csv`.

Sorted, **all of them are identical**. The differences are pure row ordering,
caused by Python's per-process string hash randomisation making set and dict
iteration order vary between runs (this codebase iterates sets of labels in
several places, including the emissions frontier selection).

Consequences, and getting these wrong will waste a whole run:

- **Never compare file bytes, hashes, or `git diff` on generated outputs.** A
  naive hash comparison reports ~15 false regressions on an unchanged codebase.
- **Always normalise before comparing:** sort by all columns, or by an explicit
  stable key, and reset the index.
- The plan's "diff row for row" instruction means *after normalisation*.
- Optionally set `PYTHONHASHSEED=0` to make runs byte-stable, but do **not**
  rely on it — the tests must pass without it, or they encode an accident.

### T0. Determinism guard (write first, run first)

Render the same economy twice with no code change and assert every generated CSV
is equal after sorting. This protects every other test in this list; if it fails,
the comparison strategy itself is broken and nothing below can be trusted.

### T1. Baseline capture (run before touching anything)

A script — `scripts/capture_common_esto_baseline.py` — that renders the
reference economies and writes **normalised** snapshots under
`tests/fixtures/common_esto_dashboard/baseline_<economy>/`. Commit these; they
are the "before" side of every comparison and must be captured on unmodified
code.

Capture at minimum: `chart_manifest.csv`, `emissions_by_sector_and_fuel.csv`,
`emissions_factor_resolution.csv`, `page_assignment_summary.csv`, the page
inventory, and the bundle fingerprint from T3.

Use 20USA (rich, all three sources, full hierarchy) **and** 02BD (sparse, LEAP
absent from demand, aggregate-only sectors). 02BD catches the "source reports
only a parent" case that 20USA does not exercise.

### T2. Chart manifest equivalence — broadest cheap signal

Compare the sorted manifest (642 rows × 16 columns for 20USA). It carries
`page_key`, `chart_key`, `chart_type`, `row_count`, `suppressed`,
`total_abs_value`, `abs_diff`, `pct_diff` per chart, so it catches charts
appearing or disappearing, suppression flipping, and any aggregate value moving —
in one assertion, without opening a bundle.

### T3. Chart bundle numeric fingerprint — the strongest test

The manifest aggregates; this does not. For every chart bundle, decode each
trace's `x`/`y` (they are base64 `bdata` with a `dtype`, not plain lists) and
record `(chart_key, trace name, x values, y values)`. Compare the whole
structure sorted by `(chart_key, trace name)`.

This is what actually appears on screen, so it is the assertion that most
directly means "the dashboard shows the same thing".

### T4. Named emissions invariants

Assert the specific numbers this work has been validated against, so a failure
names itself rather than appearing as an anonymous diff:

- 20USA 2022 total = **3,443 Mt CO2e**, and equal across LEAP, ESTO and 9th.
- The 2022 sector split (Transport 1,810 / Buildings 611 / Industry 573 /
  Other demand 449 / Non-energy 403 for a single scenario).
- Top fuels by 2022 emissions in order: Natural gas, Motor gasoline,
  Gas/diesel oil.

### T5. Factor table equality — gates Phase B

`emissions_factor_resolution.csv` (54 rows) must be identical after the
resolution logic moves to `leap_mappings`. Same factors, same
`factor_source_keys`, same `esto_components`. This is the whole proof that the
move was a relocation and not a rewrite.

### T6. Frontier set equality — gates Phase A step 6

The precise unit assertion for switching parenthood onto `axis_nodes.csv`: the
exact set of `(source_system, scenario, common_flow_label, common_product_label)`
tuples retained by `select_non_overlapping_rows` must be unchanged.

Assert on the *set*, not on totals — totals can coincidentally match while the
retained rows differ. This is the test that would have caught the original
4,838-vs-3,443 bug.

### T7. Page and navigation inventory

The set of `page_key`s rendered, and the nav chip order per page. Cheap, and it
catches a page silently disappearing — which the emissions gating logic makes a
real possibility.

### T8. Direct-vs-prebuilt frame equality — gates Phase C

The migration diff. Join the render-time converted frame against
`common_esto_comparison_data.csv` on
`(comparison_scope, source_system, economy, scenario, year, common_row_id)` and
assert equal `value`, with **no unmatched rows on either side**. Run for every
economy, not a sample.

Unmatched rows matter more than value differences here: a silently dropped
mapping shows up as a missing row, not a wrong number.

### Tolerances

Default to **exact equality**. These changes relocate and re-key arithmetic
rather than altering it, and the empirical check above shows summation is stable
in practice.

Allow a relative tolerance of `1e-9` only where grouping order genuinely changed,
and require it to be justified in the commit message. A tolerance loose enough to
hide a real change is worse than no test — if something needs more than `1e-9`,
that is a finding.

## Executing this unattended

Written 2026-08-06 for an overnight run. Read this before starting.

### Environment

- Python: `C:\Users\Work\miniconda3\python.exe`.
- **`LEAP_MAPPINGS_ROOT` must be set explicitly** when working in a
  `leap_dashboard` worktree. `REPO_ROOT.parent` resolves to the worktrees
  directory, not the repo parent, so every upstream path silently misses:
  `LEAP_MAPPINGS_ROOT=C:/Users/Work/github/leap_mappings`.
- A full render is ~3–5 min per economy; the full test suite is ~5 min. Budget
  for repeated cycles rather than one pass.
- **`scripts/render_full_mapping_tree_explorer.py` crashes in a worktree**
  (it does not honour `LEAP_MAPPINGS_ROOT` and looks for
  `results/tree_structure/all_dataset_trees.csv`). This is pre-existing and
  unrelated. It runs *after* the dashboard render and *before*
  `publish_to_docs`, so renders and page output are unaffected but the publish
  step cannot be exercised from a worktree. Do not "fix" it as part of this
  work; note it and move on.

### Working across repos

`leap_mappings` had **5 pre-existing modified files** at the time of writing
(`apec_anchor_validation.py`, `apply_common_esto_structure.py`,
`structural_resolver.py`, and two config files) that belong to someone else's
in-progress work. Do not commit, revert, stash, or refactor around them. If a
required change collides with one, stop and report rather than resolving it.

### Stop conditions — halt and report rather than working around

1. **C0 gate fails**: any of the 3,347 unmapped structural LEAP links carries
   real values. The direct-map approach needs rethinking; do not proceed.
2. **Any number moves.** The safety property is that no phase changes a value.
   20USA 2022 emissions must stay 3,443 Mt CO2e; energy charts must reproduce
   exactly. A diff is a finding to explain, never a baseline to update.
3. **Fan-out appears at the common level** when generating the map. That is an
   upstream structure bug — report it, do not add allocation downstream.
4. **A collision with the pre-existing `leap_mappings` changes.**
5. **The scope would grow into `leap_mappings` pipeline stages** beyond the two
   named outputs and the apply function.

### Do this first, before any code change

1. Write and run **T0** (determinism guard). If it fails, stop — the comparison
   strategy is broken.
2. Write and run **T1** (baseline capture) for 20USA and 02BD on unmodified
   code, and commit the fixtures. There is no way to recover a "before" snapshot
   once the code has changed, so this is not optional and cannot be deferred.

### Recommended overnight scope

Do **not** attempt A + B + C in one unattended run. They span three repos, and
B and C both create published artifacts that other systems consume.

Highest value per unit of risk, in order:

1. **Phase A steps 1–4** (measure dimension, unit plumbing, gating,
   comparison pairing). One repo, no new artifacts, fully covered by existing
   tests plus the render diff. This is the safe overnight target.
2. **Phase A step 6** (frontier parenthood onto `axis_nodes.csv`). Self-contained
   and removes a real boundary violation, but touches the code that produced the
   4,838-vs-3,443 bug, so it needs the emissions regression test green before and
   after.
3. **Phase C step C0 only** — the investigation. Cheap, needs no code changes,
   and its answer determines whether Phase C is viable at all. Ideal unattended
   work: it produces a finding, not a change.

Leave Phase B and the rest of Phase C for a supervised session: both move files
between repos and publish artifacts the Space consumes.

### Definition of done for an unattended run

- `C:\Users\Work\miniconda3\python.exe -m pytest tests` green (145 passed,
  2 skipped at time of writing).
- `LEAP_MAPPINGS_ROOT=... COMMON_ESTO_ECONOMIES=20_USA python codebase\common_esto_dashboard_workflow.py`
  renders, and `outputs/common_esto_dashboard/20USA/supporting_files/emissions_by_sector_and_fuel.csv`
  still totals 3,443 Mt CO2e for 2022 across LEAP, ESTO and 9th.
- `scripts/check_common_esto_dashboard_publish_ready.py` passes.
- `scripts/analyze_common_esto_dashboard_page_noise.py` flags 0.
- A written summary of what changed, what was verified, and every stop condition
  hit. Uncommitted unless explicitly asked to commit.

## Resolved during owner review (2026-08-06)

- **Mapping application.** Changing mapping semantics is fine provided the
  tables come from `leap_mappings`. Applying a mapping is a **merge onto an
  existing mapping output**, the same shape as the emissions-factor merge the
  dashboard already does. Corrected measurement: `apply_common_structure` is
  **137 lines** — a join plus an aggregation — and the surrounding 2,150 lines
  are orchestration and QA the dashboard does not need. The complexity is in
  *building* the structure (1,883 lines), which stays upstream and is already
  consumed as data. Publish the merge as an **importable function** in
  `leap_mappings` so there is one canonical implementation that doubles as the
  guide for how it is meant to be done.
  (An earlier draft argued this step was complex by comparing whole-file line
  counts. That measured the wrong thing; Phase C is smaller than it implied.)
- **Caching.** Cache-first, invalidated on input change; updates are rare.
  **Initialise the cache before the app starts** and ship it warm as a runtime
  asset, so cold start is a fallback rather than the normal path.
- **Provenance.** `derived_from` on **every** published factor artifact, B1 and
  B2 alike, valued `ninth` today. No published factor exists without stating
  its source.
- **Derivation chain moves.** Real ESTO factors are expected; LEAP is expected
  to be aligned to ESTO rather than sourced independently. Build the ESTO
  scaffold to become LEAP's *source*: today LEAP derives via
  `leap_fuel_to_ninth`, later via `leap_fuel_to_esto` (a clean 1:1, 70 of 70).
  Make the derivation source a config parameter, not a hardcoded path.
- **Build a direct native → common map and convert with one merge.** The common
  row sits at the granularity the scope's sources agree on, so the 9th's
  ESTO-level fan-out (248 pairs) re-collapses completely: **0 of 1,920** 9th
  pairs and **0 of 1,108** LEAP pairs fan out at the common level in
  `esto_leap_ninth`, and value preservation through the split measures exactly
  0.0 difference. Generate per scope, only for sources party to that scope
  (the 9th does fan out in `esto_leap`, where it is not a participant).
  An earlier draft rejected this; that was wrong.
- **Datasets are therefore independent after all.** The data-dependent
  `target_dataset_share` allocation exists only to reach ESTO's finer
  vocabulary; the direct path never needs it, so converting the 9th does **not**
  require ESTO and ESTO's version does **not** belong in the 9th's cache key.
  An earlier draft claimed both; both were consequences of the two-step path.
- **No allocation logic in the dashboard, and no fallback.** The zero fan-out is
  guaranteed by the mapping system's central rule — *do not split a source
  aggregate unless there is an explicit allocation method* — and is already
  asserted upstream by the (empty)
  `results/common_esto/qa_common_esto_source_aggregates_split.csv`. Fan-out at
  the common level would be a structure bug to fix upstream, not a case to
  handle downstream. Diff direct against two-step once at migration to prove no
  numbers moved, then retire the two-step path rather than keeping it "just in
  case" — a downstream fallback would turn a loud upstream failure into a quiet
  approximation.
- **Fidelity over uniformity.** The 9th keeps its own factors permanently, so
  9th emissions reproduce published 9th emissions. A common factor set is nice;
  matching the published outputs matters more. The common-axis table stays
  available as the hold-factors-constant diagnostic view.
- **The AGENTS.md rule** forbids a second *implementation*, not the dashboard
  performing conversion. Phase C complies by importing upstream code, and the
  paragraph itself gets updated as part of Phase C.
