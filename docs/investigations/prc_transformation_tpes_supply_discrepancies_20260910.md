# PRC Transformation, TPES, own-use, and Supply investigation

Date: 2026-09-10  
Scope: PRC (`05_PRC`), Target, 2023  
Status: investigation only; no implementation changes made

## Executive conclusion

The supplied comparison workbook is not a same-input reproduction of the
dashboard artifacts. Its source workbook is the 2023 sheet in
`mixed_fixture_full_release_20260910_tpes_bunkers`, but the only dashboard run
manifest records an export directory from `dummy_leap_test_workbooks_79_corrected_totals_validated_20260909`.
The dashboard run is also recorded as failed because of an emissions-factor
keyword error. Consequently, the exact numerical differences must not yet be
used to approve a mapping or dashboard fix.

The evidence nevertheless identifies two high-confidence causes:

1. The comparison workbook maps dashboard composite labels to the wrong input
   fuel columns. `07.04-07.05 Petroleum products` is a jet-fuel composite in
   the generated Common ESTO data, while the comparison selects `Bitumen +
   Petroleum coke`. `07.12-07.17 Petroleum products` is the six-product
   composite (white spirit, lubricants, bitumen, paraffin waxes, petroleum
   coke, and other products), while the comparison selects five columns and
   omits bitumen and petroleum coke.
2. The transformation dashboard is a complete presentation boundary, not the
   single `Total Transformation` source row. The renderer selects flow codes
   `09`, `08`, `10.01`, and `10.02`, then resolves a non-overlapping frontier.
   The comparison workbook compares that result with one LEAP row and a
   parent own-use row.

These are dashboard/comparison-methodology issues, not evidence of a
projection allocation or a source-to-Common-ESTO split. Relevant lineage rows
have `allocation_share = 1.0` and blank `allocation_source`.

## Evidence and provenance

Relevant supplied files:

- Input: `C:\Users\Work\.codex\worktrees\e48a\leap_review_tools\outputs\mixed_fixture_full_release_20260910_tpes_bunkers\compact_pairwise\05_PRC\05_PRC_target_v2024_h2022_s111111111.xlsx`
- Comparison: `C:\Users\Work\Downloads\PRC_all_detail_power_process_bunkers_953126a_20260910\05_PRC\PRC_chart_values_with_2023_input_comparison.xlsx`
- Mapping artifacts: `C:\Users\Work\Downloads\PRC_all_detail_power_process_bunkers_953126a_20260910\05_PRC\dashboard\mapping_chain\`
- Run manifest: `C:\Users\Work\Downloads\PRC_all_detail_power_process_bunkers_953126a_20260910\05_PRC\dashboard\run_records\prc_all_detail_953126a_20260910\run_manifest.json`

The manifest says:

- `comparison_scope = esto_leap_ninth`;
- export directory = `dummy_leap_test_workbooks_79_corrected_totals_validated_20260909`;
- status = `failed`;
- error = `render_common_esto_dashboard() got an unexpected keyword argument 'emissions_factor_file_path'`.

As a direct check, the supplied input workbook has 2023 `Total Primary
Supply` values of `-398.910401` for both gasoline-type and kerosene-type jet
fuel, while `raw_leap_results.csv` from the dashboard artifact set has
`-295.078939` for each. This proves the artifacts do not originate from the
supplied workbook.

## Composite Supply rows

The comparison sheet reports:

| Dashboard label | Input columns selected | Input group total | Dashboard net | Difference |
|---|---|---:|---:|---:|
| `07.04-07.05 Petroleum products` | Bitumen + Petroleum coke | `-79.15799593970192` | `-797.820802403175` | `-718.6628064634731` |
| `07.12-07.17 Petroleum products` | Lubricants + Refinery feedstocks + Paraffin waxes + White spirit SBP + Other products | `-158.31599187940384` | `-237.47398781910576` | `-79.15799593970192` |

The Common ESTO artifact identifies the first label as a generated
`connected_component_rollup` over products `07.04` and `07.05` (gasoline-type
and kerosene-type jet fuel). Its 2023 LEAP rows are:

- `03 Exports`, `07.04 Gasoline type jet fuel`: `-295.078939`;
- `03 Exports`, `07.05 Kerosene type jet fuel`: `-295.078939`;
- `05 International aviation bunkers`, each of those products: `+103.831462`.

The dashboard normalizes bunker withdrawal signs, so its net is:

`-590.157878 - 207.662924 = -797.820802`.

That explains the dashboard value independently of the input columns selected
by the comparison sheet. The source rows are exact LEAP-to-ESTO relationships,
with `allocation_share = 1.0`, no allocation source, and no fallback.

The second label is the generated six-product `connected_component_rollup`
`07.12-07.17 Petroleum products`. Its 2023 LEAP `03 Exports` rows contain
`-39.578998` for each of the six products, summing to `-237.473988`. The input
comparison selects only four nonzero products and omits bitumen and petroleum
coke, giving `-158.315992`.

Classification: **dashboard-only aggregation/comparison error**, with a
separate **source-artifact provenance mismatch** preventing final numerical
sign-off. It is not an invalid mapping or allocation finding.

## Transformation and TPES boundary

The comparison sheet compares each fuel against `Total Transformation` only.
For example, its 2023 rows include:

- `07.04-07.05 Petroleum products`: input `Bitumen + Petroleum coke`
  `-53.925071`; dashboard net `1969.902688`;
- `07.12-07.17 Petroleum products`: input five-column total `-107.850143`;
  dashboard net `5120.470834`;
- `08.01 Natural gas`: input `-2902.804457`; dashboard `-4324.125043`;
- `17 Electricity`: input `32873.316935`; dashboard `30469.524098`;
- `18 Heat`: input `10467.001340`; dashboard `-3480.069818`.

The dashboard implementation documents and applies the following boundary:

- transformation flow roots: `09`, `08`, `10.01`, `10.02`;
- non-overlapping common-row frontier;
- positive and negative values kept as separate gross stacks;
- supply composition: `01`, `02`, `03`, and `04-05`, with bunker signs
  normalized and stock changes outside the projection-comparable supply total.

Relevant code paths are `select_transformation_overview_rows`,
`_non_overlapping_common_row_frontier`, `_build_supply_stack_chart`, and the
template's `supply_codes` / `normalize_bunker_withdrawal_signs` settings.

For `07.04-07.05`, the Common ESTO transformation row is the non-expanding
rollup `09.07 Oil refineries (including own use)`. Its exact LEAP lineage is:

- `Oil Refining/Oil Refining`, `Gasoline type jet fuel` → `09.07 Oil refineries (including own use)`, `07.04 Gasoline type jet fuel`, `984.951344`;
- `Oil Refining/Oil Refining`, `Kerosene type jet fuel` → `09.07 Oil refineries (including own use)`, `07.05 Kerosene type jet fuel`, `984.951344`.

The two rows sum to the displayed `1969.902688`. The comparison's Bitumen and
petroleum-coke columns are therefore not the source rows behind that dashboard
label.

Classification: **valid aggregation difference caused by comparing different
boundaries**, compounded by the same **dashboard-only composite-label error**.
The `Total Transformation` row is an authoritative LEAP balance total, but it
is not interchangeable with the dashboard's process/frontier composition.

## Other loss and own use

The supplied 2023 input workbook's parent row `Other loss and own use` is zero
for the relevant fuels. The detailed child rows are nonzero, including:

- `Other loss and own use/Coal mines`: petroleum-products child total
  `+0.303956`;
- `Other loss and own use/Oil and gas extraction`: petroleum-products child
  total `+6.657756`;
- `Other loss and own use/Electricity CHP and heat plants`: electricity
  `+2330.008023`;
- `Other loss and own use/Liquefaction and regasification plants`: electricity
  `+14.795983`, natural gas `+203.818673`;
- `Other loss and own use/Transmission and distribution loss`: electricity
  `+1332.974616`, heat `+3448.719937`;
- `Other loss and own use/Non specified own uses`: other biomass `+23.607413`.

The Common ESTO artifact contains the detailed Common rows, not a parent
`10.01` total. For 2023, the petroleum-products child rows are stored with
own-use sign semantics as `-0.303956` and `-6.657756`, while the electricity,
natural-gas, and heat children retain their own mapped products. No parent and
child are both selected in the dashboard's resolved frontier.

Classification: the apparent discrepancy is a **dashboard/comparison
boundary error**, not duplicate parent/child counting in the Common ESTO
consumer. The comparison's parent-only check is not a valid test of the
detailed dashboard own-use frontier.

## Allocation, fallback, and sign checks

- Relevant LEAP lineage rows are exact (`allocation_share = 1.0`; blank
  `allocation_source`).
- `leap_source_rollup_audit.csv` is empty for this artifact set.
- The fallback audit contains unrelated standard/interim branch suppression
  rules; it does not identify a fallback for the petroleum composite rows.
- The relevant raw LEAP transformation inputs are negative for inputs and
  positive for outputs; own-use source rows are positive and the dashboard
  applies the configured own-use/loss sign semantics.
- `allocate_ninth_projection_to_esto` is not on the LEAP path that produced
  these dashboard rows. Its sign-stable positive/negative allocation logic and
  conservation diagnostics therefore do not explain these discrepancies.

## Required next reproduction and smallest safe fix

Before implementation, rerun the mapping chain and dashboard from the supplied
`mixed_fixture_full_release_20260910_tpes_bunkers` PRC workbook, producing a
new manifest whose input path, commit/configuration fingerprints, comparison
scope, and status are all internally consistent. Then rebuild the comparison
workbook so each dashboard composite expands to the exact Common ESTO component
products and each comparison uses the same flow boundary as the chart.

Do not add correction factors, split source totals, or alter mapping
configuration. The smallest safe change is to the investigation/comparison
harness: correct its label-to-input-column mapping and compare either
`Total Primary Supply` to Common flow `07`, or the dashboard supply frontier to
the same `01+02+03+04-05` boundary. For transformation, compare like-for-like
frontiers rather than `Total Transformation` against the complete dashboard
boundary.

Tests required before any production change:

1. Same-input provenance assertion between the source workbook, raw LEAP
   artifact, manifest, and dashboard output.
2. Composite-label expansion tests for `07.04-07.05` and `07.12-07.17`.
3. Supply conservation tests with bunker sign normalization.
4. Transformation frontier tests proving a parent and its explanatory
   children are never both counted.
5. Own-use child tests covering coal mines, electricity/CHP/heat plants,
   liquefaction/regasification, oil and gas extraction, transmission losses,
   and non-specified own uses.
6. A regression test proving relevant lineage rows remain exact and are not
   allocated or fanned out.
